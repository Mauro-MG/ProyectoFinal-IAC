#!/bin/sh
# Genera un certificado autofirmado para localhost la primera vez que arranca el gateway.
# Queda en infra/certs/ (fuera de git): abastored.crt sirve para que los clientes
# (pruebas, scripts, navegador) confíen en el gateway; la llave nunca sale de esa carpeta.
set -e
DIR=/etc/nginx/certs
if [ ! -s "$DIR/abastored.crt" ] || [ ! -s "$DIR/abastored.key" ]; then
    echo "gateway: generando certificado autofirmado para localhost"
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
        -keyout "$DIR/abastored.key" -out "$DIR/abastored.crt" \
        -subj "/CN=localhost/O=AbastoRed Equipo 01" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,digitalSignature,keyCertSign"
    chmod 600 "$DIR/abastored.key"
fi
