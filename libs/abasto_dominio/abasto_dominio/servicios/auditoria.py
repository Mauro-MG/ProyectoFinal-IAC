"""
Registro de auditoría de las operaciones que cambian datos.

1. PostgreSQL (auditoria_eventos): el evento se agrega a la MISMA transacción de la
   operación; si la operación se revierte, el evento también. La tabla es de sólo
   inserción (un trigger impide UPDATE y DELETE).
2. MongoDB (eventos_auditoria): cuando la transacción se confirma, el evento se
   copia a la bitácora centralizada que consulta ms-auditoria, con el servicio que
   lo generó, el X-Correlation-ID de la petición y la lista de campos cambiados.
   Así se puede seguir una operación distribuida entre varios servicios.

Si MongoDB no responde, la operación NO falla (PostgreSQL ya tiene el evento); la
copia faltante se puede reconstruir desde auditoria_eventos.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from flask import current_app, g, has_app_context, has_request_context, request
from pymongo.errors import PyMongoError
from sqlalchemy import event
from sqlalchemy.orm import Session

from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import AuditoriaEvento

COLECCION = 'eventos_auditoria'
_PENDIENTES = 'auditoria_pendiente'   # eventos agregados en la transacción en curso
_LISTOS = 'auditoria_lista'           # eventos ya con id, esperando el commit


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


def cambios(anteriores, nuevos):
    """[{campo, antes, despues}] de los campos que realmente cambiaron."""
    anteriores, nuevos = anteriores or {}, nuevos or {}
    return [{'campo': k, 'antes': anteriores.get(k), 'despues': nuevos.get(k)}
            for k in sorted(set(anteriores) | set(nuevos)) if anteriores.get(k) != nuevos.get(k)]


def _componente():
    if not has_app_context():
        return 'desconocido'
    return current_app.name if current_app.name.startswith('ms-') else 'web'


def _contexto():
    if not has_request_context():
        return {'servicio': _componente(), 'correlation_id': None, 'metodo': None, 'ruta': None, 'rol': None}
    return {
        'servicio': _componente(),
        'correlation_id': getattr(g, 'correlation_id', None),
        'metodo': request.method,
        'ruta': request.path,
        'rol': (getattr(g, 'claims', None) or {}).get('rol'),
    }


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
    db.session.info.setdefault(_PENDIENTES, []).append((evento, _contexto()))
    return evento


def documento_mongo(evento, contexto):
    return {
        'id_postgres': evento.id,
        **contexto,
        'usuario_id': str(evento.usuario_id) if evento.usuario_id else None,
        'tipo_evento': evento.tipo_evento,
        'entidad': evento.entidad,
        'entidad_id': evento.entidad_id,
        'descripcion': evento.descripcion,
        'cambios': cambios(evento.datos_anteriores, evento.datos_nuevos),
        'datos_anteriores': evento.datos_anteriores,
        'datos_nuevos': evento.datos_nuevos,
        'ip': str(evento.ip_address) if evento.ip_address else None,
        'fecha': datetime.now(timezone.utc),
    }


@event.listens_for(Session, 'after_flush')
def _tras_flush(sesion, _contexto_flush):
    # Después del flush el evento ya tiene id; el documento se arma aquí porque después del
    # commit los atributos expiran y leerlos obligaría a consultar otra vez la base.
    pendientes = sesion.info.pop(_PENDIENTES, [])
    listos = sesion.info.setdefault(_LISTOS, [])
    for evento, contexto in pendientes:
        if evento.id is None:
            sesion.info.setdefault(_PENDIENTES, []).append((evento, contexto))
        else:
            listos.append(documento_mongo(evento, contexto))


@event.listens_for(Session, 'after_commit')
def _tras_commit(sesion):
    documentos = sesion.info.pop(_LISTOS, [])
    if not documentos or extensiones.mongo_client is None or not has_app_context():
        return
    try:
        extensiones.mongo_db()[COLECCION].insert_many(documentos, ordered=False)
    except PyMongoError:
        pass   # PostgreSQL conserva el evento; la copia centralizada se puede reconstruir


@event.listens_for(Session, 'after_rollback')
def _tras_rollback(sesion):
    sesion.info.pop(_PENDIENTES, None)
    sesion.info.pop(_LISTOS, None)
