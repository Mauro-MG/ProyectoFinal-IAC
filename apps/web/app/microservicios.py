"""
Llamadas del sistema web a los microservicios.

El web manda el mismo JWT con el que el usuario inició sesión (guardado en la
sesión de Flask), así el microservicio aplica los permisos del usuario y su
sesión se valida en Redis igual que en cualquier otro cliente. Cada llamada
lleva un X-Correlation-ID para rastrearla en la bitácora.

El web no escribe en las bases de datos: su usuario de PostgreSQL es de solo
lectura. Cada alta, cambio o baja se manda al servicio dueño del dato con
`escribir()` (ver docs/web_y_apis.md).

Si el servicio no responde, se lanza ServicioNoDisponible y la vista decide:
para consultas, calcular con la biblioteca de dominio (análisis, notificaciones);
para escrituras, avisar que el cambio no se guardó. Así una caída parcial no
tumba el web.

Cortacircuitos: tras una falla se guarda `ms:caido:{servicio}` en Redis por
30 s; mientras exista, las vistas van directo al respaldo sin esperar el
tiempo de espera de la conexión en cada página.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from decimal import Decimal
from uuid import UUID, uuid4

import requests
from flask import current_app, flash, request, session
from redis.exceptions import RedisError

from abasto_dominio import extensiones, registro_servicios

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


def _serializable(valor):
    """Decimal, fecha y hora a texto para el cuerpo JSON (los esquemas Pydantic de los servicios los aceptan así)."""
    if isinstance(valor, dict):
        return {k: _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_serializable(v) for v in valor]
    if isinstance(valor, Decimal):
        return format(valor, 'f')
    if isinstance(valor, (date, time)):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    return valor


def llamar(servicio, metodo, ruta, publico=False, **kwargs):
    """`publico=True` para las rutas que no llevan token (inicio de sesión, registro, recuperación)."""
    token = None if publico else session.get('jwt_token')
    if not publico and not token:
        raise ServicioNoDisponible('La sesión no tiene token para los microservicios (Redis no disponible al entrar).')
    if _esta_caido(servicio):
        raise ServicioNoDisponible(f'ms-{servicio} falló hace menos de {SEGUNDOS_EN_ESPERA} s; se usa el respaldo.')
    base = current_app.config[f'MS_{servicio.upper()}_URL']
    headers = {'Accept': 'application/json', 'X-Correlation-ID': f'web-{uuid4().hex[:24]}',
               # IP real del usuario (la que el gateway le pasó al web): el límite de peticiones y la
               # bitácora del servicio la usan en lugar de la IP del contenedor web
               'X-Forwarded-For': request.remote_addr or ''}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    headers.update(kwargs.pop('headers', {}))
    if 'json' in kwargs:
        kwargs['json'] = _serializable(kwargs['json'])
    timeout = kwargs.pop('timeout', current_app.config.get('MS_TIMEOUT_SEGUNDOS', 3))
    try:
        respuesta = requests.request(metodo, f'{base}/api/v1{ruta}', headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as error:
        current_app.logger.warning('ms-%s no disponible: %s', servicio, error.__class__.__name__)
        _marcar_caido(servicio)
        raise ServicioNoDisponible(f'ms-{servicio} no respondió.')
    if respuesta.status_code in (502, 503, 504):
        _marcar_caido(servicio)
        raise ServicioNoDisponible(f'ms-{servicio} respondió {respuesta.status_code}.')
    return RespuestaServicio(respuesta)


def escribir(servicio, metodo, ruta, exito=None, **kwargs):
    """
    Toda escritura del web pasa por aquí: la hace el servicio dueño del dato con sus reglas, sus
    permisos y su auditoría. Regresa los datos de la respuesta, o None si el servicio rechazó el
    cambio o no respondió (en ese caso ya se mostró el motivo con flash y no se guardó nada).
    """
    try:
        respuesta = llamar(servicio, metodo, ruta, **kwargs)
    except ServicioNoDisponible:
        flash(f'El servicio de {servicio} no está disponible; el cambio no se guardó. Intenta en un momento.', 'error')
        return None
    if not respuesta.ok:
        detalles = (respuesta.datos.get('error') or {}).get('detalles') or []
        flash(respuesta.mensaje_error + ''.join(f" {d.get('campo', '')}: {d.get('mensaje', '')}." for d in detalles
                                                if isinstance(d, dict)), 'error')
        return None
    if exito:
        flash(exito, 'ok')
    return respuesta.datos


SERVICIOS = registro_servicios.NOMBRES


def salud_todos():
    """/health de los 24 servicios en paralelo (una caída no suma tiempos de espera)."""
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
