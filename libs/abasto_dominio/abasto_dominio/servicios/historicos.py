"""
Históricos de algoritmos en MongoDB.

* `snapshots_precios`: fotografía diaria del precio al consumidor por zona,
  producto y sector (mínimo, promedio, máximo, muestras). PostgreSQL guarda
  cada precio capturado; aquí se guarda el resultado agregado, que es lo que
  consultan las tendencias sin recalcular sobre miles de renglones.
* `ejecuciones_analisis`: resultado de cada ejecución del análisis de
  cobertura (índice de acceso y brechas por zona), para ver cómo evoluciona
  una zona en el tiempo.

Ambas colecciones se ligan a PostgreSQL por `zona_id` y `producto_id`.
"""
from datetime import datetime, timedelta, timezone

from pymongo import UpdateOne
from sqlalchemy import func

from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, PrecioComercio, ProductoMaestro, ZonaMunicipal
from abasto_dominio.servicios.precios import SECTOR


def _snapshots():
    return extensiones.mongo_db()['snapshots_precios']


def _ejecuciones():
    return extensiones.mongo_db()['ejecuciones_analisis']


def generar_snapshot_precios(dias_ventana=7):
    """Calcula en PostgreSQL y guarda (upsert) la fotografía del día. Regresa cuántos documentos escribió."""
    hoy = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    filas = (db.session.query(Comercio.zona_id, ZonaMunicipal.nombre, PrecioComercio.producto_id,
                              ProductoMaestro.nombre, SECTOR,
                              func.min(PrecioComercio.precio), func.avg(PrecioComercio.precio),
                              func.max(PrecioComercio.precio), func.count(PrecioComercio.id))
             .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
             .join(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
             .join(ProductoMaestro, PrecioComercio.producto_id == ProductoMaestro.id)
             .filter(PrecioComercio.estado_validacion == 'VALIDADO', PrecioComercio.activo.is_(True),
                     PrecioComercio.fecha_registro >= func.now() - timedelta(days=dias_ventana))
             .group_by(Comercio.zona_id, ZonaMunicipal.nombre, PrecioComercio.producto_id,
                       ProductoMaestro.nombre, SECTOR)
             .all())
    operaciones = []
    for zona_id, zona, producto_id, producto, sector, minimo, promedio, maximo, muestras in filas:
        clave = {'fecha': hoy, 'zona_id': zona_id, 'producto_id': producto_id, 'sector': sector}
        operaciones.append(UpdateOne(clave, {'$set': {
            **clave, 'schema_version': 1, 'zona': zona, 'producto': producto,
            'minimo': float(minimo), 'promedio': round(float(promedio), 2), 'maximo': float(maximo),
            'muestras': muestras, 'ventana_dias': dias_ventana, 'generado_en': datetime.now(timezone.utc),
        }}, upsert=True))
    if operaciones:
        _snapshots().bulk_write(operaciones, ordered=False)
    return {'fecha': hoy, 'documentos': len(operaciones)}


def consultar_snapshots(producto_id=None, zona_id=None, sector=None, desde=None, pagina=1, por_pagina=50):
    filtro = {}
    if producto_id:
        filtro['producto_id'] = int(producto_id)
    if zona_id:
        filtro['zona_id'] = int(zona_id)
    if sector:
        filtro['sector'] = sector
    if desde:
        filtro['fecha'] = {'$gte': desde}
    total = _snapshots().count_documents(filtro)
    cursor = (_snapshots().find(filtro, {'_id': 0}).sort([('fecha', -1), ('zona_id', 1)])
              .skip((pagina - 1) * por_pagina).limit(por_pagina))
    return list(cursor), total


def tendencia_snapshots(producto_id, zona_id=None):
    """Agregación: promedio por fecha y sector (todas las zonas o una)."""
    filtro = {'producto_id': int(producto_id)}
    if zona_id:
        filtro['zona_id'] = int(zona_id)
    pipeline = [
        {'$match': filtro},
        {'$group': {'_id': {'fecha': '$fecha', 'sector': '$sector'},
                    'promedio': {'$avg': '$promedio'}, 'minimo': {'$min': '$minimo'},
                    'maximo': {'$max': '$maximo'}, 'muestras': {'$sum': '$muestras'}}},
        {'$sort': {'_id.fecha': 1}},
    ]
    return [{'fecha': r['_id']['fecha'], 'sector': r['_id']['sector'], 'promedio': round(r['promedio'], 2),
             'minimo': r['minimo'], 'maximo': r['maximo'], 'muestras': r['muestras']}
            for r in _snapshots().aggregate(pipeline)]


def registrar_ejecucion_analisis(indicadores_zonas, usuario_id=None):
    doc = {
        'schema_version': 1,
        'fecha': datetime.now(timezone.utc),
        'usuario_id': str(usuario_id) if usuario_id else None,
        'zonas': [{'zona_id': z['id'], 'zona': z['nombre'], 'indice_acceso': z['indice_acceso'],
                   'clasificacion': z['clasificacion'], 'canasta_critica': z['canasta_critica'],
                   'comercios': z['comercios']} for z in indicadores_zonas],
    }
    resultado = _ejecuciones().insert_one(doc)
    return str(resultado.inserted_id)


def evolucion_indice(zona_id=None, dias=90):
    """Agregación con $unwind: índice de acceso promedio por zona y día."""
    pipeline = [
        {'$match': {'fecha': {'$gte': datetime.now(timezone.utc) - timedelta(days=dias)}}},
        {'$unwind': '$zonas'},
    ]
    if zona_id:
        pipeline.append({'$match': {'zonas.zona_id': int(zona_id)}})
    pipeline += [
        {'$group': {'_id': {'zona_id': '$zonas.zona_id', 'zona': '$zonas.zona',
                            'dia': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$fecha'}}},
                    'indice_acceso': {'$avg': '$zonas.indice_acceso'}, 'ejecuciones': {'$sum': 1}}},
        {'$sort': {'_id.dia': 1, '_id.zona': 1}},
    ]
    return [{'zona_id': r['_id']['zona_id'], 'zona': r['_id']['zona'], 'dia': r['_id']['dia'],
             'indice_acceso': round(r['indice_acceso'], 1), 'ejecuciones': r['ejecuciones']}
            for r in _ejecuciones().aggregate(pipeline)]
