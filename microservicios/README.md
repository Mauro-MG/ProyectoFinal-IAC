# Módulo de microservicios

**Estado:** diseñado, se implementa en el segundo parcial.

Cada servicio será una aplicación Flask independiente, con su propio `Dockerfile`, y se podrá
desplegar y actualizar por separado. No comparte vistas, plantillas ni sesiones con el sistema web;
sólo lee las bases de datos autorizadas y valida el JWT contra la lista de revocación en Redis.

## Servicios

| Servicio | Carpeta | Responsabilidad | Base de la lógica actual |
| :--- | :--- | :--- | :--- |
| Comercios | `comercios/` | Alta, consulta y validación de comercios | `web/app/rutas/comercios.py` |
| Productos | `productos/` | Catálogo maestro y catálogo por comercio | `web/app/rutas/catalogo.py` |
| Precios | `precios/` | Registro y validación de precios (RN-001) | `web/app/servicios/inventario.py` |
| Inventario | `inventario/` | Existencias y movimientos (RN-009) | `web/app/servicios/inventario.py` |
| Pedidos | `pedidos/` | Flujo de pedidos de abasto (RN-004, RN-010 a RN-014) | `web/app/servicios/pedidos.py` |
| Geográfico | `geografico/` | Zonas, asignación de zona por ubicación, buffers | `web/app/servicios/geo.py`, `db/postgres/02_geo.sql` |
| Cobertura | `cobertura/` | Cobertura e índice de acceso por zona | `web/app/servicios/analisis.py` |
| Comparación | `comparacion/` | Consumidor formal/informal vs. mayoreo | `web/app/servicios/precios.py` |
| Recomendaciones | `recomendaciones/` | Recomendación de surtido por reglas | `web/app/servicios/analisis.py` |
| Acceso alimentario | `acceso_alimentario/` | Índice de acceso y ranking de zonas | `web/app/servicios/analisis.py` |
| Alertas | `alertas/` | Precios atípicos, stock bajo, pedidos sin respuesta | nuevo |
| Reportes | `reportes/` | Exportaciones JSON/XML para la app de escritorio | `web/app/rutas/reportes.py` |
| Monitoreo | `monitoreo/` | Consulta periódica de `/health/*` e historial de disponibilidad | nuevo |

La lógica de negocio del monolito ya está separada en `web/app/servicios/` (sin dependencias de
Flask ni de las vistas) precisamente para moverla a estos servicios sin reescribirla.

## Estructura que tendrá cada servicio

```
<servicio>/
├── Dockerfile
├── requirements.txt
├── app.py              # rutas /api/v1/..., respuesta JSON o XML según Accept
├── esquemas/           # validación de entrada y esquemas XSD de salida
├── openapi.yaml        # documentación Swagger
└── tests/
```

## Requisitos comunes

- Versionamiento en la ruta: `/api/v1/...`
- Respuesta JSON (app móvil) o XML (app de escritorio) según el encabezado `Accept`.
- JWT obligatorio en rutas protegidas; consulta a Redis para tokens revocados.
- Límite de consumo por usuario/IP con contadores en Redis (`rate_limit:*`).
- Identificador de correlación `X-Correlation-ID` en cada petición y en los logs.
- Endpoints de salud: `/health/live`, `/health/ready`, `/health/database`, `/health/redis`,
  `/health/mongodb`, `/health/storage`.
- Pruebas de carga con Locust por perfil (comerciante, proveedor, analista).
