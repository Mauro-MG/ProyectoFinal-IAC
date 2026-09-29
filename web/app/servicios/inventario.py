"""
Catálogo del comercio, existencias y precios.

Reglas aplicadas:
  RN-001  Un precio fuera del 10 %-150 % del promedio de la zona (últimos 7 días)
          queda PENDIENTE_VALIDACION y no entra en la comparación.
  RN-009  Toda variación de existencia se registra como movimiento
          (ENTRADA, SALIDA o AJUSTE); la existencia nunca queda negativa.
"""
from datetime import timedelta
from decimal import Decimal

from flask import current_app
from redis.exceptions import RedisError
from sqlalchemy import func

from app import extensions
from app.extensions import db
from app.models import Comercio, InventarioComercio, MovimientoInventario, PrecioComercio
from app.servicios import ReglaNegocioError
from app.servicios.auditoria import registrar_evento
from app.servicios.cache import invalidar_analisis


def _bloquear(inventario):
    """Relee el renglón con SELECT ... FOR UPDATE para evitar actualizaciones perdidas."""
    return (db.session.query(InventarioComercio)
            .filter_by(id=inventario.id)
            .with_for_update()
            .populate_existing()
            .one())


def agregar_al_catalogo(comercio, producto, usuario, existencia=0, stock_minimo=0,
                        stock_maximo=None, precio=None):
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
    if precio:
        actualizar_precio(inventario, precio, usuario)
    invalidar_analisis()
    return inventario


def quitar_del_catalogo(inventario, usuario):
    inventario.activo = False
    registrar_evento(usuario.id, 'ELIMINACION', 'InventarioComercio', inventario.id,
                     f'{inventario.producto.nombre} retirado del catálogo de {inventario.comercio.nombre_comercio}')
    invalidar_analisis()


def registrar_movimiento(inventario, tipo, cantidad, usuario, motivo=None, pedido=None):
    """
    ENTRADA suma, SALIDA resta y AJUSTE fija la existencia al conteo físico
    capturado (en ese caso `cantidad` es el conteo, no la diferencia).
    """
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
    )
    db.session.add(movimiento)
    registrar_evento(usuario.id, 'ACTUALIZACION', 'InventarioComercio', inventario.id,
                     f'{tipo.capitalize()} de {inventario.producto.nombre}'
                     f'{" (" + motivo + ")" if motivo else ""}',
                     datos_anteriores={'existencia': anterior},
                     datos_nuevos={'existencia': nueva})
    invalidar_analisis()
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
            extensions.redis_client.setex(
                f'precio_promedio:zona:{comercio.zona_id}:producto:{inventario.producto_id}',
                current_app.config['PRECIO_PROMEDIO_TTL_SEGUNDOS'], f'{promedio:.2f}')
        except RedisError:
            current_app.logger.warning('No se pudo actualizar la caché de precios en Redis.')
    return estado_validacion
