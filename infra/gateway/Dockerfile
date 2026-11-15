# Gateway HTTPS de AbastoRed (nginx). Única entrada publicada: puertos 80 (redirige) y 443.
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl
COPY nginx.conf /etc/nginx/nginx.conf
COPY encabezados_proxy.conf /etc/nginx/encabezados_proxy.conf
# Los scripts de /docker-entrypoint.d corren antes de iniciar nginx
COPY 05-certificado.sh /docker-entrypoint.d/05-certificado.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/05-certificado.sh && chmod +x /docker-entrypoint.d/05-certificado.sh

HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD wget -q --no-check-certificate -O /dev/null https://127.0.0.1/health || exit 1
