# Casos de Prueba y Demostración

## CP-AUTH-01 Inicio de sesión correcto

**Datos:** `admin@abastored.mx` / `Admin123!`.

**Pasos:** abrir `/auth/login`, ingresar credenciales y enviar.

**Resultado esperado:** redirección a `/dashboard/panel`, rol visible y evento `LOGIN` en auditoría.

## CP-AUTH-02 Login inválido

**Datos:** correo válido con contraseña incorrecta.

**Resultado esperado:** mensaje de error y sin acceso al panel.

## CP-JWT-01 Emisión de token

**Pasos:** enviar `POST /api/auth/token` con credenciales válidas.

**Resultado esperado:** respuesta JSON con `access_token` y `token_type`.

## CP-JWT-02 Endpoint protegido sin token

**Pasos:** abrir `/api/precios/resumen` sin cabecera `Authorization`.

**Resultado esperado:** HTTP 401 con mensaje `Token JWT requerido`.

## CP-CAT-01 CRUD de productos

**Actor:** Administrador General.

**Pasos:** crear producto, editarlo, consultar detalle y desactivarlo.

**Resultado esperado:** datos persistidos en PostgreSQL y eventos de auditoría `CREACION`, `ACTUALIZACION`, `ELIMINACION`.

## CP-CAT-02 CRUD de comercios

**Actor:** Comerciante o Administrador.

**Pasos:** crear comercio, editarlo, consultar detalle y desactivarlo.

**Resultado esperado:** solo el propietario o rol autorizado puede operar el comercio.

## CP-PREC-01 Registro normal de precio

**Actor:** Comerciante Informal, Minorista Formal o Administrador.

**Pasos:** seleccionar comercio, producto y precio dentro del rango esperado.

**Resultado esperado:** precio con estado `VALIDADO`, cache Redis actualizada si está disponible y evento de auditoría.

## CP-PREC-02 Precio fuera de umbral

**Actor:** Comerciante Informal, Minorista Formal o Administrador.

**Pasos:** registrar precio mayor a 150% o menor a 10% del promedio regional de 7 días.

**Resultado esperado:** precio guardado como `PENDIENTE_VALIDACION` y mensaje de advertencia.

## CP-DASH-01 Comparación de precios

**Actor:** Analista de Mercado.

**Pasos:** abrir `/precios`, filtrar por producto.

**Resultado esperado:** tabla con promedio, mínimo, máximo y número de muestras por zona y sector.

## CP-AUD-01 Consulta de auditoría

**Actor:** Auditor o Administrador General.

**Pasos:** abrir `/auditoria` y consultar detalle.

**Resultado esperado:** eventos visibles, ordenados por fecha y sin opciones de modificación.

## CP-INF-01 Arranque local con contenedores

**Pasos:** ejecutar `docker compose up --build`.

**Resultado esperado:** servicios web, PostgreSQL/PostGIS, MongoDB y Redis sanos; `/health` responde `status: ok`.

## Pruebas Planeadas para Etapas Posteriores

Las siguientes pruebas forman parte de la trazabilidad y del diseño de la solución, pero no requieren implementación durante el primer parcial. Se ejecutarán cuando se desarrollen los microservicios, aplicaciones adicionales y servicios de nube correspondientes.

| ID | Componente futuro | Propósito de la prueba |
| :--- | :--- | :--- |
| **CP-DASH-02** | Dashboard analítico | Verificar los filtros por producto, zona y periodo. |
| **CP-GEO-01** | MS Geográfico/PostGIS | Verificar la creación y validación de polígonos geográficos. |
| **CP-ALT-01** | MS de Alertas | Comprobar que un evento de precio atípico produzca una alerta. |
| **CP-REC-01** | MS de Recomendaciones | Verificar la generación de recomendaciones de surtido por zona. |
| **CP-IDX-01** | MS de Acceso Alimentario | Validar el cálculo del Índice de Acceso Alimentario. |
| **CP-MOB-01** | Aplicación móvil | Comprobar la captura de precios sin conexión. |
| **CP-MOB-02** | Aplicación móvil/MS de Precios | Comprobar la sincronización cuando se recupera la conexión. |
| **CP-MOB-03** | Aplicación móvil | Medir el consumo de datos del modo reducido. |
| **CP-PED-01** | MS de Pedidos | Crear correctamente un pedido que cumpla el monto mínimo. |
| **CP-PED-02** | MS de Pedidos | Rechazar un pedido inferior al monto mínimo del proveedor. |
| **CP-AUD-02** | Aplicación de escritorio | Consultar el historial de auditoría por usuario, entidad y periodo. |
| **CP-INF-02** | Infraestructura en nube | Verificar la disponibilidad del sistema en más de una zona. |
| **CP-SEC-01** | API Gateway | Comprobar el acceso con un JWT válido. |
| **CP-SEC-02** | API Gateway | Rechazar un JWT expirado o revocado. |
| **CP-SEC-03** | Seguridad de datos | Verificar el cifrado de campos personales en reposo. |
| **CP-PERF-01** | Analítica/PostGIS | Medir que las consultas espaciales respondan en un máximo de 3 segundos. |
| **CP-MON-01** | Monitoreo | Detectar tres verificaciones de salud fallidas consecutivas. |
| **CP-MON-02** | Registro centralizado | Localizar todos los eventos de una solicitud mediante `correlation_id`. |
| **CP-MON-03** | Métricas | Consultar latencia, errores y solicitudes en el tablero de monitoreo. |

## Alcance de las Pruebas del Primer Parcial

Durante el primer parcial, los casos de prueba representan procedimientos de validación manual para el producto mínimo funcional. La automatización mediante `pytest`, pruebas de integración, pruebas de carga y validaciones de servicios distribuidos se realizará en etapas posteriores.

Los casos actuales permiten comprobar:

*   Inicio de sesión correcto e incorrecto.
*   Generación y validación básica de JWT.
*   Operaciones sobre productos y comercios.
*   Registro y validación de precios.
*   Comparación de precios.
*   Consulta de auditoría.
*   Arranque de la infraestructura inicial.
