#!/usr/bin/env bash
# =============================================================================
# Muestreo de recursos EN LA VM durante una corrida (lo copia y lanza correr_gcp.sh; se ejecuta con sudo).
#   bash muestreo_vm.sh <segundos_máximos>
# Escribe en stdout (correr_gcp.sh lo guarda en muestras_vm.csv):
#   VM,<epoch>,<mem_disp_mb>,<disco_libre_gb>,<carga_1min>,<us>,<sy>,<id>,<wa>,<st>     cada ~5 s
#   CT,<epoch>,<contenedor>,<cpu%>,<memoria usada / límite>,<mem%>                         cada ~5 s
#   RS,<epoch>,<contenedor>,<reinicios>,<oom_killed>,<estado>,<salud>                     cada ~30 s
#   ALERTA,<epoch>,<texto>         si un contenedor se reinicia o queda OOMKilled desde el inicio
# Se detiene sola al pasar <segundos_máximos> o cuando existe /tmp/abasto_muestreo.parar.
# Solo lee: no detiene ni modifica contenedores.
# =============================================================================
set -u
MAXIMO=${1:-2400}
rm -f /tmp/abasto_muestreo.parar
FIN=$(( $(date +%s) + MAXIMO ))
declare -A BASE
estado() {
    docker inspect --format '{{.Name}},{{.RestartCount}},{{.State.OOMKilled}},{{.State.Status}},{{if .State.Health}}{{.State.Health.Status}}{{end}}' $(docker ps -aq) | sed 's#^/##'
}
while IFS=, read -r nombre reinicios oom _ _; do BASE[$nombre]="$reinicios,$oom"; done < <(estado)
vuelta=0
while [ "$(date +%s)" -lt "$FIN" ] && [ ! -e /tmp/abasto_muestreo.parar ]; do
    t=$(date +%s)
    mem=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    disco=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
    carga=$(cut -d' ' -f1 /proc/loadavg)
    cpu=$(vmstat 1 2 | tail -1 | awk '{print $13","$14","$15","$16","$17}')
    echo "VM,$t,$mem,$disco,$carga,$cpu"
    docker stats --no-stream --format "CT,$t,{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}" | tr -d '%'
    if [ $((vuelta % 6)) -eq 0 ]; then
        while IFS=, read -r nombre reinicios oom st salud; do
            echo "RS,$t,$nombre,$reinicios,$oom,$st,$salud"
            if [ "${BASE[$nombre]:-$reinicios,$oom}" != "$reinicios,$oom" ]; then
                echo "ALERTA,$t,$nombre reinicios=$reinicios oom=$oom (al inicio ${BASE[$nombre]:-?})"
            fi
        done < <(estado)
    fi
    vuelta=$((vuelta + 1))
    sleep 3
done
echo "FIN,$(date +%s)"
