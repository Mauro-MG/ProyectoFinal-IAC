#!/usr/bin/env bash
# =============================================================================
# AbastoRed - recursos de Google Cloud (idempotente)
#
#   bash apps/infra/gcp/aprovisionar.sh            # muestra el plan, no cambia nada
#   bash apps/infra/gcp/aprovisionar.sh --aplicar  # lo aplica
#
# Crea o ajusta, sin borrar nada existente:
#   1. Bucket privado de archivos (acceso uniforme, sin acceso público, versionado,
#      los reportes vencen a los 30 días y los respaldos a los 60).
#   2. Cuenta de servicio dedicada abastored-archivos: solo storage.objectAdmin sobre
#      ESE bucket. Los servicios la suplantan desde la VM (sin llaves descargadas).
#   3. Permiso a la cuenta de la VM para suplantarla (iam.serviceAccountTokenCreator).
#   4. Reglas de firewall: 80/443 abiertos para la etiqueta abastored y SSH solo desde
#      Identity-Aware Proxy (35.235.240.0/20). Bases de datos: ningún puerto público.
#   5. VM: tipo de máquina, disco y alcance de las credenciales (requiere detenerla).
# =============================================================================
set -euo pipefail

PROYECTO="${PROYECTO:-integracion-505802}"
ZONA="${ZONA:-us-central1-c}"
REGION="${ZONA%-*}"
VM="${VM:-integracion}"
TIPO="${TIPO:-e2-standard-4}"
DISCO_GB="${DISCO_GB:-50}"
BUCKET="${BUCKET:-abastored-archivos-${PROYECTO}}"
CUENTA="abastored-archivos@${PROYECTO}.iam.gserviceaccount.com"
APLICAR=false
[[ "${1:-}" == "--aplicar" ]] && APLICAR=true

paso() { echo; echo "== $*"; }
hacer() {
    echo "   \$ $*"
    if $APLICAR; then "$@"; fi
}

gcloud config set project "$PROYECTO" >/dev/null
CUENTA_VM=$(gcloud compute instances describe "$VM" --zone "$ZONA" --format='value(serviceAccounts[0].email)')
echo "Proyecto: $PROYECTO · VM: $VM ($ZONA) · cuenta de la VM: $CUENTA_VM"
$APLICAR || echo "(modo plan: no se cambia nada; usa --aplicar)"

paso "1. Bucket privado gs://$BUCKET"
if gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
    echo "   ya existe"
else
    hacer gcloud storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access \
        --public-access-prevention --default-storage-class STANDARD
fi
REGLAS=$(mktemp)
cat > "$REGLAS" <<'JSON'
{"rule": [
  {"action": {"type": "Delete"}, "condition": {"age": 30, "matchesPrefix": ["reportes/"]}},
  {"action": {"type": "Delete"}, "condition": {"age": 60, "matchesPrefix": ["respaldos/"]}},
  {"action": {"type": "Delete"}, "condition": {"daysSinceNoncurrentTime": 30}}
]}
JSON
hacer gcloud storage buckets update "gs://$BUCKET" --versioning --lifecycle-file="$REGLAS"

paso "2. Cuenta de servicio dedicada $CUENTA"
if gcloud iam service-accounts describe "$CUENTA" >/dev/null 2>&1; then
    echo "   ya existe"
else
    hacer gcloud iam service-accounts create abastored-archivos \
        --display-name "AbastoRed - solo archivos del bucket"
fi
hacer gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --member "serviceAccount:$CUENTA" --role roles/storage.objectAdmin

paso "3. La cuenta de la VM puede suplantarla (firma de URLs con IAM signBlob, sin llaves)"
hacer gcloud iam service-accounts add-iam-policy-binding "$CUENTA" \
    --member "serviceAccount:$CUENTA_VM" --role roles/iam.serviceAccountTokenCreator

paso "4. Firewall"
regla() {   # nombre puertos origen
    if gcloud compute firewall-rules describe "$1" >/dev/null 2>&1; then
        echo "   $1 ya existe"
    else
        hacer gcloud compute firewall-rules create "$1" --network default --direction INGRESS             --allow "$2" --source-ranges "$3" --target-tags abastored
    fi
}
regla abastored-web "tcp:80,tcp:443" "0.0.0.0/0"          # solo el gateway publica puertos
regla abastored-ssh-iap "tcp:22" "35.235.240.0/20"        # SSH solo a través de Identity-Aware Proxy
hacer gcloud compute instances add-tags "$VM" --zone "$ZONA" --tags abastored

if [[ "${SIN_VM:-}" == 1 ]]; then echo; echo "(SIN_VM=1: no se toca la VM)"; exit 0; fi
paso "5. VM $VM: $TIPO, disco de $DISCO_GB GB y credenciales con alcance cloud-platform"
ACTUAL=$(gcloud compute instances describe "$VM" --zone "$ZONA" --format='value(machineType.basename())')
DISCO=$(gcloud compute instances describe "$VM" --zone "$ZONA" --format='value(disks[0].source.basename())')
TAMANO=$(gcloud compute disks describe "$DISCO" --zone "$ZONA" --format='value(sizeGb)')
if (( TAMANO < DISCO_GB )); then
    hacer gcloud compute disks resize "$DISCO" --zone "$ZONA" --size "${DISCO_GB}GB" --quiet
else
    echo "   disco de ${TAMANO} GB: suficiente"
fi
if [[ "$ACTUAL" != "$TIPO" ]] || ! gcloud compute instances describe "$VM" --zone "$ZONA" \
        --format='value(serviceAccounts[0].scopes)' | grep -q cloud-platform; then
    echo "   La VM se detiene unos minutos (también lo que corre en ella)."
    hacer gcloud compute instances stop "$VM" --zone "$ZONA"
    hacer gcloud compute instances set-machine-type "$VM" --zone "$ZONA" --machine-type "$TIPO"
    hacer gcloud compute instances set-service-account "$VM" --zone "$ZONA" \
        --service-account "$CUENTA_VM" --scopes cloud-platform
    hacer gcloud compute instances start "$VM" --zone "$ZONA"
else
    echo "   ya es $TIPO con alcance cloud-platform"
fi

paso "Listo"
echo "Variables para .env en la VM: GCS_BUCKET=$BUCKET GCS_PROYECTO=$PROYECTO GCS_CUENTA_FIRMA=$CUENTA"
