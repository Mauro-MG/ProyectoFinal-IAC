"""
Notificaciones internas, guardadas en MongoDB (colección `notificaciones`).

Son documentos pequeños, de estructura variable según el tipo (un aviso de
pedido lleva folio y estado; uno de stock bajo lleva producto y existencia) y
sin relaciones que requieran joins: por eso viven en MongoDB. Se ligan a
PostgreSQL por `usuario_id` y por `entidad` ({tipo, id}).

El contador de no leídas se mantiene en Redis (`notif:no_leidas:{usuario}`)
para que la campana del web no consulte MongoDB en cada página.

`notificar()` es lo que llaman el web y los demás servicios: envía el aviso al
microservicio de notificaciones y, si no responde, lo guarda directo para no
perderlo. `crear()` es la escritura directa que usa el propio microservicio.
"""
from datetime import datetime, timedelta, timezone

import requests
from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app, has_app_context
from pymongo import DESCENDING
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from abasto_dominio import extensiones

TIPOS = ('pedido', 'stock_bajo', 'precio_atipico', 'comercio', 'importacion', 'sistema')
DIAS_RETENCION = 90


def _coleccion():
    return extensiones.mongo_db()['notificaciones']


def _clave_contador(usuario_id):
    return f'notif:no_leidas:{usuario_id}'


def _invalidar_contador(usuario_id):
    try:
        extensiones.redis_client.delete(_clave_contador(usuario_id))
    except RedisError:
        pass


def _a_dict(doc):
    return {
        'id': str(doc['_id']),
        'usuario_id': doc['usuario_id'],
        'tipo': doc['tipo'],
        'titulo': doc['titulo'],
        'mensaje': doc['mensaje'],
        'url': doc.get('url'),
        'entidad': doc.get('entidad'),
        'prioridad': doc.get('prioridad', 'normal'),
        'leida': doc.get('leida', False),
        'origen': doc.get('origen'),
        'creada_en': doc['creada_en'],
    }


def _oid(notificacion_id):
    try:
        return ObjectId(notificacion_id)
    except (InvalidId, TypeError):
        return None


# ---------------------------------------------------------------- escritura directa

def crear(usuario_id, tipo, titulo, mensaje, url=None, entidad=None, prioridad='normal', origen='web'):
    ahora = datetime.now(timezone.utc)
    doc = {
        'schema_version': 2,
        'usuario_id': str(usuario_id),
        'tipo': tipo,
        'titulo': titulo,
        'mensaje': mensaje,
        'url': url,
        'entidad': entidad,
        'prioridad': prioridad,
        'leida': False,
        'origen': origen,
        'creada_en': ahora,
        'expira_en': ahora + timedelta(days=DIAS_RETENCION),
    }
    resultado = _coleccion().insert_one(doc)
    _invalidar_contador(usuario_id)
    doc['_id'] = resultado.inserted_id
    return _a_dict(doc)


def listar(usuario_id, solo_no_leidas=False, tipo=None, pagina=1, por_pagina=20):
    filtro = {'usuario_id': str(usuario_id)}
    if solo_no_leidas:
        filtro['leida'] = False
    if tipo:
        filtro['tipo'] = tipo
    total = _coleccion().count_documents(filtro)
    cursor = (_coleccion().find(filtro).sort('creada_en', DESCENDING)
              .skip((pagina - 1) * por_pagina).limit(por_pagina))
    return [_a_dict(d) for d in cursor], total


def obtener(notificacion_id, usuario_id):
    oid = _oid(notificacion_id)
    doc = _coleccion().find_one({'_id': oid, 'usuario_id': str(usuario_id)}) if oid else None
    return _a_dict(doc) if doc else None


def contar_no_leidas(usuario_id):
    """Lee el contador de Redis; si no está, lo calcula en MongoDB y lo guarda 5 minutos."""
    try:
        guardado = extensiones.redis_client.get(_clave_contador(usuario_id))
        if guardado is not None:
            return int(guardado)
    except RedisError:
        pass
    total = _coleccion().count_documents({'usuario_id': str(usuario_id), 'leida': False})
    try:
        extensiones.redis_client.setex(_clave_contador(usuario_id), 300, total)
    except RedisError:
        pass
    return total


def marcar_leida(notificacion_id, usuario_id, leida=True):
    oid = _oid(notificacion_id)
    if not oid:
        return False
    resultado = _coleccion().update_one(
        {'_id': oid, 'usuario_id': str(usuario_id)},
        {'$set': {'leida': leida, 'leida_en': datetime.now(timezone.utc) if leida else None}})
    _invalidar_contador(usuario_id)
    return resultado.matched_count == 1


def marcar_todas(usuario_id):
    resultado = _coleccion().update_many({'usuario_id': str(usuario_id), 'leida': False},
                                         {'$set': {'leida': True, 'leida_en': datetime.now(timezone.utc)}})
    _invalidar_contador(usuario_id)
    return resultado.modified_count


def eliminar(notificacion_id, usuario_id):
    oid = _oid(notificacion_id)
    if not oid:
        return False
    resultado = _coleccion().delete_one({'_id': oid, 'usuario_id': str(usuario_id)})
    _invalidar_contador(usuario_id)
    return resultado.deleted_count == 1


def resumen(usuario_id=None, dias=30):
    """Agregación: cuántas notificaciones por tipo y cuántas siguen sin leer."""
    filtro = {'creada_en': {'$gte': datetime.now(timezone.utc) - timedelta(days=dias)}}
    if usuario_id:
        filtro['usuario_id'] = str(usuario_id)
    pipeline = [
        {'$match': filtro},
        {'$group': {'_id': '$tipo', 'total': {'$sum': 1},
                    'no_leidas': {'$sum': {'$cond': [{'$eq': ['$leida', False]}, 1, 0]}},
                    'ultima': {'$max': '$creada_en'}}},
        {'$sort': {'total': -1}},
    ]
    return [{'tipo': r['_id'], 'total': r['total'], 'no_leidas': r['no_leidas'], 'ultima': r['ultima']}
            for r in _coleccion().aggregate(pipeline)]


def recientes(usuario_id, limite=6):
    """Para el panel del web. Regresa None si MongoDB no responde."""
    try:
        items, _ = listar(usuario_id, por_pagina=limite)
        return items
    except PyMongoError:
        return None


# ---------------------------------------------------------------- envío (web y otros servicios)

def notificar(usuario_ids, tipo, titulo, mensaje, url=None, entidad=None, prioridad='normal', origen=None):
    """
    Envía la notificación a cada usuario a través del microservicio de
    notificaciones. Si el servicio no está configurado o no responde, la
    guarda directo en MongoDB. Nunca lanza excepción: un aviso perdido no debe
    deshacer la operación de negocio que lo originó.

    `origen` por omisión es el componente que llama (ms-pedidos -> "pedidos", el web -> "web").
    """
    if origen is None:
        nombre = current_app.name if has_app_context() else ''
        origen = nombre[3:] if nombre.startswith('ms-') else 'web'
    if isinstance(usuario_ids, (str, bytes)) or not hasattr(usuario_ids, '__iter__'):
        usuario_ids = [usuario_ids]
    usuario_ids = [str(u) for u in usuario_ids if u]
    if not usuario_ids:
        return 0

    if has_app_context() and current_app.config.get('NOTIFICACIONES_VIA_SERVICIO'):
        try:
            from abasto_dominio.sesiones import token_servicio
            token = token_servicio(origen, ['notificaciones.crear'])
            respuesta = requests.post(
                f"{current_app.config['MS_NOTIFICACIONES_URL']}/api/v1/notificaciones/lote",
                json={'usuarios': usuario_ids, 'tipo': tipo, 'titulo': titulo, 'mensaje': mensaje,
                      'url': url, 'entidad': entidad, 'prioridad': prioridad, 'origen': origen},
                headers={'Authorization': f'Bearer {token}'},
                timeout=current_app.config.get('MS_TIMEOUT_SEGUNDOS', 3))
            if respuesta.status_code == 201:
                return len(usuario_ids)
            current_app.logger.warning('ms-notificaciones respondió %s; se guarda directo.', respuesta.status_code)
        except (requests.RequestException, RedisError) as error:
            current_app.logger.warning('ms-notificaciones no disponible (%s); se guarda directo.', error)

    enviadas = 0
    for usuario_id in usuario_ids:
        try:
            crear(usuario_id, tipo, titulo, mensaje, url, entidad, prioridad, origen)
            enviadas += 1
        except PyMongoError:
            if has_app_context():
                current_app.logger.warning('MongoDB no disponible; no se guardó la notificación %s.', tipo)
    return enviadas
