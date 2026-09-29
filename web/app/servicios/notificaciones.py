"""
Notificaciones para los usuarios, guardadas en MongoDB (colección notifications).

Son documentos pequeños, sin relaciones y de estructura variable según el tipo,
por eso viven en MongoDB y no en PostgreSQL. Si MongoDB no responde, la
operación principal continúa: una notificación perdida no debe impedir que se
acepte un pedido.
"""
from datetime import datetime, timezone

from flask import current_app
from pymongo.errors import PyMongoError

from app import extensions


def _coleccion():
    return extensions.mongo_client[current_app.config['MONGO_DB']]['notifications']


def notificar(usuario_id, tipo, mensaje, url=None):
    try:
        _coleccion().insert_one({
            'schema_version': 1,
            'user_id': str(usuario_id),
            'type': tipo,
            'payload': {'mensaje': mensaje, 'url': url},
            'read': False,
            'created_at': datetime.now(timezone.utc),
        })
    except PyMongoError:
        current_app.logger.warning('MongoDB no disponible; no se guardó la notificación %s.', tipo)


def recientes(usuario_id, limite=6):
    try:
        cursor = (_coleccion()
                  .find({'user_id': str(usuario_id)})
                  .sort('created_at', -1)
                  .limit(limite))
        return [{'mensaje': d['payload'].get('mensaje'), 'url': d['payload'].get('url'),
                 'leida': d.get('read', False), 'fecha': d['created_at']} for d in cursor]
    except PyMongoError:
        return None


def marcar_leidas(usuario_id):
    try:
        _coleccion().update_many({'user_id': str(usuario_id), 'read': False}, {'$set': {'read': True}})
    except PyMongoError:
        pass
