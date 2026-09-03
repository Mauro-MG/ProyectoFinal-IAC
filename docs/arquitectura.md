# Diseño y Arquitectura de Software

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal

### 1. Diagramas C4

#### Nivel 1: Diagrama de Contexto
```mermaid
C4Context
    title Diagrama de Contexto de Sistema: AbastoRed
    
    Person(formal, "Minorista Formal", "Tienda de abarrotes, minisúper")
    Person(informal, "Comerciante Informal", "Tianguis, puesto semifijo")
    Person(mayorista, "Proveedor/Mayorista", "Vende al por mayor y distribuye")
    Person(analista, "Gobierno/Analista", "Monitorea precios y acceso alimentario")
    
    System(abastored, "Plataforma AbastoRed", "Plataforma que conecta a actores del abasto formal e informal, unificando precios, logística e indicadores geoespaciales.")
    System_Ext(maps, "Google Maps API", "Provee mapas y geocodificación")
    System_Ext(sat, "Servicios del SAT", "Facturación para sector formal (Opcional)")

    Rel(formal, abastored, "Consulta mayoristas, gestiona inventario", "HTTPS/Mobile")
    Rel(informal, abastored, "Reporta precios, ubica tianguis", "HTTPS/Mobile/Offline")
    Rel(mayorista, abastored, "Gestiona catálogo y entregas", "HTTPS/Web")
    Rel(analista, abastored, "Analiza dispersión y cobertura", "HTTPS/Web/Desktop")
    
    Rel(abastored, maps, "Calcula distancias y renderiza mapas", "REST API")
    Rel(abastored, sat, "Emite/Valida facturas CFDI", "SOAP/REST")
```

#### Nivel 2: Diagrama de Contenedores
```mermaid
C4Container
    title Diagrama de Contenedores
    
    Person(comerciante, "Comerciante", "Formal / Informal")
    Person(gobierno, "Analista / Admin")
    
    Container(app_movil, "App Móvil", "Kotlin, Android", "Permite captura offline, check-in GPS y pedidos.")
    Container(app_web, "Aplicación Web", "Flask / Jinja2 / JS", "Dashboard de análisis, catálogos mayoristas.")
    Container(app_desktop, "App Escritorio", "PySide / Electron", "Auditoría avanzada, exportación de logs masivos.")
    
    Container(api_gateway, "API Gateway / Nginx", "Nginx", "Enrutamiento, balanceo de carga, validación JWT.")
    
    Container(ms_operativos, "MS Operativos", "Flask, Python", "Manejo de Comercios, Productos, Precios, Inventario, Pedidos.")
    Container(ms_analitica, "MS de Analítica Espacial", "Flask, Python (GeoPandas)", "Geográfico, Cobertura, Recomendaciones, Acceso.")
    
    ContainerDb(db_sql, "PostgreSQL + PostGIS", "PostgreSQL", "Transacciones financieras, usuarios, datos geoespaciales.")
    ContainerDb(db_nosql, "MongoDB", "MongoDB", "Catálogos de productos no estructurados, logs de auditoría.")
    ContainerDb(db_cache, "Redis", "Redis", "Caché de precios en tiempo real, sesiones JWT.")
    Container(storage, "GCS", "Google Cloud Storage", "Imágenes de productos, comprobantes.")

    Rel(comerciante, app_movil, "Usa")
    Rel(gobierno, app_web, "Usa")
    Rel(gobierno, app_desktop, "Usa")
    
    Rel(app_movil, api_gateway, "API requests", "JSON/HTTPS")
    Rel(app_web, api_gateway, "API requests", "JSON/HTTPS")
    Rel(app_desktop, api_gateway, "API requests", "JSON/HTTPS")
    
    Rel(api_gateway, ms_operativos, "Enruta")
    Rel(api_gateway, ms_analitica, "Enruta")
    
    Rel(ms_operativos, db_sql, "Lee/Escribe", "SQL")
    Rel(ms_operativos, db_nosql, "Lee/Escribe", "PyMongo")
    Rel(ms_operativos, db_cache, "Almacena/Recupera", "Redis Prot.")
    
    Rel(ms_analitica, db_sql, "Consultas espaciales", "PostGIS")
```

### 2. Diagramas de Secuencia

#### Flujo: Registro de Precios Offline a Online
```mermaid
sequenceDiagram
    participant App as App Móvil (Local)
    participant LocalDB as SQLite (Móvil)
    participant API as API Gateway
    participant MS_Precios as MS de Precios
    participant Redis as Caché
    participant Postgre as Base de Datos

    App->>LocalDB: Guarda precio ingresado offline
    note over App,LocalDB: Pasa el tiempo, sin conexión
    App->>App: Detecta conexión a Internet
    App->>API: POST /api/precios/sync (Bulk JSON)
    API->>MS_Precios: Valida JWT y enruta
    MS_Precios->>MS_Precios: Aplica Regla de Negocio (RN-001 y RN-005)
    MS_Precios->>Postgre: Inserta registros válidos
    MS_Precios->>Redis: Invalida/Actualiza caché zonal de precios
    MS_Precios-->>API: 200 OK (Aceptados y Rechazados)
    API-->>App: Confirma Sincronización
    App->>LocalDB: Marca registros como "Sincronizados"
```

### 3. Justificación Tecnológica

*   **Aplicación Web (Flask/Jinja2)**: Permite renderizado rápido del lado del servidor (SSR) en paneles de administración para gobierno, evitando la sobrecarga de SPAs complejas donde el SEO no es necesario.
*   **Microservicios (Flask REST)**: Python facilita la integración directa con librerías matemáticas y geoespaciales (Pandas, GeoPandas) necesarias para los MS Analíticos, además de tener un desarrollo ágil y bajo overhead usando contenedores.
*   **Persistencia Políglota**:
    *   *PostgreSQL (+ PostGIS)*: Esencial por sus capacidades ACID robustas para el manejo de "Pedidos" e "Inventarios", y PostGIS es el estándar de la industria para cálculos geoespaciales (intersección de polígonos de tianguis, buffers).
    *   *MongoDB*: Ideal para "Catálogos de Productos" debido a que los atributos de los productos varían enormemente (tallas, pesos, marcas, caducidades) y para "Logs de Auditoría" por su alta velocidad de escritura desestructurada.
    *   *Redis*: Utilizado para mantener el estado de los tokens JWT, carritos de compra temporales, y cachear los precios promedio diarios, reduciendo masivamente la carga de la base de datos principal.
*   **Infraestructura (Docker + GCE)**: El uso de contenedores asegura que el ambiente de desarrollo sea idéntico al de producción. Google Compute Engine provee un balance adecuado entre control (IaaS) y costo, comparado con clústeres manejados como GKE que podrían ser muy costosos para un proyecto de este volumen inicial.

### 4. Diagrama de Componentes del Sistema Web

```mermaid
flowchart LR
    UI[Jinja2 Templates + CSS responsive]
    Auth[Blueprint Auth]
    Dashboard[Blueprint Dashboard]
    Comercios[Blueprint Comercios]
    Productos[Blueprint Productos]
    Precios[Blueprint Precios]
    Auditoria[Blueprint Auditoría]
    API[Blueprint API JWT]
    Models[Modelos SQLAlchemy]
    AuditUtil[Utilidad registrar_evento]

    UI --> Auth
    UI --> Dashboard
    UI --> Comercios
    UI --> Productos
    UI --> Precios
    UI --> Auditoria
    API --> Models
    Auth --> Models
    Comercios --> Models
    Productos --> Models
    Precios --> Models
    Auth --> AuditUtil
    Comercios --> AuditUtil
    Productos --> AuditUtil
    Precios --> AuditUtil
    AuditUtil --> Models
```

### 5. Diagrama de Despliegue

```mermaid
flowchart TB
    Dev[Equipo de desarrollo] --> Compose[Docker Compose local]
    Compose --> Web[Contenedor abastored-web: Flask/Gunicorn]
    Compose --> PG[Contenedor PostgreSQL + PostGIS]
    Compose --> Mongo[Contenedor MongoDB]
    Compose --> Redis[Contenedor Redis]

    Web --> PG
    Web --> Mongo
    Web --> Redis

    subgraph Produccion_GCE[Producción propuesta en Google Compute Engine]
        LB[Balanceador HTTPS]
        VM1[VM GCE zona A: Web/API]
        VM2[VM GCE zona B: Web/API]
        CloudSQL[Cloud SQL PostgreSQL + PostGIS]
        Memorystore[Memorystore Redis]
        Atlas[MongoDB administrado o VM MongoDB]
        GCS[Bucket GCS]
        LB --> VM1
        LB --> VM2
        VM1 --> CloudSQL
        VM2 --> CloudSQL
        VM1 --> Memorystore
        VM2 --> Memorystore
        VM1 --> Atlas
        VM2 --> Atlas
        VM1 --> GCS
        VM2 --> GCS
    end
```

### 6. Diagrama de Red

```mermaid
flowchart LR
    Internet((Internet)) --> HTTPS[HTTPS 443]
    HTTPS --> Nginx[API Gateway / Nginx]
    Nginx --> WebSubnet[Subred privada web]
    WebSubnet --> DataSubnet[Subred privada de datos]
    DataSubnet --> PostgreSQL[(PostgreSQL/PostGIS 5432)]
    DataSubnet --> MongoDB[(MongoDB 27017)]
    DataSubnet --> Redis[(Redis 6379)]
    WebSubnet --> GCS[(Bucket de archivos)]
```

Reglas de red propuestas:
*   Solo el gateway público acepta tráfico externo.
*   PostgreSQL, MongoDB y Redis no se exponen a Internet.
*   El acceso administrativo se realiza por VPN o túnel seguro.
*   Las contraseñas y llaves JWT se inyectan por variables de entorno o gestor de secretos.

### 7. Diagrama de Comunicación Entre Aplicaciones

```mermaid
flowchart LR
    Mobile[App móvil comerciantes] -->|REST JSON + JWT| Gateway[API Gateway]
    Web[Web administradores/analistas] -->|HTTPS + sesión + JWT API| Gateway
    Desktop[Desktop auditoría] -->|REST JSON + JWT| Gateway
    Gateway --> Operativos[Servicios operativos]
    Gateway --> Analitica[Servicios analíticos]
    Operativos --> PostgreSQL[(PostgreSQL)]
    Operativos --> MongoDB[(MongoDB)]
    Operativos --> Redis[(Redis)]
    Analitica --> PostgreSQL
    Analitica --> MongoDB
```

### 8. Diagrama de Autenticación

```mermaid
sequenceDiagram
    participant U as Usuario
    participant Web as Web/API Flask
    participant PG as PostgreSQL
    participant Redis as Redis

    U->>Web: Envía email y contraseña
    Web->>PG: Busca usuario activo y hash
    PG-->>Web: Usuario, rol y password_hash
    Web->>Web: Verifica bcrypt
    Web->>Web: Genera JWT firmado
    Web->>PG: Registra evento LOGIN
    Web-->>U: Sesión web o access_token
    U->>Web: Solicitud con Authorization Bearer
    Web->>Redis: Consulta blacklist jwt:blacklist:{hash}
    Web->>Web: Valida firma y expiración
    Web-->>U: Recurso o HTTP 401
```

### 9. Diagrama de Almacenamiento de Datos

```mermaid
flowchart TB
    Usuarios[Usuarios, roles, permisos] --> PostgreSQL
    Comercios[Comercios, zonas, geometrías] --> PostgreSQL
    Pedidos[Pedidos y detalle] --> PostgreSQL
    Precios[Precios transaccionales] --> PostgreSQL
    Snapshots[Snapshots, telemetría, lotes de sincronización] --> MongoDB
    Logs[Errores y notificaciones] --> MongoDB
    Cache[Promedios por zona/producto] --> Redis
    Blacklist[Tokens JWT revocados] --> Redis
    Archivos[Imágenes y comprobantes] --> GCS
```

### 10. Distribución de Responsabilidades

*   **Sistema web:** autenticación, panel por perfil, catálogos, comparación de precios, auditoría básica y administración operativa.
*   **Microservicios:** precios masivos, alertas, recomendaciones, acceso alimentario, sincronización offline y procesos de alta carga.
*   **PostgreSQL:** usuarios, roles, comercios, productos maestros, precios, pedidos, auditoría transaccional y geometrías PostGIS.
*   **MongoDB:** lotes de sincronización, snapshots analíticos, telemetría geográfica, errores y notificaciones flexibles.
*   **Redis:** blacklist de JWT, caché de promedios, contadores de rate limit, bloqueos temporales y datos efímeros.
*   **Buckets:** imágenes de productos/comercios, comprobantes y exportaciones.
*   **Contenedores:** web, PostgreSQL/PostGIS, MongoDB, Redis y futuros microservicios.
*   **Compute Engine:** ejecución inicial de contenedores web/API; el clúster queda reservado para analítica geoespacial o sincronizaciones masivas cuando el volumen lo justifique.
