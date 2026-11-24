"""
ms-comercios: registro y administración de comercios formales e informales.

Es DUEÑO de: comercios y responsables_comercio.
- Datos fiscales opcionales (RFC, razón social, régimen), ubicación, contacto, horarios, días de
  operación, giro y tipo de comercio; verificación municipal y baja lógica.
- Responsables del establecimiento (dueño, encargado, empleados), con o sin cuenta.
- Búsqueda geográfica de comercios cercanos (PostGIS, ST_DWithin sobre la geometría del comercio).
- La zona se pide a ms-geolocalizacion (dueña de las zonas); si no responde, se calcula con la
  biblioteca de dominio leyendo las zonas (sólo lectura) para no detener el registro.
- Fotos y evidencias: se suben a ms-documentos; aquí sólo se fija la foto principal (PUT /foto).
Se integra con ms-notificaciones (aviso al dueño cuando su comercio se valida).
"""
from pathlib import Path
from uuid import UUID

from flask import g
from sqlalchemy import cast, or_, text

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene, usuario_actual
from abasto_api.clientes import llamar
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, ResponsableComercio, Usuario, ZonaMunicipal
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.geo import zona_para_punto
from abasto_dominio.servicios.notificaciones import notificar

from esquemas import (CONTRATOS_XML, CercanosConsulta, ComercioEntrada, ComerciosConsulta, FotoEntrada,
                      ResponsableEntrada, ValidacionEntrada)

srv = Servicio('comercios', 'Comercios',
               'Registro y administración de comercios formales e informales: datos fiscales opcionales, ubicación, '
               'contacto, horarios, giro, tipo, verificación y baja lógica; búsqueda geográfica; establecimientos y '
               'responsables.',
               xsd=Path(__file__).parent / 'xsd' / 'comercios.xsd', contratos=CONTRATOS_XML)
app = srv.app

CAMPOS = ('nombre_comercio', 'tipo_comercio', 'direccion', 'colonia', 'municipio', 'estado', 'latitud',
          'longitud', 'telefono_comercio', 'horario_apertura', 'horario_cierre', 'dias_operacion', 'descripcion',
          'giro', 'email_contacto', 'rfc', 'razon_social', 'regimen_fiscal')


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
            'dias_operacion': c.dias_operacion, 'descripcion': c.descripcion, 'giro': c.giro,
            'email_contacto': c.email_contacto, 'rfc': c.rfc, 'razon_social': c.razon_social,
            'regimen_fiscal': c.regimen_fiscal, 'foto_url': c.foto_url,
            'fecha_verificacion': c.fecha_verificacion, 'creado_en': c.created_at,
            'responsables': [responsable_a_dict(r) for r in c.responsables],
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
    return {k: getattr(c, k) for k in ('nombre_comercio', 'tipo_comercio', 'direccion', 'municipio', 'zona_id', 'giro',
                                       'rfc', 'razon_social')}


def responsable_a_dict(r):
    return {'id': r.id, 'comercio_id': str(r.comercio_id), 'nombre': r.nombre, 'puesto': r.puesto,
            'telefono': r.telefono, 'email': r.email, 'usuario_id': str(r.usuario_id) if r.usuario_id else None,
            'alta': r.created_at}


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
                                       Comercio.direccion.ilike(f'%{q.texto}%'),
                                       Comercio.razon_social.ilike(f'%{q.texto}%')))
    if q.giro:
        consulta = consulta.filter(Comercio.giro == q.giro)
    if q.municipio:
        consulta = consulta.filter(Comercio.municipio == q.municipio)
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


def zona_de(latitud, longitud):
    """Pregunta a ms-geolocalizacion (ST_Contains en PostGIS). Si no responde, se calcula aquí con Haversine."""
    try:
        respuesta = llamar('geolocalizacion', 'GET', '/api/v1/zonas/localizar', token=g.token,
                           params={'latitud': str(latitud), 'longitud': str(longitud)})
        if respuesta.status_code == 200:
            return respuesta.json()['zona']['id']
        if respuesta.status_code == 404:
            return None
    except ErrorApi:
        pass
    zona = zona_para_punto(latitud, longitud, _zonas())
    return zona.id if zona else None


def _asignar_zona(comercio, zona_id):
    if zona_id:
        if not db.session.get(ZonaMunicipal, zona_id):
            raise ErrorApi(422, 'zona_inexistente', 'La zona indicada no existe.')
        comercio.zona_id = zona_id
    elif comercio.latitud is not None and comercio.longitud is not None:
        comercio.zona_id = zona_de(comercio.latitud, comercio.longitud)
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


# ---------------------------------------------------------------- foto, responsables y cercanos

@srv.ruta('/comercios/<uuid:id>/foto', 'PUT', resumen='Fijar la foto principal', etiqueta='Comercios',
          permisos=['comercios.gestionar'], cuerpo=FotoEntrada, raiz_xml='comercio', entrada_xml='foto_entrada',
          ejemplo_entrada={'documento_id': '6735c1f0a1b2c3d4e5f60718'})
def fijar_foto(id, datos):
    """La foto se sube antes a ms-documentos (entidad comercio, categoría foto_comercio); aquí se verifica con
    ms-documentos que exista y sea de este comercio, y se guarda su ruta."""
    comercio = _comercio(id, editar=True)
    respuesta = llamar('documentos', 'GET', f'/api/v1/documentos/{datos.documento_id}', token=g.token)
    if respuesta.status_code != 200:
        raise ErrorApi(422 if respuesta.status_code in (403, 404) else 503, 'documento_invalido',
                       'El documento no existe en ms-documentos o no tienes acceso a él.')
    documento = respuesta.json()
    if documento.get('entidad') != 'comercio' or documento.get('entidad_id') != str(comercio.id) \
            or not (documento.get('tipo_mime') or '').startswith('image/'):
        raise ErrorApi(422, 'documento_invalido', 'El documento debe ser una imagen de este comercio.')
    antes = comercio.foto_url
    comercio.foto_url = f'/ms/documentos/api/v1/documentos/{datos.documento_id}/contenido'
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Comercio', comercio.id, 'Foto principal',
                     datos_anteriores={'foto_url': antes}, datos_nuevos={'foto_url': comercio.foto_url})
    db.session.commit()
    return comercio_a_dict(comercio, detalle=True)


@srv.ruta('/comercios/<uuid:id>/responsables', 'GET', resumen='Responsables del establecimiento',
          etiqueta='Responsables', permisos=['comercios.gestionar', 'comercios.ver_todos'], raiz_xml='responsables')
def listar_responsables(id):
    comercio = _comercio(id)
    return {'comercio_id': str(comercio.id), 'responsables': [responsable_a_dict(r) for r in comercio.responsables]}


@srv.ruta('/comercios/<uuid:id>/responsables', 'POST', resumen='Agregar un responsable', etiqueta='Responsables',
          permisos=['comercios.gestionar'], cuerpo=ResponsableEntrada, status=201, raiz_xml='responsable',
          entrada_xml='responsable_entrada',
          ejemplo_entrada={'nombre': 'Lucía Garza', 'puesto': 'ENCARGADO', 'telefono': '8112345678'})
def agregar_responsable(id, datos):
    comercio = _comercio(id, editar=True)
    usuario_id = None
    if datos.usuario_id:
        try:
            usuario = db.session.get(Usuario, UUID(datos.usuario_id))
        except ValueError:
            raise ErrorApi(400, 'parametro_invalido', 'usuario_id debe ser un UUID.')
        if not usuario or not usuario.activo:
            raise ErrorApi(422, 'usuario_inexistente', 'La cuenta indicada no existe o está inactiva.')
        usuario_id = usuario.id
    if datos.puesto == 'DUENO' and any(r.puesto == 'DUENO' for r in comercio.responsables):
        raise ErrorApi(409, 'dueno_existente', 'El comercio ya tiene un responsable con puesto de dueño.')
    responsable = ResponsableComercio(comercio_id=comercio.id, usuario_id=usuario_id,
                                      **datos.model_dump(exclude={'usuario_id'}))
    db.session.add(responsable)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'ResponsableComercio', responsable.id,
                     f'{datos.nombre} ({datos.puesto.lower()}) en {comercio.nombre_comercio}',
                     datos_nuevos=datos.model_dump())
    db.session.commit()
    return responsable_a_dict(responsable)


@srv.ruta('/responsables/<int:id>', 'DELETE', resumen='Dar de baja un responsable', etiqueta='Responsables',
          permisos=['comercios.gestionar'], raiz_xml='resultado')
def baja_responsable(id):
    responsable = db.session.get(ResponsableComercio, id)
    if not responsable or not responsable.activo:
        raise no_encontrado('El responsable')
    _comercio(responsable.comercio_id, editar=True)
    responsable.activo = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'ResponsableComercio', responsable.id,
                     f'Baja de {responsable.nombre}')
    db.session.commit()
    return {'mensaje': 'Responsable dado de baja', 'id': str(id)}


@srv.ruta('/comercios/cercanos', 'GET', resumen='Comercios verificados cerca de un punto', etiqueta='Búsqueda geográfica',
          permisos=['comercios.gestionar', 'comercios.ver_todos', 'proveedores.consultar', 'pedidos.atender'],
          consulta=CercanosConsulta, raiz_xml='cercanos')
def cercanos(q):
    """ST_DWithin sobre geography con el índice GIST de comercios.geom, ordenados por distancia."""
    filas = db.session.execute(text(
        "SELECT id, ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1000 AS km "
        "FROM comercios WHERE activo AND estado_registro = 'VERIFICADO' AND geom IS NOT NULL "
        + ('AND tipo_comercio = CAST(:tipo AS tipo_comercio) ' if q.tipo_comercio else '') +
        'AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radio) '
        'ORDER BY km LIMIT :limite'),
        {'lat': q.latitud, 'lon': q.longitud, 'radio': float(q.radio_km) * 1000, 'tipo': q.tipo_comercio,
         'limite': q.limite}).all()
    comercios = {c.id: c for c in Comercio.query.filter(Comercio.id.in_([f.id for f in filas])).all()}
    return {'latitud': float(q.latitud), 'longitud': float(q.longitud), 'radio_km': float(q.radio_km),
            'total': len(filas), 'comercios': [{**comercio_a_dict(comercios[f.id]), 'distancia_km': round(float(f.km), 3)}
                                               for f in filas]}
