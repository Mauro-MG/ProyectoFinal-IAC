#!/usr/bin/env bash
# =============================================================================
# Simulacro de restauración SIN tocar los datos en uso (en la VM):
#   sudo bash /opt/abastored/actual/apps/infra/gcp/probar_restauracion.sh <respaldo>
#
# 1. Descarga el respaldo del bucket y verifica su SHA-256.
# 2. PostgreSQL: lo restaura en una base nueva «restauracion_prueba».
#    MongoDB: lo restaura renombrando la base a «restauracion_prueba».
# 3. Compara el número de filas/documentos de cada tabla y colección contra las originales
#    (las que cambiaron después del respaldo se marcan; no es un error si el sistema siguió en uso).
# 4. Borra las dos copias. Las bases del sistema no se detienen ni se modifican.
# =============================================================================
set -euo pipefail
RESPALDO="${1:?Indica el respaldo (gcloud storage ls gs://<bucket>/respaldos/)}"
cd /opt/abastored/actual
set -a; . <(tr -d '\r' < ./.env); set +a
TEMPORAL=$(mktemp -d)
COMPOSE=(docker compose -p abastored -f docker-compose.yml -f docker-compose.gcp.yml)
PRUEBA=restauracion_prueba

limpiar() {
    "${COMPOSE[@]}" exec -T abastored-postgres sh -c "dropdb -U \"\$POSTGRES_USER\" --if-exists $PRUEBA" || true
    "${COMPOSE[@]}" exec -T abastored-mongo sh -c "mongosh --quiet -u \"\$MONGO_INITDB_ROOT_USERNAME\" \
        -p \"\$(cat /run/secrets/mongo_password)\" --authenticationDatabase admin $PRUEBA --eval 'db.dropDatabase()'" \
        >/dev/null || true
    rm -rf "$TEMPORAL"
}
trap limpiar EXIT

gcloud storage cp "gs://$GCS_BUCKET/respaldos/$RESPALDO/*" "$TEMPORAL/" \
    --impersonate-service-account="$GCS_CUENTA_FIRMA" --quiet
# Respaldos anteriores guardaban la ruta absoluta de su carpeta temporal: se verifica por nombre
(cd "$TEMPORAL" && sed -E 's#  /.*/#  #' SHA256SUMS | sha256sum -c -)

echo "== PostgreSQL -> base $PRUEBA"
"${COMPOSE[@]}" exec -T abastored-postgres sh -c "dropdb -U \"\$POSTGRES_USER\" --if-exists $PRUEBA; \
    createdb -U \"\$POSTGRES_USER\" $PRUEBA"
# Las extensiones (PostGIS) y los roles por servicio ya existen en el servidor; --no-owner evita depender de ellos
"${COMPOSE[@]}" exec -T abastored-postgres sh -c \
    "pg_restore --no-owner --no-acl -U \"\$POSTGRES_USER\" -d $PRUEBA" < "$TEMPORAL/postgres.dump"

contar_pg() {   # conteo exacto por tabla
    "${COMPOSE[@]}" exec -T abastored-postgres sh -c "psql -U \"\$POSTGRES_USER\" -d $1 -At -F' ' -c \"
        SELECT format('SELECT %L, count(*) FROM %I.%I;', schemaname||'.'||tablename, schemaname, tablename)
        FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema','tiger','topology')
        ORDER BY 1\" | psql -U \"\$POSTGRES_USER\" -d $1 -At -F' '"
}
contar_pg "$POSTGRES_DB" > "$TEMPORAL/pg_original.txt"
contar_pg "$PRUEBA" > "$TEMPORAL/pg_restaurada.txt"

echo "== MongoDB -> base $PRUEBA"
"${COMPOSE[@]}" exec -T abastored-mongo sh -c \
    "mongorestore --quiet --archive --gzip --nsFrom '$MONGO_DB.*' --nsTo '$PRUEBA.*' --nsInclude '$MONGO_DB.*' \
     -u \"\$MONGO_INITDB_ROOT_USERNAME\" -p \"\$(cat /run/secrets/mongo_password)\" --authenticationDatabase admin" \
    < "$TEMPORAL/mongo.archive.gz"
contar_mongo() {
    "${COMPOSE[@]}" exec -T abastored-mongo sh -c "mongosh --quiet -u \"\$MONGO_INITDB_ROOT_USERNAME\" \
        -p \"\$(cat /run/secrets/mongo_password)\" --authenticationDatabase admin $1 --eval \
        'db.getCollectionNames().sort().forEach(c => print(c + \" \" + db.getCollection(c).countDocuments()))'"
}
contar_mongo "$MONGO_DB" > "$TEMPORAL/mongo_original.txt"
contar_mongo "$PRUEBA" > "$TEMPORAL/mongo_restaurada.txt"

comparar() {   # $1 nombre, $2 original, $3 restaurada
    local tablas iguales distintas faltan
    tablas=$(wc -l < "$3"); iguales=$(comm -12 <(sort "$2") <(sort "$3") | wc -l)
    faltan=$(comm -23 <(cut -d' ' -f1 "$2" | sort) <(cut -d' ' -f1 "$3" | sort) | wc -l)
    echo "$1: $tablas restauradas, $iguales con el mismo conteo que hoy, $faltan creadas después del respaldo"
    join <(sort "$2") <(sort "$3") | awk '$2 != $3 {print "   cambió desde el respaldo: " $1 " (hoy " $2 ", respaldo " $3 ")"}'
}
echo "== Resultado del respaldo $RESPALDO"
comparar PostgreSQL "$TEMPORAL/pg_original.txt" "$TEMPORAL/pg_restaurada.txt"
comparar MongoDB "$TEMPORAL/mongo_original.txt" "$TEMPORAL/mongo_restaurada.txt"
echo "Simulacro terminado; se borran las copias de prueba."
