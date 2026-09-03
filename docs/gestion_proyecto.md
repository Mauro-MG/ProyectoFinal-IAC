# Gestión del Proyecto

## Estrategia de ramas

La estrategia propuesta está documentada en el `README.md`:
*   `main`: versión estable.
*   `develop`: integración.
*   `feature/*`: funcionalidades.
*   `hotfix/*`: correcciones urgentes.


## Tablero de tareas

Estados mínimos del tablero:
*   **Pendiente:** tareas priorizadas sin iniciar.
*   **En progreso:** tareas asignadas durante el sprint.
*   **En revisión:** tareas terminadas pendientes de validación.
*   **Hecho:** tareas verificadas.
*   **Bloqueado:** tareas con dependencia externa.

Backlog inicial:
*   Completar módulo de pedidos a mayoristas.
*   Implementar trazado visual de polígonos.
*   Agregar sincronización móvil offline.
*   Separar microservicios de precios, alertas y recomendaciones.
*   Agregar pruebas automatizadas de endpoints y permisos.
*   Preparar despliegue en Compute Engine.
*   Implementar cifrado de campos sensibles.

## Registro de incidencias inicial

| ID | Severidad | Descripción | Estado | Acción |
| :--- | :--- | :--- | :--- | :--- |
| INC-001 | Alta | Dockerfile apuntaba a `app:app` en vez de `wsgi:app`. | Corregida | Usar `wsgi:app` en Gunicorn. |
| INC-002 | Alta | Healthcheck apuntaba a `/health` sin ruta implementada. | Corregida | Agregar endpoint `/health`. |
| INC-003 | Alta | Variables Docker no coincidían con `config.py`. | Corregida | Construir URI desde `POSTGRES_*`, `MONGO_*`, `REDIS_*`. |
| INC-004 | Alta | Enums de modelos y SQL no coincidían. | Corregida | Alinear `tipo_comercio`, `estado_pedido` y `tipo_evento_auditoria`. |
| INC-005 | Media | Comparación de precios era placeholder. | Corregida | Agregar consulta agregada real. |
| INC-006 | Media | Faltaban diagramas arquitectónicos específicos. | Corregida | Completar `docs/arquitectura.md`. |
| INC-007 | Media | Faltaban documentos de prototipos, casos de uso y plan. | Corregida | Agregar documentos en `docs/`. |
| INC-008 | Media | No hay pruebas automatizadas completas. | Pendiente | Agregar suite con `pytest` y base de datos de prueba. |

## Estándares de codificación

*   Python con PEP 8.
*   Nombres de variables y funciones en `snake_case`.
*   Clases en `PascalCase`.
*   Tablas y columnas en `snake_case`.
*   Textos de interfaz y documentación en español.
*   Operaciones destructivas preferentemente como baja lógica (`activo = false`).
*   Toda operación crítica debe registrar auditoría.

## Convenciones de nombres

*   Blueprints: nombre plural del módulo (`productos`, `comercios`, `precios`).
*   Templates: carpeta por módulo y nombres descriptivos (`lista.html`, `formulario.html`, `detalle.html`).
*   Tablas de auditoría: entidad afectada y `entidad_id` como referencia textual.
*   Claves Redis: prefijo de dominio, identificadores y TTL explícito.
