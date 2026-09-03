# Especificación de Requerimientos

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal (AbastoRed - EQUIPO 01)

### Requerimientos Funcionales

#### Módulo Web (Portales Administrativos y Analíticos)
| ID | Descripción | Prioridad | Criterios de Aceptación |
| :--- | :--- | :--- | :--- |
| **RF-001** | El sistema debe permitir al Administrador gestionar (CRUD) el catálogo maestro de productos genéricos. | Alta | El catálogo se guarda y se refleja inmediatamente en los microservicios, permitiendo categorías y subcategorías. |
| **RF-002** | El sistema debe mostrar al Analista dashboards comparativos de precios (Formal vs Informal). | Alta | Visualización mediante gráficos de líneas y dispersión; filtros por categoría, fecha y zona geográfica. |
| **RF-003** | El sistema debe permitir al Coordinador Municipal trazar polígonos geográficos en un mapa para delimitar zonas de tianguis. | Media | Uso de mapa interactivo; guardado de coordenadas en formato GeoJSON en la BD. |

#### Microservicios (Backend)
| ID | Descripción | Prioridad | Criterios de Aceptación |
| :--- | :--- | :--- | :--- |
| **RF-004** | El sistema deberá validar los precios registrados comparándolos con el promedio regional de los últimos 7 días. Posteriormente, el MS de Alertas procesará los registros atípicos. | Alta | Si el precio supera el 150% o es menor al 10% del promedio regional, deberá guardarse con el estado. |
| **RF-005** | El MS de Recomendaciones debe sugerir a los comerciantes un surtido basado en faltantes (brechas) de su zona. | Media | Retorna lista de hasta 5 productos con mayor demanda no satisfecha en un radio de 2km. |
| **RF-006** | El MS de Acceso Alimentario debe calcular un índice basado en densidad poblacional vs densidad de comercios de productos frescos. | Baja | Retorna un valor numérico de 0 a 100 clasificado por color en el mapa. |

#### Aplicación Móvil (Comerciantes)
| ID | Descripción | Prioridad | Criterios de Aceptación |
| :--- | :--- | :--- | :--- |
| **RF-007** | La app debe permitir al Comerciante Informal registrar/actualizar precios de su catálogo simplificado de forma offline y sincronizar cuando haya red. | Alta | Los datos se guardan en SQLite local; al detectar red, se envían al backend con timestamp original. |
| **RF-008** | La app debe permitir al Minorista Formal generar una orden de pedido ("carrito") dirigida a un Mayorista específico. | Alta | La orden calcula totales, impuestos y costo de envío; notifica al mayorista. |
| **RF-009** | La app debe consumir pocos recursos y datos (modo "low-data"). | Alta | Carga de imágenes opcional; payload de API comprimido (GZIP/Protobuf). |

#### Aplicación Desktop (Auditoría y Soporte)
| ID | Descripción | Prioridad | Criterios de Aceptación |
| :--- | :--- | :--- | :--- |
| **RF-010** | La app Desktop debe permitir al Auditor buscar transacciones y cambios de precios en los últimos 5 años mediante logs. | Media | Búsqueda por rango de fechas, usuario o ID de entidad, exportable a PDF/Excel. |

### Requerimientos No Funcionales

#### Base de Datos e Infraestructura
| ID | Descripción | Prioridad | Criterios de Aceptación |
| :--- | :--- | :--- | :--- |
| **RNF-001** | **Persistencia Políglota**: Los datos transaccionales estrictos (pedidos, usuarios) deben residir en PostgreSQL, catálogos flexibles en MongoDB, y cachés en Redis. | Alta | Verificable en la arquitectura y despliegue; consultas SQL y NoSQL según el dominio. |
| **RNF-002** | **Escalabilidad**: Los microservicios deben desplegarse como contenedores Docker en Google Compute Engine (GCE) o GKE. | Alta | Uso de Dockerfiles y manifiestos de despliegue válidos. |
| **RNF-003** | **Disponibilidad**: El sistema base debe tener un uptime del 99.5%. | Media | Despliegue en al menos dos zonas de disponibilidad dentro de GCE. |

#### Seguridad y Rendimiento
| ID | Descripción | Prioridad | Criterios de Aceptación |
| :--- | :--- | :--- | :--- |
| **RNF-004** | **Autenticación**: Todo acceso a los MS (excepto endpoints públicos) debe requerir un token JWT válido. | Alta | Endpoints retornan HTTP 401 si el token expira o es inválido. |
| **RNF-005** | **Latencia Geográfica**: Las consultas de análisis espacial no deben tardar más de 3 segundos en responder. | Alta | Uso de índices espaciales (PostGIS o GeoJSON en MongoDB) optimizados. |
| **RNF-006** | **Privacidad**: Los datos personales de comerciantes informales deben estar cifrados en reposo en la BD (AES-256). | Alta | Nombres y RFCs no son legibles directamente desde el motor de BD sin la llave. |

#### Monitoreo

| ID | Descripción | Prioridad | Criterios de Aceptación |
| :--- | :--- | :--- | :--- |
| **RNF-007** | **Monitoreo de disponibilidad:** la aplicación web y los futuros microservicios deberán exponer un endpoint de salud. | Alta | Cada componente responde mediante `/health` e informa su nombre y estado actual. |
| **RNF-008** | **Registro centralizado:** los errores y eventos técnicos deberán registrarse indicando fecha, nivel, servicio y un identificador de correlación. | Media | Los eventos de una misma solicitud pueden localizarse utilizando el campo `correlation_id`. |
| **RNF-009** | **Métricas operativas:** el sistema deberá medir latencia, cantidad de solicitudes y tasa de errores por componente. | Media | El futuro tablero de monitoreo muestra latencia, solicitudes por minuto y errores HTTP 5xx. |
