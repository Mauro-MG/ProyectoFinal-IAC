# El sistema web y los microservicios

El web **lee** de PostgreSQL para armar sus pantallas, con el usuario `abastored_web`, que es de solo
lectura. Las altas, cambios y bajas los manda a la API del servicio dueño del dato, y es ese servicio el
que valida, audita, notifica e invalida cachés. Si el web intentara escribir directo, PostgreSQL lo
rechazaría (`permission denied`). Esto lo comprueba `tests/integracion/test_propiedad_datos.py`.

## Cómo llama el web a los servicios

Todo pasa por `apps/web/app/microservicios.py`:

- **Token.** `llamar()` manda el JWT con el que el usuario inició sesión. Así el servicio aplica los
  permisos de esa persona, y en la auditoría aparece el usuario real, no el web.
- **Encabezados.** Cada llamada lleva:
  - `X-Correlation-ID`, para seguir la operación en `ms-auditoria → GET /trazas/{id}`;
  - `X-Forwarded-For` con la IP del usuario, para que el límite de peticiones se cuente por usuario y
    no por el contenedor web.
- **Escrituras.** `escribir()` es la forma de hacer cualquier cambio:
  - si el servicio rechaza el cambio, muestra su mensaje (por ejemplo «Ya existe esa categoría»);
  - si el servicio no responde, avisa que el cambio no se guardó;
  - en ningún caso escribe por su cuenta.
- **Sin sesión.** Iniciar sesión, registrarse y recuperar la contraseña usan `llamar(..., publico=True)`,
  que no lleva token.

## Qué pantalla llama a qué servicio

| Pantalla del web | Acción | Servicio | Endpoint |
| :--- | :--- | :--- | :--- |
| Iniciar sesión | validar credenciales, bloqueo por intentos, emitir JWT | ms-seguridad | `POST /auth/login` |
| Cerrar sesión | revocar el token | ms-seguridad | `POST /auth/logout` |
| Crear cuenta | alta del usuario | ms-seguridad | `POST /auth/registro` |
| Recuperar contraseña | enlace de un solo uso | ms-seguridad | `POST /auth/recuperacion`, `POST /auth/recuperacion/confirmacion` |
| Admin → Usuarios | cambiar rol o activar/desactivar (cierra sus sesiones) | ms-seguridad | `PATCH /usuarios/{id}` |
| Admin → Roles | permisos de cada rol | ms-seguridad | `PUT /roles/{id}/permisos` |
| Admin → Parámetros | valor con tipo y rango | ms-configuracion | `PUT /parametros/{clave}` |
| Catálogo → Productos | alta, edición, baja | ms-catalogo | `POST /productos`, `PUT /productos/{id}`, `DELETE /productos/{id}` |
| Catálogo → Categorías | alta, activar/desactivar | ms-catalogo | `POST /categorias`, `PATCH /categorias/{id}` |
| Catálogo → Zonas | alta y edición | ms-geolocalizacion | `POST /zonas`, `PATCH /zonas/{id}` |
| Comercios | registro, edición, baja | ms-comercios | `POST /comercios`, `PUT /comercios/{id}`, `DELETE /comercios/{id}` |
| Comercios (coordinador) | validar, suspender, rechazar | ms-comercios | `PATCH /comercios/{id}/validacion` |
| Comercio → Archivos | subir, ver, borrar; foto principal | ms-documentos, ms-comercios | `POST /documentos`, `PUT /comercios/{id}/foto` |
| Inventario → Agregar productos | renglón con existencia inicial | ms-inventario | `POST /comercios/{id}/inventario` (el precio lo fija ms-inventario con ms-precios) |
| Inventario → Movimiento | entrada, salida, ajuste | ms-inventario | `POST /inventario/{id}/movimientos` |
| Inventario → Editar | stock mínimo y máximo | ms-inventario | `PATCH /inventario/{id}` |
| Inventario → Editar | precio de venta (historial, atípicos) | ms-precios | `PUT /inventario/{id}/precio` |
| Inventario → Quitar | baja lógica del renglón | ms-inventario | `DELETE /inventario/{id}` |
| Inventario → Importar CSV | carga masiva | ms-inventario | `POST /comercios/{id}/importaciones` |
| Precios pendientes | validar o rechazar un precio atípico | ms-precios | `PATCH /precios/{id}/validacion` |
| Pedidos | abrir borrador, agregar y quitar partidas | ms-pedidos | `POST /pedidos`, `POST /pedidos/{id}/partidas`, `DELETE /pedidos/{id}/partidas/{p}` |
| Pedidos | enviar, aceptar, preparar, despachar, recibir, cancelar, rechazar | ms-pedidos (→ ms-proveedores y ms-inventario) | `POST /pedidos/{id}/acciones/{accion}` |
| Mi empresa (proveedor) | registro y datos de la empresa | ms-proveedores | `POST /proveedores`, `PATCH /proveedores/{id}` |
| Mi empresa (proveedor) | zonas de entrega | ms-proveedores | `PUT /proveedores/{id}/zonas` |
| Mi catálogo (proveedor) | publicar, cambiar, retirar | ms-proveedores | `POST /mi-catalogo`, `PATCH /mi-catalogo/{id}`, `DELETE /mi-catalogo/{id}` |
| Mi equipo (proveedor) | alta y baja de operadores | ms-seguridad | `POST /operadores`, `PATCH /operadores/{id}` |
| Notificaciones | marcar leída, marcar todas, eliminar | ms-notificaciones | `PATCH /notificaciones/{id}`, `POST /notificaciones/marcar-todas`, `DELETE /notificaciones/{id}` |
| Reportes → Exportar CSV | registrar la exportación en la bitácora | ms-auditoria | `POST /eventos` |
| Admin → Sesiones | listar y revocar | ms-seguridad | `GET /sesiones`, `DELETE /sesiones/{jti}` |
| Admin → Servicios | salud, métricas, traza de una petición | ms-monitoreo, ms-auditoria | `GET /metricas`, `GET /trazas/{id}` |
| Análisis y panel | indicadores, brechas, recomendaciones | ms-analisis, ms-recomendaciones | `GET /analisis/...` |

## Qué pasa si un servicio está caído

- **Consultas** (análisis, notificaciones, contador de avisos). El web calcula o lee el dato
  directamente con la biblioteca de dominio. Para eso le basta su permiso de solo lectura. Tras una
  falla, el cortacircuitos (`ms:caido:{servicio}` en Redis, 30 s) evita esperar el tiempo de espera de
  la conexión en cada página.
- **Escrituras.** No hay respaldo. El usuario ve «el servicio de … no está disponible; el cambio no se
  guardó» y puede intentarlo de nuevo. Escribir por fuera del dueño se saltaría sus reglas y su
  auditoría.

## Cómo se comprueba

| Prueba | Qué demuestra |
| :--- | :--- |
| `test_web_por_apis.py` | Recorre el web con formularios reales (CSRF, por el gateway): registro, comercio, inventario, precio, pedido completo entre tres usuarios, operadores del proveedor y un parámetro. En ms-auditoria comprueba que cada cambio lo registró el servicio dueño y no el web. |
| `test_propiedad_datos.py` | Pregunta a PostgreSQL quién puede escribir cada tabla, que el web sea de solo lectura, que la auditoría sea de solo inserción, que un servicio no pueda escribir en una tabla ajena y que los servicios estén conectados con su propio usuario. |
