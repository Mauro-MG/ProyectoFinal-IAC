#!/usr/bin/env bash
# =============================================================================
# AbastoRed - despliegue o actualización en la VM de Compute Engine
#
#   bash apps/infra/gcp/desplegar.sh [commit]     # por omisión, HEAD
#
# Empaqueta el commit indicado (git archive: solo lo versionado, nunca secretos ni
# .env), lo copia a la VM por SSH a través de IAP y ejecuta instalar_en_vm.sh, que:
#   - instala Docker si falta;
#   - deja la versión en /opt/abastored/versiones/<commit> y apunta /opt/abastored/actual;
#   - conserva .env, secrets/, infra/certs/ y los volúmenes entre versiones;
#   - construye y levanta con docker-compose.yml + docker-compose.gcp.yml;
#   - aplica las migraciones idempotentes y espera a que los 29 contenedores estén sanos.
# Volver a la versión anterior: bash apps/infra/gcp/desplegar.sh <commit anterior>
# =============================================================================
set -euo pipefail
PROYECTO="${PROYECTO:-integracion-505802}"
ZONA="${ZONA:-us-central1-c}"
VM="${VM:-integracion}"
COMMIT=$(git rev-parse --short "${1:-HEAD}")
PAQUETE="abastored-${COMMIT}.tar.gz"
RAIZ=$(git rev-parse --show-toplevel)

cd "$RAIZ"
echo "Empaquetando $COMMIT ..."
git archive --format=tar.gz -o "/tmp/$PAQUETE" "$COMMIT"
SSH=(gcloud compute ssh "$VM" --project "$PROYECTO" --zone "$ZONA" --tunnel-through-iap --quiet)
# El instalador sale del mismo commit y con fin de línea LF, no de la copia de trabajo
git show "$COMMIT:apps/infra/gcp/instalar_en_vm.sh" | tr -d '\r' > /tmp/instalar_en_vm.sh
gcloud compute scp "/tmp/$PAQUETE" /tmp/instalar_en_vm.sh "$VM:/tmp/" \
    --project "$PROYECTO" --zone "$ZONA" --tunnel-through-iap --quiet
"${SSH[@]}" --command "sudo bash /tmp/instalar_en_vm.sh /tmp/$PAQUETE $COMMIT"
rm -f "/tmp/$PAQUETE"
IP=$(gcloud compute instances describe "$VM" --project "$PROYECTO" --zone "$ZONA" \
     --format='value(networkInterfaces[0].accessConfigs[0].natIP)')
echo "Listo: https://$IP/  (certificado: /opt/abastored/compartido/certs/abastored.crt en la VM)"
