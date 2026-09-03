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
