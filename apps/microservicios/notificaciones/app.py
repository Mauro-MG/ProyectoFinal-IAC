"""
ms-notificaciones: avisos internos y push para cada usuario.

Es DUEÑO de: notificaciones, preferencias_notificacion, plantillas_notificacion, dispositivos_push y
entregas_canal (MongoDB). Preferencias por tipo y canal, plantillas con variables, registro de
dispositivos y entrega por canales autorizados (ver canales.py).

Los demás componentes (web, ms-pedidos, ms-inventario, ms-precios, ms-comercios)
le envían avisos con un token de servicio (POST /notificaciones/lote); cada
usuario consulta, marca y borra los suyos.

MongoDB: notificaciones (CRUD, filtros, índices, TTL de 90 días y agregación por tipo).
Redis: contador de no leídas por usuario (`notif:no_leidas:{usuario}`, 5 min).
"""
from pathlib import Path
from uuid import UUID

from datetime import datetime, timezone

from flask import g
from pymongo.errors import DuplicateKeyError

from abasto_api import ErrorApi, Servicio, no_encontrado, sobre_lista, tiene
from abasto_dominio import extensiones
from abasto_dominio.servicios import notificaciones as notif

from esquemas import (CONTRATOS_XML, DispositivoEntrada, EnvioPlantillaEntrada, HistorialConsulta, LecturaEntrada,
                      LoteEntrada, NotificacionEntrada, NotificacionesConsulta, PlantillaEntrada, PreferenciasEntrada,
                      ResumenConsulta)
import canales

srv = Servicio('notificaciones', 'Notificaciones',
               'Notificaciones internas: alta individual y por lote (entre servicios), consulta paginada con filtros, '
               'marcado de lectura, borrado, contador de no leídas en Redis y resumen con agregaciones de MongoDB.',
               xsd=Path(__file__).parent / 'xsd' / 'notificaciones.xsd', contratos=CONTRATOS_XML)
app = srv.app


def _yo():
    return g.claims['sub']


EJEMPLO = {'id': '6710f2c3a1b2c3d4e5f60718', 'usuario_id': '1ebd...', 'tipo': 'pedido',
           'titulo': 'Pedido PED-00007: enviado al proveedor', 'mensaje': 'Tianguis Los Nogales / Bodega 14',
           'url': '/pedidos/…', 'prioridad': 'alta', 'leida': False, 'origen': 'pedidos',
           'creada_en': '2026-10-12T18:20:00+00:00'}


@srv.ruta('/notificaciones', 'GET', resumen='Mis notificaciones', etiqueta='Notificaciones',
          permisos=[], consulta=NotificacionesConsulta, raiz_xml='notificaciones')
def listar(q):
    items, total = notif.listar(_yo(), q.solo_no_leidas, q.tipo, q.pagina, q.por_pagina)
    return {**sobre_lista(items, total, q.pagina, q.por_pagina, 'notificaciones'),
            'no_leidas': notif.contar_no_leidas(_yo())}


@srv.ruta('/notificaciones/contador', 'GET', resumen='Número de no leídas (Redis)', etiqueta='Notificaciones',
          raiz_xml='contador')
def contador():
    """Lo consulta la campana del web en cada página: sale de Redis y sólo va a MongoDB si la clave expiró."""
    return {'usuario_id': _yo(), 'no_leidas': notif.contar_no_leidas(_yo())}


@srv.ruta('/notificaciones/<id>', 'GET', resumen='Una notificación', etiqueta='Notificaciones',
          raiz_xml='notificacion', ejemplo_salida=EJEMPLO)
def obtener(id):
    datos = notif.obtener(id, _yo())
    if not datos:
        raise no_encontrado('La notificación')
    return datos


@srv.ruta('/notificaciones/<id>', 'PATCH', resumen='Marcar como leída o no leída', etiqueta='Notificaciones',
          cuerpo=LecturaEntrada, raiz_xml='notificacion', entrada_xml='lectura_entrada',
         ejemplo_entrada={'leida': True})
def marcar(id, datos):
    if not notif.marcar_leida(id, _yo(), datos.leida):
        raise no_encontrado('La notificación')
    return notif.obtener(id, _yo())


@srv.ruta('/notificaciones/marcar-todas', 'POST', resumen='Marcar todas como leídas', etiqueta='Notificaciones',
          raiz_xml='resultado')
def marcar_todas():
    cambiadas = notif.marcar_todas(_yo())
    return {'mensaje': f'{cambiadas} notificaciones marcadas como leídas', 'cambiadas': cambiadas}


@srv.ruta('/notificaciones/<id>', 'DELETE', resumen='Eliminar notificación', etiqueta='Notificaciones',
          raiz_xml='resultado')
def eliminar(id):
    if not notif.eliminar(id, _yo()):
        raise no_encontrado('La notificación')
    return {'mensaje': 'Notificación eliminada', 'id': id}


@srv.ruta('/notificaciones', 'POST', resumen='Enviar un aviso a un usuario (administración)',
          etiqueta='Envío', permisos=['usuarios.gestionar', 'notificaciones.crear'], cuerpo=NotificacionEntrada,
          status=201, raiz_xml='notificacion', entrada_xml='notificacion_entrada',
          ejemplo_entrada={'usuario_id': '1ebd...', 'tipo': 'sistema', 'titulo': 'Mantenimiento',
                           'mensaje': 'El domingo de 2 a 4 am la plataforma estará en mantenimiento.'})
def crear(datos):
    try:
        UUID(datos.usuario_id)
    except ValueError:
        raise ErrorApi(422, 'datos_invalidos', 'usuario_id debe ser un UUID.')
    creada, _ = canales.entregar(datos.usuario_id, datos.tipo, datos.titulo, datos.mensaje, datos.url,
                                 prioridad=datos.prioridad, origen=g.claims.get('origen') or 'administracion')
    if not creada:
        raise ErrorApi(409, 'canal_apagado', 'El usuario apagó las notificaciones internas de ese tipo.')
    return creada


@srv.ruta('/notificaciones/lote', 'POST', resumen='Enviar un aviso a varios usuarios (entre servicios)',
          etiqueta='Envío', permisos=['notificaciones.crear'], cuerpo=LoteEntrada, status=201, raiz_xml='lote',
          entrada_xml='lote_entrada', 
          ejemplo_entrada={'usuarios': ['1ebd...', '7c2a...'], 'tipo': 'pedido', 'titulo': 'Pedido PED-00007: aceptado',
                           'mensaje': 'Tianguis Los Nogales / Bodega 14', 'url': '/pedidos/…',
                           'entidad': {'tipo': 'pedido', 'id': '…'}, 'prioridad': 'normal', 'origen': 'pedidos'})
def crear_lote(datos):
    """Lo usan los demás servicios con un token de servicio (permiso notificaciones.crear)."""
    creadas = []
    for usuario in dict.fromkeys(datos.usuarios):
        creada, _ = canales.entregar(usuario, datos.tipo, datos.titulo, datos.mensaje, datos.url,
                                     datos.entidad.model_dump() if datos.entidad else None, datos.prioridad, datos.origen)
        if creada:
            creadas.append(creada['id'])
    return {'creadas': len(creadas), 'ids': creadas}


@srv.ruta('/notificaciones/resumen', 'GET', resumen='Resumen por tipo (agregación MongoDB)', etiqueta='Notificaciones',
          consulta=ResumenConsulta, raiz_xml='resumen')
def resumen(q):
    if q.todos and not tiene('usuarios.gestionar'):
        raise ErrorApi(403, 'sin_permiso', 'Sólo la administración puede ver el resumen de todas las cuentas.')
    return {'dias': q.dias, 'resumen': notif.resumen(None if q.todos else _yo(), q.dias)}


# ---------------------------------------------------------------- preferencias, plantillas y dispositivos

@srv.ruta('/preferencias', 'GET', resumen='Mis preferencias de notificación', etiqueta='Preferencias',
          raiz_xml='preferencias')
def mis_preferencias():
    return canales.preferencias(_yo())


@srv.ruta('/preferencias', 'PUT', resumen='Cambiar mis preferencias', etiqueta='Preferencias',
          cuerpo=PreferenciasEntrada, raiz_xml='preferencias', entrada_xml='preferencias_entrada',
          ejemplo_entrada={'canales': {'todos': ['interno', 'push'], 'precio_atipico': ['interno']},
                           'silencio': {'desde': 22, 'hasta': 7}})
def cambiar_preferencias(datos):
    """`canales` por tipo de aviso (o "todos" para el resto). Lo urgente (prioridad alta) siempre llega a la bandeja."""
    tipos_validos = set(notif.TIPOS) | {'todos'}
    desconocidos = sorted(set(datos.canales) - tipos_validos)
    if desconocidos:
        raise ErrorApi(422, 'tipo_invalido', f'Tipos de aviso que no existen: {desconocidos}.')
    return canales.guardar_preferencias(_yo(), datos.canales, datos.silencio.model_dump())


def plantilla_a_dict(p):
    return {**{k: p[k] for k in ('clave', 'tipo', 'titulo', 'mensaje', 'prioridad')},
            'variables': sorted(canales.campos_de(p['titulo']) | canales.campos_de(p['mensaje']))}


@srv.ruta('/plantillas', 'GET', resumen='Plantillas de avisos', etiqueta='Plantillas',
          permisos=['usuarios.gestionar', 'notificaciones.crear'], raiz_xml='plantillas')
def listar_plantillas():
    return {'plantillas': [plantilla_a_dict(p) for p in canales.plantillas()]}


@srv.ruta('/plantillas', 'POST', resumen='Crear o reemplazar una plantilla', etiqueta='Plantillas',
          permisos=['usuarios.gestionar'], cuerpo=PlantillaEntrada, status=201, raiz_xml='plantilla',
          entrada_xml='plantilla_entrada',
          ejemplo_entrada={'clave': 'cotizacion_nueva', 'tipo': 'cotizacion', 'titulo': 'Nueva cotización en {zona}',
                           'mensaje': '{titulo}: {productos} producto(s).', 'prioridad': 'normal'})
def guardar_plantilla(datos):
    canales.plantillas()
    extensiones.mongo_db()['plantillas_notificacion'].update_one(
        {'clave': datos.clave}, {'$set': {**datos.model_dump(), 'actualizada': datetime.now(timezone.utc)}}, upsert=True)
    return plantilla_a_dict(datos.model_dump())


@srv.ruta('/notificaciones/plantilla', 'POST', resumen='Enviar un aviso con una plantilla', etiqueta='Envío',
          permisos=['usuarios.gestionar', 'notificaciones.crear'], cuerpo=EnvioPlantillaEntrada, status=201,
          raiz_xml='lote', entrada_xml='envio_plantilla_entrada',
          ejemplo_entrada={'clave': 'mantenimiento', 'usuarios': ['1ebd...'],
                           'variables': {'fecha': 'domingo 16', 'inicio': '2:00', 'fin': '4:00'}})
def enviar_plantilla(datos):
    p = canales.plantilla(datos.clave)
    if not p:
        raise no_encontrado(f'La plantilla {datos.clave}')
    faltan = sorted((canales.campos_de(p['titulo']) | canales.campos_de(p['mensaje'])) - set(datos.variables))
    if faltan:
        raise ErrorApi(422, 'faltan_variables', f'Faltan variables de la plantilla: {faltan}.')
    titulo, mensaje = p['titulo'].format(**datos.variables), p['mensaje'].format(**datos.variables)
    creadas = []
    for usuario in dict.fromkeys(datos.usuarios):
        creada, _ = canales.entregar(usuario, p['tipo'], titulo[:200], mensaje[:1000], datos.url, None, p['prioridad'],
                                     g.claims.get('origen') or 'administracion')
        if creada:
            creadas.append(creada['id'])
    return {'creadas': len(creadas), 'ids': creadas}


def dispositivo_a_dict(d):
    return {'token_final': d['token'][-8:], 'plataforma': d['plataforma'], 'nombre': d.get('nombre'),
            'activo': d.get('activo', True), 'registrado': d['registrado']}


@srv.ruta('/dispositivos', 'POST', resumen='Registrar este dispositivo para push', etiqueta='Push',
          cuerpo=DispositivoEntrada, status=201, raiz_xml='dispositivo', entrada_xml='dispositivo_entrada',
          ejemplo_entrada={'token': 'fcm:APA91bH...', 'plataforma': 'android', 'nombre': 'Celular de Rosa'})
def registrar_dispositivo(datos):
    """Si el token ya estaba registrado por otra cuenta (otro usuario usó el mismo teléfono), pasa a esta."""
    documento = {'usuario_id': _yo(), 'token': datos.token, 'plataforma': datos.plataforma, 'nombre': datos.nombre,
                 'activo': True, 'registrado': datetime.now(timezone.utc)}
    try:
        extensiones.mongo_db()['dispositivos_push'].insert_one(dict(documento))
    except DuplicateKeyError:
        extensiones.mongo_db()['dispositivos_push'].update_one({'token': datos.token}, {'$set': documento})
    return dispositivo_a_dict(documento)


@srv.ruta('/dispositivos', 'GET', resumen='Mis dispositivos', etiqueta='Push', raiz_xml='dispositivos')
def mis_dispositivos():
    return {'dispositivos': [dispositivo_a_dict(d) for d in
                             extensiones.mongo_db()['dispositivos_push'].find({'usuario_id': _yo(), 'activo': True})]}


@srv.ruta('/dispositivos/<path:token>', 'DELETE', resumen='Dar de baja un dispositivo', etiqueta='Push',
          raiz_xml='resultado')
def baja_dispositivo(token):
    resultado = extensiones.mongo_db()['dispositivos_push'].update_one({'token': token, 'usuario_id': _yo()},
                                                                       {'$set': {'activo': False}})
    if not resultado.matched_count:
        raise no_encontrado('El dispositivo')
    return {'mensaje': 'Dispositivo dado de baja', 'id': token[-8:]}


@srv.ruta('/notificaciones/historial', 'GET', resumen='Historial de entregas por canal', etiqueta='Push',
          consulta=HistorialConsulta, raiz_xml='historial')
def historial(q):
    """Por cada aviso: en qué canal se entregó, se omitió (preferencias o silencio) o no tenía dispositivo."""
    filtro = {'usuario_id': _yo()}
    if q.canal:
        filtro['canal'] = q.canal
    entregas = list(extensiones.mongo_db()['entregas_canal'].find(filtro, {'_id': 0, 'usuario_id': 0})
                    .sort('fecha', -1).limit(q.limite))
    return {'total': len(entregas), 'entregas': entregas}
