#!/usr/bin/env bash
# =============================================================================
# Recuperación bajo carga (SOLO en el entorno local): 100 usuarios durante 4 minutos y, mientras tanto,
#   t=60 s  se detiene ms-inventario      t=90 s  se vuelve a arrancar
#   t=150 s se detiene Redis              t=180 s se vuelve a arrancar
# Las horas de cada evento quedan en eventos.txt junto a los resultados de Locust, para cruzarlas con el
# historial por segundo (locust_stats_history.csv) y medir el tiempo de recuperación.
# =============================================================================
set -euo pipefail
RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
bash "$RAIZ/tests/carga/correr.sh" recuperacion 100 20 4m > /dev/null 2>&1 &
CARGA=$!
sleep 5
DESTINO=$(ls -d "$RAIZ"/tests/carga/resultados/*_recuperacion | tail -1)
evento() { echo "$(date +%s) $(date +%H:%M:%S) $*" | tee -a "$DESTINO/eventos.txt"; }
evento inicio
sleep 55; evento "detener ms-inventario"; docker stop ms-inventario > /dev/null
sleep 30; evento "arrancar ms-inventario"; docker start ms-inventario > /dev/null
sleep 60; evento "detener abastored-redis"; docker stop abastored-redis > /dev/null
sleep 30; evento "arrancar abastored-redis"; docker start abastored-redis > /dev/null
wait $CARGA
evento fin
echo "Resultados en $DESTINO"
