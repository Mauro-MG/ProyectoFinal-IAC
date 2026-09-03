from functools import wraps
from flask import flash, redirect, url_for, request, abort
from flask_login import current_user

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.url))
            if current_user.rol.nombre not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.url))
            permisos = current_user.rol.permisos or {}
            if not permisos.get(permission):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
