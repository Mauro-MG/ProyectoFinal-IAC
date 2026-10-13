"""
Llamadas del sistema web a los microservicios.

El web manda el mismo JWT con el que el usuario inició sesión (guardado en la
sesión de Flask), así el microservicio aplica los permisos del usuario y su
sesión se valida en Redis igual que en cualquier otro cliente. Cada llamada
lleva un X-Correlation-ID para rastrearla en la bitácora.

Si el servicio no responde, se lanza ServicioNoDisponible y la vista decide:
calcular con la biblioteca de dominio (análisis, notificaciones) o mostrar un
aviso (archivos, sesiones). Así una caída parcial no tumba el web.

Cortacircuitos: tras una falla se guarda `ms:caido:{servicio}` en Redis por
30 s; mientras exista, las vistas van directo al respaldo sin esperar el
tiempo de espera de la conexión en cada página.
"""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import requests
from flask import current_app, session
from redis.exceptions import RedisError

from abasto_dominio import extensiones

SEGUNDOS_EN_ESPERA = 30


class ServicioNoDisponible(Exception):
    pass


class RespuestaServicio:
    def __init__(self, respuesta):
        self.status = respuesta.status_code
        self.ok = respuesta.ok
        try:
            self.datos = respuesta.json()
        except ValueError:
            self.datos = {}
        self.contenido = respuesta.content
        self.headers = respuesta.headers

    @property
    def mensaje_error(self):
        return (self.datos.get('error') or {}).get('mensaje', f'El servicio respondió {self.status}.')


def _marcar_caido(servicio):
    try:
        extensiones.redis_client.set(f'ms:caido:{servicio}', 1, ex=SEGUNDOS_EN_ESPERA)
    except RedisError:
        pass


def _esta_caido(servicio):
    try:
        return bool(extensiones.redis_client.exists(f'ms:caido:{servicio}'))
    except RedisError:
        return False


def llamar(servicio, metodo, ruta, **kwargs):
    token = session.get('jwt_token')
    if not token:
        raise ServicioNoDisponible('La sesión no tiene token para los microservicios (Redis no disponible al entrar).')
    if _esta_caido(servicio):
        raise ServicioNoDisponible(f'ms-{servicio} falló hace menos de {SEGUNDOS_EN_ESPERA} s; se usa el respaldo.')
    base = current_app.config[f'MS_{servicio.upper()}_URL']
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json',
               'X-Correlation-ID': f'web-{uuid4().hex[:24]}'}
    headers.update(kwargs.pop('headers', {}))
    try:
        respuesta = requests.request(metodo, f'{base}/api/v1{ruta}', headers=headers,
                                     timeout=current_app.config.get('MS_TIMEOUT_SEGUNDOS', 3), **kwargs)
    except requests.RequestException as error:
        current_app.logger.warning('ms-%s no disponible: %s', servicio, error.__class__.__name__)
        _marcar_caido(servicio)
        raise ServicioNoDisponible(f'ms-{servicio} no respondió.')
    if respuesta.status_code in (502, 503, 504):
        _marcar_caido(servicio)
        raise ServicioNoDisponible(f'ms-{servicio} respondió {respuesta.status_code}.')
    return RespuestaServicio(respuesta)


SERVICIOS = ('seguridad', 'comercios', 'catalogo', 'inventario', 'precios', 'pedidos', 'analisis', 'notificaciones')


def salud_todos():
    """/health de los ocho servicios en paralelo (una caída no suma tiempos de espera)."""
    bases = {s: current_app.config[f'MS_{s.upper()}_URL'] for s in SERVICIOS}

    def consultar(servicio):
        try:
            respuesta = requests.get(f'{bases[servicio]}/health', timeout=2)
            return respuesta.json() | {'http': respuesta.status_code,
                                       'tiempo_ms': round(respuesta.elapsed.total_seconds() * 1000)}
        except (requests.RequestException, ValueError) as error:
            return {'servicio': f'ms-{servicio}', 'estado': 'sin_respuesta', 'error': error.__class__.__name__,
                    'dependencias': []}

    with ThreadPoolExecutor(max_workers=len(SERVICIOS)) as grupo:
        return dict(zip(SERVICIOS, grupo.map(consultar, SERVICIOS)))
