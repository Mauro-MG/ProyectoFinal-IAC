"""
Eventos del pedido de abasto en MongoDB (colección `eventos_pedido`).

PostgreSQL guarda el estado actual del pedido y su historial mínimo; aquí se
guarda cada transición como documento completo (quién, cuándo, partidas y
montos en ese momento). Es información de alta frecuencia y sólo de escritura,
y sirve para calcular el desempeño de cada proveedor con agregaciones:
tiempo de respuesta, tiempo de entrega y tasa de rechazo.

Relación con PostgreSQL: `pedido_id`, `comercio_id`, `proveedor_id` y
`producto_id` son los identificadores de las tablas correspondientes.
"""
from datetime import datetime, timedelta, timezone

from flask import current_app, has_app_context
from pymongo.errors import PyMongoError

from abasto_dominio import extensiones


def _coleccion():
    return extensiones.mongo_db()['eventos_pedido']


def registrar(pedido, accion, estado_anterior, estado_nuevo, usuario, comentario=None):
    """Guarda la transición. Si MongoDB falla, se registra en el log y la operación sigue."""
    doc = {
        'schema_version': 1,
        'pedido_id': str(pedido.id),
        'folio': pedido.folio_legible,
        'comercio_id': str(pedido.comercio_id),
        'proveedor_id': str(pedido.proveedor_id),
        'zona_id': pedido.comercio.zona_id,
        'accion': accion,
        'estado_anterior': estado_anterior,
        'estado_nuevo': estado_nuevo,
        'actor': {'usuario_id': str(usuario.id), 'rol': usuario.rol.nombre},
        'comentario': comentario,
        'subtotal': float(pedido.subtotal or 0),
        'partidas': [{'producto_id': d.producto_id, 'producto': d.producto.nombre,
                      'cantidad': float(d.cantidad), 'precio_unitario': float(d.precio_unitario)}
                     for d in pedido.detalles],
        'fecha': datetime.now(timezone.utc),
    }
    try:
        _coleccion().insert_one(doc)
    except PyMongoError as error:
        if has_app_context():
            current_app.logger.warning('No se guardó el evento del pedido %s en MongoDB: %s', pedido.id, error)


def linea_tiempo(pedido_id):
    cursor = _coleccion().find({'pedido_id': str(pedido_id)}, {'_id': 0}).sort('fecha', 1)
    return list(cursor)


def desempeno_proveedores(dias=90, proveedor_id=None):
    """
    Pipeline de agregación:
      1. eventos de los últimos `dias` días;
      2. por pedido, la fecha en que entró a cada estado;
      3. horas de respuesta (ENVIADO -> ACEPTADO/RECHAZADO) y de entrega (ACEPTADO -> ENTREGADO);
      4. por proveedor: promedios, pedidos atendidos y tasa de rechazo.
    """
    filtro = {'fecha': {'$gte': datetime.now(timezone.utc) - timedelta(days=dias)}}
    if proveedor_id:
        filtro['proveedor_id'] = str(proveedor_id)

    def fecha_de(*estados):
        return {'$min': {'$cond': [{'$in': ['$estado_nuevo', list(estados)]}, '$fecha', None]}}

    horas = 1000 * 60 * 60
    pipeline = [
        {'$match': filtro},
        {'$group': {
            '_id': '$pedido_id',
            'proveedor_id': {'$first': '$proveedor_id'},
            'enviado': fecha_de('ENVIADO'),
            'respondido': fecha_de('ACEPTADO', 'RECHAZADO'),
            'aceptado': fecha_de('ACEPTADO'),
            'entregado': fecha_de('ENTREGADO'),
            'rechazado': {'$max': {'$cond': [{'$eq': ['$estado_nuevo', 'RECHAZADO']}, 1, 0]}},
            'monto': {'$max': '$subtotal'},
        }},
        {'$match': {'enviado': {'$ne': None}}},
        {'$project': {
            'proveedor_id': 1, 'rechazado': 1, 'monto': 1,
            'entregado': {'$cond': [{'$ne': ['$entregado', None]}, 1, 0]},
            'horas_respuesta': {'$cond': [{'$ne': ['$respondido', None]},
                                          {'$divide': [{'$subtract': ['$respondido', '$enviado']}, horas]}, None]},
            'horas_entrega': {'$cond': [{'$and': [{'$ne': ['$entregado', None]}, {'$ne': ['$aceptado', None]}]},
                                        {'$divide': [{'$subtract': ['$entregado', '$aceptado']}, horas]}, None]},
        }},
        {'$group': {
            '_id': '$proveedor_id',
            'pedidos': {'$sum': 1},
            'entregados': {'$sum': '$entregado'},
            'rechazados': {'$sum': '$rechazado'},
            'monto_total': {'$sum': '$monto'},
            'horas_respuesta_prom': {'$avg': '$horas_respuesta'},
            'horas_entrega_prom': {'$avg': '$horas_entrega'},
        }},
        {'$addFields': {'tasa_rechazo': {'$cond': [{'$gt': ['$pedidos', 0]},
                                                   {'$divide': ['$rechazados', '$pedidos']}, 0]}}},
        {'$sort': {'pedidos': -1}},
    ]
    resultado = []
    for r in _coleccion().aggregate(pipeline):
        resultado.append({
            'proveedor_id': r['_id'],
            'pedidos': r['pedidos'],
            'entregados': r['entregados'],
            'rechazados': r['rechazados'],
            'monto_total': round(r['monto_total'] or 0, 2),
            'horas_respuesta_prom': round(r['horas_respuesta_prom'], 1) if r['horas_respuesta_prom'] is not None else None,
            'horas_entrega_prom': round(r['horas_entrega_prom'], 1) if r['horas_entrega_prom'] is not None else None,
            'tasa_rechazo': round(r['tasa_rechazo'] * 100, 1),
        })
    return resultado


def productos_mas_pedidos(dias=30, zona_id=None, limite=10):
    """Agregación con $unwind: productos más pedidos (cantidad) en pedidos enviados."""
    filtro = {'estado_nuevo': 'ENVIADO', 'fecha': {'$gte': datetime.now(timezone.utc) - timedelta(days=dias)}}
    if zona_id:
        filtro['zona_id'] = int(zona_id)
    pipeline = [
        {'$match': filtro},
        {'$unwind': '$partidas'},
        {'$group': {'_id': '$partidas.producto_id', 'producto': {'$first': '$partidas.producto'},
                    'cantidad': {'$sum': '$partidas.cantidad'}, 'pedidos': {'$sum': 1}}},
        {'$sort': {'cantidad': -1}},
        {'$limit': limite},
    ]
    return [{'producto_id': r['_id'], 'producto': r['producto'], 'cantidad': r['cantidad'], 'pedidos': r['pedidos']}
            for r in _coleccion().aggregate(pipeline)]
