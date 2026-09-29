"""
Caché de resultados de análisis en Redis.

Las claves incluyen un número de versión (analisis:version). Cada vez que cambia
un inventario se incrementa la versión, así que los resultados viejos dejan de
usarse sin tener que buscarlos y borrarlos; expiran solos por TTL.
Si Redis no está disponible, se calcula directo en PostgreSQL.
"""
import json

from flask import current_app
from redis.exceptions import RedisError

from app import extensions

CLAVE_VERSION = 'analisis:version'


def obtener_o_calcular(nombre, calcular, ttl=300):
    redis_client = extensions.redis_client
    try:
        version = redis_client.get(CLAVE_VERSION) or '0'
        clave = f'analisis:v{version}:{nombre}'
        guardado = redis_client.get(clave)
        if guardado is not None:
            return json.loads(guardado)
    except RedisError:
        current_app.logger.warning('Redis no disponible; se calcula %s sin caché.', nombre)
        return calcular()

    resultado = calcular()
    try:
        redis_client.setex(clave, ttl, json.dumps(resultado))
    except RedisError:
        pass
    return resultado


def invalidar_analisis():
    try:
        extensions.redis_client.incr(CLAVE_VERSION)
    except RedisError:
        current_app.logger.warning('No se pudo invalidar la caché de análisis en Redis.')
