"""
Autenticación y autorización de los servicios.

Cada petición protegida debe traer `Authorization: Bearer <token>`. El token se
valida con abasto_dominio.sesiones (firma + vigencia + sesión activa en Redis
+ no revocado) y se revisan los permisos que trae el propio token.
"""
from uuid import UUID

from flask import g, request

from abasto_dominio import sesiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Usuario

from abasto_api.errores import ErrorApi


def token_de_peticion():
    encabezado = request.headers.get('Authorization', '')
    if not encabezado.startswith('Bearer '):
        raise ErrorApi(401, 'token_requerido', 'Falta el encabezado Authorization: Bearer <token>.',
                       headers={'WWW-Authenticate': 'Bearer'})
    return encabezado.removeprefix('Bearer ').strip()


def autenticar(permisos=()):
    """Valida el token y los permisos; deja los datos en `g.claims`."""
    claims = sesiones.validar_token(token_de_peticion())
    g.claims = claims
    g.token = request.headers['Authorization'].removeprefix('Bearer ').strip()
    if permisos and not any(sesiones.tiene_permiso(claims, p) for p in permisos):
        raise ErrorApi(403, 'sin_permiso',
                       f'Tu rol ({claims.get("rol")}) no tiene ninguno de estos permisos: {", ".join(permisos)}.')
    return claims


def usuario_actual():
    """El usuario del token (sólo tokens de usuario, no de servicio)."""
    if getattr(g, 'usuario', None) is not None:
        return g.usuario
    claims = getattr(g, 'claims', None)
    if not claims or claims.get('tipo') != 'acceso':
        raise ErrorApi(403, 'sin_permiso', 'Esta operación requiere un usuario, no un token de servicio.')
    usuario = db.session.get(Usuario, UUID(claims['sub']))
    if not usuario or not usuario.activo:
        raise ErrorApi(401, 'usuario_inactivo', 'La cuenta del token ya no está activa.')
    g.usuario = usuario
    return usuario


def tiene(permiso):
    return sesiones.tiene_permiso(getattr(g, 'claims', {}) or {}, permiso)
