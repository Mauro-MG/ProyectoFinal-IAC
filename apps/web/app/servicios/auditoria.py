from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from flask import has_request_context, request

from app.extensions import db
from app.models import AuditoriaEvento


def _a_json(valor):
    if isinstance(valor, dict):
        return {k: _a_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_a_json(v) for v in valor]
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (UUID, datetime, date)):
        return str(valor)
    return valor


def registrar_evento(usuario_id, tipo_evento, entidad, entidad_id, descripcion,
                     datos_anteriores=None, datos_nuevos=None):
    """Agrega el evento a la sesión actual; se guarda con el commit de la operación."""
    evento = AuditoriaEvento(
        usuario_id=usuario_id,
        tipo_evento=tipo_evento,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        descripcion=descripcion,
        datos_anteriores=_a_json(datos_anteriores),
        datos_nuevos=_a_json(datos_nuevos),
        ip_address=request.remote_addr if has_request_context() else None,
        user_agent=request.user_agent.string if has_request_context() else None,
    )
    db.session.add(evento)
    return evento
