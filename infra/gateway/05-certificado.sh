#!/bin/sh
# Genera un certificado autofirmado la primera vez que arranca el gateway.
# Queda en infra/certs/ (fuera de git): abastored.crt sirve para que los clientes
# (pruebas, scripts, navegador, apps) confíen en el gateway; la llave nunca sale de esa carpeta.
# GATEWAY_SAN agrega nombres o IP públicas, p. ej. "IP:34.135.84.31,DNS:abastored.ejemplo.mx"
# (en Google Cloud lo fija apps/infra/gcp/desplegar.sh). Para cambiarlo se borra infra/certs/.
set -e
DIR=/etc/nginx/certs
if [ ! -s "$DIR/abastored.crt" ] || [ ! -s "$DIR/abastored.key" ]; then
    SAN="DNS:localhost,IP:127.0.0.1${GATEWAY_SAN:+,$GATEWAY_SAN}"
    echo "gateway: generando certificado autofirmado para $SAN"
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
        -keyout "$DIR/abastored.key" -out "$DIR/abastored.crt" \
        -subj "/CN=localhost/O=AbastoRed Equipo 01" \
        -addext "subjectAltName=$SAN" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,digitalSignature,keyCertSign"
    chmod 600 "$DIR/abastored.key"
fi
