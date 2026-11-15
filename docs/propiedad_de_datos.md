# Propiedad de datos entre microservicios

Regla: **cada tabla o colección tiene un solo servicio dueño, y solo el dueño escribe en ella.**
Cuando otro servicio necesita cambiar ese dato, llama a la API del dueño con el token del usuario y
el mismo `X-Correlation-ID`. Así se aplican las mismas reglas y permisos, y la operación se puede
rastrear en `ms-auditoria → GET /trazas/{correlation_id}`.

Varios servicios sí **leen** tablas de otros, con consultas de solo lectura. Por ejemplo,
ms-disponibilidad, ms-busqueda, ms-reportes y ms-analisis son servicios de consulta. Esta lectura
compartida está permitida y se documenta en la columna «Lo leen». En la fase 3 cada servicio usará su
propio usuario de PostgreSQL con permiso de escritura **solo** en sus tablas (`db/postgres/05_roles.sql`).

## PostgreSQL

| Tabla | Dueño (escribe) | Lo leen | Cómo la cambian los demás |
| :--- | :--- | :--- | :--- |
| `usuarios`, `roles` | ms-seguridad | todos (validación del token, nombres) | `POST /auth/registro`, `PATCH /usuarios/{id}`, `PUT /roles/{id}/permisos` |
| `comercios`, `responsables_comercio` | ms-comercios | inventario, ventas, pedidos, entregas, abastecimiento, análisis, reportes, búsqueda | `PUT /comercios/{id}`, `PUT /comercios/{id}/foto`, `PATCH /comercios/{id}/validacion` |
| `zonas_municipales`, `colonias` | ms-geolocalizacion | comercios (cálculo de respaldo), análisis, disponibilidad, búsqueda | `POST/PATCH /zonas` |
| `productos_maestros`, `categorias`, `marcas`, `unidades_medida`, `variantes_producto`, `equivalencias_producto` | ms-catalogo | todos los que muestran productos | `POST/PUT /productos`, `/variantes`, `/equivalentes` |
| `inventario_comercio`, `movimientos_inventario`, `reservas_inventario`, `transferencias_inventario` | ms-inventario | disponibilidad, ventas, recomendaciones, demanda, análisis, reportes, búsqueda | `POST /comercios/{id}/movimientos/lote` (ventas, pedidos, sincronización), `POST /inventario/{id}/movimientos`, `/reservas`, `/transferencias` |
| `precios_comercio`, `promociones` | ms-precios | ventas (precio promocional), análisis, reportes | `PUT /inventario/{id}/precio`, `POST /promociones` |
| `proveedores`, `proveedor_zonas`, `catalogo_proveedor`, `precios_mayoreo`, `evaluaciones_proveedor`, `salidas_catalogo` | ms-proveedores | pedidos, disponibilidad, abastecimiento, búsqueda, análisis | `POST /proveedores/{id}/salidas` (pedidos al despachar), `/mi-catalogo`, `/verificacion` |
| `pedidos_abasto`, `detalle_pedidos`, `historial_pedido` | ms-pedidos | entregas, documentos (permisos), reportes, recomendaciones | `POST /pedidos`, `POST /pedidos/{id}/acciones/{accion}` (entregas, abastecimiento) |
| `ventas`, `detalle_ventas`, `devoluciones`, `detalle_devoluciones` | ms-ventas | reportes, documentos (permisos) | `POST /ventas`, `POST /ventas/{id}/devoluciones` (sincronización) |
| `entregas`, `eventos_entrega`, `incidencias_entrega` | ms-entregas | documentos (permisos) | `/entregas/...` |
| `solicitudes_cotizacion`, `necesidades_solicitud`, `cotizaciones`, `partidas_cotizacion`, `ordenes_compra`, `partidas_orden` | ms-abastecimiento | — | `/solicitudes/...`, `/ordenes/...` |
| `configuracion_sistema`, `catalogos_administrativos` | ms-configuracion | todos, con `parametro()` y caché de 60 s por versión | `PUT /parametros/{clave}`, `/catalogos/...` |
| `auditoria_eventos` | **excepción**: todos insertan; ms-auditoria la consulta | ms-auditoria | Solo `INSERT`, dentro de la transacción de cada operación; un trigger impide `UPDATE` y `DELETE` |

### Excepciones documentadas

1. **`auditoria_eventos`.** Todos los servicios insertan su evento en la **misma transacción** de su
   operación. Así, si la operación se revierte, el evento también, y nunca queda un cambio sin
   auditar. Es de solo inserción: nadie puede modificar ni borrar un registro. ms-auditoria es dueño de
   la copia centralizada en MongoDB.
2. **`inventario_comercio.precio_venta`.** ms-precios cambia el precio vigente del renglón, que es la
   única columna de esa tabla que no escribe ms-inventario. El precio pertenece al dominio de precios,
   que guarda su historial y la validación de precios atípicos (RN-001), y vive en el renglón para no
   duplicarlo. La fase 3 lo restringe por columna: `GRANT UPDATE (precio_venta) ON inventario_comercio TO ms_precios`.
3. **El sistema web** todavía tiene operaciones que escriben con la biblioteca de dominio. La fase 3
   las cambia para que pasen por las APIs, y el web queda con un usuario de solo lectura. Ver
   `docs/web_y_apis.md`.

## MongoDB

| Colección | Dueño |
| :--- | :--- |
| `notificaciones`, `preferencias_notificacion`, `plantillas_notificacion`, `dispositivos_push`, `entregas_canal` | ms-notificaciones |
| `eventos_pedido` | ms-pedidos |
| `snapshots_precios` | ms-precios |
| `ejecuciones_analisis` | ms-analisis |
| `importaciones` | ms-inventario |
| `archivos.files` / `archivos.chunks` (GridFS) | ms-documentos |
| `reportes.files` / `reportes.chunks` (GridFS), `reportes_programados` | ms-reportes |
| `eventos_auditoria` | ms-auditoria (cada servicio agrega su copia al confirmar su transacción) |
| `bitacora_peticiones` | **excepción**: `abasto_api` inserta una línea por petición en cada servicio; ms-monitoreo y ms-auditoria la consultan |
| `alertas_infraestructura` | ms-monitoreo |
| `sincronizacion_lotes`, `sincronizacion_operaciones` | ms-sincronizacion |
| `demanda_busquedas` | ms-demanda |
| `recomendaciones_emitidas` | ms-recomendaciones |
| `integraciones_lotes`, `integraciones_conectores` | ms-integraciones |

## Operaciones que cruzan servicios (consistencia)

No hay transacciones distribuidas. Cada operación que cruza servicios usa tres mecanismos:

- **Orden de llamada.** Primero se llama al dueño y después se guarda el dato propio, sin dejar
  transacciones abiertas durante la llamada; así no quedan bloqueos cruzados.
- **Referencia idempotente.** Si una llamada se repite (reintento, doble clic, lote offline
  reenviado), el dueño responde lo que ya había aplicado y no repite el cambio.
- **Compensación.** Si el segundo paso falla, se deshace el primero con una operación inversa.

| Operación | Servicios | Referencia | Si falla |
| :--- | :--- | :--- | :--- |
| Registrar venta | ms-ventas → ms-inventario (salidas) | `venta:{id}`; `id_cliente` de la app | Sin existencia: 409 y no se guarda la venta. Si falla al guardar: entradas `venta-anulada:{id}` |
| Devolución | ms-ventas → ms-inventario (entradas) | `devolucion:{venta}:{n}` | 409/503 y la venta no cambia |
| Despachar pedido | ms-pedidos → ms-proveedores (`/salidas`) | `pedido:{id}` | El pedido no cambia de estado |
| Recibir pedido | ms-entregas → ms-pedidos → ms-inventario (entradas) | `pedido:{id}` | La entrega y el pedido no cambian |
| Salida a ruta | ms-entregas → ms-pedidos (`preparar`, `despachar`) | — | La entrega no cambia |
| Orden de compra → pedido | ms-abastecimiento → ms-pedidos | estado `CONVERTIDA` + bloqueo en Redis | La orden sigue `GENERADA` |
| Operación offline | ms-sincronizacion → dueño de cada operación | `sync:{operacion_id}`, `id_cliente` | `pendiente_reintento` |
| Importación de archivo | ms-integraciones → proveedores, inventario o precios | por fila | Error de esa fila en el lote; las demás se aplican |
| Foto del comercio | ms-documentos (archivo) → ms-comercios (`/foto`) | id del documento | El archivo queda; la foto no cambia |
