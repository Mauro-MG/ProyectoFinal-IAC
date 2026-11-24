"""
Catálogo de permisos.

Cada rol guarda en roles.permisos (JSONB) la lista de códigos que tiene. El web
los revisa con @permiso_requerido y los microservicios con @requiere(...); el
token JWT lleva la misma lista, así que un servicio no necesita consultar la
base de datos para autorizar.
"""
PERMISOS = {
    'usuarios.gestionar': 'Gestionar usuarios',
    'roles.gestionar': 'Gestionar roles y permisos',
    'config.gestionar': 'Configurar parámetros del sistema',
    'sesiones.gestionar': 'Consultar y revocar sesiones activas',
    'servicios.monitorear': 'Consultar estado y actividad de los microservicios',
    'catalogos.gestionar': 'Gestionar catálogo maestro, categorías y zonas',
    'comercios.gestionar': 'Registrar y administrar sus propios comercios',
    'comercios.ver_todos': 'Consultar todos los comercios',
    'comercios.validar': 'Validar o rechazar comercios',
    'inventario.gestionar': 'Administrar catálogo del comercio, existencias y precios',
    'importaciones.ejecutar': 'Importar inventario y precios desde un archivo CSV',
    'archivos.gestionar': 'Subir y consultar fotos, evidencias y documentos',
    'precios.consultar': 'Consultar comparación de precios',
    'proveedores.consultar': 'Consultar proveedores y precios de mayoreo',
    'pedidos.crear': 'Crear pedidos de abasto',
    'pedidos.atender': 'Recibir y atender pedidos (proveedor)',
    'pedidos.ver_todos': 'Consultar todos los pedidos',
    'proveedor.catalogo': 'Administrar catálogo mayorista y condiciones de venta',
    'proveedor.equipo': 'Administrar los operadores de su empresa',
    'analisis.ver': 'Consultar cobertura, brechas e índice de acceso',
    'recomendaciones.ver': 'Consultar recomendaciones de surtido',
    'reportes.ver': 'Consultar y exportar reportes',
    'auditoria.ver': 'Consultar la bitácora de auditoría',
    'notificaciones.crear': 'Emitir notificaciones a otros usuarios (uso entre servicios)',
    # Entrega final (servicios 8109-8124)
    'proveedores.verificar': 'Verificar, rechazar o suspender proveedores',
    'ventas.registrar': 'Registrar ventas y devoluciones de su comercio',
    'entregas.gestionar': 'Asignar y actualizar entregas de pedidos (proveedor)',
    'entregas.recibir': 'Confirmar la recepción de entregas y reportar incidencias (comercio)',
    'abastecimiento.solicitar': 'Solicitar cotizaciones y generar órdenes de compra',
    'abastecimiento.cotizar': 'Responder solicitudes de cotización (proveedor)',
    'sincronizacion.enviar': 'Enviar lotes de operaciones hechas sin conexión (apps)',
    'integraciones.ejecutar': 'Importar y exportar información en CSV, JSON o XML',
    'demanda.ver': 'Consultar demanda histórica, tendencias y estimaciones',
    'demanda.registrar': 'Registrar búsquedas de productos (uso entre servicios)',
    'auditoria.registrar': 'Registrar eventos de auditoría de sistemas externos (uso entre servicios)',
}
