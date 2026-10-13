"""Base común de los microservicios de AbastoRed (ver servicio.py)."""
from abasto_api.errores import ErrorApi, no_encontrado, prohibido
from abasto_api.seguridad import tiene, usuario_actual
from abasto_api.servicio import BaseConsulta, BaseEntrada, Servicio, paginar, sobre_lista

__all__ = ['Servicio', 'BaseEntrada', 'BaseConsulta', 'ErrorApi', 'no_encontrado', 'prohibido',
           'usuario_actual', 'tiene', 'paginar', 'sobre_lista']
