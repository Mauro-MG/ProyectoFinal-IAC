"""
Llamadas de un servicio a otro.

Propaga el token del usuario (o usa un token de servicio) y el
X-Correlation-ID, para que la petición se pueda rastrear en la bitácora de
ambos servicios. Si el otro servicio no responde, lanza ErrorApi 503.
"""
import requests
from flask import current_app, g

from abasto_dominio.sesiones import token_servicio

from abasto_api.errores import ErrorApi


def llamar(servicio, metodo, ruta, token=None, permisos_servicio=None, **kwargs):
    base = current_app.config[f'MS_{servicio.upper()}_URL']
    if token is None:
        token = token_servicio(current_app.name, permisos_servicio or [])
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json',
               'X-Correlation-ID': getattr(g, 'correlation_id', '')}
    headers.update(kwargs.pop('headers', {}))
    try:
        respuesta = requests.request(metodo, f'{base}{ruta}', headers=headers,
                                     timeout=current_app.config.get('MS_TIMEOUT_SEGUNDOS', 3), **kwargs)
    except requests.RequestException as error:
        raise ErrorApi(503, 'servicio_no_disponible', f'ms-{servicio} no respondió: {error.__class__.__name__}.')
    return respuesta
