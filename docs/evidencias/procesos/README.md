# Tres procesos completos

Prueba: `tests/integracion/test_procesos_completos.py`. Se corrió el 25/11/2026 en local y contra Google Cloud
(bucket real), con `PROCESOS_EVIDENCIA=1`, que guarda cada paso con:

- actor y app cliente;
- método y ruta;
- código HTTP;
- `X-Correlation-ID`;
- resultado visible.

| Corrida | Archivo | Resultado |
| :--- | :--- | :--- |
| Local (Docker en este equipo) | [20261125_1711_local.json](20261125_1711_local.json) | 3 de 3 aprobadas |
| Google Cloud (`https://34.135.84.31`, bucket `abastored-archivos-integracion-505802`) | [20261125_1711_gcp.json](20261125_1711_gcp.json) | 3 de 3 aprobadas; foto y PDF descargados desde `storage.googleapis.com` |

```bash
PROCESOS_EVIDENCIA=1 python -m pytest tests/integracion/test_procesos_completos.py -q
PROCESOS_EVIDENCIA=1 PRUEBAS_HOST=https://34.135.84.31 PRUEBAS_CA=apps/infra/gcp/certificado_gateway_gcp.crt     python -m pytest tests/integracion/test_procesos_completos.py -q
```

| Proceso | Actores y apps | Servicios | Datos | Archivo en el bucket | Aviso | Auditoría |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Alta de comercio**: registro → comercio con ubicación (zona por PostGIS) → foto → validación → aviso | comerciante (Android, JSON), coordinador (escritorio, XML), auditor | seguridad, comercios, geolocalización, documentos, notificaciones, auditoría | PostgreSQL (usuario, comercio), MongoDB (metadatos, aviso, bitácora), Redis (sesiones, contador de avisos) | foto del local, descargada con URL firmada | «Puesto Rosa proceso: verificado» | 3 eventos de ms-comercios |
| **2. Abasto**: recomendación → oferta → pedido → aceptación → entrega con QR → inventario sube | minorista (Android), proveedor (web), auditor | recomendaciones, proveedores, pedidos, entregas, inventario, notificaciones, auditoría | PostgreSQL (pedido, entrega, movimientos), MongoDB (eventos del pedido, avisos), Redis (sesiones, bloqueo del lote) | — | «Pedido PED-…: enviado al proveedor» al equipo del proveedor | 7 eventos del pedido |
| **3. Importación, análisis y reporte**: CSV → aviso → brechas y DBSCAN (XML) → reporte PDF | minorista (web), analista (escritorio, XML), auditor | inventario, documentos, notificaciones, análisis, reportes, auditoría | PostgreSQL (inventario), MongoDB (importación, reporte), Redis (caché de análisis, bloqueo de importación) | CSV importado y PDF del reporte, descargado con URL firmada | «Importación de inventario terminada» | evento `Importacion` |

Para ver cualquier paso completo en todos los servicios que tocó:
`GET /ms/auditoria/api/v1/trazas/<correlation_id>`, con un usuario auditor.
