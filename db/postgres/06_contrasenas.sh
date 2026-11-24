#!/bin/sh
# Pone a cada usuario de 05_roles.sql la contraseña de su secreto (/run/secrets/pg_<usuario>) y le permite
# entrar. Lo ejecuta la imagen de PostgreSQL al crear la base, después de los .sql (orden alfabético).
# Las contraseñas no se escriben en ningún archivo del repositorio, en variables de entorno ni en la
# línea de comandos: psql las lee del archivo con \set y las escapa al usarlas (:'clave').
set -e

for archivo in /run/secrets/pg_*; do
    [ -f "$archivo" ] || continue
    usuario="${archivo#/run/secrets/pg_}"
    psql -v ON_ERROR_STOP=1 -q --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
\set clave \`cat $archivo\`
ALTER ROLE "$usuario" LOGIN PASSWORD :'clave';
SQL
    echo "06_contrasenas: $usuario puede entrar"
done
