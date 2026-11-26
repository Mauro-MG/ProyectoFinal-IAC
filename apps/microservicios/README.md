# Microservicios

24 aplicaciones Flask independientes, cada una en su propio contenedor. Dentro de la red de Docker
escuchan en el 8000 con gunicorn; desde fuera solo se llega por el gateway HTTPS
(`https://<host>/ms/<servicio>/...`). En desarrollo, `docker-compose.dev.yml` publica cada una en
`127.0.0.1:81xx`.

La lista de servicios y sus puertos está en un solo lugar,
`libs/abasto_dominio/abasto_dominio/registro_servicios.py`. De ahí la toman la configuración, el web,
ms-monitoreo y las pruebas.

Todos comparten dos bibliotecas del repositorio:

- `libs/abasto_dominio`: modelos SQLAlchemy, reglas de negocio y auditoría.
- `libs/abasto_api`: la clase `Servicio`, que da a todos el mismo comportamiento:
  - rutas bajo `/api/v1`;
  - JWT con sesión en Redis y permisos por ruta;
  - validación con Pydantic;
  - respuestas JSON o XML según `Accept`, y XSD;
  - errores estandarizados y límite de peticiones;
  - `X-Correlation-ID` y bitácora en MongoDB;
  - `/health/*`, OpenAPI 3.0.3 y Swagger UI.

Qué tablas escribe cada servicio y cuáles solo lee: [`docs/propiedad_de_datos.md`](../../docs/propiedad_de_datos.md).

| Servicio | Puerto | Responsabilidad | Es dueño de |
| :--- | :--- | :--- | :--- |
| `seguridad/` | 8101 | Login, registro, recuperación de acceso, JWT y refresh, usuarios, roles, sesiones, bloqueo por intentos | usuarios, roles |
| `comercios/` | 8102 | Comercios formales e informales, datos fiscales, horarios, giro, verificación, responsables, búsqueda geográfica | comercios, responsables_comercio |
| `catalogo/` | 8103 | Productos, categorías, marcas, unidades, variantes, códigos de barras, equivalencias | productos_maestros, categorias, marcas, unidades_medida, variantes_producto, equivalencias_producto |
| `inventario/` | 8104 | Existencias por comercio y sucursal, movimientos, lote transaccional, reservas, transferencias, CSV | inventario_comercio, movimientos_inventario, reservas_inventario, transferencias_inventario |
| `precios/` | 8105 | Precio al consumidor, atípicos, comparación, promociones, estadísticas por municipio y zona | precios_comercio, promociones |
| `pedidos/` | 8106 | Pedidos de abasto y su ciclo; existencias por la API de proveedores e inventario | pedidos_abasto, detalle_pedidos, historial_pedido |
| `analisis/` | 8107 | Cobertura, brechas, índice de acceso, municipios, datos para Highcharts | ejecuciones_analisis (Mongo) |
| `notificaciones/` | 8108 | Avisos internos y push, preferencias, plantillas, dispositivos, historial por canal | notificaciones y colecciones de canales (Mongo) |
| `proveedores/` | 8109 | Registro, verificación, zonas de servicio, condiciones, capacidad, catálogo mayorista, evaluación | proveedores, proveedor_zonas, catalogo_proveedor, precios_mayoreo, evaluaciones_proveedor |
| `abastecimiento/` | 8110 | Cotizaciones consolidadas, comparación, sugerencia de reabastecimiento, órdenes de compra | solicitudes_cotizacion, cotizaciones, ordenes_compra (y sus partidas) |
| `disponibilidad/` | 8111 | Disponibilidad por comercio, zona y proveedor; reservado y tiempo de surtido; cambios para apps | solo lectura y caché |
| `geolocalizacion/` | 8112 | Geocodificación, validación de coordenadas, distancias, radios, cobertura (PostGIS) | zonas_municipales, colonias |
| `sincronizacion/` | 8113 | Lotes offline de Android y escritorio: duplicados, conflictos, reintentos, confirmación | lotes y operaciones (Mongo) |
| `documentos/` | 8114 | Archivos en Cloud Storage con validación del tipo real, URL firmadas temporales y control de acceso; migración desde GridFS | `archivos_metadatos` (Mongo) + objetos del bucket |
| `reportes/` | 8115 | Reportes en PDF, CSV, Excel y JSON; programación | bucket `reportes`, reportes_programados (Mongo) |
| `recomendaciones/` | 8116 | Recomendación de surtido explicada y medición de resultados | recomendaciones_emitidas (Mongo) |
| `demanda/` | 8117 | Demanda histórica, tendencias, estacionalidad, no satisfecha, estimación | demanda_busquedas (Mongo) |
| `ventas/` | 8118 | Ventas y devoluciones con actualización de inventario (saga) y comprobante | ventas, detalle_ventas, devoluciones |
| `entregas/` | 8119 | Entregas: responsable, estados, QR de confirmación, incidencias, evidencia, rastreo | entregas, eventos_entrega, incidencias_entrega |
| `auditoria/` | 8120 | Bitácora centralizada, traza por correlation_id, historial por registro, conciliación | eventos_auditoria (Mongo) |
| `integraciones/` | 8121 | Importación y exportación CSV/JSON/XML, conectores con mapeo, errores por fila | lotes y conectores (Mongo) |
| `configuracion/` | 8122 | Parámetros con tipo y rango, parámetros públicos, catálogos administrativos | configuracion_sistema, catalogos_administrativos |
| `monitoreo/` | 8123 | Salud de los 24 servicios, bases de datos, métricas (p95), alertas | alertas_infraestructura (Mongo) |
| `busqueda/` | 8124 | Búsqueda unificada sin acentos, relevancia, filtros, sugerencias | solo lectura y caché |

## Estructura de cada servicio

```
<servicio>/
├── app.py            # srv = Servicio(...); rutas con @srv.ruta('/...', 'GET', permisos=[...], ...)
├── esquemas.py       # modelos de entrada, consulta y salida + CONTRATOS_XML (raíz -> modelo)
├── modelos.py        # (si aplica) tablas propias del servicio
├── xsd/<servicio>.xsd   # generado de esquemas.py (no se edita a mano)
├── requirements.txt  # (si aplica) dependencias propias, p. ej. reportlab en ms-reportes
└── Dockerfile        # se construye desde la raíz del repositorio (instala libs/)
```

## Tareas comunes

```bash
# Revisar todos los servicios sin Docker: regenera XSD, importa app.py y valida el OpenAPI
python scripts/revisar_servicios.py

# Regenerar el XSD de un servicio después de cambiar un esquema (una prueba verifica que esté al día)
python -m abasto_api.contratos apps/microservicios/pedidos

# Reconstruir y reiniciar un servicio
docker compose up -d --build ms-pedidos

# Ver su bitácora (una línea JSON por petición)
docker compose logs -f ms-pedidos
```
