Plan de Implementación - Primer Parcial
Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal (EQUIPO 01)
Construir y documentar la base arquitectónica y el Producto Mínimo Funcional (MVP) de la plataforma híbrida que integra digitalmente a comerciantes informales (tianguis, puestos semifijos, vendedores ambulantes), minoristas formales (tiendas de abarrotes, recauderías, minisúpers), proveedores de abasto y coordinadores municipales.

Revisión y Decisiones Clave para el Usuario
IMPORTANT

Enfoque del MVP del Primer Parcial: El objetivo de esta entrega es entregar una base técnica 100% funcional y ejecutable en Docker, con datos reales en PostgreSQL, esquema documental definido para MongoDB, estrategia de memoria para Redis, autenticación JWT, control de acceso por roles (RBAC), dos catálogos CRUD operativos, un proceso transaccional central de negocio (Registro y comparación de precios / Pedido de abasto) y registro de auditoría, complementado con toda la documentación analítica y arquitectónica exigida por la rúbrica.

NOTE

Nombre sugerido de la plataforma: "AbastoRed" (Plataforma Híbrida de Abasto y Monitoreo de Precios Formal-Informal). El directorio de trabajo se ubicará en C:\Users\mauro\.gemini\antigravity\scratch\abasto_red.

1. Alcance y Entregables del Primer Parcial
El trabajo se organiza en 5 fases secuenciales de acuerdo con los criterios de evaluación:

Mermaid diagram
2. Plan Detallado por Fases
Fase 1: Análisis del Problema, Actores y Requerimientos
Contexto Real: Diagnóstico de la asimetría de información entre el comercio formal (supermercados, tiendas de conveniencia) y el comercio informal (tianguis, mercados sobre ruedas, recauderías locales). Se abordan las limitaciones de inventario, la volatilidad de precios en perecederos y la falta de canales directos de abasto con productores/mayoristas.
Matriz de Perfiles (RBAC):
Administrador General: Control total del sistema, configuración y auditoría.
Comerciante Informal: Acceso a catálogos simplificados, reporte de precios, consulta de abasto y alertas.
Minorista Formal: Gestión de inventario estructurado, publicación de precios y solicitud de pedidos.
Proveedor / Mayorista: Publicación de ofertas de mayoreo, gestión de entregas y recepción de pedidos.
Analista de Mercado: Acceso a tableros de comparación formal vs informal, detección de brechas y dispersión de precios.
Coordinador Municipal: Delimitación y validación de zonas de tianguis, puntos de venta y monitoreo del índice de acceso.
Auditor: Inspección de bitácoras de eventos, trazabilidad de transacciones y cambios de precios.
Requerimientos Formales:
Especificación de RF y RNF categorizados por los 8 componentes exigidos (Web, Microservicios, Móvil, Desktop, BD, Infraestructura, Seguridad, Monitoreo).
Historias de usuario con criterios de aceptación en formato Gherkin (Given-When-Then).
Reglas de negocio (ej. validación de bandas de precios, tolerancias geográficas para tianguis, reglas de surtido mínimo).
Fase 2: Diseño Arquitectónico y Diagramas
Diagrama de Contexto (C4 Nivel 1): Interacción de usuarios con el ecosistema AbastoRed.
Diagrama de Contenedores (C4 Nivel 2): Separación estricta entre Sistema Web (Flask), Módulo de Microservicios (REST Flask dual JSON/XML), Móvil (Android), Desktop, Bases de Datos y Almacenamiento.
Diagramas de Secuencia:
Flujo de Autenticación JWT con verificación de revocación en Redis.
Flujo de Registro de Precios y Detección de Dispersión Formal/Informal.
Flujo de Pedido de Abasto a Proveedor.
Justificación Tecnológica Integral:
Web vs Microservicios: Autonomía de gestión vs escalabilidad de endpoints de consumo móvil/desktop.
PostgreSQL: Integridad referencial ACID, transacciones de pedidos, usuarios, comercios y auditoría.
MongoDB: Registros de telemetría, lotes de sincronización offline de la app móvil y series de tiempo de variabilidad de precios.
Redis: Blacklist de tokens JWT, almacenamiento temporal de cotizaciones, rate limiting y caché geoespacial.
GCS: Fotografías de comercios, comprobantes de abasto y evidencias fotográficas de productos.
Fase 3: Diseño de Bases de Datos
PostgreSQL (Esquema Relacional abasto_relational):
usuarios y roles: Autenticación, contraseñas hasheadas (bcrypt) y RBAC.
comercios: Información de negocio, tipo (FORMAL, INFORMAL_TIANGUIS, INFORMAL_FIJO, MAYORISTA), coordenadas (lat, lon), zona municipal y estado de verificación.
categorias y productos_maestros: Catálogo estandarizado de la canasta básica (código, nombre, unidad de medida, imagen).
precios_comercio: Histórico transaccional de precios registrados por punto de venta con fecha de vigencia y tipo de captura.
pedidos_abasto y detalle_pedidos: Transacción de abasto con estados (BORRADOR, SOLICITADO, CONFIRMADO, ENTREGADO, CANCELADO).
auditoria_eventos: Trazabilidad obligatoria (usuario_id, ip, operacion, entidad, detalle_json, timestamp).
Scripts DDL con llaves primarias (UUID), foráneas, constraints (CHECK, UNIQUE) y datos semilla (Seeds con comercios reales y canasta básica).
MongoDB (Colecciones Semiestructuradas):
sync_batches: Recepción de lotes de sincronización offline de clientes móviles.
price_snapshots: Historial masivo no estructurado para análisis temporal.
geo_telemetry: Marcadores geográficos dinámicos y trazas de ubicación de tianguis móviles.
Redis:
jwt:blacklist:<jti> (TTL configurable).
session:<user_id> (Datos de sesión en memoria).
cache:prices:zone:<zone_id> (Caché de consultas de precios).
rate_limit:<ip_or_user> (Control de cuotas).
Fase 4: Infraestructura Inicial y Contenedores (Docker)
Configuración completa de docker-compose.yml orquestando:
Contenedor abastored-db-postgres (PostgreSQL 16 Alpine con inicialización automática de tablas y seeds).
Contenedor abastored-db-mongo (MongoDB 7.0 con credenciales y volumen persistente).
Contenedor abastored-cache-redis (Redis 7.2 Alpine con contraseña).
Contenedor abastored-web (Python 3.11 + Flask + Gunicorn / Desarrollo).
Archivos auxiliares: .env.example, .dockerignore, requirements.txt.
Fase 5: Producto Mínimo Funcional del Sistema Web (MVP Web)
Arquitectura de Software: Estructura modular en Flask (Blueprints: auth, public, comercios, productos, transacciones, auditoria).
Frontend:
Jinja2 + HTML5 semántico + CSS moderno responsivo (con paleta institucional limpia, adaptable a escritorio y móvil).
JavaScript modular para interacción dinámica sin dependencias pesadas innecesarias.
Módulos Operativos en el MVP:
Página Pública: Buscador de puntos de venta (comercios formales y tianguis) y consulta de disponibilidad de productos de la canasta básica.
Módulo de Autenticación: Registro de comercios/usuarios, Login con generación de JWT y sesión web segura, Logout con invalidación.
Control de Acceso (RBAC): Menú de navegación dinámico según perfil autenticado.
Catálogo 1 - Comercios: CRUD completo de comercios con tipificación (formal/informal), datos de contacto y ubicación.
Catálogo 2 - Catálogo Maestro de Productos: CRUD completo de productos básicos con unidades de medida, categorías y precios de referencia.
Proceso Principal del Negocio (Transaccional):
Registro y Actualización de Precios por Comercio: Validación contra umbrales mínimos/máximos, actualización en PostgreSQL y cálculo inmediato de la diferencia contra el promedio de la zona.
O creación de Pedido de Abasto: Generación de orden de compra entre comerciante y proveedor con cálculo de totales y reglas de validación.
Módulo de Auditoría: Visualizador en el portal privado para rol Administrador/Auditor de cada evento transaccional registrado.
3. Plan de Verificación y Pruebas
Pruebas Automatizadas
Pruebas unitarias y de integración con pytest:
Verificación de hashing seguro y validación de tokens JWT.
Pruebas de integración de base de datos contra PostgreSQL (CRUD de Comercios y Productos).
Prueba del proceso transaccional (Registro de precios / Generación de pedidos con rollback ante error).
Verificación de persistencia en la tabla de auditoría tras operaciones críticas.
Demostración Técnica (Checklist de Cumplimiento)
 Levantamiento con 1 comando: docker compose up --build levanta Web, PostgreSQL, MongoDB y Redis con healthcheck saludable.
 Acceso Público: Navegación sin login mostrando comercios y canasta básica.
 Acceso Privado y Roles: Login con credenciales de prueba (admin, comerciante_informal, minorista_formal, analista).
 Operación de Catálogos: Alta, consulta y edición de Comercios y Productos en PostgreSQL.
 Proceso Principal: Ejecución de una transacción de negocio en tiempo real.
 Auditoría Visible: Consulta en el panel del administrador del registro exacto de las operaciones realizadas.
