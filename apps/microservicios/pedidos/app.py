"""
ms-pedidos: pedido de abasto del comercio al proveedor.

Usa la misma máquina de estados que el web (abasto_dominio.servicios.pedidos):
BORRADOR -> ENVIADO -> ACEPTADO -> EN_PREPARACION -> ENVIADO_A_COMERCIO -> ENTREGADO,
con CANCELADO y RECHAZADO.

PostgreSQL: pedidos_abasto, detalle_pedidos, historial_pedido; al recibir, movimientos_inventario.
MongoDB: eventos_pedido (cada transición completa) y agregaciones de desempeño.
Redis: bloqueo distribuido `bloqueo:pedido:{id}` mientras se ejecuta una acción, para que el web y
el servicio (o dos clics) no apliquen la misma transición dos veces.
Integración: cada transición avisa a la otra parte por ms-notificaciones.
"""
from pathlib import Path
from uuid import UUID

from flask import g

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene, usuario_actual
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, PedidoAbasto, Proveedor
from abasto_dominio.modelos.pedido import ESTADOS_PEDIDO
from abasto_dominio.servicios import eventos
from abasto_dominio.servicios import pedidos as flujo
from abasto_dominio.servicios.bloqueos import bloqueo

from esquemas import (CONTRATOS_XML, AccionEntrada, EstadisticasConsulta, PartidaEntrada, PedidoEntrada,
                      PedidosConsulta)

srv = Servicio('pedidos', 'Pedidos de abasto',
               'Creación de pedidos de abasto y su ciclo completo entre comercio y proveedor, con validación de '
               'pedido mínimo, cobertura y existencia, historial en PostgreSQL y eventos en MongoDB.',
               xsd=Path(__file__).parent / 'xsd' / 'pedidos.xsd', contratos=CONTRATOS_XML)
app = srv.app


def _uuid(valor, campo):
    try:
        return UUID(str(valor))
    except ValueError:
        raise ErrorApi(400, 'parametro_invalido', f'{campo} debe ser un UUID.')


def pedido_a_dict(p, detalle=False):
    usuario = getattr(g, 'usuario', None)
    datos = {
        'id': str(p.id), 'folio': p.folio_legible, 'estado': p.estado, 'estado_legible': p.estado_legible,
        'comercio_id': str(p.comercio_id), 'comercio': p.comercio.nombre_comercio,
        'proveedor_id': str(p.proveedor_id), 'proveedor': p.proveedor.nombre_empresa,
        'subtotal': p.subtotal, 'pedido_minimo': p.proveedor.pedido_minimo,
        'fecha_envio': p.fecha_envio, 'fecha_entrega_estimada': p.fecha_entrega_estimada,
        'actualizado': p.updated_at,
    }
    if detalle:
        datos.update({
            'fecha_respuesta': p.fecha_respuesta, 'fecha_entrega_real': p.fecha_entrega_real,
            'motivo_rechazo': p.motivo_rechazo, 'comision_plataforma': p.comision_plataforma, 'notas': p.notas,
            'partidas': [{'id': d.id, 'producto_id': d.producto_id, 'producto': d.producto.nombre,
                          'unidad_medida': d.producto.unidad_medida, 'cantidad': d.cantidad,
                          'precio_unitario': d.precio_unitario, 'subtotal': d.subtotal} for d in p.detalles],
            'acciones': flujo.acciones_disponibles(p, usuario) if usuario else [],
        })
    return datos


def _pedido(id):
    pedido = db.session.get(PedidoAbasto, id)
    if not pedido:
        raise no_encontrado('El pedido')
    usuario = usuario_actual()
    if not flujo.puede_ver(pedido, usuario):
        raise prohibido('El pedido no es de tu comercio ni de tu empresa.')
    return pedido


EJEMPLO_PEDIDO = {'comercio_id': '6f1c...', 'proveedor_id': '9a2e...',
                  'partidas': [{'producto_id': 12, 'cantidad': 40}, {'producto_id': 13, 'cantidad': 15}],
                  'notas': 'Entregar antes de las 7:00'}


@srv.ruta('/pedidos', 'GET', resumen='Mis pedidos', etiqueta='Pedidos',
          permisos=['pedidos.crear', 'pedidos.atender', 'pedidos.ver_todos'], consulta=PedidosConsulta,
          raiz_xml='pedidos')
def listar(q):
    """Comerciante: los de sus comercios. Proveedor u operador: los recibidos (sin borradores). Auditor/admin: todos."""
    usuario = usuario_actual()
    consulta = PedidoAbasto.query
    if tiene('pedidos.ver_todos'):
        pass
    elif tiene('pedidos.atender'):
        empresa = usuario.proveedor_vinculado
        if not empresa:
            raise ErrorApi(409, 'sin_empresa', 'Tu cuenta no está ligada a un proveedor.')
        consulta = consulta.filter(PedidoAbasto.proveedor_id == empresa.id, PedidoAbasto.estado != 'BORRADOR')
    else:
        consulta = consulta.join(Comercio).filter(Comercio.usuario_id == usuario.id)
    if q.estado:
        consulta = consulta.filter(PedidoAbasto.estado == q.estado)
    if q.comercio_id:
        consulta = consulta.filter(PedidoAbasto.comercio_id == _uuid(q.comercio_id, 'comercio_id'))
    resultado = paginar(consulta.order_by(PedidoAbasto.updated_at.desc()), q.pagina, q.por_pagina, pedido_a_dict)
    resultado['pedidos'] = resultado.pop('items')
    return resultado


@srv.ruta('/pedidos', 'POST', resumen='Crear pedido (borrador con partidas)', etiqueta='Pedidos',
          permisos=['pedidos.crear'], cuerpo=PedidoEntrada, status=201, raiz_xml='pedido',
          entrada_xml='pedido_entrada', 
          ejemplo_entrada=EJEMPLO_PEDIDO)
def crear(datos):
    """Crea el borrador (o reutiliza el que ya exista entre ese comercio y ese proveedor) y agrega las partidas.
    Valida que el proveedor entregue en la zona (RN-011) y la venta mínima de cada producto (RN-012).
    Para enviarlo: POST /pedidos/{id}/acciones/enviar."""
    usuario = usuario_actual()
    comercio = db.session.get(Comercio, _uuid(datos.comercio_id, 'comercio_id'))
    proveedor = db.session.get(Proveedor, _uuid(datos.proveedor_id, 'proveedor_id'))
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    if not proveedor or not proveedor.activo:
        raise no_encontrado('El proveedor')
    if comercio.usuario_id != usuario.id:
        raise prohibido('Sólo el dueño del comercio puede hacer pedidos para él.')
    pedido = flujo.obtener_borrador(comercio, proveedor, usuario)
    for partida in datos.partidas:
        flujo.agregar_producto(pedido, partida.producto_id, partida.cantidad, usuario)
    if datos.notas:
        pedido.notas = datos.notas
    db.session.commit()
    return pedido_a_dict(pedido, detalle=True)


@srv.ruta('/pedidos/<uuid:id>', 'GET', resumen='Detalle del pedido', etiqueta='Pedidos',
          permisos=['pedidos.crear', 'pedidos.atender', 'pedidos.ver_todos'], raiz_xml='pedido',
         )
def detalle(id):
    """Incluye `acciones`: las transiciones que el usuario del token puede ejecutar ahora."""
    return pedido_a_dict(_pedido(id), detalle=True)


@srv.ruta('/pedidos/<uuid:id>/partidas', 'POST', resumen='Agregar partida al borrador', etiqueta='Pedidos',
          permisos=['pedidos.crear'], cuerpo=PartidaEntrada, status=201, raiz_xml='pedido',
          entrada_xml='partida_entrada',
          ejemplo_entrada={'producto_id': 14, 'cantidad': 10})
def agregar_partida(id, datos):
    pedido = _pedido(id)
    if not flujo.es_del_comercio(pedido, usuario_actual()):
        raise prohibido('Sólo el comercio puede modificar su pedido.')
    flujo.agregar_producto(pedido, datos.producto_id, datos.cantidad, usuario_actual())
    db.session.commit()
    return pedido_a_dict(pedido, detalle=True)


@srv.ruta('/pedidos/<uuid:id>/partidas/<int:partida_id>', 'DELETE', resumen='Quitar partida del borrador',
          etiqueta='Pedidos', permisos=['pedidos.crear'], raiz_xml='pedido')
def quitar_partida(id, partida_id):
    pedido = _pedido(id)
    if not flujo.es_del_comercio(pedido, usuario_actual()):
        raise prohibido('Sólo el comercio puede modificar su pedido.')
    flujo.quitar_producto(pedido, partida_id, usuario_actual())
    db.session.commit()
    return pedido_a_dict(pedido, detalle=True)


@srv.ruta('/pedidos/<uuid:id>/acciones/<accion>', 'POST', resumen='Ejecutar una transición del pedido',
          etiqueta='Pedidos', permisos=['pedidos.crear', 'pedidos.atender'], cuerpo=AccionEntrada,
          raiz_xml='pedido', entrada_xml='accion_entrada',
          ejemplo_entrada={'comentario': 'Sin existencia de aceite esta semana'})
def ejecutar(id, accion, datos):
    """`accion`: enviar, cancelar (comercio); aceptar, rechazar, preparar, despachar (proveedor u operador);
    recibir (comercio). El cuerpo es opcional salvo al rechazar. Una transición no permitida desde el estado
    actual responde 409. Mientras se ejecuta, un bloqueo en Redis impide aplicarla dos veces."""
    if accion not in flujo.TRANSICIONES:
        raise ErrorApi(404, 'accion_inexistente', f'Acción no válida. Usa: {", ".join(flujo.TRANSICIONES)}.')
    with bloqueo(f'pedido:{id}', ttl_segundos=30, mensaje='El pedido se está actualizando; intenta de nuevo.'):
        pedido = _pedido(id)
        anterior = pedido.estado
        nuevo = flujo.ejecutar_accion(pedido, accion, usuario_actual(), datos.comentario)
        db.session.commit()
    return {**pedido_a_dict(pedido, detalle=True), 'transicion': {'accion': accion, 'de': anterior, 'a': nuevo}}


@srv.ruta('/pedidos/<uuid:id>/historial', 'GET', resumen='Historial (PostgreSQL) y eventos (MongoDB)',
          etiqueta='Pedidos', permisos=['pedidos.crear', 'pedidos.atender', 'pedidos.ver_todos'], raiz_xml='historial')
def historial(id):
    pedido = _pedido(id)
    return {
        'pedido_id': str(pedido.id), 'folio': pedido.folio_legible,
        'historial': [{'de': h.estado_anterior, 'a': h.estado_nuevo, 'a_legible': ESTADOS_PEDIDO[h.estado_nuevo],
                       'usuario_id': str(h.usuario_id) if h.usuario_id else None, 'comentario': h.comentario,
                       'fecha': h.created_at} for h in pedido.historial],
        'eventos': eventos.linea_tiempo(pedido.id),
    }


@srv.ruta('/estadisticas/proveedores', 'GET', resumen='Desempeño de proveedores (agregación MongoDB)',
          etiqueta='Estadísticas', permisos=['pedidos.ver_todos', 'analisis.ver', 'pedidos.atender'],
          consulta=EstadisticasConsulta, raiz_xml='desempeno')
def desempeno(q):
    """Horas promedio de respuesta y de entrega, pedidos, monto y tasa de rechazo por proveedor, calculados con un
    pipeline sobre eventos_pedido. Un proveedor sólo ve su propio renglón."""
    proveedor_id = None
    if not (tiene('pedidos.ver_todos') or tiene('analisis.ver')):
        empresa = usuario_actual().proveedor_vinculado
        if not empresa:
            raise ErrorApi(409, 'sin_empresa', 'Tu cuenta no está ligada a un proveedor.')
        proveedor_id = empresa.id
    filas = eventos.desempeno_proveedores(q.dias, proveedor_id)
    nombres = {str(p.id): p.nombre_empresa for p in Proveedor.query.all()}
    return {'dias': q.dias, 'proveedores': [{**f, 'proveedor': nombres.get(f['proveedor_id'])} for f in filas]}


@srv.ruta('/estadisticas/productos', 'GET', resumen='Productos más pedidos (agregación MongoDB)',
          etiqueta='Estadísticas', permisos=['pedidos.ver_todos', 'analisis.ver'], consulta=EstadisticasConsulta,
          raiz_xml='productos_pedidos')
def productos_mas_pedidos(q):
    return {'dias': q.dias, 'zona_id': q.zona_id, 'productos': eventos.productos_mas_pedidos(q.dias, q.zona_id)}
