"""
Control de acceso por permisos.

Cada rol guarda en la columna roles.permisos (JSONB) la lista de códigos que
tiene asignados. El administrador puede cambiarlos desde /admin/roles sin
tocar código. Las vistas se protegen con @permiso_requerido.
"""
from functools import wraps

from flask import abort, redirect, request, url_for
from flask_login import current_user

PERMISOS = {
    'usuarios.gestionar': 'Gestionar usuarios',
    'roles.gestionar': 'Gestionar roles y permisos',
    'config.gestionar': 'Configurar parámetros del sistema',
    'catalogos.gestionar': 'Gestionar catálogo maestro, categorías y zonas',
    'comercios.gestionar': 'Registrar y administrar sus propios comercios',
    'comercios.ver_todos': 'Consultar todos los comercios',
    'comercios.validar': 'Validar o rechazar comercios',
    'inventario.gestionar': 'Administrar catálogo del comercio, existencias y precios',
    'precios.consultar': 'Consultar comparación de precios',
    'proveedores.consultar': 'Consultar proveedores y precios de mayoreo',
    'pedidos.crear': 'Crear pedidos de abasto',
    'pedidos.atender': 'Recibir y atender pedidos (proveedor)',
    'pedidos.ver_todos': 'Consultar todos los pedidos',
    'proveedor.catalogo': 'Administrar catálogo mayorista y condiciones de venta',
    'analisis.ver': 'Consultar cobertura, brechas e índice de acceso',
    'recomendaciones.ver': 'Consultar recomendaciones de surtido',
    'reportes.ver': 'Consultar y exportar reportes',
    'auditoria.ver': 'Consultar la bitácora de auditoría',
}


def permiso_requerido(*codigos):
    """Permite el acceso si el usuario tiene al menos uno de los permisos indicados."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login', next=request.path))
            if not any(current_user.tiene_permiso(c) for c in codigos):
                abort(403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador
