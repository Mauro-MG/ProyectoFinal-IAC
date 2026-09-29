# Plan de Trabajo del Semestre

## Parcial 1: Base técnica y PMF web

Objetivo: demostrar comprensión del negocio, arquitectura, datos y sistema web inicial.

Entregables:
*   Análisis del problema.
*   Requerimientos, historias, reglas y trazabilidad.
*   Matriz de perfiles y permisos.
*   Diseño arquitectónico y datos.
*   Sistema web mínimo funcional.
*   Contenedores locales.

## Parcial 2: Procesos operativos y servicios

Objetivo: ampliar el PMF hacia procesos completos de abastecimiento.

Actividades:
*   Implementar pedidos a mayoristas.
*   Separar endpoints REST de precios y pedidos.
*   Agregar módulo de proveedores.
*   Implementar alertas por variación de precios.
*   Agregar pruebas automatizadas de permisos y reglas.
*   Crear migraciones formales de base de datos.

## Parcial 3: Analítica y movilidad

Objetivo: cubrir valor diferencial del proyecto.

Actividades:
*   Prototipo móvil de captura offline.
*   Sincronización de lotes hacia backend.
*   Dashboard geográfico con zonas y polígonos.
*   Cálculo inicial de índice de acceso alimentario.
*   Uso de MongoDB para snapshots y telemetría.
*   Uso de Redis para cachés, contadores y rate limiting.

## Parcial 4: Seguridad, despliegue y cierre

Objetivo: preparar demostración final robusta y desplegable.

Actividades:
*   Despliegue en Google Compute Engine.
*   Configuración HTTPS y variables secretas.
*   Auditoría avanzada y exportaciones.
*   Cifrado de campos sensibles.
*   Pruebas de carga básicas.
*   Documentación final de instalación, operación y demo.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
| :--- | :--- | :--- |
| Baja adopción de comerciantes informales | Alto | Interfaz simple, baja captura obligatoria y comunicación de privacidad. |
| Datos de precios falsos o extremos | Alto | Reglas de validación, auditoría y estado pendiente. |
| Complejidad geoespacial | Medio | Usar PostGIS desde el inicio y limitar alcance por zonas piloto. |
| Falta de infraestructura local | Medio | Docker Compose como entorno estándar. |
| Alcance demasiado amplio | Alto | Priorizar PMF web, precios, catálogos y auditoría antes de móvil/desktop. |
