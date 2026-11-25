# Pruebas de integración contra el despliegue en Google Cloud

- **Fecha:** 2026-11-25
- **Commit desplegado:** `e58954e` (VM `integracion`, https://34.135.84.31, bucket real `abastored-archivos-integracion-505802`)
- **Commit de las pruebas:** el de este archivo

```bash
PRUEBAS_HOST=https://34.135.84.31 PRUEBAS_CA=apps/infra/gcp/certificado_gateway_gcp.crt PRUEBAS_GCS_REAL=1     python -m pytest tests/integracion -q -rs
```

**Resultado:** 182 aprobadas, 15 omitidas, 0 fallidas (4 min 53 s; despliegue `e58954e`).

**Repetición final** (25/11/2026, despliegue y pruebas del commit `670ba4e`): **185 aprobadas, 19 omitidas, 0
fallidas** (5 min 29 s). Las 4 omitidas nuevas son `test_fallas.py`, que detiene contenedores y no se corre
contra el servidor desplegado.

Con `PRUEBAS_GCS_REAL=1` corre también `test_url_firmada_expira_en_el_bucket_real`: la URL firmada V4 descarga el archivo directo de `storage.googleapis.com` y, pasado su tiempo de vida, Google la rechaza.

## Omitidas y por qué

Ninguna se omite por fallar. Las 15 requieren detener contenedores o leer secretos del equipo donde corre el sistema, y no se hace contra el servidor desplegado. Todas corren en la suite local (Docker en este equipo).

| Archivo | Omitidas | Motivo |
| :--- | :---: | :--- |
| test_almacenamiento.py | 2 | Detienen el emulador de almacenamiento con Docker (no se detiene un bucket real) |
| test_monitoreo.py | 3 | Detienen contenedores para ver el estado «degradado/caído» |
| test_propiedad_datos.py | 5 | Revisan permisos de los roles de PostgreSQL con `docker exec` |
| test_resiliencia.py | 2 | Detienen PostgreSQL/Redis/MongoDB |
| test_seguridad.py | 3 | Dos fabrican tokens con el secreto JWT (no está en este equipo); una detiene Redis |
| test_fallas.py (repetición final) | 4 | Detienen o congelan PostgreSQL, MongoDB y ms-inventario |

## Ajustes a las pruebas que salieron de esta corrida

- El paquete de certificados de confianza ahora es *autoridades públicas + certificado del gateway*. Antes era solo el del gateway, y la descarga real del bucket no se podía verificar. No se desactiva la verificación TLS.
- La prueba de ráfagas del gateway usa conexiones reutilizadas. Contra un servidor remoto, abrir TLS en cada petición repartía la ráfaga en varios segundos, y cabía en el margen del límite sin probarlo.
- El login que comprueba que un operador desactivado ya no entra respeta el límite por minuto de ms-seguridad.
