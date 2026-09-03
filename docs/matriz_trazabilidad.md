# Matriz de Trazabilidad de Requerimientos

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal

| ID Req. | Descripción (Resumen) | Historia de Usuario | Regla de Negocio Asociada | Componentes Afectados | Casos de Prueba (ID Propuesto) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RF-001** | Gestión del catálogo maestro. | HU-002 | - | Web Admin, MS Productos, PostgreSQL/MongoDB | CP-CAT-01, CP-CAT-02 |
| **RF-002** | Dashboards de comparación. | HU-007 | - | Web Admin, MS Comparación, PostgreSQL | CP-DASH-01, CP-DASH-02 |
| **RF-003** | Trazado de polígonos de zonas. | HU-006 | RN-002 | Web Admin, MS Geográfico, PostGIS | CP-GEO-01 |
| **RF-004** | Alertas por variación de precio. | HU-008 | RN-001 | MS Precios, MS Alertas, Redis | CP-ALT-01, CP-ALT-02 |
| **RF-005** | Recomendaciones por brechas. | HU-005 | RN-003 | MS Recomendaciones | CP-REC-01 |
| **RF-006** | Cálculo de Índice de Acceso. | HU-005 | RN-008 | MS Acceso Alimentario, PostGIS | CP-IDX-01 |
| **RF-007** | Captura de precios offline. | HU-001 | RN-005 | App Móvil, SQLite local, MS Precios | CP-MOB-01 (Offline), CP-MOB-02 (Sync) |
| **RF-008** | Creación de Pedidos. | HU-003 | RN-004 | App Móvil, MS Pedidos, PostgreSQL | CP-PED-01, CP-PED-02 |
| **RF-009** | Modo móvil de bajo consumo de datos. | HU-001 | RN-005 | App Móvil, API Gateway | CP-MOB-03 |
| **RF-010** | Consulta de auditoría de 5 años. | - | RN-006 | App Desktop, Web Auditoría, PostgreSQL/MongoDB | CP-AUD-02 |
| **RNF-001** | Persistencia políglota. | Todas | - | PostgreSQL, MongoDB, Redis | Revisión Arquitectónica |
| **RNF-002** | Escalabilidad en contenedores sobre GCE/GKE. | Todas | - | Docker, GCE, futuros microservicios | CP-INF-01 |
| **RNF-003** | Disponibilidad objetivo 99.5%. | Todas | - | GCE multi-zona, balanceador | CP-INF-02 |
| **RNF-004** | Autenticación JWT. | Todas | RN-007 | API Gateway, MS Todos | CP-SEC-01 (Token Válido), CP-SEC-02 (Expirado) |
| **RNF-005** | Latencia espacial < 3s. | HU-005, HU-006 | - | MS Analítica, PostGIS | CP-PERF-01 (Prueba de Carga Jmeter) |
| **RNF-006** | Auditoría inmutable. | - | RN-006 | MS Reportes, App Desktop | CP-AUD-01 |
