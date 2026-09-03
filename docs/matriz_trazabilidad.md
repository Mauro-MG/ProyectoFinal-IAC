# Matriz de Trazabilidad de Requerimientos

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal

La matriz relaciona los requerimientos con las historias de usuario, reglas de negocio, componentes y casos de prueba. Los elementos identificados como **futuros** forman parte del diseño arquitectónico, pero no requieren implementación durante el primer parcial.

| ID del requerimiento | Descripción resumida | Historia de usuario | Regla asociada | Componentes | Casos de prueba |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RF-001** | Gestión del catálogo maestro de productos. | HU-009 | — | Web, PostgreSQL y futuro MS de Productos/MongoDB | CP-CAT-01 |
| **RF-002** | Comparación y análisis de precios. | HU-007 | — | Web, PostgreSQL y futuro MS de Comparación | CP-DASH-01, CP-DASH-02 (futuro) |
| **RF-003** | Trazado de polígonos para zonas de tianguis. | HU-006 | RN-002 | Web, futuro MS Geográfico y PostGIS | CP-GEO-01 (futuro) |
| **RF-004** | Validación y futura alerta de precios atípicos. | HU-008 | RN-001 | Web, PostgreSQL, Redis y futuros MS de Precios y Alertas | CP-PREC-02, CP-ALT-01 (futuro) |
| **RF-005** | Recomendaciones de surtido por zona. | HU-010 | RN-003 | Futuro MS de Recomendaciones, PostgreSQL y MongoDB | CP-REC-01 (futuro) |
| **RF-006** | Cálculo del Índice de Acceso Alimentario. | HU-005 | RN-008 | Futuro MS de Acceso Alimentario y PostGIS | CP-IDX-01 (futuro) |
| **RF-007** | Captura móvil de precios sin conexión. | HU-001 | RN-005 | Futura App Móvil, SQLite y MS de Precios | CP-MOB-01, CP-MOB-02 (futuros) |
| **RF-008** | Creación de pedidos dirigidos a mayoristas. | HU-003 | RN-004 | Futura App Móvil, MS de Pedidos y PostgreSQL | CP-PED-01, CP-PED-02 (futuros) |
| **RF-009** | Modo móvil con bajo consumo de datos. | HU-001 | RN-005 | Futura App Móvil y API Gateway | CP-MOB-03 (futuro) |
| **RF-010** | Consulta histórica de auditoría. | HU-011 | RN-006 | Web, PostgreSQL, futura App Desktop y MongoDB | CP-AUD-01, CP-AUD-02 (futuro) |
| **RNF-001** | Persistencia políglota. | Todas | — | PostgreSQL, MongoDB y Redis | CP-INF-01 y revisión arquitectónica |
| **RNF-002** | Escalabilidad mediante contenedores. | Todas | — | Docker, Compute Engine y futuro GKE | CP-INF-01, CP-INF-02 (futuro) |
| **RNF-003** | Disponibilidad objetivo del 99.5%. | Todas | — | Balanceador, Compute Engine y monitoreo | CP-INF-02 (futuro) |
| **RNF-004** | Autenticación mediante JWT. | Todas | RN-007 | Web, API, Redis y futuro API Gateway | CP-JWT-01, CP-JWT-02, CP-SEC-01 y CP-SEC-02 (futuros) |
| **RNF-005** | Latencia de consultas espaciales menor o igual a 3 segundos. | HU-005, HU-006 | — | Futuro MS de Analítica y PostGIS | CP-PERF-01 (futuro) |
| **RNF-006** | Privacidad y cifrado de información personal. | Todas | — | Web, bases de datos y futuros servicios | CP-SEC-03 (futuro) |
| **RNF-007** | Monitoreo de disponibilidad. | Todas | — | Web, futuros microservicios y plataforma de monitoreo | CP-INF-01, CP-MON-01 (futuro) |
| **RNF-008** | Registro técnico centralizado. | Todas | RN-006 | Futuros servicios, MongoDB o Cloud Logging | CP-MON-02 (futuro) |
| **RNF-009** | Métricas operativas. | Todas | — | Web, futuros servicios y tablero de monitoreo | CP-MON-03 (futuro) |

## Estados de implementación

| Clasificación | Significado |
| :--- | :--- |
| **Actual** | Se encuentra implementado en el producto mínimo funcional del primer parcial. |
| **Futuro** | Se encuentra analizado y diseñado, pero será implementado en parciales posteriores. |
| **Mixto** | Cuenta con una implementación inicial que será ampliada posteriormente. |

Los elementos futuros permanecen en la matriz porque permiten demostrar la trazabilidad de la arquitectura completa, aunque su implementación no sea obligatoria durante el primer parcial.
