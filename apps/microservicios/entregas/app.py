"""
ms-entregas: logística de la entrega de un pedido de abasto.

Es DUEÑO de: entregas, eventos_entrega e incidencias_entrega. El estado del PEDIDO lo cambia
sólo ms-pedidos: este servicio le pide las transiciones con el token del usuario.

    PROGRAMADA -> ASIGNADA -> EN_RUTA -> ENTREGADA
                       `-> CON_INCIDENCIA (mientras haya una incidencia abierta) -> de vuelta

- El proveedor programa la entrega de un pedido aceptado y asigna responsable y vehículo.
- Al salir (EN_RUTA) se pide a ms-pedidos `preparar` (si hace falta) y `despachar`.
- El repartidor muestra un QR con el código de confirmación; el comercio lo escanea (o captura el
  código) y con eso se pide a ms-pedidos `recibir`, que genera la entrada al inventario.
- Evidencia fotográfica: se sube a ms-documentos (entidad `entrega`) y aquí se guarda su id.
- Trazabilidad: cada cambio queda en eventos_entrega con fecha, usuario y ubicación.
- Avisos a la otra parte por ms-notificaciones.
"""
import secrets
from datetime import datetime
from pathlib import Path
from uuid import UUID

from flask import g, request
from redis.exceptions import RedisError
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene, usuario_actual
from abasto_api.clientes import llamar
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, Usuario
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.bloqueos import bloqueo
from abasto_dominio.servicios.notificaciones import notificar

from esquemas import (AsignacionEntrada, CONTRATOS_XML, ConfirmacionEntrada, EntregaEntrada, EntregasConsulta,
                      IncidenciaEntrada, ResolucionEntrada, UbicacionEntrada)
from modelos import Entrega, EventoEntrega, IncidenciaEntrega

srv = Servicio('entregas', 'Entregas',
               'Gestión de entregas de pedidos: asignación de responsables, estados logísticos, fechas estimadas, '
               'confirmación de recepción con QR, incidencias, evidencias fotográficas y trazabilidad.',
               xsd=Path(__file__).parent / 'xsd' / 'entregas.xsd', contratos=CONTRATOS_XML)
app = srv.app

PROVEEDOR = ['entregas.gestionar']
COMERCIO = ['entregas.recibir']
ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # sin 0/O ni 1/I para capturarlo sin errores


def _uuid(valor, campo):
    try:
        return UUID(str(valor))
    except ValueError:
        raise ErrorApi(400, 'parametro_invalido', f'{campo} debe ser un UUID.')


def pedido_de(pedido_id):
    """Lectura del pedido (tabla de ms-pedidos, sólo lectura)."""
    return db.session.execute(text(
        'SELECT id, folio, estado::text AS estado, comercio_id, proveedor_id, fecha_entrega_estimada '
        'FROM pedidos_abasto WHERE id = :id'), {'id': pedido_id}).first()


def es_del_proveedor(entrega):
    return str(entrega.proveedor_id) == g.claims.get('proveedor_id')


def es_del_comercio(entrega):
    return str(entrega.comercio.usuario_id) == g.claims['sub']


def _entrega(id, parte=None):
    entrega = db.session.get(Entrega, id)
    if not entrega:
        raise no_encontrado('La entrega')
    proveedor, comercio = es_del_proveedor(entrega), es_del_comercio(entrega)
    if parte == 'proveedor' and not proveedor:
        raise prohibido('Sólo el proveedor (o su operador) puede hacer esto.')
    if parte == 'comercio' and not comercio:
        raise prohibido('Sólo el comercio que recibe puede hacer esto.')
    if not (proveedor or comercio or tiene('pedidos.ver_todos')):
        raise prohibido('La entrega no es de tu empresa ni de tu comercio.')
    return entrega


def entrega_a_dict(e, detalle=False):
    pedido = pedido_de(e.pedido_id)
    abiertas = [i for i in e.incidencias if i.estado == 'ABIERTA']
    datos = {'id': str(e.id), 'pedido_id': str(e.pedido_id),
             'folio_pedido': f'PED-{pedido.folio:05d}' if pedido else None,
             'estado_pedido': pedido.estado if pedido else None, 'proveedor_id': str(e.proveedor_id),
             'proveedor': e.proveedor.nombre_empresa, 'comercio_id': str(e.comercio_id),
             'comercio': e.comercio.nombre_comercio, 'direccion': e.comercio.direccion,
             'latitud': e.comercio.latitud, 'longitud': e.comercio.longitud, 'estado': e.estado,
             'responsable_id': str(e.responsable_id) if e.responsable_id else None,
             'responsable_nombre': e.responsable_nombre, 'vehiculo': e.vehiculo, 'fecha_estimada': e.fecha_estimada,
             'fecha_salida': e.fecha_salida, 'fecha_entrega': e.fecha_entrega, 'recibido_por': e.recibido_por,
             'evidencia_archivo_id': e.evidencia_archivo_id, 'incidencias_abiertas': len(abiertas)}
    if detalle:
        datos['eventos'] = [{'estado': v.estado, 'comentario': v.comentario, 'latitud': v.latitud,
                             'longitud': v.longitud, 'usuario_id': str(v.usuario_id) if v.usuario_id else None,
                             'fecha': v.created_at} for v in e.eventos]
        datos['incidencias'] = [incidencia_a_dict(i) for i in e.incidencias]
    return datos


def incidencia_a_dict(i):
    return {'id': i.id, 'entrega_id': str(i.entrega_id), 'tipo': i.tipo, 'descripcion': i.descripcion,
            'estado': i.estado, 'resolucion': i.resolucion,
            'reportada_por': str(i.reportada_por) if i.reportada_por else None, 'fecha': i.created_at,
            'resuelta': i.resuelta_at}


def _evento(entrega, estado, comentario=None, latitud=None, longitud=None):
    db.session.add(EventoEntrega(entrega_id=entrega.id, estado=estado, comentario=comentario, latitud=latitud,
                                 longitud=longitud, usuario_id=UUID(g.claims['sub'])))


def _cambiar_estado(entrega, nuevo, comentario=None, latitud=None, longitud=None):
    anterior = entrega.estado
    entrega.estado = nuevo
    _evento(entrega, nuevo, comentario, latitud, longitud)
    registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'Entrega', entrega.id,
                     f'Entrega del pedido {entrega.pedido_id}: {anterior} -> {nuevo}',
                     datos_anteriores={'estado': anterior}, datos_nuevos={'estado': nuevo, 'comentario': comentario})


def accion_pedido(pedido_id, accion, comentario=None):
    """Transición del pedido en ms-pedidos con el token del usuario (respeta sus permisos y reglas)."""
    respuesta = llamar('pedidos', 'POST', f'/api/v1/pedidos/{pedido_id}/acciones/{accion}', token=g.token,
                       json={'comentario': comentario} if comentario else {})
    if respuesta.ok:
        return respuesta.json()
    try:
        mensaje = respuesta.json().get('error', {}).get('mensaje')
    except ValueError:
        mensaje = None
    if respuesta.status_code >= 500:
        raise ErrorApi(503, 'servicio_no_disponible', f'ms-pedidos respondió {respuesta.status_code}.')
    raise ErrorApi(409, 'pedido_rechazo', f'ms-pedidos no permitió «{accion}»: {mensaje}')


def _responsable(responsable_id, proveedor_id):
    if not responsable_id:
        return None
    usuario = db.session.get(Usuario, _uuid(responsable_id, 'responsable_id'))
    empresa = usuario.proveedor_vinculado if usuario else None
    if not empresa or empresa.id != proveedor_id:
        raise ErrorApi(422, 'responsable_invalido', 'El responsable debe ser un usuario de tu empresa.')
    return usuario


# ---------------------------------------------------------------- programación y asignación

@srv.ruta('/entregas', 'POST', resumen='Programar la entrega de un pedido', etiqueta='Entregas', permisos=PROVEEDOR,
          cuerpo=EntregaEntrada, status=201, raiz_xml='entrega', entrada_xml='entrega_entrada',
          ejemplo_entrada={'pedido_id': '0b7c...', 'fecha_estimada': '2026-11-20', 'vehiculo': 'Camioneta 3.5 t'})
def programar(datos):
    pedido = pedido_de(_uuid(datos.pedido_id, 'pedido_id'))
    if not pedido:
        raise no_encontrado('El pedido')
    if str(pedido.proveedor_id) != g.claims.get('proveedor_id'):
        raise prohibido('El pedido no es de tu empresa.')
    if pedido.estado not in ('ACEPTADO', 'EN_PREPARACION'):
        raise ErrorApi(409, 'pedido_no_aceptado', f'Sólo se programan pedidos aceptados (está {pedido.estado}).')
    if Entrega.query.filter_by(pedido_id=pedido.id).first():
        raise ErrorApi(409, 'entrega_existente', 'El pedido ya tiene una entrega programada.')
    responsable = _responsable(datos.responsable_id, pedido.proveedor_id)
    entrega = Entrega(pedido_id=pedido.id, proveedor_id=pedido.proveedor_id, comercio_id=pedido.comercio_id,
                      fecha_estimada=datos.fecha_estimada or pedido.fecha_entrega_estimada,
                      responsable_id=responsable.id if responsable else None,
                      responsable_nombre=datos.responsable_nombre or (responsable.nombre if responsable else None),
                      vehiculo=datos.vehiculo, estado='ASIGNADA' if responsable or datos.responsable_nombre else 'PROGRAMADA',
                      codigo_confirmacion=''.join(secrets.choice(ALFABETO) for _ in range(8)))
    db.session.add(entrega)
    db.session.flush()
    _evento(entrega, entrega.estado, 'Entrega programada')
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'Entrega', entrega.id,
                     f'Entrega programada para el pedido PED-{pedido.folio:05d}',
                     datos_nuevos={'fecha_estimada': entrega.fecha_estimada, 'vehiculo': entrega.vehiculo})
    db.session.commit()
    notificar(entrega.comercio.usuario_id, 'entrega', f'Tu pedido PED-{pedido.folio:05d} tiene fecha de entrega',
              f'{entrega.proveedor.nombre_empresa} programó la entrega para el {entrega.fecha_estimada:%d/%m/%Y}.'
              if entrega.fecha_estimada else f'{entrega.proveedor.nombre_empresa} programó la entrega.',
              entidad={'tipo': 'entrega', 'id': str(entrega.id)}, origen='entregas')
    return entrega_a_dict(entrega, detalle=True)


@srv.ruta('/entregas/<uuid:id>/asignacion', 'PATCH', resumen='Asignar responsable, vehículo o fecha',
          etiqueta='Entregas', permisos=PROVEEDOR, cuerpo=AsignacionEntrada, raiz_xml='entrega',
          entrada_xml='asignacion_entrada', ejemplo_entrada={'responsable_nombre': 'Rogelio Treviño', 'vehiculo': 'NL-45-873'})
def asignar(id, datos):
    entrega = _entrega(id, 'proveedor')
    if entrega.estado in ('ENTREGADA', 'CANCELADA'):
        raise ErrorApi(409, 'entrega_cerrada', f'La entrega ya está {entrega.estado}.')
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise ErrorApi(422, 'sin_cambios', 'Indica al menos un campo.')
    responsable = _responsable(datos.responsable_id, entrega.proveedor_id)
    antes = {k: getattr(entrega, k) for k in ('responsable_id', 'responsable_nombre', 'vehiculo', 'fecha_estimada')}
    if responsable:
        entrega.responsable_id = responsable.id
        entrega.responsable_nombre = datos.responsable_nombre or responsable.nombre
    elif datos.responsable_nombre:
        entrega.responsable_nombre = datos.responsable_nombre
    for campo in ('vehiculo', 'fecha_estimada'):
        if campo in cambios:
            setattr(entrega, campo, cambios[campo])
    if entrega.estado == 'PROGRAMADA' and entrega.responsable_nombre:
        _cambiar_estado(entrega, 'ASIGNADA', f'Responsable: {entrega.responsable_nombre}')
    else:
        _evento(entrega, entrega.estado, 'Cambio de asignación')
        registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Entrega', entrega.id, 'Cambio de asignación',
                         datos_anteriores=antes, datos_nuevos=cambios)
    db.session.commit()
    return entrega_a_dict(entrega, detalle=True)


@srv.ruta('/entregas/<uuid:id>/qr', 'GET', resumen='Código QR de confirmación (repartidor)', etiqueta='Entregas',
          permisos=PROVEEDOR, raiz_xml='qr')
def qr(id):
    """El repartidor muestra este QR al llegar; el comercio lo escanea con la app. Sólo lo ve el proveedor."""
    entrega = _entrega(id, 'proveedor')
    return {'entrega_id': str(entrega.id), 'codigo': entrega.codigo_confirmacion,
            'contenido_qr': f'ABASTORED:ENTREGA:{entrega.id}:{entrega.codigo_confirmacion}',
            'instrucciones': 'Muestra este código al comercio para que confirme la recepción.'}


# ---------------------------------------------------------------- en ruta y rastreo

@srv.ruta('/entregas/<uuid:id>/salida', 'POST', resumen='Salida a ruta (despacha el pedido)', etiqueta='Rastreo',
          permisos=PROVEEDOR, cuerpo=UbicacionEntrada, raiz_xml='entrega', entrada_xml='ubicacion_entrada',
          ejemplo_entrada={'comentario': 'Sale de bodega', 'latitud': 25.7, 'longitud': -100.2})
def salida(id, datos):
    """Pide a ms-pedidos `preparar` (si el pedido sigue ACEPTADO) y `despachar`; si ms-pedidos no lo permite, la
    entrega no cambia."""
    with bloqueo(f'entrega:{id}', ttl_segundos=30, mensaje='La entrega se está actualizando.'):
        entrega = _entrega(id, 'proveedor')
        if entrega.estado not in ('PROGRAMADA', 'ASIGNADA'):
            raise ErrorApi(409, 'estado_invalido', f'La entrega está {entrega.estado}; no puede salir a ruta.')
        pedido = pedido_de(entrega.pedido_id)
        db.session.rollback()   # sin transacción abierta mientras ms-pedidos actualiza el pedido
        if pedido.estado == 'ACEPTADO':
            accion_pedido(entrega.pedido_id, 'preparar')
        accion_pedido(entrega.pedido_id, 'despachar', datos.comentario)
        entrega = db.session.get(Entrega, id)
        entrega.fecha_salida = datetime.now()
        _cambiar_estado(entrega, 'EN_RUTA', datos.comentario or 'Salió a ruta', datos.latitud, datos.longitud)
        db.session.commit()
    notificar(entrega.comercio.usuario_id, 'entrega', 'Tu pedido va en camino',
              f'{entrega.proveedor.nombre_empresa} ya salió con tu pedido'
              + (f' ({entrega.responsable_nombre}).' if entrega.responsable_nombre else '.'),
              entidad={'tipo': 'entrega', 'id': str(entrega.id)}, prioridad='alta', origen='entregas')
    return entrega_a_dict(entrega, detalle=True)


@srv.ruta('/entregas/<uuid:id>/eventos', 'POST', resumen='Registrar avance o ubicación', etiqueta='Rastreo',
          permisos=PROVEEDOR, cuerpo=UbicacionEntrada, status=201, raiz_xml='entrega', entrada_xml='ubicacion_entrada',
          ejemplo_entrada={'comentario': 'A 10 minutos', 'latitud': 25.79, 'longitud': -100.55})
def avance(id, datos):
    entrega = _entrega(id, 'proveedor')
    if entrega.estado not in ('EN_RUTA', 'CON_INCIDENCIA'):
        raise ErrorApi(409, 'estado_invalido', 'Sólo se registran avances de entregas en ruta.')
    _evento(entrega, entrega.estado, datos.comentario, datos.latitud, datos.longitud)
    db.session.commit()
    return entrega_a_dict(entrega, detalle=True)


# ---------------------------------------------------------------- recepción

def intentos_fallidos(entrega_id):
    try:
        return int(extensiones.redis_client.get(f'entregas:intentos:{entrega_id}') or 0)
    except RedisError:
        return 0   # sin Redis no se cuentan los intentos; el código sigue siendo obligatorio


def sumar_intento(entrega_id):
    try:
        pipe = extensiones.redis_client.pipeline()
        pipe.incr(f'entregas:intentos:{entrega_id}')
        pipe.expire(f'entregas:intentos:{entrega_id}', 3600)
        pipe.execute()
    except RedisError:
        pass


@srv.ruta('/entregas/<uuid:id>/confirmacion', 'POST', resumen='Confirmar la recepción con el código QR',
          etiqueta='Recepción', permisos=COMERCIO, cuerpo=ConfirmacionEntrada, raiz_xml='entrega',
          entrada_xml='confirmacion_entrada',
          ejemplo_entrada={'codigo': 'K7M2Q9XP', 'recibido_por': 'María López', 'comentario': 'Completo'})
def confirmar(id, datos):
    """El código debe coincidir (3 intentos fallidos por hora bloquean la confirmación). Pide a ms-pedidos `recibir`,
    que da entrada al inventario del comercio en ms-inventario."""
    with bloqueo(f'entrega:{id}', ttl_segundos=30, mensaje='La entrega se está actualizando.'):
        entrega = _entrega(id, 'comercio')
        if entrega.estado not in ('EN_RUTA', 'CON_INCIDENCIA'):
            raise ErrorApi(409, 'estado_invalido', f'La entrega está {entrega.estado}; aún no se puede recibir.')
        if any(i.estado == 'ABIERTA' and i.tipo == 'RECHAZO' for i in entrega.incidencias):
            raise ErrorApi(409, 'entrega_rechazada', 'Hay un rechazo abierto; resuélvelo antes de recibir.')
        if intentos_fallidos(id) >= 3:
            raise ErrorApi(429, 'demasiados_intentos', 'Demasiados códigos incorrectos; intenta en una hora.')
        if not secrets.compare_digest(datos.codigo.upper(), entrega.codigo_confirmacion):
            sumar_intento(id)
            raise ErrorApi(422, 'codigo_incorrecto', 'El código no corresponde a esta entrega.')
        db.session.rollback()
        accion_pedido(entrega.pedido_id, 'recibir', datos.comentario)
        entrega = db.session.get(Entrega, id)
        entrega.fecha_entrega = datetime.now()
        entrega.recibido_por = datos.recibido_por
        _cambiar_estado(entrega, 'ENTREGADA', f'Recibió {datos.recibido_por}' +
                        (f': {datos.comentario}' if datos.comentario else ''))
        db.session.commit()
    destinatarios = [entrega.proveedor.usuario_id] + ([entrega.responsable_id] if entrega.responsable_id else [])
    notificar(destinatarios, 'entrega', 'Entrega confirmada',
              f'{entrega.comercio.nombre_comercio} confirmó la recepción ({datos.recibido_por}).',
              entidad={'tipo': 'entrega', 'id': str(entrega.id)}, origen='entregas')
    return entrega_a_dict(entrega, detalle=True)


@srv.ruta('/entregas/<uuid:id>/evidencia', 'POST', resumen='Subir foto de evidencia', etiqueta='Recepción',
          permisos=PROVEEDOR + COMERCIO, status=201, raiz_xml='entrega', errores=(400, 401, 403, 404, 413, 415, 422),
          multipart={'type': 'object', 'required': ['archivo'], 'properties': {
              'archivo': {'type': 'string', 'format': 'binary', 'description': 'JPG, PNG o WEBP'},
              'descripcion': {'type': 'string'}}})
def evidencia(id):
    """Reenvía el archivo a ms-documentos (entidad `entrega`, categoría `evidencia_entrega`) y guarda su id."""
    entrega = _entrega(id)
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        raise ErrorApi(400, 'archivo_requerido', 'Envía la foto en el campo "archivo".')
    respuesta = llamar('documentos', 'POST', '/api/v1/documentos', token=g.token,
                       files={'archivo': (archivo.filename, archivo.stream, archivo.mimetype)},
                       data={'categoria': 'evidencia_entrega', 'entidad': 'entrega', 'entidad_id': str(entrega.id),
                             'descripcion': request.form.get('descripcion') or 'Evidencia de entrega'}, timeout=15)
    if respuesta.status_code != 201:
        try:
            error = respuesta.json().get('error', {})
        except ValueError:
            error = {}
        raise ErrorApi(respuesta.status_code if respuesta.status_code in (400, 403, 413, 415, 422) else 503,
                       error.get('codigo', 'documentos_error'), f"ms-documentos: {error.get('mensaje')}")
    documento = respuesta.json()
    entrega.evidencia_archivo_id = documento['id']
    _evento(entrega, entrega.estado, f'Evidencia: {documento["nombre"]}')
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Entrega', entrega.id, 'Evidencia fotográfica',
                     datos_nuevos={'archivo_id': documento['id'], 'sha256': documento.get('sha256')})
    db.session.commit()
    return entrega_a_dict(entrega, detalle=True)


# ---------------------------------------------------------------- incidencias

@srv.ruta('/entregas/<uuid:id>/incidencias', 'POST', resumen='Reportar una incidencia', etiqueta='Incidencias',
          permisos=PROVEEDOR + COMERCIO, cuerpo=IncidenciaEntrada, status=201, raiz_xml='incidencia',
          entrada_xml='incidencia_entrada',
          ejemplo_entrada={'tipo': 'FALTANTE', 'descripcion': 'Faltaron 2 cajas de aceite'})
def reportar(id, datos):
    entrega = _entrega(id)
    if entrega.estado in ('CANCELADA',):
        raise ErrorApi(409, 'entrega_cancelada', 'La entrega está cancelada.')
    incidencia = IncidenciaEntrega(entrega_id=entrega.id, tipo=datos.tipo, descripcion=datos.descripcion,
                                   reportada_por=UUID(g.claims['sub']))
    db.session.add(incidencia)
    db.session.flush()
    if entrega.estado in ('EN_RUTA', 'ASIGNADA', 'PROGRAMADA'):
        _cambiar_estado(entrega, 'CON_INCIDENCIA', f'{datos.tipo}: {datos.descripcion}')
    else:
        _evento(entrega, entrega.estado, f'Incidencia {datos.tipo}: {datos.descripcion}')
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'IncidenciaEntrega', incidencia.id,
                     f'Incidencia {datos.tipo} en la entrega {entrega.id}', datos_nuevos=datos.model_dump())
    db.session.commit()
    otra_parte = entrega.comercio.usuario_id if es_del_proveedor(entrega) else entrega.proveedor.usuario_id
    notificar(otra_parte, 'incidencia', f'Incidencia en la entrega: {datos.tipo.replace("_", " ").lower()}',
              datos.descripcion, entidad={'tipo': 'entrega', 'id': str(entrega.id)}, prioridad='alta',
              origen='entregas')
    return incidencia_a_dict(incidencia)


@srv.ruta('/incidencias/<int:id>/resolucion', 'POST', resumen='Resolver una incidencia', etiqueta='Incidencias',
          permisos=PROVEEDOR + COMERCIO, cuerpo=ResolucionEntrada, raiz_xml='incidencia',
          entrada_xml='resolucion_entrada', ejemplo_entrada={'resolucion': 'Se repusieron las 2 cajas'})
def resolver(id, datos):
    """Al cerrar la última incidencia abierta, la entrega vuelve a EN_RUTA (si ya había salido) o a ASIGNADA."""
    incidencia = db.session.get(IncidenciaEntrega, id)
    if not incidencia:
        raise no_encontrado('La incidencia')
    entrega = _entrega(incidencia.entrega_id)
    if incidencia.estado == 'RESUELTA':
        raise ErrorApi(409, 'incidencia_resuelta', 'La incidencia ya estaba resuelta.')
    incidencia.estado, incidencia.resolucion, incidencia.resuelta_at = 'RESUELTA', datos.resolucion, datetime.now()
    db.session.flush()
    if entrega.estado == 'CON_INCIDENCIA' and not any(i.estado == 'ABIERTA' for i in entrega.incidencias):
        _cambiar_estado(entrega, 'EN_RUTA' if entrega.fecha_salida else 'ASIGNADA', f'Resuelta: {datos.resolucion}')
    else:
        _evento(entrega, entrega.estado, f'Incidencia {incidencia.id} resuelta: {datos.resolucion}')
    registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'IncidenciaEntrega', incidencia.id, 'Incidencia resuelta',
                     datos_anteriores={'estado': 'ABIERTA'}, datos_nuevos={'estado': 'RESUELTA',
                                                                           'resolucion': datos.resolucion})
    db.session.commit()
    return incidencia_a_dict(incidencia)


# ---------------------------------------------------------------- consulta

@srv.ruta('/entregas', 'GET', resumen='Mis entregas', etiqueta='Entregas',
          permisos=PROVEEDOR + COMERCIO + ['pedidos.ver_todos'], consulta=EntregasConsulta, raiz_xml='entregas')
def listar(q):
    """Proveedor u operador: las de su empresa. Comercio: las que va a recibir. Auditor: todas."""
    consulta = Entrega.query
    if tiene('pedidos.ver_todos'):
        pass
    elif g.claims.get('proveedor_id') and tiene('entregas.gestionar'):
        consulta = consulta.filter(Entrega.proveedor_id == UUID(g.claims['proveedor_id']))
    else:
        consulta = consulta.join(Comercio, Comercio.id == Entrega.comercio_id).filter(
            Comercio.usuario_id == usuario_actual().id)
    if q.estado:
        consulta = consulta.filter(Entrega.estado == q.estado)
    if q.fecha:
        consulta = consulta.filter(Entrega.fecha_estimada == q.fecha)
    resultado = paginar(consulta.order_by(Entrega.fecha_estimada.nulls_last(), Entrega.created_at.desc()),
                        q.pagina, q.por_pagina, entrega_a_dict)
    resultado['entregas'] = resultado.pop('items')
    return resultado


@srv.ruta('/entregas/<uuid:id>', 'GET', resumen='Entrega con su trazabilidad', etiqueta='Entregas',
          permisos=PROVEEDOR + COMERCIO + ['pedidos.ver_todos'], raiz_xml='entrega')
def detalle(id):
    return entrega_a_dict(_entrega(id), detalle=True)


@srv.ruta('/pedidos/<uuid:pedido_id>/entrega', 'GET', resumen='Entrega de un pedido', etiqueta='Entregas',
          permisos=PROVEEDOR + COMERCIO + ['pedidos.ver_todos'], raiz_xml='entrega')
def de_pedido(pedido_id):
    entrega = Entrega.query.filter_by(pedido_id=pedido_id).first()
    if not entrega:
        raise no_encontrado('La entrega de ese pedido')
    return entrega_a_dict(_entrega(entrega.id), detalle=True)
