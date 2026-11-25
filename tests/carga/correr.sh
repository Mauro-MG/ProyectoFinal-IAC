#!/usr/bin/env bash
# =============================================================================
# Corre un escenario de Locust contra el sistema LOCAL y guarda los resultados originales.
#
#   bash tests/carga/correr.sh <nombre> <usuarios> <usuarios_por_segundo> <duración> [opciones de locust]
#   bash tests/carga/correr.sh carga   100 10 5m
#   bash tests/carga/correr.sh estres  400  2 6m
#
# Antes: datos masivos cargados (scripts/datos_masivos.py generar) y sesiones de prueba emitidas:
#   docker exec -i ms-seguridad python - < tests/carga/emitir_sesiones.py > tests/carga/resultados/sesiones.json
#
# Deja en tests/carga/resultados/<fecha>_<nombre>/: estadísticas CSV e historial de Locust, reporte HTML,
# muestras de docker stats cada 10 s (CPU y memoria por contenedor) y un archivo con commit y ambiente.
# =============================================================================
set -euo pipefail
NOMBRE=${1:?nombre}; USUARIOS=${2:?usuarios}; TASA=${3:?usuarios por segundo}; DURACION=${4:?duración}; shift 4
RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
DESTINO="$RAIZ/tests/carga/resultados/$(date +%Y%m%d_%H%M)_$NOMBRE"
mkdir -p "$DESTINO"
RED=$(docker inspect ms-ventas --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | tr ' ' '\n' | grep publica)

{
    echo "fecha: $(date -Iseconds)"
    echo "commit: $(git -C "$RAIZ" rev-parse --short HEAD) $(git -C "$RAIZ" status --porcelain | wc -l | tr -d ' ') archivos sin commit"
    echo "escenario: $NOMBRE · $USUARIOS usuarios · $TASA/s · $DURACION · $*"
    echo "equipo: $(docker info --format '{{.NCPU}} CPU, {{.MemTotal}} bytes de memoria para Docker, {{.OperatingSystem}}')"
    echo "contenedores: $(docker ps -q | wc -l | tr -d ' ') en ejecución"
} > "$DESTINO/ambiente.txt"

# Muestras de recursos mientras corre la prueba
( while true; do
    docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' | sed "s/^/$(date +%H:%M:%S),/"
    sleep 10
  done ) > "$DESTINO/docker_stats.csv" &
MUESTREO=$!
trap 'kill $MUESTREO 2>/dev/null || true' EXIT

MSYS_NO_PATHCONV=1 docker run --rm --network "$RED" \
    -v "$RAIZ/tests/carga:/mnt/locust" locustio/locust:2.32.2 \
    -f /mnt/locust/locustfile.py --headless -u "$USUARIOS" -r "$TASA" -t "$DURACION" \
    --csv "/mnt/locust/resultados/$(basename "$DESTINO")/locust" --csv-full-history \
    --html "/mnt/locust/resultados/$(basename "$DESTINO")/reporte.html" --only-summary "$@" \
    2>&1 | tee "$DESTINO/salida.txt"
echo "Resultados en $DESTINO"
