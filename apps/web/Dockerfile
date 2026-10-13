# Sistema web de AbastoRed (monolito Flask)
# Se construye desde la raíz del repositorio: docker build -f apps/web/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Biblioteca de dominio compartida con los microservicios (editable: en desarrollo se monta ./libs)
COPY libs/abasto_dominio /libs/abasto_dominio
RUN pip install --no-cache-dir -e /libs/abasto_dominio

WORKDIR /app
COPY apps/web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/web/ .

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
