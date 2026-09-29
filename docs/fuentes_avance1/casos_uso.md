# Casos de Uso Principales

## CU-001 Inicio de sesión y acceso por perfil

**Actores:** Administrador General, Comerciante Informal, Minorista Formal, Analista de Mercado, Auditor.

**Flujo principal:**
1. El usuario ingresa correo y contraseña.
2. El sistema valida credenciales contra PostgreSQL.
3. El sistema crea sesión web y JWT básico.
4. El usuario llega al panel con menú según su rol.
5. El sistema registra evento de auditoría.

**Resultado esperado:** acceso autorizado y navegación diferenciada por perfil.

## CU-002 Gestión de catálogo de productos

**Actor principal:** Administrador General.

**Flujo principal:**
1. El administrador abre el catálogo de productos.
2. Registra un nuevo producto maestro con categoría, unidad y bandera de canasta básica.
3. Edita los datos del producto.
4. Desactiva el producto cuando ya no debe mostrarse.
5. El sistema registra altas, cambios y bajas lógicas en auditoría.

**Resultado esperado:** catálogo funcional con operaciones CRUD sobre PostgreSQL.

## CU-003 Gestión de comercios

**Actores:** Administrador General, Coordinador Municipal, Comerciante Informal, Minorista Formal.

**Flujo principal:**
1. El usuario autorizado registra un comercio.
2. Captura tipo, dirección, municipio y estado.
3. Consulta el listado filtrado según su perfil.
4. Edita información operativa del comercio.
5. Desactiva el comercio si deja de operar.

**Resultado esperado:** los usuarios gestionan solo los comercios permitidos por su rol.

## CU-004 Registro y comparación de precios

**Actores:** Comerciante Informal, Minorista Formal, Administrador General, Analista de Mercado.

**Flujo principal:**
1. El usuario autorizado selecciona comercio, producto y precio.
2. El sistema consulta el último precio del comercio.
3. El sistema compara el precio contra el promedio regional de 7 días.
4. Si el precio sale del umbral, queda como `PENDIENTE_VALIDACION`.
5. El sistema guarda el precio en PostgreSQL, actualiza caché Redis y registra auditoría.
6. El analista consulta promedios por producto, zona y sector.

**Resultado esperado:** proceso principal de negocio ejecutable con persistencia real.

## CU-005 Consulta de auditoría

**Actores:** Administrador General, Auditor.

**Flujo principal:**
1. El actor abre el módulo de auditoría.
2. Consulta los eventos ordenados por fecha.
3. Abre el detalle de un evento.
4. El sistema impide modificaciones o eliminaciones sobre la bitácora.

**Resultado esperado:** trazabilidad básica e inmutabilidad de registros.
