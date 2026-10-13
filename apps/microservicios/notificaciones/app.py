"""
ms-notificaciones: avisos internos para cada usuario.

Los demás componentes (web, ms-pedidos, ms-inventario, ms-precios, ms-comercios)
le envían avisos con un token de servicio (POST /notificaciones/lote); cada
usuario consulta, marca y borra los suyos.

MongoDB: notificaciones (CRUD, filtros, índices, TTL de 90 días y agregación por tipo).
Redis: contador de no leídas por usuario (`notif:no_leidas:{usuario}`, 5 min).
"""
from pathlib import Path
from uuid import UUID

from flask import g

from abasto_api import ErrorApi, Servicio, no_encontrado, sobre_lista, tiene
from abasto_dominio.servicios import notificaciones as notif

from esquemas import (CONTRATOS_XML, LecturaEntrada, LoteEntrada, NotificacionEntrada,
                      NotificacionesConsulta, ResumenConsulta)

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
    return notif.crear(datos.usuario_id, datos.tipo, datos.titulo, datos.mensaje, datos.url,
                       prioridad=datos.prioridad, origen=g.claims.get('origen') or 'administracion')


@srv.ruta('/notificaciones/lote', 'POST', resumen='Enviar un aviso a varios usuarios (entre servicios)',
          etiqueta='Envío', permisos=['notificaciones.crear'], cuerpo=LoteEntrada, status=201, raiz_xml='lote',
          entrada_xml='lote_entrada', 
          ejemplo_entrada={'usuarios': ['1ebd...', '7c2a...'], 'tipo': 'pedido', 'titulo': 'Pedido PED-00007: aceptado',
                           'mensaje': 'Tianguis Los Nogales / Bodega 14', 'url': '/pedidos/…',
                           'entidad': {'tipo': 'pedido', 'id': '…'}, 'prioridad': 'normal', 'origen': 'pedidos'})
def crear_lote(datos):
    """Lo usan los demás servicios con un token de servicio (permiso notificaciones.crear)."""
    creadas = [notif.crear(u, datos.tipo, datos.titulo, datos.mensaje, datos.url,
                           datos.entidad.model_dump() if datos.entidad else None, datos.prioridad, datos.origen)['id']
               for u in dict.fromkeys(datos.usuarios)]
    return {'creadas': len(creadas), 'ids': creadas}


@srv.ruta('/notificaciones/resumen', 'GET', resumen='Resumen por tipo (agregación MongoDB)', etiqueta='Notificaciones',
          consulta=ResumenConsulta, raiz_xml='resumen')
def resumen(q):
    if q.todos and not tiene('usuarios.gestionar'):
        raise ErrorApi(403, 'sin_permiso', 'Sólo la administración puede ver el resumen de todas las cuentas.')
    return {'dias': q.dias, 'resumen': notif.resumen(None if q.todos else _yo(), q.dias)}
