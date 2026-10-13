# ms-analisis · AbastoRed
# Se construye desde la raíz del repositorio: docker build -f apps/microservicios/analisis/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Bibliotecas compartidas (dominio y base de API)
COPY libs/abasto_dominio /libs/abasto_dominio
COPY libs/abasto_api /libs/abasto_api
RUN pip install --no-cache-dir /libs/abasto_dominio /libs/abasto_api

WORKDIR /srv
COPY apps/microservicios/analisis/ .

EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fs http://localhost:8000/health/live || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "app:app"]
