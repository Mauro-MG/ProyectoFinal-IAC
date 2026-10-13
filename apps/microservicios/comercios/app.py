"""
ms-comercios: registro de comercios, validación municipal, zonas y evidencias.

PostgreSQL + PostGIS: comercios, zonas_municipales (geometría y buffer de zona).
MongoDB (GridFS, bucket `archivos`): fotos del comercio y evidencias de validación.
Redis: caché de zonas (`comercios:zonas`, 10 min).
Se integra con ms-notificaciones (aviso al dueño cuando su comercio se valida).
"""
from pathlib import Path
import json
from uuid import UUID

from flask import Response, g, request
from redis.exceptions import RedisError
from sqlalchemy import cast, or_

from abasto_api import (ErrorApi, Servicio, no_encontrado, paginar, prohibido, sobre_lista, tiene,
                        usuario_actual)
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, ZonaMunicipal
from abasto_dominio.servicios import archivos
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.geo import distancia_km, zona_para_punto
from abasto_dominio.servicios.notificaciones import notificar

from esquemas import (CONTRATOS_XML, ArchivosConsulta, ComercioEntrada, ComerciosConsulta, LocalizarConsulta,
                      ValidacionEntrada)

srv = Servicio('comercios', 'Comercios',
               'Registro y validación de comercios formales e informales, zonas municipales, localización '
               'geográfica y evidencias (fotos y documentos en GridFS).',
               xsd=Path(__file__).parent / 'xsd' / 'comercios.xsd', contratos=CONTRATOS_XML)
app = srv.app

CAMPOS = ('nombre_comercio', 'tipo_comercio', 'direccion', 'colonia', 'municipio', 'estado', 'latitud',
          'longitud', 'telefono_comercio', 'horario_apertura', 'horario_cierre', 'descripcion')


def comercio_a_dict(c, detalle=False):
    datos = {
        'id': str(c.id), 'nombre_comercio': c.nombre_comercio, 'tipo_comercio': c.tipo_comercio,
        'sector': c.sector, 'direccion': c.direccion, 'colonia': c.colonia, 'municipio': c.municipio,
        'estado': c.estado, 'zona_id': c.zona_id, 'zona': c.zona.nombre if c.zona else None,
        'estado_registro': c.estado_registro, 'usuario_id': str(c.usuario_id),
    }
    if detalle:
        datos.update({
            'latitud': c.latitud, 'longitud': c.longitud, 'telefono_comercio': c.telefono_comercio,
            'horario_apertura': c.horario_apertura, 'horario_cierre': c.horario_cierre,
            'descripcion': c.descripcion, 'fecha_verificacion': c.fecha_verificacion, 'creado_en': c.created_at,
        })
    return datos


def _comercio(id, editar=False):
    comercio = db.session.get(Comercio, id)
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    es_dueno = str(comercio.usuario_id) == g.claims['sub']
    if editar and not (es_dueno or tiene('catalogos.gestionar')):
        raise prohibido('Sólo el dueño del comercio o un administrador puede modificarlo.')
    if not editar and not (es_dueno or tiene('comercios.ver_todos')):
        raise prohibido('No puedes consultar comercios de otros usuarios.')
    return comercio


def _foto(c):
    return {k: getattr(c, k) for k in ('nombre_comercio', 'tipo_comercio', 'direccion', 'municipio', 'zona_id')}


def _zonas():
    return ZonaMunicipal.query.filter_by(activa=True).all()


EJEMPLO_COMERCIO = {
    'nombre_comercio': 'Tianguis Los Nogales - Puesto 40', 'tipo_comercio': 'INFORMAL_TIANGUIS',
    'direccion': 'Tianguis Los Nogales, pasillo F', 'municipio': 'García', 'estado': 'Nuevo León',
    'latitud': 25.821, 'longitud': -100.589, 'horario_apertura': '07:00:00', 'horario_cierre': '15:00:00'}


# ---------------------------------------------------------------- comercios

@srv.ruta('/comercios', 'GET', resumen='Buscar comercios', etiqueta='Comercios',
          permisos=['comercios.gestionar', 'comercios.ver_todos'], consulta=ComerciosConsulta, raiz_xml='comercios',
         )
def listar_comercios(q):
    """Con `comercios.ver_todos` (coordinador, analista, admin) ve todos; si no, sólo los suyos. Paginado."""
    consulta = Comercio.query.filter_by(activo=True)
    if not tiene('comercios.ver_todos'):
        consulta = consulta.filter(Comercio.usuario_id == UUID(g.claims['sub']))
    if q.texto:
        consulta = consulta.filter(or_(Comercio.nombre_comercio.ilike(f'%{q.texto}%'),
                                       Comercio.direccion.ilike(f'%{q.texto}%')))
    if q.zona_id:
        consulta = consulta.filter(Comercio.zona_id == q.zona_id)
    if q.estado_registro:
        consulta = consulta.filter(Comercio.estado_registro == q.estado_registro)
    if q.tipo_comercio:
        consulta = consulta.filter(Comercio.tipo_comercio == q.tipo_comercio)
    if q.sector:
        consulta = consulta.filter(cast(Comercio.tipo_comercio, db.String).like(f'{q.sector.upper()}%'))
    return paginar(consulta.order_by(Comercio.nombre_comercio), q.pagina, q.por_pagina, comercio_a_dict)


@srv.ruta('/comercios/<uuid:id>', 'GET', resumen='Detalle de comercio', etiqueta='Comercios',
          permisos=['comercios.gestionar', 'comercios.ver_todos'], raiz_xml='comercio')
def obtener_comercio(id):
    return comercio_a_dict(_comercio(id), detalle=True)


@srv.ruta('/comercios', 'POST', resumen='Registrar comercio', etiqueta='Comercios', permisos=['comercios.gestionar'],
          cuerpo=ComercioEntrada, status=201, raiz_xml='comercio', entrada_xml='comercio_entrada',
         ejemplo_entrada=EJEMPLO_COMERCIO)
def crear_comercio(datos):
    """Queda PENDIENTE hasta que la coordinación municipal lo valide. Si no se indica zona, se asigna la zona
    cuyo radio contiene la ubicación (RN-016)."""
    usuario = usuario_actual()
    comercio = Comercio(usuario_id=usuario.id, estado_registro='PENDIENTE')
    for campo in CAMPOS:
        setattr(comercio, campo, getattr(datos, campo))
    _asignar_zona(comercio, datos.zona_id)
    db.session.add(comercio)
    db.session.flush()
    registrar_evento(usuario.id, 'CREACION', 'Comercio', comercio.id,
                     f'Registro del comercio {comercio.nombre_comercio} (ms-comercios)', datos_nuevos=_foto(comercio))
    db.session.commit()
    invalidar_analisis()
    return comercio_a_dict(comercio, detalle=True)


def _asignar_zona(comercio, zona_id):
    if zona_id:
        if not db.session.get(ZonaMunicipal, zona_id):
            raise ErrorApi(422, 'zona_inexistente', 'La zona indicada no existe.')
        comercio.zona_id = zona_id
    elif comercio.latitud is not None and comercio.longitud is not None:
        zona = zona_para_punto(comercio.latitud, comercio.longitud, _zonas())
        comercio.zona_id = zona.id if zona else None
    else:
        comercio.zona_id = None


@srv.ruta('/comercios/<uuid:id>', 'PUT', resumen='Actualizar comercio', etiqueta='Comercios',
          permisos=['comercios.gestionar', 'catalogos.gestionar'], cuerpo=ComercioEntrada, raiz_xml='comercio',
          entrada_xml='comercio_entrada', ejemplo_entrada=EJEMPLO_COMERCIO)
def actualizar_comercio(id, datos):
    comercio = _comercio(id, editar=True)
    antes = _foto(comercio)
    for campo in CAMPOS:
        setattr(comercio, campo, getattr(datos, campo))
    _asignar_zona(comercio, datos.zona_id)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Comercio', comercio.id,
                     f'Edición del comercio {comercio.nombre_comercio} (ms-comercios)',
                     datos_anteriores=antes, datos_nuevos=_foto(comercio))
    db.session.commit()
    invalidar_analisis()
    return comercio_a_dict(comercio, detalle=True)


@srv.ruta('/comercios/<uuid:id>/validacion', 'PATCH', resumen='Validar, suspender o rechazar', etiqueta='Comercios',
          permisos=['comercios.validar'], cuerpo=ValidacionEntrada, raiz_xml='comercio',
          entrada_xml='validacion_entrada',
          ejemplo_entrada={'estado': 'VERIFICADO', 'observaciones': 'Visita en sitio el 12/10'})
def validar_comercio(id, datos):
    """Sólo los VERIFICADOS aparecen en el portal público (RN-015). Se avisa al dueño."""
    comercio = db.session.get(Comercio, id)
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    anterior = comercio.estado_registro
    if anterior == datos.estado:
        raise ErrorApi(409, 'sin_cambio', f'El comercio ya está {anterior.lower()}.')
    comercio.estado_registro = datos.estado
    comercio.verificado_por = UUID(g.claims['sub'])
    comercio.fecha_verificacion = db.func.now()
    registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'Comercio', comercio.id,
                     f'{comercio.nombre_comercio}: {anterior} -> {datos.estado}',
                     datos_anteriores={'estado_registro': anterior},
                     datos_nuevos={'estado_registro': datos.estado, 'observaciones': datos.observaciones})
    db.session.commit()
    invalidar_analisis()
    notificar(comercio.usuario_id, 'comercio', f'{comercio.nombre_comercio}: {datos.estado.lower()}',
              datos.observaciones or 'La coordinación municipal revisó tu comercio.',
              url=f'/comercios/{comercio.id}', entidad={'tipo': 'comercio', 'id': str(comercio.id)},
              origen='comercios')
    return comercio_a_dict(comercio, detalle=True)


@srv.ruta('/comercios/<uuid:id>', 'DELETE', resumen='Dar de baja (lógica)', etiqueta='Comercios',
          permisos=['comercios.gestionar', 'catalogos.gestionar'], raiz_xml='resultado')
def baja_comercio(id):
    comercio = _comercio(id, editar=True)
    comercio.activo = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'Comercio', comercio.id,
                     f'Baja lógica del comercio {comercio.nombre_comercio} (ms-comercios)')
    db.session.commit()
    invalidar_analisis()
    return {'mensaje': 'Comercio dado de baja', 'id': str(comercio.id)}


# ---------------------------------------------------------------- zonas

def zona_a_dict(z):
    return {'id': z.id, 'nombre': z.nombre, 'municipio': z.municipio, 'estado': z.estado,
            'latitud_centro': float(z.latitud_centro), 'longitud_centro': float(z.longitud_centro),
            'radio_km': float(z.radio_km), 'poblacion': z.poblacion}


@srv.ruta('/zonas', 'GET', resumen='Zonas municipales', etiqueta='Zonas', publico=True, raiz_xml='zonas',
         )
def listar_zonas():
    """Lista pública de zonas activas. Se guarda 10 minutos en Redis (comercios:zonas)."""
    try:
        guardado = extensiones.redis_client.get('comercios:zonas')
        if guardado:
            return {'origen': 'cache', 'zonas': json.loads(guardado)}
    except RedisError:
        pass
    zonas = [zona_a_dict(z) for z in ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre)]
    try:
        extensiones.redis_client.setex('comercios:zonas', 600, json.dumps(zonas))
    except RedisError:
        pass
    return {'origen': 'postgres', 'zonas': zonas}


@srv.ruta('/zonas/localizar', 'GET', resumen='¿En qué zona cae un punto?', etiqueta='Zonas', publico=True,
          consulta=LocalizarConsulta, raiz_xml='localizacion', errores=(400, 404, 422))
def localizar(q):
    """Buffer: distancia de Haversine del punto al centro de cada zona contra su radio."""
    zonas = _zonas()
    zona = zona_para_punto(q.latitud, q.longitud, zonas)
    cercanas = sorted(({'zona_id': z.id, 'zona': z.nombre,
                        'distancia_km': round(distancia_km(q.latitud, q.longitud, z.latitud_centro, z.longitud_centro), 2),
                        'radio_km': float(z.radio_km)} for z in zonas), key=lambda x: x['distancia_km'])[:3]
    if not zona:
        raise ErrorApi(404, 'fuera_de_zona', 'El punto no cae dentro de ninguna zona registrada.',
                       detalles=cercanas)
    return {'zona': zona_a_dict(zona), 'cercanas': cercanas}


# ---------------------------------------------------------------- archivos (GridFS)

@srv.ruta('/comercios/<uuid:id>/archivos', 'POST', resumen='Subir foto o evidencia', etiqueta='Archivos',
          permisos=['archivos.gestionar'], status=201, raiz_xml='archivo',
          errores=(400, 401, 403, 404, 413, 422),
          multipart={'type': 'object', 'required': ['archivo', 'categoria'], 'properties': {
              'archivo': {'type': 'string', 'format': 'binary'},
              'categoria': {'type': 'string', 'enum': ['foto_comercio', 'evidencia_validacion', 'documento']},
              'descripcion': {'type': 'string'}}})
def subir_archivo(id):
    """multipart/form-data. JPG, PNG, WEBP o PDF hasta 10 MB. El dueño sube fotos; el coordinador, evidencias."""
    comercio = db.session.get(Comercio, id)
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    if str(comercio.usuario_id) != g.claims['sub'] and not tiene('comercios.validar'):
        raise prohibido('Sólo el dueño o la coordinación pueden adjuntar archivos a este comercio.')
    archivo = request.files.get('archivo')
    categoria = request.form.get('categoria', 'foto_comercio')
    if not archivo or not archivo.filename:
        raise ErrorApi(400, 'archivo_requerido', 'Envía el archivo en el campo "archivo" (multipart/form-data).')
    if categoria not in ('foto_comercio', 'evidencia_validacion', 'documento'):
        raise ErrorApi(422, 'categoria_invalida', 'categoria debe ser foto_comercio, evidencia_validacion o documento.')
    meta = archivos.guardar(archivo.read(), archivo.filename, archivo.mimetype, categoria, 'comercio', comercio.id,
                            g.claims['sub'], request.form.get('descripcion'))
    if categoria == 'foto_comercio':
        comercio.foto_url = f'/archivos/{meta["id"]}'
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'Archivo', meta['id'],
                     f'{archivos.CATEGORIAS[categoria]} de {comercio.nombre_comercio}: {meta["nombre"]}')
    db.session.commit()
    return meta


@srv.ruta('/comercios/<uuid:id>/archivos', 'GET', resumen='Archivos del comercio', etiqueta='Archivos',
          permisos=['comercios.gestionar', 'comercios.ver_todos'], consulta=ArchivosConsulta, raiz_xml='archivos')
def listar_archivos(id, q):
    _comercio(id)
    items, total = archivos.listar('comercio', id, q.categoria, pagina=q.pagina, por_pagina=q.por_pagina)
    return sobre_lista(items, total, q.pagina, q.por_pagina, 'archivos')


@srv.ruta('/archivos/<archivo_id>', 'GET', resumen='Descargar archivo', etiqueta='Archivos',
          permisos=['comercios.gestionar', 'comercios.ver_todos', 'archivos.gestionar'], errores=(401, 403, 404))
def descargar_archivo(archivo_id):
    """Lo ven quien lo subió, el dueño del comercio y quien tiene comercios.ver_todos (coordinación)."""
    meta, contenido = archivos.abrir(archivo_id)
    if not meta:
        raise no_encontrado('El archivo')
    if meta['usuario_id'] != g.claims['sub'] and not tiene('comercios.ver_todos'):
        comercio = db.session.get(Comercio, UUID(meta['entidad_id'])) if meta['entidad'] == 'comercio' else None
        if not comercio or str(comercio.usuario_id) != g.claims['sub']:
            raise prohibido('No tienes acceso a este archivo.')
    return Response(contenido.read(), mimetype=meta['tipo_mime'],
                    headers={'Content-Disposition': f'inline; filename="{meta["nombre"]}"'})


@srv.ruta('/archivos/<archivo_id>', 'DELETE', resumen='Eliminar archivo', etiqueta='Archivos',
          permisos=['archivos.gestionar'], raiz_xml='resultado')
def eliminar_archivo(archivo_id):
    meta = archivos.obtener_metadatos(archivo_id)
    if not meta:
        raise no_encontrado('El archivo')
    if meta['usuario_id'] != g.claims['sub'] and not tiene('catalogos.gestionar'):
        raise prohibido('Sólo quien subió el archivo o un administrador puede eliminarlo.')
    archivos.eliminar(archivo_id)
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'Archivo', archivo_id, f'Archivo eliminado: {meta["nombre"]}')
    db.session.commit()
    return {'mensaje': 'Archivo eliminado', 'id': archivo_id}
