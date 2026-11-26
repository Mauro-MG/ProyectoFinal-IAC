"""
ms-ventas: ventas y devoluciones del comercio con actualización de inventario.

Es DUEÑO de: ventas, detalle_ventas, devoluciones y detalle_devoluciones. NO escribe en el
inventario: descuenta (o regresa) la mercancía con POST /comercios/{id}/movimientos/lote de
ms-inventario, con el token del usuario y el mismo X-Correlation-ID (la traza completa se ve en
ms-auditoria → /trazas/{correlation_id}).

Consistencia entre los dos servicios (patrón saga, ver docs/propiedad_de_datos.md):
1. Se valida la venta y se calcula su id, sin escribir todavía.
2. ms-inventario aplica TODAS las salidas en una transacción con referencia `venta:{id}`
   (si una partida no alcanza, responde 409 y no cambia nada: la venta no se registra).
3. Se guarda la venta. Si este paso fallara, se compensa con un lote de ENTRADAS
   `venta-anulada:{id}`. Si el cliente reintenta, la referencia evita descontar dos veces.

Idempotencia para las apps offline: `id_cliente` (UUID generado en el dispositivo) es único;
si la misma venta llega dos veces se responde la que ya existe con `duplicada: true`.
"""
import hashlib
import uuid
from collections import namedtuple
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from flask import g
from sqlalchemy import func, text

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene, usuario_actual
from abasto_api.clientes import llamar
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, InventarioComercio
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.bloqueos import bloqueo

from esquemas import CONTRATOS_XML, DevolucionEntrada, ProductosConsulta, ResumenConsulta, VentaEntrada, VentasConsulta
from modelos import DetalleDevolucion, DetalleVenta, Devolucion, Venta

srv = Servicio('ventas', 'Ventas',
               'Registro de ventas y devoluciones con detalle de productos y cantidades, actualización transaccional '
               'del inventario (por ms-inventario), historial comercial, ventas por periodo, comercio y producto, y '
               'comprobantes internos.',
               xsd=Path(__file__).parent / 'xsd' / 'ventas.xsd', contratos=CONTRATOS_XML)
app = srv.app

DOS = Decimal('0.01')
ESPACIO_VENTAS = uuid.UUID('6f1d3c52-8a1e-4b7e-9c41-2b5e0a7d9f30')   # espacio fijo para uuid5(comercio:id_cliente)
PorDevolver = namedtuple('PorDevolver', 'partida_id cantidad')


def _uuid(valor, campo):
    try:
        return uuid.UUID(str(valor))
    except ValueError:
        raise ErrorApi(400, 'parametro_invalido', f'{campo} debe ser un UUID.')


def _comercio(comercio_id, editar=True):
    comercio = db.session.get(Comercio, _uuid(comercio_id, 'comercio_id'))
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    if str(comercio.usuario_id) != g.claims['sub'] and not (not editar and tiene('comercios.ver_todos')):
        raise prohibido('El comercio no es tuyo.')
    return comercio


def partida_a_dict(d):
    return {'id': d.id, 'producto_id': d.producto_id, 'producto': d.producto.nombre,
            'unidad_medida': d.producto.unidad_medida, 'cantidad': d.cantidad, 'precio_unitario': d.precio_unitario,
            'subtotal': d.subtotal, 'cantidad_devuelta': d.cantidad_devuelta}


def venta_a_dict(v, detalle=True):
    datos = {'id': str(v.id), 'folio': v.folio_legible, 'comercio_id': str(v.comercio_id),
             'comercio': v.comercio.nombre_comercio, 'total': v.total,
             'total_devuelto': sum((d.total for d in v.devoluciones), Decimal(0)), 'metodo_pago': v.metodo_pago,
             'estado': v.estado, 'origen': v.origen, 'id_cliente': v.id_cliente, 'fecha_venta': v.fecha_venta}
    if detalle:
        datos['partidas'] = [partida_a_dict(d) for d in v.partidas]
        datos['devoluciones'] = [{'id': d.id, 'motivo': d.motivo, 'total': d.total, 'fecha': d.created_at}
                                 for d in v.devoluciones]
    return datos


def precio_vigente(renglon):
    """Precio promocional vigente (de ms-precios, sólo lectura) o el precio de venta del renglón."""
    promocion = db.session.execute(text(
        'SELECT precio_promocional FROM promociones WHERE inventario_id = :i AND activa '
        'AND CURRENT_DATE BETWEEN inicio AND fin ORDER BY precio_promocional LIMIT 1'), {'i': renglon.id}).scalar()
    return promocion if promocion is not None else renglon.precio_venta


def mover_inventario(comercio_id, referencia, movimientos):
    """Llama a ms-inventario con el token del usuario. Traduce sus errores a errores de esta API."""
    respuesta = llamar('inventario', 'POST', f'/api/v1/comercios/{comercio_id}/movimientos/lote', token=g.token,
                       json={'referencia': referencia, 'movimientos': movimientos})
    if respuesta.status_code in (200, 201):
        return respuesta.json()
    try:
        error = respuesta.json().get('error', {})
    except ValueError:
        error = {}
    if respuesta.status_code in (409, 422):
        raise ErrorApi(409, 'inventario_insuficiente', f"ms-inventario rechazó el movimiento: {error.get('mensaje')}",
                       detalles=error.get('detalles'))
    if respuesta.status_code in (401, 403):
        raise ErrorApi(403, 'sin_permiso', f"ms-inventario: {error.get('mensaje')}")
    raise ErrorApi(503, 'servicio_no_disponible', f'ms-inventario respondió {respuesta.status_code}; no se registró.')


# ---------------------------------------------------------------- registrar

@srv.ruta('/ventas', 'POST', resumen='Registrar una venta', etiqueta='Ventas', permisos=['ventas.registrar'],
          cuerpo=VentaEntrada, status=201, raiz_xml='venta', entrada_xml='venta_entrada',
          ejemplo_entrada={'comercio_id': '3122a5b1-...', 'metodo_pago': 'EFECTIVO', 'origen': 'android',
                           'id_cliente': '0f8b6c2e-7d1a-4c55-9a3e-1b2c3d4e5f60',
                           'partidas': [{'producto_id': 3, 'cantidad': 2}, {'producto_id': 7, 'cantidad': 1}]})
def registrar(datos):
    """Descuenta el inventario en ms-inventario (todo o nada) y guarda la venta con su folio. Sin `precio_unitario`
    se usa la promoción vigente o el precio de venta del producto. 409 si no alcanza la existencia."""
    if datos.id_cliente:
        previa = Venta.query.filter_by(id_cliente=datos.id_cliente).first()
        if previa:
            if str(previa.comercio_id) != datos.comercio_id:
                raise ErrorApi(409, 'id_cliente_duplicado', 'Ese id_cliente ya se usó en otro comercio.')
            return {**venta_a_dict(previa), 'duplicada': True}, 200
    comercio = _comercio(datos.comercio_id)
    usuario = usuario_actual()
    # Con id_cliente, el id de la venta sale de él (siempre el mismo). Si ms-inventario tardó más que el timeout y
    # aplicó la salida después de que esta petición se rindió, el reintento de la app usa la misma referencia
    # `venta:{id}`: ms-inventario responde «ya aplicado» y no descuenta dos veces (tests/integracion/test_fallas.py).
    venta_id = uuid.uuid5(ESPACIO_VENTAS, f'{comercio.id}:{datos.id_cliente}') if datos.id_cliente else uuid.uuid4()
    partidas, movimientos = [], []
    for i, p in enumerate(datos.partidas):
        if p.inventario_id:
            renglon = db.session.get(InventarioComercio, p.inventario_id)
            renglon = renglon if renglon and renglon.comercio_id == comercio.id else None
        else:
            renglon = InventarioComercio.query.filter_by(comercio_id=comercio.id, producto_id=p.producto_id).first()
        if not renglon or not renglon.activo:
            raise ErrorApi(422, 'producto_no_vendido', f'Partida {i + 1}: el comercio no vende ese producto.',
                           detalles=[{'campo': f'partidas[{i}]', 'mensaje': 'no está en el inventario del comercio'}])
        precio = p.precio_unitario if p.precio_unitario is not None else precio_vigente(renglon)
        if precio is None:
            raise ErrorApi(422, 'sin_precio', f'{renglon.producto.nombre} no tiene precio; envía precio_unitario.')
        partidas.append((renglon, p.cantidad, Decimal(precio)))
        movimientos.append({'inventario_id': renglon.id, 'tipo': 'SALIDA', 'cantidad': str(p.cantidad),
                            'motivo': f'Venta ({datos.metodo_pago.lower()})'})
    total = sum((c * pr for _, c, pr in partidas), Decimal(0)).quantize(DOS)
    db.session.rollback()   # termina la transacción de lectura antes de llamar a ms-inventario (sin bloqueos abiertos)

    mover_inventario(comercio.id, f'venta:{venta_id}', movimientos)
    try:
        venta = Venta(id=venta_id, comercio_id=comercio.id, usuario_id=usuario.id, total=total,
                      metodo_pago=datos.metodo_pago, origen=datos.origen, id_cliente=datos.id_cliente,
                      fecha_venta=datos.fecha_venta or func.now())
        db.session.add(venta)
        for renglon, cantidad, precio in partidas:
            db.session.add(DetalleVenta(venta_id=venta_id, inventario_id=renglon.id, producto_id=renglon.producto_id,
                                        cantidad=cantidad, precio_unitario=precio,
                                        subtotal=(cantidad * precio).quantize(DOS)))
        db.session.flush()
        registrar_evento(usuario.id, 'CREACION', 'Venta', venta.id,
                         f'Venta {venta.folio_legible or ""} de {comercio.nombre_comercio} por ${total}',
                         datos_nuevos={'total': total, 'partidas': len(partidas), 'metodo_pago': datos.metodo_pago,
                                       'origen': datos.origen})
        db.session.commit()
    except Exception:
        db.session.rollback()
        # Compensación: regresar al inventario lo que ya se había descontado
        mover_inventario(comercio.id, f'venta-anulada:{venta_id}', [{**m, 'tipo': 'ENTRADA',
                                                                       'motivo': 'Venta no registrada (compensación)'}
                                                                      for m in movimientos])
        raise
    return venta_a_dict(db.session.get(Venta, venta_id))


@srv.ruta('/ventas/<uuid:id>/devoluciones', 'POST', resumen='Registrar una devolución', etiqueta='Devoluciones',
          permisos=['ventas.registrar'], cuerpo=DevolucionEntrada, status=201, raiz_xml='venta',
          entrada_xml='devolucion_entrada',
          ejemplo_entrada={'motivo': 'Producto en mal estado', 'partidas': [{'partida_id': 15, 'cantidad': 1}]})
def devolver(id, datos):
    """Regresa la mercancía al inventario (ENTRADA en ms-inventario) y marca la venta como DEVUELTA_PARCIAL o
    DEVUELTA. No se puede devolver más de lo vendido menos lo ya devuelto."""
    with bloqueo(f'venta:{id}', ttl_segundos=30, mensaje='La venta se está actualizando; intenta de nuevo.'):
        venta = db.session.get(Venta, id)
        if not venta:
            raise no_encontrado('La venta')
        _comercio(venta.comercio_id)
        if venta.estado == 'DEVUELTA':
            raise ErrorApi(409, 'venta_devuelta', 'La venta ya se devolvió completa.')
        por_id = {d.id: d for d in venta.partidas}
        solicitadas = datos.partidas or [PorDevolver(d.id, d.cantidad - d.cantidad_devuelta)
                                         for d in venta.partidas if d.cantidad > d.cantidad_devuelta]
        cambios = []
        for p in solicitadas:
            detalle = por_id.get(p.partida_id)
            if not detalle:
                raise ErrorApi(422, 'partida_ajena', f'La partida {p.partida_id} no es de esta venta.')
            if p.cantidad > detalle.cantidad - detalle.cantidad_devuelta:
                raise ErrorApi(409, 'devolucion_excedida', f'De {detalle.producto.nombre} sólo quedan '
                               f'{(detalle.cantidad - detalle.cantidad_devuelta).normalize():f} por devolver.')
            cambios.append((detalle, Decimal(p.cantidad)))
        numero = len(venta.devoluciones) + 1
        movimientos = [{'inventario_id': d.inventario_id, 'tipo': 'ENTRADA', 'cantidad': str(c),
                        'motivo': f'Devolución de la venta {venta.folio_legible}: {datos.motivo}'} for d, c in cambios]
        comercio_id = venta.comercio_id
        db.session.rollback()
        mover_inventario(comercio_id, f'devolucion:{id}:{numero}', movimientos)

        venta = db.session.get(Venta, id)
        devolucion = Devolucion(venta_id=venta.id, motivo=datos.motivo, usuario_id=usuario_actual().id,
                                total=sum((db.session.get(DetalleVenta, d.id).precio_unitario * c for d, c in cambios),
                                          Decimal(0)).quantize(DOS))
        db.session.add(devolucion)
        db.session.flush()
        for d, c in cambios:
            detalle = db.session.get(DetalleVenta, d.id)
            detalle.cantidad_devuelta += c
            db.session.add(DetalleDevolucion(devolucion_id=devolucion.id, detalle_venta_id=detalle.id, cantidad=c))
        db.session.flush()
        completa = all(d.cantidad_devuelta >= d.cantidad for d in venta.partidas)
        anterior = venta.estado
        venta.estado = 'DEVUELTA' if completa else 'DEVUELTA_PARCIAL'
        registrar_evento(usuario_actual().id, 'CAMBIO_ESTADO', 'Venta', venta.id,
                         f'Devolución de ${devolucion.total} en la venta {venta.folio_legible}: {datos.motivo}',
                         datos_anteriores={'estado': anterior}, datos_nuevos={'estado': venta.estado,
                                                                               'devuelto': devolucion.total})
        db.session.commit()
    return venta_a_dict(venta)


# ---------------------------------------------------------------- consulta

@srv.ruta('/ventas', 'GET', resumen='Historial de ventas del comercio', etiqueta='Ventas',
          permisos=['ventas.registrar', 'comercios.ver_todos'], consulta=VentasConsulta, raiz_xml='ventas')
def listar(q):
    comercio = _comercio(q.comercio_id, editar=False)
    consulta = Venta.query.filter_by(comercio_id=comercio.id)
    if q.desde:
        consulta = consulta.filter(Venta.fecha_venta >= q.desde)
    if q.hasta:
        consulta = consulta.filter(Venta.fecha_venta < q.hasta + timedelta(days=1))
    if q.metodo_pago:
        consulta = consulta.filter_by(metodo_pago=q.metodo_pago)
    if q.estado:
        consulta = consulta.filter_by(estado=q.estado)
    total = consulta.with_entities(func.coalesce(func.sum(Venta.total), 0)).scalar()
    resultado = paginar(consulta.order_by(Venta.fecha_venta.desc()), q.pagina, q.por_pagina,
                        lambda v: venta_a_dict(v, detalle=False))
    resultado['ventas'] = resultado.pop('items')
    return {**resultado, 'total_periodo': total}


@srv.ruta('/ventas/<uuid:id>', 'GET', resumen='Detalle de una venta', etiqueta='Ventas',
          permisos=['ventas.registrar', 'comercios.ver_todos'], raiz_xml='venta')
def detalle(id):
    venta = db.session.get(Venta, id)
    if not venta:
        raise no_encontrado('La venta')
    _comercio(venta.comercio_id, editar=False)
    return venta_a_dict(venta)


@srv.ruta('/ventas/<uuid:id>/comprobante', 'GET', resumen='Comprobante interno de la venta', etiqueta='Ventas',
          permisos=['ventas.registrar', 'comercios.ver_todos'], raiz_xml='comprobante')
def comprobante(id):
    """Comprobante interno (no fiscal) con su texto listo para imprimir en ticket y una huella SHA-256 de los datos,
    para comprobar que no se alteró."""
    venta = db.session.get(Venta, id)
    if not venta:
        raise no_encontrado('La venta')
    comercio = _comercio(venta.comercio_id, editar=False)
    partidas = [partida_a_dict(d) for d in venta.partidas]
    devuelto = sum((d.total for d in venta.devoluciones), Decimal(0))
    renglones = '\n'.join(f"{p['cantidad']:>6g} {p['producto'][:24]:<24} {p['subtotal']:>9.2f}" for p in partidas)
    texto = (f'{comercio.nombre_comercio}\n{comercio.direccion}\nFolio {venta.folio_legible}  '
             f'{venta.fecha_venta:%d/%m/%Y %H:%M}\n{"-" * 42}\n{renglones}\n{"-" * 42}\n'
             f'TOTAL {venta.total:>36.2f}\n' + (f'DEVUELTO {devuelto:>33.2f}\n' if devuelto else '') +
             f'Pago: {venta.metodo_pago.lower()}\nComprobante interno, sin validez fiscal.')
    datos_firmados = (f'{venta.id}|{venta.folio}|{venta.total}|{venta.fecha_venta.isoformat()}|'
                      + '|'.join(f"{p['producto_id']}:{p['cantidad']}:{p['precio_unitario']}" for p in partidas))
    huella = hashlib.sha256(datos_firmados.encode()).hexdigest()
    return {'folio': venta.folio_legible, 'venta_id': str(venta.id), 'comercio': comercio.nombre_comercio,
            'direccion': comercio.direccion, 'rfc': comercio.rfc, 'fecha': venta.fecha_venta,
            'metodo_pago': venta.metodo_pago, 'partidas': partidas, 'total': venta.total, 'total_devuelto': devuelto,
            'leyenda': 'Comprobante interno, sin validez fiscal.', 'huella_sha256': huella, 'texto': texto}


@srv.ruta('/ventas/resumen', 'GET', resumen='Ventas por día, semana o mes', etiqueta='Estadísticas',
          permisos=['ventas.registrar', 'comercios.ver_todos'], consulta=ResumenConsulta, raiz_xml='resumen')
def resumen(q):
    comercio = _comercio(q.comercio_id, editar=False)
    unidad = {'dia': 'day', 'semana': 'week', 'mes': 'month'}[q.periodo]
    filas = db.session.execute(text(
        f"SELECT date_trunc('{unidad}', v.fecha_venta)::date AS periodo, count(*) AS ventas, sum(v.total) AS total, "
        f'COALESCE(sum((SELECT sum(d.total) FROM devoluciones d WHERE d.venta_id = v.id)), 0) AS devuelto '
        f'FROM ventas v WHERE v.comercio_id = :c AND v.fecha_venta >= :desde GROUP BY 1 ORDER BY 1'),
        {'c': comercio.id, 'desde': date.today() - timedelta(days=q.dias)}).all()
    serie = [{'periodo': f.periodo, 'ventas': f.ventas, 'total': float(f.total),
              'ticket_promedio': round(float(f.total) / f.ventas, 2), 'devuelto': float(f.devuelto)} for f in filas]
    ventas, total = sum(p['ventas'] for p in serie), sum(p['total'] for p in serie)
    return {'comercio_id': str(comercio.id), 'periodo': q.periodo, 'dias': q.dias, 'ventas': ventas, 'total': total,
            'ticket_promedio': round(total / ventas, 2) if ventas else 0.0, 'serie': serie}


@srv.ruta('/ventas/productos', 'GET', resumen='Productos más vendidos', etiqueta='Estadísticas',
          permisos=['ventas.registrar', 'comercios.ver_todos'], consulta=ProductosConsulta, raiz_xml='productos')
def mas_vendidos(q):
    comercio = _comercio(q.comercio_id, editar=False)
    filas = db.session.execute(text(
        'SELECT d.producto_id, p.nombre, sum(d.cantidad - d.cantidad_devuelta) AS unidades, '
        'sum((d.cantidad - d.cantidad_devuelta) * d.precio_unitario) AS importe, count(DISTINCT v.id) AS ventas '
        'FROM detalle_ventas d JOIN ventas v ON v.id = d.venta_id JOIN productos_maestros p ON p.id = d.producto_id '
        'WHERE v.comercio_id = :c AND v.fecha_venta >= :desde GROUP BY d.producto_id, p.nombre '
        'ORDER BY unidades DESC LIMIT :limite'),
        {'c': comercio.id, 'desde': date.today() - timedelta(days=q.dias), 'limite': q.limite}).all()
    return {'comercio_id': str(comercio.id), 'dias': q.dias, 'productos': [
        {'producto_id': f.producto_id, 'producto': f.nombre, 'unidades': float(f.unidades),
         'importe': float(f.importe), 'ventas': f.ventas} for f in filas]}

