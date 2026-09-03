# Diseño de Base de Datos y Almacenamiento

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal

### 1. Modelo Conceptual (PostgreSQL - Entidades Relacionales)

```mermaid
erDiagram
    USUARIO ||--o{ COMERCIO : administra
    COMERCIO ||--o{ PRECIO : reporta
    COMERCIO ||--o{ PEDIDO : realiza
    MAYORISTA ||--o{ PEDIDO : recibe
    MAYORISTA {
        int id PK
        string razon_social
    }
    USUARIO {
        int id PK
        string nombre
        string email
        string rol_id FK
    }
    COMERCIO {
        int id PK
        string nombre
        string tipo "Formal/Informal"
        geometry ubicacion "Punto GPS"
        int zona_id FK
    }
    ZONA {
        int id PK
        string nombre
        geometry poligono "GeoJSON/PostGIS"
    }
    PRECIO {
        int id PK
        int comercio_id FK
        string producto_ref "Ref a MongoDB"
        float valor
        datetime fecha_reporte
    }
    PEDIDO {
        int id PK
        int comercio_id FK
        int mayorista_id FK
        float total
        string estado
    }
    ZONA ||--o{ COMERCIO : contiene
```

### 2. Diseño de PostgreSQL (Modelo Lógico Espacial y Transaccional)

El motor principal será PostgreSQL utilizando la extensión **PostGIS**.
*   `comercios` (id [PK], usuario_id [FK], nombre, tipo_comercio, latitud, longitud, geom [Geometry(Point, 4326)], creado_en). El campo `geom` se indexará usando GIST para búsquedas rápidas por radio.
*   `zonas_tianguis` (id [PK], nombre, municipio, poligono [Geometry(Polygon, 4326)], dias_operacion).
*   `pedidos` (id [PK], comercio_comprador_id, mayorista_vendedor_id, estado, total, fecha_creacion, fecha_entrega).
*   `pedidos_detalle` (id [PK], pedido_id [FK], producto_mongo_id [String], cantidad, precio_unitario).

### 3. Diseño en MongoDB (Documentos y Catálogos Flexibles)

Se utiliza MongoDB por el patrón *Polymorphic Pattern* y *Attribute Pattern*, dado que los productos tienen diferentes características.

**Colección: `catalogo_productos`**
Se usa un enfoque mixto: embeber atributos específicos, referenciar categorías.
```json
{
  "_id": ObjectId("5f8c..."),
  "sku": "LIMON-PER-01",
  "nombre": "Limón Persa 1Kg",
  "categoria_principal": "Frutas y Verduras",
  "unidad_medida": "Kg",
  "atributos": [
    {"k": "origen", "v": "Veracruz"},
    {"k": "calibre", "v": "Mediano"}
  ],
  "imagenes": ["url_gcs_1.jpg"],
  "estado": "activo"
}
```
*Índices en Mongo*: Índice de texto (Text Index) sobre `nombre` y `categoria` para el motor de búsqueda del catálogo.

**Colección: `audit_logs`**
```json
{
  "_id": ObjectId("..."),
  "timestamp": ISODate("2026-09-03T10:00:00Z"),
  "actor_id": 1054,
  "accion": "ACTUALIZAR_PRECIO",
  "entidad_afectada": "PRECIO_ID_884",
  "datos_anteriores": {"valor": 25.50},
  "datos_nuevos": {"valor": 45.00},
  "ip_address": "192.168.1.1",
  "flag_anomalia": true
}
```

### 4. Diseño de Caché en Redis

Se utiliza Redis para mejorar el rendimiento, evitar recalcular promedios en cada petición y manejar sesiones de forma *stateless*.

1.  **Caché de Precios Promedio (String / Hash)**:
    *   `Key`: `precio_promedio:zona:{id_zona}:producto:{sku}`
    *   `Value`: `35.50`
    *   `TTL`: 4 horas. (Se invalida cuando un MS detecta un cambio drástico o expira para recalcularse mediante un Job en background).
2.  **Tokens Revocados o Sesiones JWT (Set)**:
    *   `Key`: `jwt:blacklist:{token_hash}`
    *   `TTL`: Mismo tiempo restante de vida del token (ej. 7 días). Evita accesos con tokens válidos temporalmente pero robados.
3.  **Límite de Tasa (Rate Limiting)**:
    *   `Key`: `rate_limit:ip:{ip_address}:ruta:{endpoint}`
    *   `Value`: Contador entero (INCR). TTL: 60 segundos.

### 5. Modelo Físico Inicial Implementado

El modelo físico inicial está definido en `db/postgres/01_schema.sql` y se carga automáticamente al iniciar PostgreSQL desde Docker Compose.

Tablas principales implementadas:
*   `roles`: catálogo de perfiles y permisos en JSONB.
*   `usuarios`: cuentas, credenciales cifradas con bcrypt y rol asignado.
*   `zonas_municipales`: zonas con centro geográfico, radio y polígono PostGIS.
*   `comercios`: comercios formales, informales y mayoristas con punto geográfico PostGIS.
*   `categorias`: catálogo de categorías.
*   `productos_maestros`: catálogo maestro de productos.
*   `precios_comercio`: historial de precios por comercio/producto, estado de validación y método de captura.
*   `proveedores`: datos básicos del mayorista.
*   `pedidos_abasto` y `detalle_pedidos`: pedido y partidas.
*   `auditoria_eventos`: bitácora append-only.
*   `configuracion_sistema`: parámetros globales.

Restricciones e índices relevantes:
*   Llaves primarias en todas las tablas.
*   Llaves foráneas entre usuarios, roles, comercios, precios, productos, pedidos y proveedores.
*   Checks para precios/cantidades positivas y estado de validación.
*   Índices por comercio/producto/fecha en precios.
*   Índices GIST para `comercios.geom` y `zonas_municipales.poligono`.
*   Triggers `updated_at` para entidades modificables.
*   Triggers que bloquean `UPDATE` y `DELETE` en `auditoria_eventos`.

### 6. MongoDB Implementado

El script `db/mongo/init.js` crea colecciones iniciales alineadas al crecimiento futuro:

*   `catalogo_productos`: catálogo flexible con atributos variables por tipo de producto.
*   `audit_logs`: bitácora documental para eventos masivos o provenientes de microservicios.
*   `sync_batches`: lotes de sincronización móvil/offline.
*   `price_snapshots`: snapshots agregados de precios por producto y zona.
*   `geo_telemetry`: telemetría geográfica con índice `2dsphere`.
*   `error_logs`: errores técnicos por servicio.
*   `notifications`: notificaciones pendientes o leídas por usuario.

Estrategia de versionamiento:
*   Los documentos analíticos deberán incluir `schema_version`.
*   Las migraciones se aplicarán por scripts incrementales en `db/mongo/migrations`.
*   Los snapshots se almacenarán como documentos append-only para conservar histórico.

Estrategia de crecimiento:
*   Índices compuestos en consultas frecuentes.
*   TTL indexes futuros para telemetría temporal.
*   Separación por colecciones cuando los documentos crezcan de forma distinta.

### 7. Redis Implementado y Propuesto

Claves iniciales:
*   `precio_promedio:zona:{id_zona}:producto:{id_producto}`: promedio consultado o actualizado por el flujo de precios. TTL: 4 horas.
*   `jwt:blacklist:{token_hash}`: tokens revocados al cerrar sesión. TTL: tiempo restante del JWT.

Claves planeadas:
*   `rate_limit:ip:{ip}:ruta:{endpoint}` para limitar abuso.
*   `lock:sync_batch:{batch_id}` para evitar doble sincronización.
*   `contador:alertas:zona:{id_zona}` para métricas rápidas.

### 8. Auditoría y Privacidad

Auditoría:
*   Todo login, logout, alta, edición y baja lógica relevante debe crear un registro en `auditoria_eventos`.
*   La tabla es append-only por trigger, por lo que ningún rol puede modificar o eliminar eventos.

Privacidad:
*   Las contraseñas se almacenan con hash bcrypt.
*   Los JWT se firman con `JWT_SECRET_KEY` y se revocan mediante hash del token en Redis.
*   Los datos personales sensibles deberán minimizarse en reportes analíticos y exportaciones.
*   Para producción se recomienda cifrado administrado del disco/base de datos y, si se captura RFC/identificación personal de comerciantes informales, cifrado de campo con AES-256 antes de persistir.
