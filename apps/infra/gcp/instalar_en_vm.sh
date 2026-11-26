#!/usr/bin/env bash
# =============================================================================
# Se ejecuta EN LA VM (lo llama desplegar.sh):  sudo bash instalar_en_vm.sh <paquete.tar.gz> <commit>
#
# Estructura:
#   /opt/abastored/versiones/<commit>   código de cada versión desplegada
#   /opt/abastored/actual  ->           versión en uso
#   /opt/abastored/compartido/          .env, secrets/ y certs/ (se generan aquí y nunca salen de la VM)
# Los datos viven en volúmenes de Docker (postgres-data, mongo-data, redis-data): no se tocan al
# actualizar. Nada de esto toca otras carpetas de la VM.
# =============================================================================
set -euo pipefail
PAQUETE="$1"
COMMIT="$2"
BASE=/opt/abastored
COMPARTIDO=$BASE/compartido
DESTINO=$BASE/versiones/$COMMIT
METADATOS=http://metadata.google.internal/computeMetadata/v1

if ! command -v docker >/dev/null; then
    echo "Instalando Docker ..."
    if command -v dnf >/dev/null; then        # CentOS Stream / RHEL (la VM del proyecto es CentOS Stream 10)
        dnf -y -q install dnf-plugins-core
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        dnf -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    else                                      # Debian / Ubuntu
        curl -fsSL https://get.docker.com | sh
    fi
    systemctl enable --now docker
fi
# firewalld (CentOS): el gateway publica 80 y 443; las bases de datos no publican puertos
if systemctl is-active --quiet firewalld; then
    firewall-cmd --quiet --permanent --add-service=http --add-service=https && firewall-cmd --quiet --reload
fi
# Bitácoras de contenedores con rotación (no llenan el disco)
if [ ! -f /etc/docker/daemon.json ]; then
    echo '{"log-driver": "json-file", "log-opts": {"max-size": "20m", "max-file": "5"}}' > /etc/docker/daemon.json
    systemctl restart docker
fi

mkdir -p "$DESTINO" "$COMPARTIDO/certs"
tar -xzf "$PAQUETE" -C "$DESTINO"
PROYECTO=$(curl -fs -H 'Metadata-Flavor: Google' $METADATOS/project/project-id)
IP=$(curl -fs -H 'Metadata-Flavor: Google' $METADATOS/instance/network-interfaces/0/access-configs/0/external-ip)

# Configuración compartida entre versiones: se crea la primera vez y en cada despliegue se asegura la configuración
# de Google Cloud (una variable que falte haría que los servicios usaran los valores locales del emulador)
[ -f "$COMPARTIDO/.env" ] || cp "$DESTINO/.env.example" "$COMPARTIDO/.env"
sed -i 's/\r$//' "$COMPARTIDO/.env"      # fin de línea LF: los scripts de respaldo lo leen con bash
fijar() {   # clave valor: reemplaza la línea o la agrega
    if grep -q "^$1=" "$COMPARTIDO/.env"; then sed -i "s|^$1=.*|$1=$2|" "$COMPARTIDO/.env"
    else echo "$1=$2" >> "$COMPARTIDO/.env"; fi
}
fijar ENTORNO produccion
fijar COOKIES_SEGURAS true
fijar GCS_BUCKET "abastored-archivos-$PROYECTO"
fijar GCS_PROYECTO "$PROYECTO"
fijar STORAGE_EMULATOR_HOST ""
fijar GCS_URL_PUBLICA ""
fijar GCS_CUENTA_FIRMA "abastored-archivos@$PROYECTO.iam.gserviceaccount.com"
fijar GATEWAY_SAN "IP:$IP"
sed -i '/^GCS_BUCKET_NAME=/d' "$COMPARTIDO/.env"
ln -sfn "$COMPARTIDO/.env" "$DESTINO/.env"
ln -sfn "$COMPARTIDO/certs" "$DESTINO/infra/certs"
[ -d "$COMPARTIDO/secrets" ] && ln -sfn "$COMPARTIDO/secrets" "$DESTINO/secrets"
cd "$DESTINO"
# Secretos aleatorios solo la primera vez (se conservan: las bases ya se crearon con ellos)
if [ ! -d "$COMPARTIDO/secrets" ]; then
    python3 scripts/preparar_entorno.py
    mv secrets "$COMPARTIDO/secrets" && ln -sfn "$COMPARTIDO/secrets" secrets
    # Carpeta solo para root; archivos legibles para el usuario de cada contenedor (postgres, mongodb) que los monta
    chmod 700 "$COMPARTIDO/secrets"; chmod 644 "$COMPARTIDO"/secrets/*
fi

# SELinux (CentOS): los archivos que se montan en contenedores (scripts de db/, certificados y secretos) necesitan
# la etiqueta container_file_t; sin ella el contenedor no puede leerlos
if command -v chcon >/dev/null && [ "$(getenforce 2>/dev/null)" = Enforcing ]; then
    chcon -R -t container_file_t "$DESTINO" "$COMPARTIDO"
fi

COMPOSE=(docker compose -p abastored -f docker-compose.yml -f docker-compose.gcp.yml)
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --remove-orphans
ln -sfn "$DESTINO" "$BASE/actual"

echo "Esperando a que los contenedores estén sanos ..."
for _ in $(seq 1 90); do
    [ "$(docker ps --filter health=starting -q | wc -l)" = 0 ] && break
    sleep 5
done
# Migraciones idempotentes (07 en adelante) sobre la base existente, en orden. Si una falla se avisa y no se
# detiene el despliegue: los servicios ya están arriba con la versión nueva.
for migracion in 07_entrega_final.sql 08_indices_volumen.sql; do
    "${COMPOSE[@]}" exec -T abastored-postgres sh -c \
        "psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -f /docker-entrypoint-initdb.d/$migracion" \
        || echo "AVISO: la migración $migracion falló; revísala antes de seguir"
done
docker ps --format '{{.Names}}\t{{.Status}}' | sort
echo "Versión $COMMIT desplegada en https://$IP/"

# Respaldo diario a las 3:30 (hora del servidor) al bucket
cp "$DESTINO/apps/infra/gcp/respaldar.sh" /usr/local/bin/abastored-respaldar
chmod 755 /usr/local/bin/abastored-respaldar
echo "30 3 * * * root /usr/local/bin/abastored-respaldar >> /var/log/abastored-respaldo.log 2>&1" \
    > /etc/cron.d/abastored-respaldo
