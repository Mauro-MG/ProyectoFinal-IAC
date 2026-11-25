# Publica la página del proyecto en Ubiquitous (https://ubiquitous.udem.edu/~iac-604775/).
# Se corre desde la red de la UDEM o con la VPN; pide la contraseña de la cuenta en la terminal (no se guarda).
#
#   powershell -ExecutionPolicy Bypass -File apps\ubiquitous\publicar.ps1
#
# Copia proyecto-final-abastored/ a public_html/ y deja el index.html del portafolio con la tarjeta nueva.
# La tarjeta se agrega a mano (ver paso 3): así no se reescribe el portafolio sin revisarlo.
param(
    [string]$Usuario = 'iac-604775',
    [string]$Servidor = 'ubiquitous.udem.edu',
    [string]$Destino = 'public_html'
)
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "1. Conexión a ${Servidor}:22 ..."
if (-not (Test-NetConnection $Servidor -Port 22 -InformationLevel Quiet)) {
    throw "No hay conexión SSH con $Servidor. Conéctate a la red de la UDEM o a la VPN."
}

Write-Host "2. Copiando proyecto-final-abastored/ (pedirá la contraseña) ..."
scp -r "$aqui\proyecto-final-abastored" "${Usuario}@${Servidor}:${Destino}/"
if ($LASTEXITCODE -ne 0) { throw "scp falló ($LASTEXITCODE)" }
ssh "${Usuario}@${Servidor}" "chmod -R a+rX ${Destino}/proyecto-final-abastored"

Write-Host @"
3. Agrega la tarjeta al portafolio:
   - descarga el index actual:   scp ${Usuario}@${Servidor}:${Destino}/index.html .
   - pega el contenido de apps\ubiquitous\tarjeta_portafolio.html como primera tarjeta de <div class="grid-entregas">
   - súbelo:                     scp index.html ${Usuario}@${Servidor}:${Destino}/index.html
4. Comprueba: https://${Servidor}/~${Usuario}/proyecto-final-abastored/
"@
