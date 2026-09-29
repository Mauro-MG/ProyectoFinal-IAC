"""
Pedidos de abasto: del comercio al proveedor.

    BORRADOR -> ENVIADO -> ACEPTADO -> EN_PREPARACION -> ENVIADO_A_COMERCIO -> ENTREGADO
                   |          `-> (el proveedor puede) RECHAZADO
                   `-> (el comercio puede) CANCELADO   (también desde BORRADOR)

Reglas aplicadas:
  RN-004  No se envía un pedido cuyo subtotal no alcance el pedido mínimo del proveedor.
  RN-010  Sólo se permiten las transiciones de la tabla TRANSICIONES y cada una
          queda en historial_pedido y en auditoría.
  RN-011  El proveedor debe entregar en la zona del comercio.
  RN-012  Cada partida respeta la cantidad mínima de venta del proveedor.
  RN-013  Al recibir el pedido se generan entradas de inventario en el comercio.
  RN-014  La plataforma cobra COMISION_PEDIDO_PCT % sobre los pedidos entregados.
"""
from datetime import date, timedelta
from decimal import Decimal

from flask import url_for

from app.extensions import db
from app.models.pedido import ESTADOS_PEDIDO
from app.models import CatalogoProveedor, DetallePedido, HistorialPedido, InventarioComercio, PedidoAbasto
from app.servicios import ReglaNegocioError
from app.servicios.auditoria import registrar_evento
from app.servicios.inventario import registrar_movimiento
from app.servicios.notificaciones import notificar
from app.servicios.parametros import parametro

# accion: (estados desde los que se puede ejecutar, estado resultante, quién la ejecuta)
TRANSICIONES = {
    'enviar':    (('BORRADOR',), 'ENVIADO', 'comercio'),
    'cancelar':  (('BORRADOR', 'ENVIADO'), 'CANCELADO', 'comercio'),
    'aceptar':   (('ENVIADO',), 'ACEPTADO', 'proveedor'),
    'rechazar':  (('ENVIADO',), 'RECHAZADO', 'proveedor'),
    'preparar':  (('ACEPTADO',), 'EN_PREPARACION', 'proveedor'),
    'despachar': (('EN_PREPARACION',), 'ENVIADO_A_COMERCIO', 'proveedor'),
    'recibir':   (('ENVIADO_A_COMERCIO',), 'ENTREGADO', 'comercio'),
}

ETIQUETAS_ACCION = {
    'enviar': 'Confirmar y enviar',
    'cancelar': 'Cancelar pedido',
    'aceptar': 'Aceptar',
    'rechazar': 'Rechazar',
    'preparar': 'Marcar en preparación',
    'despachar': 'Marcar como enviado',
    'recibir': 'Confirmar recepción',
}


def es_del_comercio(pedido, usuario):
    return pedido.comercio.usuario_id == usuario.id


def es_del_proveedor(pedido, usuario):
    return pedido.proveedor.usuario_id == usuario.id


def puede_ver(pedido, usuario):
    return (es_del_comercio(pedido, usuario) or es_del_proveedor(pedido, usuario)
            or usuario.tiene_permiso('pedidos.ver_todos'))


def acciones_disponibles(pedido, usuario):
    acciones = []
    for accion, (origenes, _, lado) in TRANSICIONES.items():
        if pedido.estado not in origenes:
            continue
        if (lado == 'comercio' and es_del_comercio(pedido, usuario)) or \
           (lado == 'proveedor' and es_del_proveedor(pedido, usuario)):
            acciones.append(accion)
    return acciones


def _registrar_historial(pedido, anterior, nuevo, usuario, comentario=None):
    db.session.add(HistorialPedido(pedido_id=pedido.id, estado_anterior=anterior, estado_nuevo=nuevo,
                                   usuario_id=usuario.id, comentario=comentario))


def obtener_borrador(comercio, proveedor, usuario):
    """Regresa el borrador abierto entre el comercio y el proveedor, o crea uno nuevo."""
    if not proveedor.cubre_zona(comercio.zona_id):
        raise ReglaNegocioError(f'{proveedor.nombre_empresa} no entrega en la zona de {comercio.nombre_comercio}.')

    pedido = PedidoAbasto.query.filter_by(comercio_id=comercio.id, proveedor_id=proveedor.id,
                                          estado='BORRADOR').first()
    if pedido:
        return pedido

    pedido = PedidoAbasto(comercio_id=comercio.id, proveedor_id=proveedor.id, estado='BORRADOR',
                          usuario_creacion_id=usuario.id)
    db.session.add(pedido)
    db.session.flush()
    _registrar_historial(pedido, None, 'BORRADOR', usuario)
    registrar_evento(usuario.id, 'CREACION', 'PedidoAbasto', pedido.id,
                     f'Borrador de pedido de {comercio.nombre_comercio} a {proveedor.nombre_empresa}')
    return pedido


def agregar_producto(pedido, producto_id, cantidad, usuario):
    if pedido.estado != 'BORRADOR':
        raise ReglaNegocioError('Sólo se pueden modificar pedidos en borrador.')
    cantidad = Decimal(str(cantidad))
    oferta = CatalogoProveedor.query.filter_by(proveedor_id=pedido.proveedor_id, producto_id=producto_id,
                                               activo=True).first()
    if not oferta:
        raise ReglaNegocioError('El proveedor no ofrece ese producto.')

    detalle = next((d for d in pedido.detalles if d.producto_id == producto_id), None)
    total = cantidad + (detalle.cantidad if detalle else 0)
    if total < oferta.cantidad_minima:
        raise ReglaNegocioError(
            f'{oferta.producto.nombre}: la venta mínima del proveedor es de '
            f'{oferta.cantidad_minima.normalize():f} {oferta.producto.unidad_medida}.')

    if detalle:
        detalle.cantidad = total
    else:
        detalle = DetallePedido(producto_id=producto_id, cantidad=total)
        pedido.detalles.append(detalle)
    detalle.precio_unitario = oferta.precio_mayoreo
    detalle.subtotal = (detalle.cantidad * detalle.precio_unitario).quantize(Decimal('0.01'))
    pedido.recalcular_subtotal()
    registrar_evento(usuario.id, 'ACTUALIZACION', 'PedidoAbasto', pedido.id,
                     f'Se agregó {oferta.producto.nombre} al pedido {pedido.folio_legible}',
                     datos_nuevos={'producto_id': producto_id, 'cantidad': total,
                                   'precio_unitario': oferta.precio_mayoreo})


def quitar_producto(pedido, detalle_id, usuario):
    if pedido.estado != 'BORRADOR':
        raise ReglaNegocioError('Sólo se pueden modificar pedidos en borrador.')
    detalle = next((d for d in pedido.detalles if d.id == detalle_id), None)
    if not detalle:
        raise ReglaNegocioError('La partida no existe.')
    pedido.detalles.remove(detalle)
    pedido.recalcular_subtotal()
    registrar_evento(usuario.id, 'ACTUALIZACION', 'PedidoAbasto', pedido.id,
                     f'Se quitó {detalle.producto.nombre} del pedido {pedido.folio_legible}')


def _validar_envio(pedido):
    if not pedido.detalles:
        raise ReglaNegocioError('Agrega al menos un producto antes de enviar el pedido.')
    if pedido.subtotal < pedido.proveedor.pedido_minimo:
        raise ReglaNegocioError(
            f'El pedido mínimo de {pedido.proveedor.nombre_empresa} es de ${pedido.proveedor.pedido_minimo:,.2f}; '
            f'tu pedido suma ${pedido.subtotal:,.2f}.')
    if not pedido.proveedor.cubre_zona(pedido.comercio.zona_id):
        raise ReglaNegocioError('El proveedor ya no entrega en la zona del comercio.')


def _ofertas_bloqueadas(pedido):
    ids = [d.producto_id for d in pedido.detalles]
    ofertas = (CatalogoProveedor.query
               .filter(CatalogoProveedor.proveedor_id == pedido.proveedor_id,
                       CatalogoProveedor.producto_id.in_(ids))
               .with_for_update()
               .all())
    return {o.producto_id: o for o in ofertas}


def _validar_existencia_proveedor(pedido, ofertas):
    faltantes = [d.producto.nombre for d in pedido.detalles
                 if d.producto_id not in ofertas or ofertas[d.producto_id].existencia_disponible < d.cantidad]
    if faltantes:
        raise ReglaNegocioError('No hay existencia suficiente de: ' + ', '.join(faltantes) +
                                '. Actualiza tu catálogo o rechaza el pedido.')


def _recibir_en_inventario(pedido, usuario):
    for detalle in pedido.detalles:
        inventario = InventarioComercio.query.filter_by(comercio_id=pedido.comercio_id,
                                                        producto_id=detalle.producto_id).first()
        if not inventario:
            # El comercio empieza a vender un producto que pidió por primera vez
            inventario = InventarioComercio(comercio_id=pedido.comercio_id, producto_id=detalle.producto_id,
                                            existencia=0, stock_minimo=0)
            db.session.add(inventario)
            db.session.flush()
        inventario.activo = True
        registrar_movimiento(inventario, 'ENTRADA', detalle.cantidad, usuario,
                             motivo=f'Recepción del pedido {pedido.folio_legible}', pedido=pedido)


def ejecutar_accion(pedido, accion, usuario, comentario=None):
    if accion not in TRANSICIONES:
        raise ReglaNegocioError('Acción no válida.')
    if accion not in acciones_disponibles(pedido, usuario):
        raise ReglaNegocioError(f'No puedes {ETIQUETAS_ACCION[accion].lower()} un pedido en estado '
                                f'{pedido.estado_legible.lower()}.')

    anterior = pedido.estado
    nuevo = TRANSICIONES[accion][1]

    if accion == 'enviar':
        _validar_envio(pedido)
        pedido.fecha_envio = db.func.now()
    elif accion == 'aceptar':
        _validar_existencia_proveedor(pedido, _ofertas_bloqueadas(pedido))
        pedido.fecha_respuesta = db.func.now()
        pedido.fecha_entrega_estimada = date.today() + timedelta(days=pedido.proveedor.tiempo_entrega_dias)
    elif accion == 'rechazar':
        if not comentario:
            raise ReglaNegocioError('Indica el motivo del rechazo para que el comerciante sepa qué hacer.')
        pedido.fecha_respuesta = db.func.now()
        pedido.motivo_rechazo = comentario
    elif accion == 'despachar':
        ofertas = _ofertas_bloqueadas(pedido)
        _validar_existencia_proveedor(pedido, ofertas)
        for detalle in pedido.detalles:
            ofertas[detalle.producto_id].existencia_disponible -= detalle.cantidad
    elif accion == 'recibir':
        _recibir_en_inventario(pedido, usuario)
        pedido.fecha_entrega_real = db.func.now()
        comision = Decimal(str(parametro('COMISION_PEDIDO_PCT'))) / 100
        pedido.comision_plataforma = (pedido.subtotal * comision).quantize(Decimal('0.01'))

    pedido.estado = nuevo
    _registrar_historial(pedido, anterior, nuevo, usuario, comentario)
    registrar_evento(usuario.id, 'CAMBIO_ESTADO', 'PedidoAbasto', pedido.id,
                     f'Pedido {pedido.folio_legible}: {anterior} -> {nuevo}',
                     datos_anteriores={'estado': anterior},
                     datos_nuevos={'estado': nuevo, 'comentario': comentario})

    # Avisar a la otra parte
    lado = TRANSICIONES[accion][2]
    destinatario = pedido.proveedor.usuario_id if lado == 'comercio' else pedido.comercio.usuario_id
    notificar(destinatario, f'pedido.{accion}',
              f'Pedido {pedido.folio_legible} ({pedido.comercio.nombre_comercio} / '
              f'{pedido.proveedor.nombre_empresa}): {ESTADOS_PEDIDO[nuevo].lower()}',
              url_for('pedido_detalle', id=pedido.id))
    return nuevo
