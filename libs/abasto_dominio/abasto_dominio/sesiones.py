"""
Sesiones con JWT verificadas en Redis (mecanismo común del web y los servicios).

Un token vale sólo si (1) su firma y vigencia son correctas, (2) su jti no está
en la lista de revocados y (3) su sesión sigue viva en Redis. Así, cerrar
sesión en cualquier componente invalida el token en todos.

Claves de Redis:
    sesion:{jti}               JSON de la sesión          TTL = vigencia del token de acceso (8 h)
    sesiones_usuario:{id}      SET con los jti activos     TTL = vigencia del refresh (7 días)
    jwt:revocado:{jti}         "1"                         TTL = lo que le quedaba al token
    refresh:{token}            JSON {usuario_id, jti}      TTL = 7 días (se rota en cada uso)
    refresh_de:{jti}           el refresh de esa sesión    TTL = 7 días (para anularlo al cerrar sesión)
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from flask import current_app
from redis.exceptions import RedisError

from abasto_dominio import extensiones
from abasto_dominio.extensiones import db


class ErrorSesion(Exception):
    def __init__(self, mensaje, codigo_http=401, codigo='token_invalido'):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo_http = codigo_http
        self.codigo = codigo


def _ahora():
    return datetime.now(timezone.utc)


def _segundos(delta):
    return int(delta.total_seconds())


def _firmar(claims):
    return jwt.encode(claims, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def _registrar_sesion(claims, usuario_id, ttl, ip=None):
    r = extensiones.redis_client
    datos = {'usuario_id': usuario_id, 'rol': claims['rol'], 'nombre': claims.get('nombre'),
             'origen': claims.get('origen'), 'ip': ip, 'creada': _ahora().isoformat()}
    pipe = r.pipeline()
    pipe.setex(f"sesion:{claims['jti']}", ttl, json.dumps(datos))
    pipe.sadd(f'sesiones_usuario:{usuario_id}', claims['jti'])
    pipe.expire(f'sesiones_usuario:{usuario_id}', _segundos(current_app.config['JWT_REFRESH_TOKEN_EXPIRES']))
    pipe.execute()


def emitir_tokens(usuario, origen='web', ip=None, con_refresh=True):
    """Crea el token de acceso (y de renovación) y registra la sesión en Redis."""
    ahora = _ahora()
    vigencia = current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    claims = {
        'sub': str(usuario.id),
        'jti': uuid4().hex,
        'tipo': 'acceso',
        'origen': origen,
        'nombre': usuario.nombre_completo,
        'rol': usuario.rol.nombre,
        'permisos': list(usuario.rol.permisos or []),
        'iat': ahora,
        'exp': ahora + vigencia,
    }
    proveedor_id = usuario.proveedor.id if usuario.proveedor else usuario.proveedor_id
    if proveedor_id:
        claims['proveedor_id'] = str(proveedor_id)

    _registrar_sesion(claims, str(usuario.id), _segundos(vigencia), ip)
    resultado = {'access_token': _firmar(claims), 'token_type': 'Bearer',
                 'expires_in': _segundos(vigencia), 'jti': claims['jti']}
    if con_refresh:
        refresh = secrets.token_urlsafe(48)
        ttl = _segundos(current_app.config['JWT_REFRESH_TOKEN_EXPIRES'])
        pipe = extensiones.redis_client.pipeline()
        pipe.setex(f'refresh:{refresh}', ttl,
                   json.dumps({'usuario_id': str(usuario.id), 'jti': claims['jti'], 'origen': origen}))
        pipe.setex(f"refresh_de:{claims['jti']}", ttl, refresh)
        pipe.execute()
        resultado['refresh_token'] = refresh
    return resultado


def token_servicio(nombre_servicio, permisos, minutos=5):
    """Token corto para que un servicio llame a otro en nombre del sistema."""
    ahora = _ahora()
    claims = {'sub': f'servicio:{nombre_servicio}', 'jti': uuid4().hex, 'tipo': 'servicio',
              'origen': nombre_servicio, 'nombre': f'Servicio {nombre_servicio}', 'rol': 'Servicio',
              'permisos': list(permisos), 'iat': ahora, 'exp': ahora + timedelta(minutes=minutos)}
    _registrar_sesion(claims, claims['sub'], minutos * 60)
    return _firmar(claims)


def decodificar(token):
    try:
        claims = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise ErrorSesion('El token expiró; inicia sesión o renuévalo.', 401, 'token_expirado')
    except jwt.InvalidTokenError:
        raise ErrorSesion('El token no es válido.', 401, 'token_invalido')
    if claims.get('tipo') not in ('acceso', 'servicio') or not claims.get('jti'):
        raise ErrorSesion('El token no es válido.', 401, 'token_invalido')
    return claims


def validar_token(token):
    """Regresa los claims del token si la sesión está activa; si no, lanza ErrorSesion."""
    claims = decodificar(token)
    try:
        r = extensiones.redis_client
        if r.exists(f"jwt:revocado:{claims['jti']}"):
            raise ErrorSesion('El token fue revocado (sesión cerrada).', 401, 'token_revocado')
        if not r.exists(f"sesion:{claims['jti']}"):
            raise ErrorSesion('La sesión ya no está activa.', 401, 'sesion_inactiva')
    except RedisError:
        raise ErrorSesion('No se pudo verificar la sesión: Redis no disponible.', 503, 'sesiones_no_disponibles')
    return claims


def sesion_activa(jti):
    """True/False según Redis; None si Redis no responde (el web decide qué hacer)."""
    try:
        return bool(extensiones.redis_client.exists(f'sesion:{jti}'))
    except RedisError:
        return None


def _anular_refresh(pipe, jti):
    """El refresh de una sesión cerrada tampoco debe servir para obtener tokens nuevos."""
    refresh = extensiones.redis_client.get(f'refresh_de:{jti}')
    if refresh:
        pipe.delete(f'refresh:{refresh}')
    pipe.delete(f'refresh_de:{jti}')


def revocar(claims):
    """Cierra la sesión del token: la borra, anula su refresh y pone su jti en la lista de revocados."""
    restante = max(int(claims['exp'] - _ahora().timestamp()), 1)
    r = extensiones.redis_client
    pipe = r.pipeline()
    pipe.delete(f"sesion:{claims['jti']}")
    pipe.setex(f"jwt:revocado:{claims['jti']}", restante, '1')
    pipe.srem(f"sesiones_usuario:{claims['sub']}", claims['jti'])
    _anular_refresh(pipe, claims['jti'])
    pipe.execute()


def revocar_jti(jti, usuario_id, ttl=None):
    r = extensiones.redis_client
    ttl = ttl or r.ttl(f'sesion:{jti}')
    pipe = r.pipeline()
    pipe.delete(f'sesion:{jti}')
    pipe.setex(f'jwt:revocado:{jti}', max(ttl or 1, 1), '1')
    pipe.srem(f'sesiones_usuario:{usuario_id}', jti)
    _anular_refresh(pipe, jti)
    pipe.execute()


def revocar_todas(usuario_id):
    """Cierra todas las sesiones de un usuario (p. ej. al desactivarlo). Regresa cuántas cerró."""
    r = extensiones.redis_client
    jtis = r.smembers(f'sesiones_usuario:{usuario_id}')
    for jti in jtis:
        revocar_jti(jti, usuario_id)
    r.delete(f'sesiones_usuario:{usuario_id}')
    return len(jtis)


def renovar(refresh_token, ip=None):
    """Cambia un refresh token válido por un par nuevo. El refresh usado deja de servir."""
    from abasto_dominio.modelos import Usuario
    r = extensiones.redis_client
    clave = f'refresh:{refresh_token}'
    try:
        datos = r.getdel(clave)
    except RedisError:
        raise ErrorSesion('No se pudo verificar la sesión: Redis no disponible.', 503, 'sesiones_no_disponibles')
    if not datos:
        raise ErrorSesion('El token de renovación no es válido o ya se usó.', 401, 'refresh_invalido')
    datos = json.loads(datos)
    usuario = db.session.get(Usuario, UUID(datos['usuario_id']))
    if not usuario or not usuario.activo:
        raise ErrorSesion('La cuenta no está activa.', 401, 'usuario_inactivo')
    if r.exists(f"sesion:{datos['jti']}"):
        revocar_jti(datos['jti'], datos['usuario_id'])
    return emitir_tokens(usuario, origen=datos.get('origen', 'api'), ip=ip)


def sesiones_activas(usuario_id=None):
    """Sesiones vivas en Redis con su tiempo restante (para el panel de administración)."""
    r = extensiones.redis_client
    patron = 'sesion:*'
    resultado = []
    for clave in r.scan_iter(match=patron, count=200):
        datos = r.get(clave)
        if not datos:
            continue
        datos = json.loads(datos)
        if usuario_id and datos.get('usuario_id') != str(usuario_id):
            continue
        datos['jti'] = clave.split(':', 1)[1]
        datos['ttl'] = r.ttl(clave)
        resultado.append(datos)
    return sorted(resultado, key=lambda s: s.get('creada') or '', reverse=True)


def tiene_permiso(claims, codigo):
    return codigo in (claims.get('permisos') or [])


# ---------------------------------------------------------------- intentos de inicio de sesión
MAX_INTENTOS = 5
VENTANA_INTENTOS = 15 * 60


def _clave_intentos(email):
    return f'login_fallidos:{(email or "").strip().lower()}'


def login_bloqueado(email):
    """True si el correo acumuló MAX_INTENTOS fallos en los últimos 15 minutos."""
    try:
        return int(extensiones.redis_client.get(_clave_intentos(email)) or 0) >= MAX_INTENTOS
    except RedisError:
        return False


def registrar_intento_fallido(email):
    try:
        clave = _clave_intentos(email)
        pipe = extensiones.redis_client.pipeline()
        pipe.incr(clave)
        pipe.expire(clave, VENTANA_INTENTOS)
        return pipe.execute()[0]
    except RedisError:
        return None


def limpiar_intentos(email):
    try:
        extensiones.redis_client.delete(_clave_intentos(email))
    except RedisError:
        pass
