"""
ms-documentos: archivos del sistema en Google Cloud Storage.

Es DUEÑO del bucket privado de archivos y de la colección `archivos_metadatos` (MongoDB): el
contenido va al bucket y la base guarda solo identificador, objeto, tipo, tamaño, SHA-256,
propietario, entidad, privacidad, estado y fechas. Otros servicios (ms-entregas, ms-comercios,
el web) suben aquí el archivo y guardan solo su id.

- Acceso al contenido, siempre después de revisar el permiso sobre el recurso:
    GET /documentos/{id}/url        URL firmada V4 que vence en 1 a 60 minutos (el bucket NO es público)
    GET /documentos/{id}/contenido  descarga a través del servicio (compatibilidad y archivos sin migrar)
- Si Cloud Storage no responde: 503 almacenamiento_no_disponible y no queda ningún registro a medias.
- Archivos anteriores en GridFS: se siguen sirviendo con el mismo id hasta migrarlos con
  POST /documentos/migracion (no destructiva: copia, verifica el SHA-256 y conserva el original).

- Carga (multipart/form-data) de imágenes, CSV, comprobantes, documentos y evidencias.
- Validación del tipo REAL: se revisan los primeros bytes del archivo (firma), no sólo el
  Content-Type que manda el cliente; tamaño máximo configurable (DOCUMENTO_MAX_MB).
- Metadatos: entidad y su id, categoría, quién lo subió, SHA-256, visibilidad.
- Control de acceso por entidad:
    privada   sólo quien lo subió (y el administrador)
    entidad   además, las partes de la entidad: dueño del comercio, comercio y proveedor
              del pedido o la entrega, la empresa proveedora; y quien tiene comercios.ver_todos
    publica   cualquier usuario autenticado (p. ej. la foto de un producto)
"""
from pathlib import Path
from uuid import UUID

from flask import Response, g, request
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado, prohibido, sobre_lista, tiene
from abasto_dominio.extensiones import db
from abasto_dominio.servicios import archivos
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.parametros import parametro

from esquemas import CONTRATOS_XML, DocumentoCambio, DocumentosConsulta, UrlConsulta

srv = Servicio('documentos', 'Documentos',
               'Carga, consulta y administración de imágenes, archivos CSV, comprobantes, documentos de comercio y '
               'evidencias en Google Cloud Storage (bucket privado y URLs firmadas), con validación del tipo real y '
               'del tamaño, metadatos y control de acceso por recurso.',
               xsd=Path(__file__).parent / 'xsd' / 'documentos.xsd', contratos=CONTRATOS_XML,
               dependencias=('postgres', 'redis', 'mongodb', 'storage'), opcionales=())
app = srv.app


# Firma (primeros bytes) de cada tipo permitido
FIRMAS = {
    'image/jpeg': [b'\xff\xd8\xff'],
    'image/png': [b'\x89PNG\r\n\x1a\n'],
    'image/webp': [b'RIFF'],
    'application/pdf': [b'%PDF'],
}

# Consulta de las partes de cada entidad (sólo lectura de tablas de otros servicios)
PARTES = {
    'comercio': 'SELECT c.usuario_id::text AS u FROM comercios c WHERE c.id = :id',
    'pedido': ('SELECT c.usuario_id::text AS u FROM pedidos_abasto p JOIN comercios c ON c.id = p.comercio_id '
               'WHERE p.id = :id UNION SELECT pr.usuario_id::text FROM pedidos_abasto p JOIN proveedores pr '
               'ON pr.id = p.proveedor_id WHERE p.id = :id UNION SELECT u.id::text FROM pedidos_abasto p JOIN usuarios u '
               'ON u.proveedor_id = p.proveedor_id WHERE p.id = :id'),
    'entrega': ('SELECT c.usuario_id::text AS u FROM entregas e JOIN comercios c ON c.id = e.comercio_id WHERE e.id = :id '
                'UNION SELECT pr.usuario_id::text FROM entregas e JOIN proveedores pr ON pr.id = e.proveedor_id '
                'WHERE e.id = :id UNION SELECT u.id::text FROM entregas e JOIN usuarios u '
                'ON u.proveedor_id = e.proveedor_id WHERE e.id = :id'),
    'venta': 'SELECT c.usuario_id::text AS u FROM ventas v JOIN comercios c ON c.id = v.comercio_id WHERE v.id = :id',
    'proveedor': ('SELECT usuario_id::text AS u FROM proveedores WHERE id = :id '
                  'UNION SELECT id::text FROM usuarios WHERE proveedor_id = :id'),
}


def _uuid_o_none(valor):
    try:
        return UUID(str(valor))
    except ValueError:
        return None


def partes_de(entidad, entidad_id):
    """Usuarios ligados a la entidad, o None si la entidad no existe."""
    if entidad not in PARTES:
        return set()
    if not _uuid_o_none(entidad_id):
        return None
    filas = db.session.execute(text(PARTES[entidad]), {'id': entidad_id}).all()
    if not filas and entidad in ('comercio', 'pedido', 'entrega', 'venta', 'proveedor'):
        existe = db.session.execute(text(f'SELECT 1 FROM {_TABLAS[entidad]} WHERE id = :id'), {'id': entidad_id}).first()
        return set() if existe else None
    return {f.u for f in filas if f.u}


_TABLAS = {'comercio': 'comercios', 'pedido': 'pedidos_abasto', 'entrega': 'entregas', 'venta': 'ventas',
           'proveedor': 'proveedores'}


def puede_ver(meta):
    yo = g.claims['sub']
    if meta['usuario_id'] == yo or tiene('catalogos.gestionar'):
        return True
    if meta.get('visibilidad') == 'publica':
        return True
    if meta.get('visibilidad') == 'privada':
        return False
    if tiene('comercios.ver_todos') and meta.get('entidad') in ('comercio', 'proveedor', 'producto'):
        return True
    return yo in (partes_de(meta.get('entidad'), meta.get('entidad_id')) or set())


def puede_adjuntar(entidad, entidad_id):
    """Para subir hay que ser parte de la entidad (o coordinación para evidencias de comercios)."""
    if entidad == 'producto':
        if not tiene('catalogos.gestionar'):
            raise prohibido('Sólo el administrador del catálogo sube fotos de productos.')
        return
    partes = partes_de(entidad, entidad_id)
    if partes is None:
        raise no_encontrado(f'La entidad {entidad} {entidad_id}')
    if entidad == 'importacion':
        return
    if g.claims['sub'] not in partes and not (entidad == 'comercio' and tiene('comercios.validar')) \
            and not tiene('catalogos.gestionar'):
        raise prohibido(f'No eres parte de ese {entidad}; no puedes adjuntarle archivos.')


def tipo_real(contenido, declarado):
    """Compara la firma del archivo con el tipo declarado. Los CSV deben ser texto UTF-8 o Latin-1."""
    if declarado == 'text/csv':
        try:
            contenido[:4096].decode('utf-8')
        except UnicodeDecodeError:
            try:
                contenido[:4096].decode('latin-1')
            except UnicodeDecodeError:
                return False
        return b'\x00' not in contenido[:4096]
    firmas = FIRMAS.get(declarado, [])
    if declarado == 'image/webp':
        return contenido[:4] == b'RIFF' and contenido[8:12] == b'WEBP'
    return any(contenido.startswith(f) for f in firmas)


def con_url(meta):
    return {**{k: v for k, v in meta.items() if k not in ('objeto', 'estado')},
            'url_contenido': f'{request.script_root}/api/v1/documentos/{meta["id"]}/contenido'}


def _documento(id, para_editar=False):
    meta = archivos.obtener_metadatos(id)
    if not meta:
        raise no_encontrado('El documento')
    if para_editar:
        if meta['usuario_id'] != g.claims['sub'] and not tiene('catalogos.gestionar'):
            raise prohibido('Sólo quien subió el documento o un administrador puede cambiarlo.')
    elif not puede_ver(meta):
        raise prohibido('No tienes acceso a este documento.')
    return meta


# ---------------------------------------------------------------- rutas

@srv.ruta('/documentos/limites', 'GET', resumen='Tipos, categorías y tamaño permitidos', etiqueta='Documentos',
          publico=True, raiz_xml='limites')
def limites():
    return {'tipos_permitidos': sorted(archivos.TIPOS_PERMITIDOS), 'categorias': sorted(archivos.CATEGORIAS),
            'entidades': list(archivos.ENTIDADES), 'max_megabytes': int(parametro('DOCUMENTO_MAX_MB'))}


@srv.ruta('/documentos', 'POST', resumen='Subir un documento', etiqueta='Documentos', permisos=['archivos.gestionar',
          'pedidos.atender', 'entregas.gestionar', 'ventas.registrar'], status=201, raiz_xml='documento',
          errores=(400, 401, 403, 404, 413, 415, 422),
          multipart={'type': 'object', 'required': ['archivo', 'categoria', 'entidad', 'entidad_id'], 'properties': {
              'archivo': {'type': 'string', 'format': 'binary'},
              'categoria': {'type': 'string', 'enum': sorted(archivos.CATEGORIAS)},
              'entidad': {'type': 'string', 'enum': list(archivos.ENTIDADES)},
              'entidad_id': {'type': 'string'},
              'visibilidad': {'type': 'string', 'enum': ['privada', 'entidad', 'publica'], 'default': 'entidad'},
              'descripcion': {'type': 'string', 'maxLength': 500}}})
def subir():
    """multipart/form-data. JPG, PNG, WEBP, PDF o CSV hasta DOCUMENTO_MAX_MB (10 MB por omisión). Se rechaza con
    415 si el contenido no corresponde al tipo declarado (p. ej. un .exe renombrado a .jpg)."""
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        raise ErrorApi(400, 'archivo_requerido', 'Envía el archivo en el campo "archivo" (multipart/form-data).')
    categoria, entidad = request.form.get('categoria'), request.form.get('entidad')
    entidad_id, visibilidad = request.form.get('entidad_id', ''), request.form.get('visibilidad', 'entidad')
    if categoria not in archivos.CATEGORIAS:
        raise ErrorApi(422, 'categoria_invalida', f'categoria debe ser una de: {", ".join(archivos.CATEGORIAS)}.')
    if entidad not in archivos.ENTIDADES:
        raise ErrorApi(422, 'entidad_invalida', f'entidad debe ser una de: {", ".join(archivos.ENTIDADES)}.')
    if visibilidad not in ('privada', 'entidad', 'publica'):
        raise ErrorApi(422, 'visibilidad_invalida', 'visibilidad debe ser privada, entidad o publica.')
    if visibilidad == 'publica' and entidad != 'producto' and not tiene('catalogos.gestionar'):
        raise ErrorApi(422, 'visibilidad_invalida', 'Sólo las fotos de productos pueden ser públicas.')
    tipo = archivo.mimetype
    if tipo not in archivos.TIPOS_PERMITIDOS:
        raise ErrorApi(415, 'tipo_no_permitido', f'Tipo {tipo} no permitido. Usa JPG, PNG, WEBP, PDF o CSV.')
    contenido = archivo.read()
    maximo = int(parametro('DOCUMENTO_MAX_MB')) * 1024 * 1024
    if len(contenido) > maximo:
        raise ErrorApi(413, 'archivo_muy_grande', f'El archivo excede {maximo // (1024 * 1024)} MB.')
    if contenido and not tipo_real(contenido, tipo):
        raise ErrorApi(415, 'tipo_no_coincide', f'El contenido del archivo no corresponde a {tipo}.')
    puede_adjuntar(entidad, entidad_id)
    # Nota: la foto principal de un comercio se fija después con PUT /comercios/{id}/foto en ms-comercios,
    # que es el dueño de la tabla comercios; este servicio sólo guarda el archivo.
    meta = archivos.guardar(contenido, archivo.filename, tipo, categoria, entidad, entidad_id, g.claims['sub'],
                            request.form.get('descripcion'), visibilidad)
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'Documento', meta['id'],
                     f'{archivos.CATEGORIAS[categoria]} de {entidad} {entidad_id}: {meta["nombre"]}',
                     datos_nuevos={k: meta[k] for k in ('nombre', 'tipo_mime', 'tamano_bytes', 'sha256', 'visibilidad')})
    db.session.commit()
    return con_url(meta)


@srv.ruta('/documentos', 'GET', resumen='Buscar documentos', etiqueta='Documentos',
          permisos=['archivos.gestionar', 'comercios.ver_todos', 'pedidos.atender', 'entregas.gestionar',
                    'ventas.registrar'], consulta=DocumentosConsulta, raiz_xml='documentos')
def listar(q):
    """Con `entidad` y `entidad_id` lista los de esa entidad si eres parte de ella; con `mios=true`, los tuyos.
    Sin filtros, sólo el administrador ve todos."""
    if q.entidad and q.entidad_id:
        partes = partes_de(q.entidad, q.entidad_id)
        if partes is None:
            raise no_encontrado(f'La entidad {q.entidad}')
        if g.claims['sub'] not in partes and not tiene('comercios.ver_todos') and not tiene('catalogos.gestionar') \
                and q.entidad != 'producto':
            raise prohibido(f'No eres parte de ese {q.entidad}.')
        items, total = archivos.listar(q.entidad, q.entidad_id, q.categoria, pagina=q.pagina, por_pagina=q.por_pagina)
    elif q.mios or not tiene('catalogos.gestionar'):
        items, total = archivos.listar(q.entidad, None, q.categoria, usuario_id=g.claims['sub'], pagina=q.pagina,
                                       por_pagina=q.por_pagina)
    else:
        items, total = archivos.listar(q.entidad, None, q.categoria, pagina=q.pagina, por_pagina=q.por_pagina)
    items = [con_url(m) for m in items if puede_ver(m)]
    return sobre_lista(items, total, q.pagina, q.por_pagina, 'documentos')


@srv.ruta('/documentos/<id>', 'GET', resumen='Metadatos de un documento', etiqueta='Documentos',
          permisos=['archivos.gestionar', 'comercios.ver_todos', 'pedidos.atender', 'entregas.gestionar',
                    'ventas.registrar', 'pedidos.crear'], raiz_xml='documento')
def metadatos(id):
    return con_url(_documento(id))


@srv.ruta('/documentos/<id>/contenido', 'GET', resumen='Descargar el contenido', etiqueta='Documentos',
          permisos=['archivos.gestionar', 'comercios.ver_todos', 'pedidos.atender', 'entregas.gestionar',
                    'ventas.registrar', 'pedidos.crear'], errores=(401, 403, 404))
def contenido(id):
    """Responde el archivo con su tipo y su SHA-256 en `X-Contenido-SHA256` para comprobar integridad.
    Para archivos grandes conviene GET /documentos/{id}/url: el cliente descarga directo del bucket."""
    meta = _documento(id)
    datos = archivos.leer(meta)
    if datos is None:
        raise ErrorApi(404, 'contenido_no_encontrado', 'El registro existe pero el archivo ya no está en el almacenamiento.')
    return Response(datos, mimetype=meta['tipo_mime'],
                    headers={'Content-Disposition': f'inline; filename="{meta["nombre"]}"',
                             'X-Contenido-SHA256': meta.get('sha256') or '', 'Cache-Control': 'private, max-age=300'})


@srv.ruta('/documentos/<id>/url', 'GET', resumen='URL firmada temporal', etiqueta='Documentos',
          permisos=['archivos.gestionar', 'comercios.ver_todos', 'pedidos.atender', 'entregas.gestionar',
                    'ventas.registrar', 'pedidos.crear'], consulta=UrlConsulta, raiz_xml='url_firmada',
          errores=(401, 403, 404, 409, 503))
def url_firmada(id, q):
    """Solo después de comprobar que el usuario puede ver ESTE documento. La URL es de solo lectura, sirve para ese
    objeto y vence en `minutos`; después Cloud Storage responde 403. Cada emisión queda en la auditoría."""
    meta = _documento(id)
    url, expira = archivos.url_temporal(meta, q.minutos)
    if not url:
        raise ErrorApi(409, 'sin_url_directa', 'El archivo aún está en GridFS; descárgalo con /contenido o migra los '
                                               'archivos con POST /documentos/migracion.')
    registrar_evento(UUID(g.claims['sub']), 'LECTURA', 'Documento', id,
                     f'URL temporal ({q.minutos} min) de {meta["nombre"]}', datos_nuevos={'expira': expira.isoformat()})
    db.session.commit()
    return {'id': id, 'url': url, 'expira': expira, 'minutos': q.minutos, 'tipo_mime': meta['tipo_mime'],
            'sha256': meta.get('sha256')}


@srv.ruta('/documentos/migracion', 'POST', resumen='Migrar archivos de GridFS a Cloud Storage', etiqueta='Administración',
          permisos=['servicios.monitorear'], raiz_xml='migracion')
def migrar():
    """No destructiva y repetible: copia cada archivo pendiente al bucket con el mismo id, comprueba el SHA-256 de la
    copia y solo entonces registra sus metadatos. GridFS no se borra."""
    resultado = archivos.migrar_desde_gridfs()
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Documento', 'migracion',
                     f"Migración GridFS -> Cloud Storage: {resultado['migrados']} archivos",
                     datos_nuevos={'migrados': resultado['migrados'], 'errores': resultado['errores'][:20]})
    db.session.commit()
    return {'migrados': resultado['migrados'], 'pendientes': archivos.pendientes_de_migrar(),
            'errores': len(resultado['errores'])}


@srv.ruta('/documentos/<id>', 'PATCH', resumen='Cambiar descripción o visibilidad', etiqueta='Documentos',
          permisos=['archivos.gestionar', 'entregas.gestionar', 'ventas.registrar'], cuerpo=DocumentoCambio,
          raiz_xml='documento', entrada_xml='documento_cambio', ejemplo_entrada={'visibilidad': 'privada'})
def cambiar(id, datos):
    meta = _documento(id, para_editar=True)
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise ErrorApi(422, 'sin_cambios', 'Indica descripcion o visibilidad.')
    if cambios.get('visibilidad') == 'publica' and meta['entidad'] != 'producto' and not tiene('catalogos.gestionar'):
        raise ErrorApi(422, 'visibilidad_invalida', 'Sólo las fotos de productos pueden ser públicas.')
    archivos.cambiar(id, cambios)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Documento', id, f'Cambio de {meta["nombre"]}',
                     datos_anteriores={k: meta.get(k) for k in cambios}, datos_nuevos=cambios)
    db.session.commit()
    return con_url(archivos.obtener_metadatos(id))


@srv.ruta('/documentos/<id>', 'DELETE', resumen='Eliminar un documento', etiqueta='Documentos',
          permisos=['archivos.gestionar', 'entregas.gestionar', 'ventas.registrar'], raiz_xml='resultado')
def eliminar(id):
    meta = _documento(id, para_editar=True)
    archivos.eliminar(id)
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'Documento', id, f'Documento eliminado: {meta["nombre"]}',
                     datos_anteriores={k: meta.get(k) for k in ('nombre', 'entidad', 'entidad_id', 'sha256')})
    db.session.commit()
    return {'mensaje': 'Documento eliminado', 'id': id}


@srv.ruta('/documentos/uso', 'GET', resumen='Espacio usado por categoría (agregación)', etiqueta='Administración',
          permisos=['servicios.monitorear'], raiz_xml='uso')
def uso():
    filas = archivos.uso_por_categoria()
    mb = lambda b: round(b / (1024 * 1024), 3)  # noqa: E731
    return {'total_archivos': sum(f['archivos'] for f in filas), 'total_megabytes': mb(sum(f['bytes'] for f in filas)),
            'categorias': [{'categoria': f['categoria'], 'archivos': f['archivos'], 'megabytes': mb(f['bytes'])}
                           for f in filas]}
