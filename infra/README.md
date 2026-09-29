# Infraestructura

**Estado:** entorno local con Docker Compose listo; despliegue en Google Cloud en el cuarto parcial.

## Local

`docker-compose.yml` en la raíz levanta el sistema web, PostgreSQL + PostGIS, MongoDB y Redis
en una red privada `abastored-network`.

## Google Cloud (planeado)

| Recurso | Uso |
| :--- | :--- |
| Compute Engine (VM `e2-medium`) | Contenedores del sistema web y de los microservicios |
| VPC privada + reglas de firewall | Sólo 443 abierto al público; bases de datos sin IP pública |
| Cloud SQL (PostgreSQL + PostGIS) o contenedor en VM | Datos transaccionales |
| Memorystore (Redis) | Sesiones, revocación de tokens, caché y contadores |
| Cloud Storage | Fotos de productos y comercios, evidencias, exportaciones |
| Secret Manager | `SECRET_KEY`, `JWT_SECRET_KEY` y contraseñas de bases de datos |
| Cloud Logging / Monitoring | Logs con `correlation_id` y alertas de disponibilidad |

Aquí se guardarán los scripts de aprovisionamiento (`gcloud`) y los archivos de despliegue.
