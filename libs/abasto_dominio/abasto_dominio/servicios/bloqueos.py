"""
Bloqueos distribuidos en Redis.

Evitan que dos procesos (por ejemplo, el web y el servicio de inventario, o dos
pestañas) ejecuten la misma operación larga a la vez sobre el mismo recurso.
Clave: `bloqueo:{recurso}` con un token aleatorio y TTL; sólo quien lo tomó
puede liberarlo (se compara el token en un script Lua atómico).
"""
import secrets
from contextlib import contextmanager

from redis.exceptions import RedisError

from abasto_dominio import extensiones
from abasto_dominio.servicios import ReglaNegocioError

_LIBERAR = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@contextmanager
def bloqueo(recurso, ttl_segundos=60, mensaje='La operación ya se está ejecutando; intenta en un momento.'):
    clave = f'bloqueo:{recurso}'
    token = secrets.token_hex(8)
    try:
        # SET NX devuelve True si lo tomó y None si alguien más ya lo tiene
        tomado = bool(extensiones.redis_client.set(clave, token, nx=True, ex=ttl_segundos))
        if not tomado:
            raise ReglaNegocioError(mensaje)
    except RedisError:
        tomado = False  # sin Redis no hay bloqueo distribuido; la base de datos sigue protegiendo los datos
    try:
        yield
    finally:
        if tomado:
            try:
                extensiones.redis_client.eval(_LIBERAR, 1, clave, token)
            except RedisError:
                pass
