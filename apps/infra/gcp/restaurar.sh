#!/usr/bin/env bash
# =============================================================================
# Restaura un respaldo del bucket (en la VM):
#   sudo bash /opt/abastored/actual/apps/infra/gcp/restaurar.sh 20261125T093000Z
#
# 1. Descarga el respaldo y verifica su SHA-256.
# 2. Detiene web y microservicios (las bases siguen arriba).
# 3. PostgreSQL: pg_restore --clean sobre la base. MongoDB: mongorestore --drop.
# 4. Vuelve a levantar todo y revisa la salud.
# Para practicar sin tocar producción: restaurar en una VM de prueba con el mismo commit.
# =============================================================================
set -euo pipefail
RESPALDO="${1:?Indica el respaldo (gcloud storage ls gs://<bucket>/respaldos/)}"
cd /opt/abastored/actual
set -a; . <(tr -d '\r' < ./.env); set +a
TEMPORAL=$(mktemp -d)
trap 'rm -rf "$TEMPORAL"' EXIT
COMPOSE=(docker compose -p abastored -f docker-compose.yml -f docker-compose.gcp.yml)

gcloud storage cp "gs://$GCS_BUCKET/respaldos/$RESPALDO/*" "$TEMPORAL/" \
    --impersonate-service-account="$GCS_CUENTA_FIRMA" --quiet
# Respaldos anteriores guardaban la ruta absoluta de su carpeta temporal: se verifica por nombre
(cd "$TEMPORAL" && sed -E 's#  /.*/#  #' SHA256SUMS | sha256sum -c -)

read -r -p "Se reemplazarán los datos actuales con el respaldo $RESPALDO. Escribe RESTAURAR para continuar: " ok
[ "$ok" = RESTAURAR ] || { echo "Cancelado."; exit 1; }

SERVICIOS=$("${COMPOSE[@]}" config --services | grep -vE '^abastored-(postgres|mongo|redis)$')
"${COMPOSE[@]}" stop $SERVICIOS
"${COMPOSE[@]}" exec -T abastored-postgres sh -c \
    'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$TEMPORAL/postgres.dump"
"${COMPOSE[@]}" exec -T abastored-mongo sh -c \
    'mongorestore --quiet --drop --archive --gzip -u "$MONGO_INITDB_ROOT_USERNAME" -p "$(cat /run/secrets/mongo_password)" --authenticationDatabase admin' \
    < "$TEMPORAL/mongo.archive.gz"
"${COMPOSE[@]}" up -d
echo "Restaurado $RESPALDO. Revisa: docker ps"
