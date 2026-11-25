"""
Archivos del sistema: contenido en Google Cloud Storage, metadatos en MongoDB.

Cada archivo es un objeto en el bucket privado (ver servicios/almacenamiento.py) y
un documento en la colección `archivos_metadatos` con su identificador, objeto,
tipo MIME, tamaño, SHA-256, propietario, entidad a la que pertenece, privacidad,
estado y fechas. La base nunca guarda el contenido.

Compatibilidad: los archivos que se subieron antes vivían en GridFS (archivos.files /
archivos.chunks). Mientras no se migren se siguen leyendo de ahí con el mismo id;
`migrar_desde_gridfs()` (scripts/migrar_archivos_a_gcs.py) los copia al bucket sin borrar nada.

Nombre del objeto: <categoria>/<entidad>/<entidad_id>/<id><ext>. El nombre que puso
el usuario solo se guarda (limpio) como metadato y para la descarga; nunca forma la ruta.
"""
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app
from gridfs.errors import NoFile

from abasto_dominio import extensiones
from abasto_dominio.servicios import ReglaNegocioError, almacenamiento
from abasto_dominio.servicios.almacenamiento import AlmacenamientoNoDisponible

TIPOS_PERMITIDOS = {
    'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp',
    'application/pdf': '.pdf', 'text/csv': '.csv',
}
CATEGORIAS = {
    'foto_comercio': 'Foto del comercio',
    'evidencia_validacion': 'Evidencia de validación',
    'foto_producto': 'Foto de producto',
    'comprobante_pedido': 'Comprobante de pedido',
    'importacion_csv': 'Archivo de importación',
    'documento': 'Documento',
    'documento_fiscal': 'Documento fiscal',
    'evidencia_entrega': 'Evidencia de entrega',
    'comprobante_venta': 'Comprobante de venta',
}
ENTIDADES = ('comercio', 'producto', 'pedido', 'proveedor', 'importacion', 'entrega', 'venta')
VISIBILIDADES = ('privada', 'entidad', 'publica')
COLECCION = 'archivos_metadatos'

__all__ = ['AlmacenamientoNoDisponible', 'guardar', 'obtener_metadatos', 'leer', 'url_temporal', 'listar', 'cambiar',
           'eliminar', 'uso_por_categoria', 'pendientes_de_migrar', 'migrar_desde_gridfs', 'limpiar_nombre']


def _coleccion():
    return extensiones.mongo_db()[COLECCION]


def _gridfs():
    return extensiones.gridfs_archivos()


def _oid(archivo_id):
    try:
        return archivo_id if isinstance(archivo_id, ObjectId) else ObjectId(archivo_id)
    except (InvalidId, TypeError):
        return None


def limpiar_nombre(nombre):
    """Nombre seguro para mostrar y para Content-Disposition: sin rutas, comillas ni caracteres de control."""
    nombre = unicodedata.normalize('NFC', (nombre or 'archivo').replace('\\', '/').split('/')[-1])
    nombre = re.sub(r'[\x00-\x1f\x7f"<>:|?*;]', '', nombre).strip(' .') or 'archivo'
    base, punto, ext = nombre.rpartition('.')
    if punto and base and len(ext) <= 5:
        return f'{base[:140]}.{ext}'
    return nombre[:150]


def _meta(doc):
    return {
        'id': str(doc['_id']), 'nombre': doc['nombre'], 'tipo_mime': doc['tipo_mime'],
        'tamano_bytes': doc['tamano_bytes'], 'categoria': doc.get('categoria'), 'entidad': doc.get('entidad'),
        'entidad_id': doc.get('entidad_id'), 'descripcion': doc.get('descripcion'), 'usuario_id': doc.get('usuario_id'),
        'sha256': doc.get('sha256'), 'visibilidad': doc.get('visibilidad', 'entidad'), 'estado': doc.get('estado'),
        'almacenamiento': doc.get('almacenamiento', 'gcs'), 'objeto': doc.get('objeto'),
        'subido_en': doc.get('subido_en'),
    }


def _meta_gridfs(archivo):
    """Archivo anterior a GCS, todavía en GridFS."""
    m = archivo.metadata or {}
    return {
        'id': str(archivo._id), 'nombre': archivo.filename, 'tipo_mime': m.get('tipo_mime'),
        'tamano_bytes': archivo.length, 'categoria': m.get('categoria'), 'entidad': m.get('entidad'),
        'entidad_id': m.get('entidad_id'), 'descripcion': m.get('descripcion'), 'usuario_id': m.get('usuario_id'),
        'sha256': m.get('sha256'), 'visibilidad': m.get('visibilidad', 'entidad'), 'estado': 'activo',
        'almacenamiento': 'gridfs', 'objeto': None, 'subido_en': archivo.upload_date,
    }


def validar(contenido, tipo_mime, categoria, entidad):
    if tipo_mime not in TIPOS_PERMITIDOS:
        raise ReglaNegocioError('Tipo de archivo no permitido. Usa JPG, PNG, WEBP, PDF o CSV.')
    if categoria not in CATEGORIAS:
        raise ReglaNegocioError('Categoría de archivo no válida.')
    if entidad not in ENTIDADES:
        raise ReglaNegocioError('Entidad no válida para el archivo.')
    limite = current_app.config.get('MAX_CONTENT_LENGTH') or 10 * 1024 * 1024
    if not contenido:
        raise ReglaNegocioError('El archivo está vacío.')
    if len(contenido) > limite:
        raise ReglaNegocioError(f'El archivo excede el máximo de {limite // (1024 * 1024)} MB.')


def guardar(contenido, nombre, tipo_mime, categoria, entidad, entidad_id, usuario_id, descripcion=None,
            visibilidad='entidad'):
    """Sube el contenido al bucket y después registra los metadatos. Si el bucket falla no queda registro;
    si falla el registro se borra el objeto: nunca quedan metadatos sin archivo ni archivos sin dueño."""
    validar(contenido, tipo_mime, categoria, entidad)
    if visibilidad not in VISIBILIDADES:
        raise ReglaNegocioError('Visibilidad no válida.')
    archivo_id = ObjectId()
    objeto = f'{categoria}/{entidad}/{entidad_id}/{archivo_id}{TIPOS_PERMITIDOS[tipo_mime]}'
    sha256 = hashlib.sha256(contenido).hexdigest()
    almacenamiento.subir(objeto, contenido, tipo_mime, {'sha256': sha256, 'usuario_id': usuario_id,
                                                         'entidad': entidad, 'entidad_id': entidad_id})
    doc = {
        '_id': archivo_id, 'nombre': limpiar_nombre(nombre), 'tipo_mime': tipo_mime, 'tamano_bytes': len(contenido),
        'sha256': sha256, 'categoria': categoria, 'entidad': entidad, 'entidad_id': str(entidad_id),
        'usuario_id': str(usuario_id), 'descripcion': descripcion, 'visibilidad': visibilidad, 'estado': 'activo',
        'almacenamiento': 'gcs', 'bucket': almacenamiento.bucket().name, 'objeto': objeto,
        'subido_en': datetime.now(timezone.utc),
    }
    try:
        _coleccion().insert_one(doc)
    except Exception:
        almacenamiento.borrar(objeto)
        raise
    return _meta(doc)


def obtener_metadatos(archivo_id):
    oid = _oid(archivo_id)
    if not oid:
        return None
    doc = _coleccion().find_one({'_id': oid})
    if doc:
        return _meta(doc) if doc.get('estado') == 'activo' else None
    try:
        return _meta_gridfs(_gridfs().get(oid))
    except NoFile:
        return None


def leer(meta):
    """Contenido del archivo (descarga a través del servicio). None si el objeto ya no existe."""
    if meta['almacenamiento'] == 'gridfs':
        try:
            return _gridfs().get(_oid(meta['id'])).read()
        except NoFile:
            return None
    return almacenamiento.descargar(meta['objeto'])


def url_temporal(meta, minutos=10):
    """URL firmada de solo lectura. Los archivos que siguen en GridFS no tienen URL directa (se descargan por
    el servicio) hasta que se migren."""
    if meta['almacenamiento'] != 'gcs':
        return None, None
    return almacenamiento.url_firmada(meta['objeto'], meta['nombre'], meta['tipo_mime'], minutos)


def _migrados():
    return [d['_id'] for d in _coleccion().find({}, {'_id': 1})]


def listar(entidad=None, entidad_id=None, categoria=None, usuario_id=None, pagina=1, por_pagina=20):
    filtro = {'estado': 'activo'}
    for clave, valor in (('entidad', entidad), ('entidad_id', entidad_id), ('categoria', categoria),
                         ('usuario_id', usuario_id)):
        if valor:
            filtro[clave] = str(valor)
    total = _coleccion().count_documents(filtro)
    items = [_meta(d) for d in _coleccion().find(filtro).sort('subido_en', -1)
             .skip((pagina - 1) * por_pagina).limit(por_pagina)]
    # Archivos anteriores que siguen en GridFS (dejan de aparecer aquí en cuanto se migran)
    filtro_gridfs = {f'metadata.{k}': v for k, v in filtro.items() if k != 'estado'}
    filtro_gridfs['_id'] = {'$nin': _migrados()}
    anteriores = [_meta_gridfs(a) for a in _gridfs().find(filtro_gridfs).sort('uploadDate', -1).limit(por_pagina)]
    return items + anteriores[:max(0, por_pagina - len(items))], total + len(anteriores)


def cambiar(archivo_id, cambios):
    """Descripción o visibilidad."""
    meta = obtener_metadatos(archivo_id)
    if meta['almacenamiento'] == 'gridfs':
        extensiones.mongo_db()['archivos.files'].update_one(
            {'_id': _oid(archivo_id)}, {'$set': {f'metadata.{k}': v for k, v in cambios.items()}})
    else:
        _coleccion().update_one({'_id': _oid(archivo_id)}, {'$set': cambios})
    return obtener_metadatos(archivo_id)


def eliminar(archivo_id):
    """Baja: el objeto se borra del bucket y los metadatos quedan con estado «eliminado» para la auditoría."""
    meta = obtener_metadatos(archivo_id)
    if not meta:
        return False
    if meta['almacenamiento'] == 'gridfs':
        _gridfs().delete(_oid(archivo_id))
        return True
    almacenamiento.borrar(meta['objeto'])
    _coleccion().update_one({'_id': _oid(archivo_id)},
                            {'$set': {'estado': 'eliminado', 'eliminado_en': datetime.now(timezone.utc)}})
    return True


def uso_por_categoria():
    """Archivos y espacio por categoría (bucket y, mientras existan, los de GridFS)."""
    totales = {}
    for r in _coleccion().aggregate([{'$match': {'estado': 'activo'}},
                                     {'$group': {'_id': '$categoria', 'n': {'$sum': 1}, 'b': {'$sum': '$tamano_bytes'}}}]):
        totales[r['_id']] = [r['n'], r['b']]
    for r in extensiones.mongo_db()['archivos.files'].aggregate([
            {'$match': {'_id': {'$nin': _migrados()}}},
            {'$group': {'_id': '$metadata.categoria', 'n': {'$sum': 1}, 'b': {'$sum': '$length'}}}]):
        n, b = totales.get(r['_id'], [0, 0])
        totales[r['_id']] = [n + r['n'], b + r['b']]
    return sorted(({'categoria': c, 'archivos': n, 'bytes': b} for c, (n, b) in totales.items()),
                  key=lambda f: -f['bytes'])


def pendientes_de_migrar():
    return extensiones.mongo_db()['archivos.files'].count_documents({'_id': {'$nin': _migrados()}})


def migrar_desde_gridfs(limite=None):
    """Copia al bucket los archivos de GridFS que aún no están, con el mismo id. No borra nada de GridFS:
    descarga el objeto subido, comprueba su SHA-256 y solo entonces registra los metadatos. Se puede repetir
    sin duplicar (lo ya migrado se salta)."""
    resultado = {'migrados': 0, 'errores': []}
    for archivo in _gridfs().find({'_id': {'$nin': _migrados()}}).limit(limite or 0):
        m = archivo.metadata or {}
        contenido = archivo.read()
        sha256 = hashlib.sha256(contenido).hexdigest()
        tipo = m.get('tipo_mime') or archivo.content_type
        if tipo not in TIPOS_PERMITIDOS or (m.get('sha256') and m['sha256'] != sha256):
            resultado['errores'].append({'id': str(archivo._id), 'error': 'tipo no permitido o huella distinta'})
            continue
        objeto = (f"{m.get('categoria', 'documento')}/{m.get('entidad', 'comercio')}/{m.get('entidad_id', 'sin')}/"
                  f'{archivo._id}{TIPOS_PERMITIDOS[tipo]}')
        try:
            if not almacenamiento.existe(objeto):
                almacenamiento.subir(objeto, contenido, tipo, {'sha256': sha256, 'migrado_de': 'gridfs'})
            copia = almacenamiento.descargar(objeto)
            if copia is None or hashlib.sha256(copia).hexdigest() != sha256:
                raise AlmacenamientoNoDisponible('la copia en el bucket no coincide con el original')
        except AlmacenamientoNoDisponible as error:
            resultado['errores'].append({'id': str(archivo._id), 'error': str(error)})
            continue
        _coleccion().insert_one({
            '_id': archivo._id, 'nombre': limpiar_nombre(archivo.filename), 'tipo_mime': tipo,
            'tamano_bytes': archivo.length, 'sha256': sha256, 'categoria': m.get('categoria'),
            'entidad': m.get('entidad'), 'entidad_id': m.get('entidad_id'), 'usuario_id': m.get('usuario_id'),
            'descripcion': m.get('descripcion'), 'visibilidad': m.get('visibilidad', 'entidad'), 'estado': 'activo',
            'almacenamiento': 'gcs', 'bucket': almacenamiento.bucket().name, 'objeto': objeto,
            'subido_en': archivo.upload_date, 'migrado_en': datetime.now(timezone.utc)})
        resultado['migrados'] += 1
    return resultado
