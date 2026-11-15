# Contenedor para correr las pruebas sin instalar nada en el equipo:
#   docker compose --profile pruebas run --rm pruebas
# Entra a la red de Docker y prueba los servicios por sus direcciones internas.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PRUEBAS_SIN_VENV=1 PRUEBAS_MODO=interno \
    PRUEBAS_COMANDO="docker compose --profile pruebas run --rm pruebas"
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory /repo

COPY libs/abasto_dominio /libs/abasto_dominio
COPY libs/abasto_api /libs/abasto_api
COPY tests/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir /libs/abasto_dominio /libs/abasto_api -r /tmp/requirements.txt

WORKDIR /repo
CMD ["python", "scripts/ejecutar_pruebas.py"]
