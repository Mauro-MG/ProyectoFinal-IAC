#!/usr/bin/env bash
# =============================================================================
# Pruebas de carga, estrés y recuperación contra el DESPLIEGUE de AbastoRed (HTTPS público + NGINX).
# Locust corre FUERA de la VM (en la laptop); la VM solo ejecuta un muestreo de recursos de solo lectura.
#
#   bash tests/carga/gcp/correr_gcp.sh preparar  <prefijo>
#   bash tests/carga/gcp/correr_gcp.sh verificar <prefijo> <escenario> [--consistencia]
#   bash tests/carga/gcp/correr_gcp.sh correr    <prefijo> <escenario> <etapas> [recuperacion] [tasa]
#   bash tests/carga/gcp/correr_gcp.sh limpiar   <prefijo>
#
#   etapas        "usuarios:segundos,...", con '?' = escalar solo si la etapa anterior fue sana
#                 p. ej. "10:180,25:180,50:180"   o   "75:180,100:240,125?:180"
#   recuperacion  carga baja al terminar o al dispararse una condición de parada, p. ej. "5:300"
#
# Configuración: tests/carga/gcp/config.env (copia de config.ejemplo.env). Resultados en
# tests/carga/resultados/gcp/<AAAAMMDD_HHMM>_<escenario>/. Los tokens quedan en resultados/gcp/privado/ (fuera de git).
# No detiene ni reinicia contenedores, bases de datos ni Redis.
# =============================================================================
set -euo pipefail
RAIZ=$(cd "$(dirname "$0")/../../.." && pwd)
DIR="$RAIZ/tests/carga/gcp"
CONFIG="$DIR/config.env"
[ -f "$CONFIG" ] || { echo "Falta $CONFIG (copia config.ejemplo.env y llénalo)"; exit 1; }
set -a; . "$CONFIG"; set +a
[ "${ABASTO_CA#/}" = "$ABASTO_CA" ] && [ "${ABASTO_CA#?:}" = "$ABASTO_CA" ] && ABASTO_CA="$RAIZ/$ABASTO_CA"
export ABASTO_CA
ACCION=${1:?acción}; PREFIJO=${2:?prefijo}
PRIVADO="$RAIZ/tests/carga/resultados/gcp/privado"
mkdir -p "$PRIVADO"
# gcloud en Windows a veces termina con «Segmentation fault» al cerrar el túnel IAP: se reintenta hasta 3 veces
vm() { local i; for i in 1 2 3; do
           gcloud compute ssh "$GCP_VM" --project "$GCP_PROYECTO" --zone "$GCP_ZONA" --tunnel-through-iap --quiet \
               --command "$1" 2> >(grep -v -e '^Existing host keys' -e '^$' >&2) && return 0
           echo "(ssh falló, intento $i)" >&2; sleep 3
       done; return 1; }
subir() { gcloud compute scp "$@" "$GCP_VM:/tmp/" --project "$GCP_PROYECTO" --zone "$GCP_ZONA" --tunnel-through-iap --quiet; }
winpath() { if command -v cygpath > /dev/null; then cygpath -w "$1"; else echo "$1"; fi; }
py() { (cd "$DIR" && PYTHONIOENCODING=utf-8 "$LOCUST_PY" "$@"); }

case "$ACCION" in
preparar)
    archivo="$PRIVADO/sesiones_$PREFIJO.json"
    [ -e "$archivo" ] && { echo "Ya existe $archivo: usa un prefijo nuevo"; exit 1; }
    tr -d '\r' < "$DIR/preparar_cuentas_vm.py" > "$PRIVADO/preparar_cuentas_vm.py"
    subir "$PRIVADO/preparar_cuentas_vm.py"
    vm "sudo docker exec -i -e PREFIJO=$PREFIJO -e COMERCIANTES=$COMERCIANTES -e ANALISTAS=$ANALISTAS \
        -e AUDITORES=$AUDITORES ms-seguridad python - < /tmp/preparar_cuentas_vm.py; rm -f /tmp/preparar_cuentas_vm.py" \
        > "$archivo"
    rm -f "$PRIVADO/preparar_cuentas_vm.py"
    py -c "import json,sys; d=json.load(open(sys.argv[1])); print({k: len(v) for k, v in d.items() if k != 'prefijo'})" \
        "$(winpath "$archivo")"
    py preparar_datos.py "$PREFIJO"
    ;;

verificar)
    ESCENARIO=${3:?escenario}; shift 3
    DESTINO="$RAIZ/tests/carga/resultados/gcp/$(date +%Y%m%d_%H%M)_$ESCENARIO"
    mkdir -p "$DESTINO"
    # Ventas enviadas por todas las corridas de este prefijo (para la revisión de consistencia)
    VENTAS=()
    for a in $(grep -l "prefijo de datos: $PREFIJO$" "$RAIZ"/tests/carga/resultados/gcp/*/ambiente.txt 2>/dev/null); do
        [ -f "$(dirname "$a")/ventas_enviadas.csv" ] && VENTAS+=(--ventas "$(winpath "$(dirname "$a")/ventas_enviadas.csv")")
    done
    py verificar.py "$PREFIJO" "$(winpath "$DESTINO")" "$@" "${VENTAS[@]}" | tee "$DESTINO/verificacion_salida.txt"
    ;;

correr)
    ESCENARIO=${3:?escenario}; ETAPAS=${4:?etapas}; RECUPERACION=${5:-}; TASA=${6:-2}
    DESTINO="$RAIZ/tests/carga/resultados/gcp/$(date +%Y%m%d_%H%M)_$ESCENARIO"
    mkdir -p "$DESTINO"
    echo "== $ESCENARIO -> $DESTINO"
    {
        echo "fecha_local: $(date '+%Y-%m-%d %H:%M:%S %z') ($(py -c 'import time; print(time.tzname[0])'))"
        echo "fecha_utc: $(date -u '+%Y-%m-%d %H:%M:%S')"
        echo "escenario: $ESCENARIO"
        echo "etapas (usuarios:segundos): $ETAPAS"
        echo "recuperacion: ${RECUPERACION:-ninguna}"
        echo "incorporacion: $TASA usuarios/s"
        echo "prefijo de datos: $PREFIJO"
        echo "commit_scripts: $(git -C "$RAIZ" rev-parse --short HEAD) ($(git -C "$RAIZ" status --porcelain -- tests/carga/gcp | wc -l | tr -d ' ') archivos de tests/carga/gcp sin commit)"
        echo "sha256_scripts:"; (cd "$DIR" && sha256sum comun.py locustfile_gcp.py muestreo_vm.sh verificar.py correr_gcp.sh | sed 's/^/  /')
        echo "host: $ABASTO_HOST (HTTPS por NGINX; TLS verificado con $(basename "$ABASTO_CA"))"
        echo "certificado_publico: $(openssl x509 -in "$ABASTO_CA" -noout -fingerprint -sha256 2>/dev/null | cut -d= -f2)"
        echo "certificado_servido: $(echo | openssl s_client -connect "${ABASTO_HOST#https://}:443" 2>/dev/null | openssl x509 -noout -fingerprint -sha256 2>/dev/null | cut -d= -f2)"
        echo "proyecto/zona/vm: $GCP_PROYECTO / $GCP_ZONA / $GCP_VM"
        echo "tipo_maquina: $(gcloud compute instances describe "$GCP_VM" --project "$GCP_PROYECTO" --zone "$GCP_ZONA" --format='value(machineType.basename())')"
        echo "generador: $(py -c 'import platform,psutil,locust; print(f"{platform.platform()} · {psutil.cpu_count()} CPU lógicas · {psutil.virtual_memory().total/2**30:.1f} GB · Python {platform.python_version()} · Locust {locust.__version__}")') · fuera de GCP, por internet público"
        echo "limites: MAX_USUARIOS=$MAX_USUARIOS DURACION_MAX_S=$DURACION_MAX_S TIMEOUT_S=$TIMEOUT_S"
        echo "paradas: errores>$UMBRAL_ERRORES 30s · p95_ok>${UMBRAL_P95_MS}ms 60s · sin respuestas 30s · mem_vm<${MEM_MIN_MB}MB · disco_vm<${DISCO_MIN_GB}GB · reinicio/OOM de contenedor · archivo PARAR"
        echo "--- VM"
        vm 'echo "commit_desplegado: $(basename $(readlink /opt/abastored/actual))";
            . /etc/os-release; echo "so: $PRETTY_NAME · kernel $(uname -r)";
            echo "cpu: $(nproc) vCPU · $(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | xargs)";
            free -m | awk "/Mem/{print \"memoria_mb: total \"\$2\" · disponible \"\$7}";
            df -h / | awk "NR==2{print \"disco: \"\$2\" total · \"\$4\" libres\"}";
            echo "docker: $(sudo docker version --format {{.Server.Version}})";
            echo "contenedores_en_ejecucion: $(sudo docker ps -q | wc -l)";
            echo "otros_proyectos_docker: $(sudo docker ps --format {{.Names}} | grep -v -E "^(ms-|abastored-|monitor-verificador)" | tr "\n" " ")";
            echo "otros_servicios_escuchando: $(sudo ss -tlnH | awk "{print \$4}" | grep -v -E ":(22|80|443)$" | sort -u | tr "\n" " ")";
            echo "limite_gateway: $(sudo docker exec abastored-gateway sh -c "grep -h -E \"limit_req(_zone)? \" /etc/nginx/nginx.conf" | xargs)";
            echo "limite_servicios: RATE_LIMIT_POR_MINUTO=$(sudo docker exec ms-ventas printenv RATE_LIMIT_POR_MINUTO || echo "120 (valor por omisión)") por usuario y servicio";
            echo "datos (usuarios comercios inventario ventas pedidos tamaño_bd): $(sudo docker exec abastored-postgres sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -tA -F\" \" -c \"select (select count(*) from usuarios),(select count(*) from comercios),(select count(*) from inventario_comercio),(select count(*) from ventas),(select count(*) from pedidos_abasto),pg_size_pretty(pg_database_size(current_database()))\"")"'
    } > "$DESTINO/ambiente.txt" 2>&1
    cat "$DESTINO/ambiente.txt"
    vm 'sudo docker ps -a --format "{{.Names}}|{{.Status}}" | sort' > "$DESTINO/estado_antes.txt"
    INICIO=$(date +%s)

    tr -d '\r' < "$DIR/muestreo_vm.sh" > "$PRIVADO/abasto_muestreo.sh"
    subir "$PRIVADO/abasto_muestreo.sh"
    gcloud compute ssh "$GCP_VM" --project "$GCP_PROYECTO" --zone "$GCP_ZONA" --tunnel-through-iap --quiet \
        --command "sudo bash /tmp/abasto_muestreo.sh $DURACION_MAX_S" > "$DESTINO/muestras_vm.csv" 2> "$DESTINO/muestreo_stderr.txt" &
    MUESTREO=$!
    for _ in $(seq 30); do grep -q '^VM,' "$DESTINO/muestras_vm.csv" 2>/dev/null && break; sleep 2; done

    set +e
    PREFIJO=$PREFIJO DESTINO="$(winpath "$DESTINO")" ETAPAS=$ETAPAS RECUPERACION=$RECUPERACION TASA=$TASA \
    PYTHONIOENCODING=utf-8 py -m locust -f locustfile_gcp.py --headless --only-summary \
        --run-time "${DURACION_MAX_S}s" --stop-timeout 30 \
        --csv "$(winpath "$DESTINO")/locust" --csv-full-history --html "$(winpath "$DESTINO")/reporte.html" \
        2>&1 | tee "$DESTINO/salida_locust.txt"
    set -e

    vm 'sudo touch /tmp/abasto_muestreo.parar' || true
    for _ in $(seq 20); do kill -0 $MUESTREO 2>/dev/null || break; sleep 2; done
    kill $MUESTREO 2>/dev/null || true
    vm 'sudo docker ps -a --format "{{.Names}}|{{.Status}}" | sort' > "$DESTINO/estado_despues.txt"
    vm "sudo journalctl -k --since @$INICIO --no-pager | grep -i -E 'out of memory|oom-kill|killed process' || echo 'sin eventos OOM del kernel desde el inicio de la corrida'" \
        > "$DESTINO/oom_kernel.txt"
    py resumen.py "$(winpath "$DESTINO")" | tee "$DESTINO/resumen.md"
    echo "Resultados en $DESTINO"
    ;;

limpiar)
    tr -d '\r' < "$DIR/preparar_cuentas_vm.py" > "$PRIVADO/preparar_cuentas_vm.py"
    subir "$PRIVADO/preparar_cuentas_vm.py"
    vm "sudo docker exec -i -e PREFIJO=$PREFIJO -e LIMPIAR=1 ms-seguridad python - < /tmp/preparar_cuentas_vm.py; rm -f /tmp/preparar_cuentas_vm.py"
    rm -f "$PRIVADO/preparar_cuentas_vm.py" "$PRIVADO/sesiones_$PREFIJO.json"
    echo "Sesiones revocadas, cuentas desactivadas y archivo de tokens borrado (los datos de prueba se conservan)"
    ;;
*) echo "acción desconocida: $ACCION"; exit 1 ;;
esac
