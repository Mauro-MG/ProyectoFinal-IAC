# Prototipos de Interfaces

Los prototipos se implementan directamente como pantallas navegables en la aplicación Flask. Esta versión evita maquetas estáticas y permite demostrar captura/consulta real de información.

## Pantalla pública

**Ruta:** `/`

**Objetivo:** explicar el valor de AbastoRed y dirigir a registro o consulta pública de comercios.

**Elementos:** hero con nombre del producto, llamada a registro, acceso a comercios públicos y resumen de módulos.

## Inicio de sesión

**Ruta:** `/auth/login`

**Objetivo:** autenticar usuarios existentes.

**Elementos:** correo, contraseña, recuperación y enlace a registro.

## Registro

**Ruta:** `/auth/registro`

**Objetivo:** dar de alta un usuario comerciante informal por defecto.

**Elementos:** nombre, apellido, correo, contraseña, confirmación y validación de correo.

## Panel por perfil

**Ruta:** `/dashboard/panel`

**Objetivo:** presentar métricas y acciones rápidas según el rol.

**Variantes:**
*   Administrador: usuarios, comercios y productos.
*   Comerciante/minorista: comercios propios.
*   Analista: comercios, productos y precios registrados.

## Catálogo de productos

**Rutas:** `/productos`, `/productos/nuevo`, `/productos/<id>`, `/productos/<id>/editar`.

**Objetivo:** administrar el catálogo maestro.

**Operaciones:** listar, crear, consultar detalle, editar y baja lógica.

## Catálogo de comercios

**Rutas:** `/comercios`, `/comercios/nuevo`, `/comercios/<id>`, `/comercios/<id>/editar`.

**Objetivo:** administrar comercios formales, informales y mayoristas.

**Operaciones:** listar por perfil, crear, consultar detalle, editar y baja lógica.

## Registro de precios

**Ruta:** `/precios/registrar`

**Objetivo:** capturar precios reales por comercio/producto.

**Reglas visibles:** si el precio sale del umbral regional, el sistema muestra advertencia y marca el registro como pendiente de validación.

## Comparación de precios

**Ruta:** `/precios`

**Objetivo:** mostrar consulta operativa para comparar promedio, mínimo, máximo y muestra por producto, zona y sector.

**Filtros:** producto.

## Auditoría

**Rutas:** `/auditoria`, `/auditoria/<id>`.

**Objetivo:** permitir consulta de eventos a Administrador General y Auditor.

**Elementos:** fecha, tipo de evento, entidad, descripción, IP y detalle.
