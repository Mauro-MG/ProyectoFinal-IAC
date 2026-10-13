"""
Control de acceso por permisos.

Cada rol guarda en la columna roles.permisos (JSONB) la lista de códigos que
tiene asignados. El administrador puede cambiarlos desde /admin/roles sin
tocar código. Las vistas se protegen con @permiso_requerido.
"""
from functools import wraps

from flask import abort, redirect, request, url_for
from flask_login import current_user

from abasto_dominio.permisos import PERMISOS  # noqa: F401  (catálogo compartido con los microservicios)


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
