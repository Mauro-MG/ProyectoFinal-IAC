"""
Catálogo del comercio, existencias y precios.

Reglas aplicadas:
  RN-001  Un precio fuera del 10 %-150 % del promedio de la zona (últimos 7 días)
          queda PENDIENTE_VALIDACION y no entra en la comparación.
  RN-009  Toda variación de existencia se registra como movimiento
          (ENTRADA, SALIDA o AJUSTE); la existencia nunca queda negativa.
  RN-017  Una SALIDA no puede tomar lo que está reservado (reservas activas no vencidas).
  RN-018  Un movimiento con `referencia` (venta, lote offline, transferencia, pedido) se aplica
          una sola vez por renglón: si llega repetido se regresa el que ya existía.
"""
from datetime import timedelta
from decimal import Decimal

from flask import current_app
from redis.exceptions import RedisError
from sqlalchemy import func

from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import (Comercio, InventarioComercio, MovimientoInventario, PrecioComercio,
                                    ReservaInventario)
from abasto_dominio.servicios import ReglaNegocioError
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.notificaciones import notificar


def estado_stock(existencia, minimo):
    """Misma regla que la columna generada inventario_comercio.estado."""
    if existencia <= 0:
        return 'AGOTADO'
    return 'BAJO' if existencia <= minimo else 'DISPONIBLE'


def _avisar_si_bajo(inventario, anterior, nueva):
    antes, despues = estado_stock(anterior, inventario.stock_minimo), estado_stock(nueva, inventario.stock_minimo)
    if antes == despues or despues == 'DISPONIBLE':
        return
    producto = inventario.producto
    notificar(inventario.comercio.usuario_id, 'stock_bajo',
              f'{producto.nombre}: {"agotado" if despues == "AGOTADO" else "stock bajo"}',
              f'{inventario.comercio.nombre_comercio} tiene {nueva.normalize():f} {producto.unidad_medida} '
              f'(mínimo {inventario.stock_minimo.normalize():f}).',
              url=f'/proveedores/buscar?producto_id={producto.id}&comercio_id={inventario.comercio_id}',
              entidad={'tipo': 'inventario', 'id': str(inventario.id)},
              prioridad='alta' if despues == 'AGOTADO' else 'normal', origen='inventario')


def _bloquear(inventario):
    """Relee el renglón con SELECT ... FOR UPDATE para evitar actualizaciones perdidas."""
    return (db.session.query(InventarioComercio)
            .filter_by(id=inventario.id)
            .with_for_update()
            .populate_existing()
            .one())


def agregar_al_catalogo(comercio, producto, usuario, existencia=0, stock_minimo=0, stock_maximo=None):
    """Agrega el producto al catálogo del comercio. El precio inicial no se fija aquí: lo fija ms-precios
    (dueño de precios_comercio) con PUT /inventario/{id}/precio una vez confirmado el renglón."""
    existente = InventarioComercio.query.filter_by(comercio_id=comercio.id, producto_id=producto.id).first()
    if existente and existente.activo:
        raise ReglaNegocioError(f'{producto.nombre} ya está en el catálogo de {comercio.nombre_comercio}.')
    if stock_maximo is not None and stock_maximo < stock_minimo:
        raise ReglaNegocioError('El stock máximo no puede ser menor que el mínimo.')

    inventario = existente or InventarioComercio(comercio_id=comercio.id, producto_id=producto.id, existencia=0)
    inventario.activo = True
    inventario.stock_minimo = stock_minimo
    inventario.stock_maximo = stock_maximo
    db.session.add(inventario)
    db.session.flush()

    registrar_evento(usuario.id, 'CREACION', 'InventarioComercio', inventario.id,
                     f'{producto.nombre} agregado al catálogo de {comercio.nombre_comercio}',
                     datos_nuevos={'stock_minimo': stock_minimo, 'stock_maximo': stock_maximo})

    if existencia and existencia > 0:
        registrar_movimiento(inventario, 'ENTRADA', existencia, usuario, motivo='Existencia inicial')
    invalidar_analisis()
    return inventario


def quitar_del_catalogo(inventario, usuario):
    inventario.activo = False
    registrar_evento(usuario.id, 'ELIMINACION', 'InventarioComercio', inventario.id,
                     f'{inventario.producto.nombre} retirado del catálogo de {inventario.comercio.nombre_comercio}')
    invalidar_analisis()


def reservado(inventario_id, excepto=None):
    """Cantidad apartada por reservas activas que no han vencido."""
    consulta = (db.session.query(func.coalesce(func.sum(ReservaInventario.cantidad), 0))
                .filter(ReservaInventario.inventario_id == inventario_id, ReservaInventario.estado == 'ACTIVA',
                        ReservaInventario.expira_at > func.now()))   # hora de la base, no la del contenedor
    if excepto is not None:
        consulta = consulta.filter(ReservaInventario.id != excepto)
    return Decimal(str(consulta.scalar()))


def movimiento_por_referencia(inventario_id, referencia):
    if not referencia:
        return None
    return MovimientoInventario.query.filter_by(inventario_id=inventario_id, referencia=referencia).first()


def registrar_movimiento(inventario, tipo, cantidad, usuario, motivo=None, pedido=None, referencia=None,
                         reserva_consumida=None):
    """
    ENTRADA suma, SALIDA resta y AJUSTE fija la existencia al conteo físico
    capturado (en ese caso `cantidad` es el conteo, no la diferencia).
    Con `referencia`, un movimiento repetido no se vuelve a aplicar (RN-018).
    `reserva_consumida`: id de la reserva que esta salida está surtiendo (no cuenta contra la salida).
    """
    repetido = movimiento_por_referencia(inventario.id, referencia)
    if repetido:
        return repetido
    cantidad = Decimal(str(cantidad))
    if cantidad < 0:
        raise ReglaNegocioError('La cantidad no puede ser negativa.')
    if tipo in ('ENTRADA', 'SALIDA') and cantidad == 0:
        raise ReglaNegocioError('La cantidad debe ser mayor a cero.')

    inventario = _bloquear(inventario)
    anterior = inventario.existencia

    if tipo == 'ENTRADA':
        nueva = anterior + cantidad
    elif tipo == 'SALIDA':
        if cantidad > anterior:
            raise ReglaNegocioError(
                f'No hay suficiente existencia: tienes {anterior.normalize():f} y quieres sacar {cantidad.normalize():f}.')
        apartado = reservado(inventario.id, excepto=reserva_consumida)
        if cantidad > anterior - apartado:
            raise ReglaNegocioError(
                f'{apartado.normalize():f} {inventario.producto.unidad_medida} están reservados: sólo puedes sacar '
                f'{(anterior - apartado).normalize():f}.')
        nueva = anterior - cantidad
    elif tipo == 'AJUSTE':
        if not motivo:
            raise ReglaNegocioError('Indica el motivo del ajuste (conteo físico, merma, caducidad...).')
        nueva = cantidad
    else:
        raise ReglaNegocioError('Tipo de movimiento no válido.')

    inventario.existencia = nueva
    movimiento = MovimientoInventario(
        inventario_id=inventario.id,
        tipo=tipo,
        cantidad=abs(nueva - anterior) if tipo == 'AJUSTE' else cantidad,
        existencia_anterior=anterior,
        existencia_nueva=nueva,
        motivo=motivo,
        pedido_id=pedido.id if pedido else None,
        usuario_id=usuario.id,
        referencia=referencia,
    )
    db.session.add(movimiento)
    registrar_evento(usuario.id, 'ACTUALIZACION', 'InventarioComercio', inventario.id,
                     f'{tipo.capitalize()} de {inventario.producto.nombre}'
                     f'{" (" + motivo + ")" if motivo else ""}',
                     datos_anteriores={'existencia': anterior},
                     datos_nuevos={'existencia': nueva})
    invalidar_analisis()
    _avisar_si_bajo(inventario, anterior, nueva)
    return movimiento


def promedio_zona(zona_id, producto_id, dias=7):
    return (db.session.query(func.avg(PrecioComercio.precio))
            .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
            .filter(Comercio.zona_id == zona_id,
                    PrecioComercio.producto_id == producto_id,
                    PrecioComercio.fecha_registro >= func.now() - timedelta(days=dias),
                    PrecioComercio.activo.is_(True),
                    PrecioComercio.estado_validacion == 'VALIDADO')
            .scalar())


def actualizar_precio(inventario, precio_nuevo, usuario, metodo_captura='MANUAL'):
    """Cambia el precio de venta y lo guarda en el historial. Regresa el estado de validación."""
    precio_nuevo = Decimal(str(precio_nuevo))
    if precio_nuevo <= 0:
        raise ReglaNegocioError('El precio debe ser mayor a cero.')
    anterior = inventario.precio_venta
    if anterior == precio_nuevo:
        return 'SIN_CAMBIO'

    comercio = inventario.comercio
    promedio = promedio_zona(comercio.zona_id, inventario.producto_id) if comercio.zona_id else None
    estado_validacion, notas = 'VALIDADO', None
    if promedio and not (promedio * Decimal('0.10') <= precio_nuevo <= promedio * Decimal('1.50')):
        estado_validacion = 'PENDIENTE_VALIDACION'
        notas = f'Fuera del rango esperado para la zona (promedio 7 días: ${promedio:.2f}).'

    inventario.precio_venta = precio_nuevo
    db.session.add(PrecioComercio(
        comercio_id=comercio.id,
        producto_id=inventario.producto_id,
        precio=precio_nuevo,
        precio_anterior=anterior,
        metodo_captura=metodo_captura,
        estado_validacion=estado_validacion,
        usuario_registro_id=usuario.id,
        notas=notas,
    ))
    registrar_evento(usuario.id, 'ACTUALIZACION', 'PrecioComercio', inventario.id,
                     f'Precio de {inventario.producto.nombre} en {comercio.nombre_comercio}',
                     datos_anteriores={'precio': anterior},
                     datos_nuevos={'precio': precio_nuevo, 'estado_validacion': estado_validacion})

    if comercio.zona_id and promedio:
        try:
            extensiones.redis_client.setex(
                f'precio_promedio:zona:{comercio.zona_id}:producto:{inventario.producto_id}',
                current_app.config['PRECIO_PROMEDIO_TTL_SEGUNDOS'], f'{promedio:.2f}')
        except RedisError:
            current_app.logger.warning('No se pudo actualizar la caché de precios en Redis.')
    if estado_validacion == 'PENDIENTE_VALIDACION':
        notificar(comercio.usuario_id, 'precio_atipico', f'Precio de {inventario.producto.nombre} en revisión',
                  f'${precio_nuevo:,.2f} está lejos del promedio de tu zona; no aparece en comparaciones '
                  'hasta que se valide.', url=f'/inventario/item/{inventario.id}',
                  entidad={'tipo': 'inventario', 'id': str(inventario.id)}, origen='precios')
    return estado_validacion
