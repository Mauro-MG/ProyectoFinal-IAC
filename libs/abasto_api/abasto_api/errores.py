"""
Errores estandarizados de todos los servicios.

Cuerpo (JSON; en XML el elemento raíz es <error>):
    {
      "error": {
        "codigo": "pedido_minimo",             identificador estable para el cliente
        "mensaje": "El pedido mínimo es...",    texto para mostrar al usuario
        "detalles": [...],                       errores de validación por campo (opcional)
        "status": 409,
        "ruta": "/api/v1/pedidos/.../acciones/enviar",
        "correlation_id": "4f1c...",
        "fecha": "2026-10-12T18:20:00+00:00"
      }
    }

Códigos HTTP: 400 entrada inválida, 401 sin token / token inválido o revocado,
403 sin permiso, 404 no existe, 405 método no permitido, 409 regla de negocio,
413 archivo demasiado grande, 415 tipo de contenido no soportado,
422 datos con formato correcto pero no válidos, 429 límite de peticiones,
500 error interno, 503 dependencia no disponible.
"""
from datetime import datetime, timezone

from flask import g, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from abasto_dominio.extensiones import db
from abasto_dominio.servicios import ReglaNegocioError
from abasto_dominio.sesiones import ErrorSesion

from abasto_api.formatos import responder


class ErrorApi(Exception):
    def __init__(self, status, codigo, mensaje, detalles=None, headers=None):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalles = detalles
        self.headers = headers


def no_encontrado(recurso='El recurso'):
    return ErrorApi(404, 'no_encontrado', f'{recurso} no existe.')


def prohibido(mensaje='No tienes permiso para esta operación.'):
    return ErrorApi(403, 'sin_permiso', mensaje)


def cuerpo_error(status, codigo, mensaje, detalles=None):
    error = {
        'codigo': codigo,
        'mensaje': mensaje,
        'status': status,
        'ruta': request.path,
        'correlation_id': getattr(g, 'correlation_id', None),
        'fecha': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    if detalles:
        error['detalles'] = detalles
    return {'error': error}


def _respuesta(status, codigo, mensaje, detalles=None, headers=None):
    g.codigo_error = codigo
    return responder(cuerpo_error(status, codigo, mensaje, detalles), status=status, raiz='error', headers=headers)


def _detalles_pydantic(error):
    return [{'campo': '.'.join(str(p) for p in e['loc']) or 'cuerpo', 'mensaje': e['msg'], 'tipo': e['type']}
            for e in error.errors(include_url=False, include_context=False)]


def registrar_manejadores(app):
    @app.errorhandler(ErrorApi)
    def _error_api(error):
        db.session.rollback()
        return _respuesta(error.status, error.codigo, error.mensaje, error.detalles, error.headers)

    @app.errorhandler(ValidationError)
    def _validacion(error):
        return _respuesta(422, 'datos_invalidos', 'Los datos enviados no son válidos.', _detalles_pydantic(error))

    @app.errorhandler(ReglaNegocioError)
    def _negocio(error):
        db.session.rollback()
        return _respuesta(409, 'regla_negocio', str(error))

    @app.errorhandler(ErrorSesion)
    def _sesion(error):
        headers = {'WWW-Authenticate': 'Bearer'} if error.codigo_http == 401 else None
        return _respuesta(error.codigo_http, error.codigo, error.mensaje, headers=headers)

    @app.errorhandler(HTTPException)
    def _http(error):
        mensajes = {
            404: ('no_encontrado', 'La ruta no existe en este servicio.'),
            405: ('metodo_no_permitido', f'El método {request.method} no está permitido en esta ruta.'),
            413: ('archivo_muy_grande', 'El archivo o cuerpo excede el tamaño permitido.'),
            415: ('tipo_no_soportado', 'Usa Content-Type application/json o application/xml.'),
        }
        codigo, mensaje = mensajes.get(error.code, (f'http_{error.code}', error.description))
        return _respuesta(error.code, codigo, mensaje)

    @app.errorhandler(Exception)
    def _interno(error):
        db.session.rollback()
        app.logger.exception('Error no controlado: %s', error)
        return _respuesta(500, 'error_interno', 'Ocurrió un error interno; quedó registrado con el correlation_id.')
