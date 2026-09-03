# Matriz de Perfiles y Permisos (RBAC)

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal (AbastoRed - EQUIPO 01)

| Perfil | Responsabilidades Principales | Operaciones CRUD y Módulos Accesibles | Restricciones y Nivel de Autorización | Componentes Utilizados |
| :--- | :--- | :--- | :--- | :--- |
| **Administrador General** | Control total de la plataforma, gestión de parámetros globales, auditoría general, configuración de seguridad. | **Usuarios**: CRUD. **Roles**: CRUD. **Parámetros**: CRUD. **Catálogo Maestro**: CRUD. **Auditoría**: L. | Nivel: 1 (Máximo). No puede modificar datos de transacciones u órdenes (solo consulta). | Web, Desktop |
| **Comerciante Informal** | Reportar precios de productos clave, registrar asistencia a zonas/tianguis, consultar precios mayoristas, recibir alertas. | **Mis Precios**: CRU. **Ubicación (Check-in)**: C. **Catálogo Mayoristas**: L. **Mis Alertas**: L. **Mis Pedidos**: CR. | Nivel: 5 (Básico). Solo accede a versión simplificada. Restringido a modificar solo sus propios precios y pedidos. Modo Offline permitido. | App Móvil |
| **Minorista Formal** | Publicar precios regulares, control de inventario básico, realizar pedidos a proveedores. | **Mi Inventario**: CRUD. **Mis Precios**: CRUD. **Mis Pedidos**: CRUD. **Catálogo Mayoristas**: L. | Nivel: 4 (Regular). Solo accede a sus propios datos de negocio e inventario. | App Móvil, Web |
| **Proveedor / Mayorista** | Publicar ofertas de mayoreo, gestionar recepción de pedidos, planificar logística de entregas a formales/informales. | **Catálogo Mayoreo**: CRUD. **Pedidos Recibidos**: CRU (Actualizar estado). **Rutas/Entregas**: L, U. | Nivel: 4 (Regular). No puede ver precios de otros mayoristas, solo de minoristas. | Web, Desktop, App Móvil (Choferes) |
| **Analista de Mercado** | Realizar comparativas de precios, detectar dispersión, calcular índices de acceso y coberturas geográficas. | **Dashboard Comparación**: L. **Mapas de Calor/Desiertos**: L. **Reportes de Brechas**: L, Exportación. | Nivel: 3 (Analítico). Acceso de solo lectura a datos anonimizados de precios y ubicaciones en tiempo real. | Web, Desktop |
| **Coordinador Municipal** | Delimitar zonas de comercio (tianguis), validar existencia de puestos, monitorear el índice de acceso en su municipio. | **Zonas/Polígonos**: CRUD. **Validaciones en Sitio**: C, U. **Directorio Zonal**: L. | Nivel: 3 (Operativo). Restringido únicamente a la delimitación geográfica de su municipio asignado. | Web, App Móvil (para validación) |
| **Auditor** | Inspección de logs, trazabilidad de datos críticos, monitoreo de cumplimiento de normativas de privacidad y cambios anómalos. | **Logs de Eventos**: L. **Historial de Precios**: L. **Auditoría de Pedidos**: L. | Nivel: 2 (Auditoría). Solo lectura total en bitácoras y registros históricos del sistema. No puede modificar. | Desktop, Web |

*Nota:* CRUD = Create, Read, Update, Delete. L = List (Read Only). C=Create, U=Update, R=Read.
