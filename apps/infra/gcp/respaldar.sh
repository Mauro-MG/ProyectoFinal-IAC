#!/usr/bin/env bash
# =============================================================================
# Respaldo de PostgreSQL y MongoDB al bucket (gs://<bucket>/respaldos/<fecha>/).
# En la VM corre cada día por cron (/etc/cron.d/abastored-respaldo). A mano:
#   sudo /usr/local/bin/abastored-respaldar   (sudo no busca en /usr/local/bin)
# Los objetos de respaldos/ vencen a los 60 días (regla del bucket). Se suben como la
# cuenta dedicada abastored-archivos (suplantada), igual que los servicios.
# Redis no se respalda: solo guarda sesiones, caché y bloqueos temporales.
# =============================================================================
set -euo pipefail
cd /opt/abastored/actual
set -a; . <(tr -d '\r' < ./.env); set +a
FECHA=$(date -u +%Y%m%dT%H%M%SZ)
TEMPORAL=$(mktemp -d)
trap 'rm -rf "$TEMPORAL"' EXIT
COMPOSE=(docker compose -p abastored -f docker-compose.yml -f docker-compose.gcp.yml)

"${COMPOSE[@]}" exec -T abastored-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
    > "$TEMPORAL/postgres.dump"
"${COMPOSE[@]}" exec -T abastored-mongo sh -c \
    'mongodump --quiet --archive --gzip -u "$MONGO_INITDB_ROOT_USERNAME" -p "$(cat /run/secrets/mongo_password)" --authenticationDatabase admin' \
    > "$TEMPORAL/mongo.archive.gz"
(cd "$TEMPORAL" && sha256sum postgres.dump mongo.archive.gz > SHA256SUMS)   # nombres relativos
gcloud storage cp "$TEMPORAL"/* "gs://$GCS_BUCKET/respaldos/$FECHA/" \
    --impersonate-service-account="$GCS_CUENTA_FIRMA" --quiet
echo "$(date -u) respaldo $FECHA: $(du -ch "$TEMPORAL" | tail -1 | cut -f1)"
