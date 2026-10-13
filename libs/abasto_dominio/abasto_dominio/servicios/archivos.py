"""
Archivos (fotos, evidencias, documentos y CSV) en MongoDB GridFS.

GridFS parte cada archivo en fragmentos de 255 KB (colecciones archivos.files
y archivos.chunks), así que no hay límite práctico de tamaño y el archivo viaja
con el respaldo de MongoDB. Los metadatos ligan el archivo con PostgreSQL:
`entidad` + `entidad_id` (p. ej. comercio y su UUID) y `usuario_id`.

En el despliegue en Google Cloud (cuarto parcial) el contenido podrá moverse a
Cloud Storage conservando estos metadatos.
"""
import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app
from gridfs.errors import NoFile

from abasto_dominio import extensiones
from abasto_dominio.servicios import ReglaNegocioError

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
}
ENTIDADES = ('comercio', 'producto', 'pedido', 'proveedor', 'importacion')


def _bucket():
    return extensiones.gridfs_archivos()


def _oid(archivo_id):
    try:
        return ObjectId(archivo_id)
    except (InvalidId, TypeError):
        return None


def _meta(archivo):
    m = archivo.metadata or {}
    return {
        'id': str(archivo._id),
        'nombre': archivo.filename,
        'tipo_mime': m.get('tipo_mime'),
        'tamano_bytes': archivo.length,
        'categoria': m.get('categoria'),
        'entidad': m.get('entidad'),
        'entidad_id': m.get('entidad_id'),
        'descripcion': m.get('descripcion'),
        'usuario_id': m.get('usuario_id'),
        'sha256': m.get('sha256'),
        'subido_en': archivo.upload_date,
    }


def guardar(contenido, nombre, tipo_mime, categoria, entidad, entidad_id, usuario_id, descripcion=None):
    """Valida y guarda el archivo; regresa sus metadatos."""
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

    archivo_id = _bucket().put(contenido, filename=nombre, metadata={
        'tipo_mime': tipo_mime, 'categoria': categoria, 'entidad': entidad, 'entidad_id': str(entidad_id),
        'usuario_id': str(usuario_id), 'descripcion': descripcion,
        'sha256': hashlib.sha256(contenido).hexdigest(),
        'subido_en': datetime.now(timezone.utc),
    })
    return obtener_metadatos(archivo_id)


def obtener_metadatos(archivo_id):
    oid = archivo_id if isinstance(archivo_id, ObjectId) else _oid(archivo_id)
    if not oid:
        return None
    try:
        return _meta(_bucket().get(oid))
    except NoFile:
        return None


def abrir(archivo_id):
    """Regresa (metadatos, archivo_gridfs) o (None, None)."""
    oid = _oid(archivo_id)
    if not oid:
        return None, None
    try:
        archivo = _bucket().get(oid)
    except NoFile:
        return None, None
    return _meta(archivo), archivo


def listar(entidad=None, entidad_id=None, categoria=None, usuario_id=None, pagina=1, por_pagina=20):
    filtro = {}
    if entidad:
        filtro['metadata.entidad'] = entidad
    if entidad_id:
        filtro['metadata.entidad_id'] = str(entidad_id)
    if categoria:
        filtro['metadata.categoria'] = categoria
    if usuario_id:
        filtro['metadata.usuario_id'] = str(usuario_id)
    coleccion = extensiones.mongo_db()['archivos.files']
    total = coleccion.count_documents(filtro)
    cursor = _bucket().find(filtro).sort('uploadDate', -1).skip((pagina - 1) * por_pagina).limit(por_pagina)
    return [_meta(a) for a in cursor], total


def eliminar(archivo_id):
    oid = _oid(archivo_id)
    if not oid or not _bucket().exists(oid):
        return False
    _bucket().delete(oid)
    return True


def uso_por_categoria():
    """Agregación sobre archivos.files: cuántos archivos y cuánto espacio por categoría."""
    pipeline = [
        {'$group': {'_id': '$metadata.categoria', 'archivos': {'$sum': 1}, 'bytes': {'$sum': '$length'}}},
        {'$sort': {'bytes': -1}},
    ]
    return [{'categoria': r['_id'], 'archivos': r['archivos'], 'bytes': r['bytes']}
            for r in extensiones.mongo_db()['archivos.files'].aggregate(pipeline)]
