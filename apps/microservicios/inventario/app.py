"""
ms-inventario: inventario por comercio, sucursal y producto.

Es DUEÑO de: inventario_comercio, movimientos_inventario, reservas_inventario y
transferencias_inventario. Nadie más los modifica: ms-ventas, ms-pedidos (recepción) y
ms-sincronizacion aplican sus movimientos con POST /comercios/{id}/movimientos/lote.

- Entradas, salidas, ajustes (conteo físico) y transferencias entre sucursales del mismo dueño.
- Existencias mínimas y máximas, alertas de faltantes (aviso por ms-notificaciones).
- Reservas: cantidad apartada que no se puede vender hasta que se consume, se libera o vence.
- Prevención de inventarios negativos: CHECK (existencia >= 0) en la tabla, SELECT ... FOR
  UPDATE al mover y validación contra lo reservado (RN-009, RN-017).
- Idempotencia: un movimiento con `referencia` repetida no se aplica dos veces (RN-018).
- Importación CSV (MongoDB guarda el resultado; el archivo, en Cloud Storage).
Redis: bloqueo `bloqueo:importacion:{comercio}` y `bloqueo:inventario-lote:{referencia}`.
La disponibilidad pública se consulta en ms-disponibilidad.
"""
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from flask import g, request

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene, usuario_actual
from abasto_api.clientes import llamar
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import (Categoria, Comercio, InventarioComercio, MovimientoInventario, ProductoMaestro,
                                    ReservaInventario, TransferenciaInventario)
from abasto_dominio.servicios import ReglaNegocioError, analisis, importaciones
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.bloqueos import bloqueo
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.inventario import (agregar_al_catalogo, quitar_del_catalogo,
                                                registrar_movimiento, reservado)
from abasto_dominio.servicios.parametros import parametro

from esquemas import (CONTRATOS_XML, InventarioConsulta, LimitesEntrada, LoteEntrada, MovimientoEntrada,
                      MovimientosConsulta, RenglonEntrada, ReservaEntrada, SucursalesConsulta, TransferenciaEntrada)

srv = Servicio('inventario', 'Inventario',
               'Inventario por comercio, sucursal y producto: entradas, salidas, ajustes y transferencias; existencias '
               'mínimas; reservas; alertas de faltantes; importación CSV; historial de movimientos y prevención de '
               'inventarios negativos.',
               xsd=Path(__file__).parent / 'xsd' / 'inventario.xsd', contratos=CONTRATOS_XML)
app = srv.app


def renglon_a_dict(r):
    return {'id': r.id, 'comercio_id': str(r.comercio_id), 'producto_id': r.producto_id,
            'producto': r.producto.nombre, 'categoria': r.producto.categoria.nombre,
            'unidad_medida': r.producto.unidad_medida, 'existencia': r.existencia, 'stock_minimo': r.stock_minimo,
            'stock_maximo': r.stock_maximo, 'precio_venta': r.precio_venta, 'estado': r.estado,
            'cantidad_sugerida': r.cantidad_sugerida, 'actualizado': r.updated_at}


def movimiento_a_dict(m):
    return {'id': m.id, 'inventario_id': m.inventario_id, 'tipo': m.tipo, 'cantidad': m.cantidad,
            'existencia_anterior': m.existencia_anterior, 'existencia_nueva': m.existencia_nueva,
            'motivo': m.motivo, 'pedido_id': str(m.pedido_id) if m.pedido_id else None,
            'usuario_id': str(m.usuario_id) if m.usuario_id else None, 'fecha': m.created_at,
            'referencia': m.referencia}


def _comercio(id, editar=True):
    comercio = db.session.get(Comercio, id)
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    es_dueno = str(comercio.usuario_id) == g.claims['sub']
    permitido = es_dueno or tiene('catalogos.gestionar') or (not editar and tiene('comercios.ver_todos'))
    if not permitido:
        raise prohibido('El comercio no es tuyo.')
    return comercio


def _renglon(id, editar=True):
    renglon = db.session.get(InventarioComercio, id)
    if not renglon or not renglon.activo:
        raise no_encontrado('El renglón de inventario')
    _comercio(renglon.comercio_id, editar)
    return renglon


# ---------------------------------------------------------------- inventario del comercio

@srv.ruta('/comercios/<uuid:comercio_id>/inventario', 'GET', resumen='Inventario del comercio', etiqueta='Inventario',
          permisos=['inventario.gestionar', 'comercios.ver_todos'], consulta=InventarioConsulta,
          raiz_xml='inventario')
def listar_inventario(comercio_id, q):
    comercio = _comercio(comercio_id, editar=False)
    consulta = (InventarioComercio.query.filter_by(comercio_id=comercio.id, activo=True)
                .join(ProductoMaestro).join(Categoria))
    if q.estado:
        consulta = consulta.filter(InventarioComercio.estado == q.estado)
    if q.categoria_id:
        consulta = consulta.filter(ProductoMaestro.categoria_id == q.categoria_id)
    if q.texto:
        consulta = consulta.filter(ProductoMaestro.nombre.ilike(f'%{q.texto}%'))
    resultado = paginar(consulta.order_by(Categoria.orden, ProductoMaestro.nombre), q.pagina, q.por_pagina,
                        renglon_a_dict)
    todos = InventarioComercio.query.filter_by(comercio_id=comercio.id, activo=True).all()
    resultado['resumen'] = {
        'comercio_id': str(comercio.id), 'comercio': comercio.nombre_comercio, 'productos': len(todos),
        'bajo': sum(1 for r in todos if r.estado == 'BAJO'), 'agotado': sum(1 for r in todos if r.estado == 'AGOTADO'),
        'valor_inventario': sum(((r.existencia * (r.precio_venta or 0)) for r in todos), 0)}
    resultado['renglones'] = resultado.pop('items')
    return resultado


def fijar_precio(inventario_id, precio, metodo_captura='MANUAL'):
    """El precio y su historial son de ms-precios (valida atípicos, RN-001). Regresa None si quedó fijado
    (o ya tenía ese precio) o el motivo por el que no se fijó."""
    try:
        respuesta = llamar('precios', 'PUT', f'/api/v1/inventario/{inventario_id}/precio', token=g.token, timeout=10,
                           json={'precio': str(precio), 'metodo_captura': metodo_captura})
    except ErrorApi as error:
        return error.mensaje
    if respuesta.status_code in (200, 409):   # 409: ya tenía ese precio
        return None
    try:
        return respuesta.json()['error']['mensaje']
    except (ValueError, KeyError, TypeError):
        return f'ms-precios respondió {respuesta.status_code}.'


@srv.ruta('/comercios/<uuid:comercio_id>/inventario', 'POST', resumen='Agregar producto al catálogo del comercio',
          etiqueta='Inventario', permisos=['inventario.gestionar'], cuerpo=RenglonEntrada, status=201,
          raiz_xml='renglon', entrada_xml='renglon_entrada',
          ejemplo_entrada={'producto_id': 19, 'existencia': 12, 'stock_minimo': 6, 'stock_maximo': 36,
                           'precio_venta': 28.5})
def agregar_producto(comercio_id, datos):
    """La existencia inicial queda como movimiento de ENTRADA (RN-009). Si viene `precio_venta`, se fija con
    ms-precios (historial y validación de atípicos, RN-001) después de guardar el renglón; si ms-precios no lo
    acepta, el renglón queda sin precio y la respuesta lo indica en `aviso`."""
    comercio = _comercio(comercio_id)
    producto = db.session.get(ProductoMaestro, datos.producto_id)
    if not producto or not producto.activo:
        raise ErrorApi(422, 'producto_inexistente', 'El producto no existe en el catálogo maestro.')
    renglon = agregar_al_catalogo(comercio, producto, usuario_actual(), datos.existencia, datos.stock_minimo,
                                  datos.stock_maximo)
    db.session.commit()
    aviso = fijar_precio(renglon.id, datos.precio_venta) if datos.precio_venta else None
    db.session.refresh(renglon)
    return {**renglon_a_dict(renglon), 'aviso': f'El precio no se guardó: {aviso}' if aviso else None}


@srv.ruta('/inventario/<int:id>', 'GET', resumen='Renglón con sus últimos movimientos', etiqueta='Inventario',
          permisos=['inventario.gestionar', 'comercios.ver_todos'], raiz_xml='renglon')
def obtener_renglon(id):
    renglon = _renglon(id, editar=False)
    return {**renglon_a_dict(renglon),
            'movimientos': [movimiento_a_dict(m) for m in renglon.movimientos.limit(10).all()]}


@srv.ruta('/inventario/<int:id>', 'PATCH', resumen='Cambiar stock mínimo o máximo', etiqueta='Inventario',
          permisos=['inventario.gestionar'], cuerpo=LimitesEntrada, raiz_xml='renglon',
          entrada_xml='limites_entrada',
          ejemplo_entrada={'stock_minimo': 8, 'stock_maximo': 40})
def cambiar_limites(id, datos):
    renglon = _renglon(id)
    minimo = datos.stock_minimo if datos.stock_minimo is not None else renglon.stock_minimo
    maximo = datos.stock_maximo if datos.stock_maximo is not None else renglon.stock_maximo
    if maximo is not None and maximo < minimo:
        raise ErrorApi(422, 'datos_invalidos', 'El stock máximo no puede ser menor que el mínimo.')
    antes = {'stock_minimo': renglon.stock_minimo, 'stock_maximo': renglon.stock_maximo}
    renglon.stock_minimo, renglon.stock_maximo = minimo, maximo
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'InventarioComercio', renglon.id,
                     f'Límites de stock de {renglon.producto.nombre} (ms-inventario)', datos_anteriores=antes,
                     datos_nuevos={'stock_minimo': minimo, 'stock_maximo': maximo})
    db.session.commit()
    db.session.refresh(renglon)
    return renglon_a_dict(renglon)


@srv.ruta('/inventario/<int:id>', 'DELETE', resumen='Quitar producto del catálogo del comercio',
          etiqueta='Inventario', permisos=['inventario.gestionar'], raiz_xml='resultado')
def quitar_producto(id):
    renglon = _renglon(id)
    quitar_del_catalogo(renglon, usuario_actual())
    db.session.commit()
    return {'mensaje': 'Producto retirado del catálogo del comercio; el historial se conserva', 'id': str(id)}


# ---------------------------------------------------------------- movimientos

@srv.ruta('/inventario/<int:id>/movimientos', 'POST', resumen='Registrar entrada, venta o ajuste',
          etiqueta='Movimientos', permisos=['inventario.gestionar'], cuerpo=MovimientoEntrada, status=201,
          raiz_xml='movimiento', entrada_xml='movimiento_entrada',
          ejemplo_entrada={'tipo': 'SALIDA', 'cantidad': 2, 'motivo': 'Venta'})
def registrar(id, datos):
    """SALIDA mayor a la existencia se rechaza con 409 (RN-009). Si el producto cruza a BAJO o AGOTADO se envía
    una notificación al dueño a través de ms-notificaciones."""
    renglon = _renglon(id)
    movimiento = registrar_movimiento(renglon, datos.tipo, datos.cantidad, usuario_actual(), motivo=datos.motivo,
                                      referencia=datos.referencia)
    db.session.commit()
    db.session.refresh(renglon)
    return {**movimiento_a_dict(movimiento), 'estado_inventario': renglon.estado}


@srv.ruta('/inventario/<int:id>/movimientos', 'GET', resumen='Historial de movimientos', etiqueta='Movimientos',
          permisos=['inventario.gestionar', 'comercios.ver_todos'], consulta=MovimientosConsulta,
          raiz_xml='movimientos')
def historial(id, q):
    renglon = _renglon(id, editar=False)
    consulta = MovimientoInventario.query.filter_by(inventario_id=renglon.id)
    if q.tipo:
        consulta = consulta.filter_by(tipo=q.tipo)
    resultado = paginar(consulta.order_by(MovimientoInventario.created_at.desc()), q.pagina, q.por_pagina,
                        movimiento_a_dict)
    resultado['movimientos'] = resultado.pop('items')
    return resultado


@srv.ruta('/comercios/<uuid:comercio_id>/faltantes', 'GET', resumen='Productos por surtir', etiqueta='Inventario',
          permisos=['inventario.gestionar', 'comercios.ver_todos'], raiz_xml='faltantes')
def faltantes(comercio_id):
    """Renglones en BAJO o AGOTADO, con cantidad sugerida y cuántos proveedores de la zona pueden surtirlos."""
    comercio = _comercio(comercio_id, editar=False)
    return {'comercio_id': str(comercio.id), 'faltantes': [
        {**renglon_a_dict(f['inventario']), 'proveedores': f['proveedores'],
         'precio_mayoreo_min': f['precio_mayoreo_min']} for f in analisis.faltantes(comercio)]}


# ---------------------------------------------------------------- importación CSV

@srv.ruta('/comercios/<uuid:comercio_id>/importaciones', 'POST', resumen='Importar inventario desde CSV',
          etiqueta='Importación', permisos=['importaciones.ejecutar'], status=201, raiz_xml='importacion',
          errores=(400, 401, 403, 404, 409, 413, 422),
          multipart={'type': 'object', 'required': ['archivo'], 'properties': {
              'archivo': {'type': 'string', 'format': 'binary',
                          'description': 'CSV UTF-8 con columnas producto, existencia, stock_minimo, stock_maximo, precio'}}})
def importar(comercio_id):
    """Cada fila se aplica en su propio savepoint; las filas con error se reportan sin deshacer las demás.
    Mientras dura, un bloqueo en Redis impide otra importación del mismo comercio (409)."""
    comercio = _comercio(comercio_id)
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        raise ErrorApi(400, 'archivo_requerido', 'Envía el CSV en el campo "archivo" (multipart/form-data).')
    if not archivo.filename.lower().endswith('.csv'):
        raise ErrorApi(422, 'tipo_invalido', 'El archivo debe ser .csv.')
    resultado = importaciones.importar_inventario(
        comercio, archivo.read(), archivo.filename, usuario_actual(),
        fijar_precio=lambda inventario_id, precio: fijar_precio(inventario_id, precio, 'IMPORTACION'))
    db.session.commit()
    return resultado


@srv.ruta('/comercios/<uuid:comercio_id>/importaciones', 'GET', resumen='Historial de importaciones',
          etiqueta='Importación', permisos=['importaciones.ejecutar', 'comercios.ver_todos'], raiz_xml='importaciones')
def historial_importaciones(comercio_id):
    comercio = _comercio(comercio_id, editar=False)
    return {'comercio_id': str(comercio.id), 'importaciones': importaciones.historial(comercio.id)}


# ---------------------------------------------------------------- lote transaccional (uso de otros servicios)

def _renglon_del_lote(comercio, partida, usuario):
    if partida.inventario_id:
        renglon = db.session.get(InventarioComercio, partida.inventario_id)
        if not renglon or renglon.comercio_id != comercio.id:
            raise ErrorApi(422, 'renglon_ajeno', f'El renglón {partida.inventario_id} no es de este comercio.')
        if not renglon.activo:
            raise ErrorApi(409, 'renglon_inactivo', f'{renglon.producto.nombre} ya no está en el catálogo del comercio.')
        return renglon
    renglon = InventarioComercio.query.filter_by(comercio_id=comercio.id, producto_id=partida.producto_id).first()
    if renglon and renglon.activo:
        return renglon
    if partida.tipo != 'ENTRADA':
        raise ErrorApi(409, 'producto_no_vendido', f'El comercio no vende el producto {partida.producto_id}.')
    producto = db.session.get(ProductoMaestro, partida.producto_id)
    if not producto or not producto.activo:
        raise ErrorApi(422, 'producto_inexistente', f'El producto {partida.producto_id} no existe.')
    if renglon:   # estaba dado de baja: vuelve al catálogo
        renglon.activo = True
        return renglon
    # Primera entrada de un producto (p. ej. el comercio recibe un pedido de algo que no vendía)
    return agregar_al_catalogo(comercio, producto, usuario)


@srv.ruta('/comercios/<uuid:comercio_id>/movimientos/lote', 'POST', resumen='Aplicar varios movimientos en una transacción',
          etiqueta='Movimientos', permisos=['inventario.gestionar', 'ventas.registrar', 'pedidos.crear'],
          cuerpo=LoteEntrada, raiz_xml='lote', entrada_xml='lote_entrada',
          ejemplo_entrada={'referencia': 'venta:9b1f...', 'movimientos': [
              {'producto_id': 3, 'tipo': 'SALIDA', 'cantidad': 2, 'motivo': 'Venta 1043'},
              {'producto_id': 7, 'tipo': 'SALIDA', 'cantidad': 1, 'motivo': 'Venta 1043'}]})
def aplicar_lote(comercio_id, datos):
    """Lo usan ms-ventas (ventas y devoluciones), ms-pedidos (recepción) y ms-sincronizacion (operaciones offline)
    con el token del usuario. Se aplican TODOS o NINGUNO: si una partida deja existencia negativa o toma lo reservado,
    se responde 409 indicando cuál y no cambia nada. Si la `referencia` ya se aplicó, responde 200 con
    `ya_aplicado: true` y los movimientos originales (reintento seguro)."""
    comercio = _comercio(comercio_id)
    usuario = usuario_actual()
    with bloqueo(f'inventario-lote:{datos.referencia}', ttl_segundos=30,
                 mensaje='Ese lote se está aplicando en este momento; intenta de nuevo.'):
        previos = (MovimientoInventario.query.join(InventarioComercio)
                   .filter(InventarioComercio.comercio_id == comercio.id,
                           MovimientoInventario.referencia.like(f'{datos.referencia}#%'))
                   .order_by(MovimientoInventario.id).all())
        if previos:
            return {'referencia': datos.referencia, 'comercio_id': str(comercio.id), 'ya_aplicado': True,
                    'movimientos': [movimiento_a_dict(m) for m in previos]}
        movimientos = []
        pedido = None
        if datos.pedido_id:
            try:
                pedido = SimpleNamespace(id=UUID(datos.pedido_id))   # sólo se guarda el id en el movimiento
            except ValueError:
                raise ErrorApi(400, 'parametro_invalido', 'pedido_id debe ser un UUID.')
        try:
            for i, partida in enumerate(datos.movimientos, start=1):
                renglon = _renglon_del_lote(comercio, partida, usuario)
                movimientos.append(registrar_movimiento(renglon, partida.tipo, partida.cantidad, usuario,
                                                        motivo=partida.motivo or f'Lote {datos.referencia}',
                                                        referencia=f'{datos.referencia}#{i}', pedido=pedido))
        except ReglaNegocioError as error:
            db.session.rollback()
            raise ErrorApi(409, 'lote_rechazado', f'Partida {i}: {error}', detalles=[{'campo': f'movimientos[{i - 1}]',
                                                                                    'mensaje': str(error)}])
        except ErrorApi:
            db.session.rollback()
            raise
        db.session.commit()
    return {'referencia': datos.referencia, 'comercio_id': str(comercio.id), 'ya_aplicado': False,
            'movimientos': [movimiento_a_dict(m) for m in movimientos]}


# ---------------------------------------------------------------- reservas

def reserva_a_dict(r, existencia=None, apartado=None):
    existencia = r.inventario.existencia if existencia is None else existencia
    apartado = reservado(r.inventario_id) if apartado is None else apartado
    return {'id': r.id, 'inventario_id': r.inventario_id, 'producto': r.inventario.producto.nombre,
            'cantidad': r.cantidad, 'motivo': r.motivo, 'referencia': r.referencia, 'estado': r.estado,
            'expira': r.expira_at, 'creada': r.created_at, 'existencia': existencia, 'reservado_total': apartado,
            'disponible': max(existencia - apartado, 0)}


def _vencer(inventario_id):
    """Las reservas vencidas se marcan al consultarlas (no hace falta un proceso aparte)."""
    (ReservaInventario.query.filter(ReservaInventario.inventario_id == inventario_id,
                                    ReservaInventario.estado == 'ACTIVA',
                                    ReservaInventario.expira_at <= db.func.now())
     .update({'estado': 'VENCIDA'}, synchronize_session=False))


@srv.ruta('/inventario/<int:id>/reservas', 'POST', resumen='Apartar existencia', etiqueta='Reservas',
          permisos=['inventario.gestionar'], cuerpo=ReservaEntrada, status=201, raiz_xml='reserva',
          entrada_xml='reserva_entrada',
          ejemplo_entrada={'cantidad': 5, 'motivo': 'Pedido de cliente por teléfono', 'minutos': 120})
def reservar(id, datos):
    """No se puede reservar más de lo disponible (existencia - reservas activas). Vence sola después de `minutos`
    (por omisión RESERVA_MINUTOS de ms-configuracion)."""
    renglon = _renglon(id)
    _vencer(renglon.id)
    renglon = (db.session.query(InventarioComercio).filter_by(id=renglon.id).with_for_update().populate_existing().one())
    apartado = reservado(renglon.id)
    if datos.cantidad > renglon.existencia - apartado:
        raise ErrorApi(409, 'sin_disponible', f'Sólo hay {(renglon.existencia - apartado).normalize():f} disponibles '
                                              f'({apartado.normalize():f} ya reservados).')
    minutos = datos.minutos or int(parametro('RESERVA_MINUTOS'))
    reserva = ReservaInventario(inventario_id=renglon.id, cantidad=datos.cantidad, motivo=datos.motivo,
                                referencia=datos.referencia, usuario_id=usuario_actual().id,
                                expira_at=db.func.now() + timedelta(minutes=minutos))   # hora de la base
    db.session.add(reserva)
    db.session.flush()
    registrar_evento(usuario_actual().id, 'CREACION', 'ReservaInventario', reserva.id,
                     f'Reserva de {datos.cantidad.normalize():f} {renglon.producto.unidad_medida} de {renglon.producto.nombre}',
                     datos_nuevos={**datos.model_dump(), 'minutos': minutos})
    db.session.commit()
    db.session.refresh(reserva)
    invalidar_analisis()
    return reserva_a_dict(reserva)


@srv.ruta('/inventario/<int:id>/reservas', 'GET', resumen='Reservas activas del renglón', etiqueta='Reservas',
          permisos=['inventario.gestionar', 'comercios.ver_todos'], raiz_xml='reservas')
def listar_reservas(id):
    renglon = _renglon(id, editar=False)
    _vencer(renglon.id)
    db.session.commit()
    activas = ReservaInventario.query.filter_by(inventario_id=renglon.id, estado='ACTIVA').order_by(
        ReservaInventario.expira_at).all()
    apartado = reservado(renglon.id)
    return {'inventario_id': renglon.id, 'existencia': renglon.existencia, 'reservado_total': apartado,
            'disponible': max(renglon.existencia - apartado, 0),
            'reservas': [reserva_a_dict(r, renglon.existencia, apartado) for r in activas]}


def _reserva(id):
    reserva = db.session.get(ReservaInventario, id)
    if not reserva:
        raise no_encontrado('La reserva')
    _comercio(reserva.inventario.comercio_id)
    _vencer(reserva.inventario_id)
    db.session.refresh(reserva)
    if reserva.estado != 'ACTIVA':
        raise ErrorApi(409, 'reserva_no_activa', f'La reserva está {reserva.estado}.')
    return reserva


@srv.ruta('/reservas/<int:id>/consumo', 'POST', resumen='Surtir la reserva (salida de inventario)', etiqueta='Reservas',
          permisos=['inventario.gestionar'], raiz_xml='reserva')
def consumir_reserva(id):
    reserva = _reserva(id)
    registrar_movimiento(reserva.inventario, 'SALIDA', reserva.cantidad, usuario_actual(),
                         motivo=f'Reserva {reserva.id}' + (f' ({reserva.motivo})' if reserva.motivo else ''),
                         referencia=f'reserva:{reserva.id}', reserva_consumida=reserva.id)
    reserva.estado = 'CONSUMIDA'
    db.session.commit()
    db.session.refresh(reserva)
    return reserva_a_dict(reserva)


@srv.ruta('/reservas/<int:id>', 'DELETE', resumen='Liberar la reserva', etiqueta='Reservas',
          permisos=['inventario.gestionar'], raiz_xml='reserva')
def liberar_reserva(id):
    reserva = _reserva(id)
    reserva.estado = 'LIBERADA'
    registrar_evento(usuario_actual().id, 'CAMBIO_ESTADO', 'ReservaInventario', reserva.id, 'Reserva liberada',
                     datos_anteriores={'estado': 'ACTIVA'}, datos_nuevos={'estado': 'LIBERADA'})
    db.session.commit()
    db.session.refresh(reserva)
    invalidar_analisis()
    return reserva_a_dict(reserva)


# ---------------------------------------------------------------- sucursales y transferencias

def transferencia_a_dict(t):
    return {'id': t.id, 'origen_id': t.origen_id, 'origen_comercio': t.origen.comercio.nombre_comercio,
            'destino_id': t.destino_id, 'destino_comercio': t.destino.comercio.nombre_comercio,
            'producto': t.origen.producto.nombre, 'cantidad': t.cantidad, 'motivo': t.motivo, 'fecha': t.created_at,
            'existencia_origen': t.origen.existencia, 'existencia_destino': t.destino.existencia}


@srv.ruta('/transferencias', 'POST', resumen='Pasar mercancía a otra sucursal', etiqueta='Sucursales',
          permisos=['inventario.gestionar'], cuerpo=TransferenciaEntrada, status=201, raiz_xml='transferencia',
          entrada_xml='transferencia_entrada',
          ejemplo_entrada={'origen_id': 120, 'destino_comercio_id': '5c0e...', 'cantidad': 6, 'motivo': 'Reabasto'})
def transferir(datos):
    """Ambos comercios deben ser del mismo dueño. Se registra una SALIDA en el origen y una ENTRADA en el destino en
    la misma transacción (si el destino no vendía el producto, se agrega a su catálogo)."""
    origen = _renglon(datos.origen_id)
    try:
        destino_comercio = _comercio(UUID(datos.destino_comercio_id))
    except ValueError:
        raise ErrorApi(400, 'parametro_invalido', 'destino_comercio_id debe ser un UUID.')
    if destino_comercio.id == origen.comercio_id:
        raise ErrorApi(422, 'misma_sucursal', 'El destino debe ser otra sucursal.')
    if destino_comercio.usuario_id != origen.comercio.usuario_id:
        raise prohibido('Sólo se transfiere entre comercios del mismo dueño.')
    usuario = usuario_actual()
    destino = InventarioComercio.query.filter_by(comercio_id=destino_comercio.id, producto_id=origen.producto_id).first()
    try:
        if not destino or not destino.activo:
            destino = destino or agregar_al_catalogo(destino_comercio, origen.producto, usuario)
            destino.activo = True
        transferencia = TransferenciaInventario(origen_id=origen.id, destino_id=destino.id, cantidad=datos.cantidad,
                                                motivo=datos.motivo, usuario_id=usuario.id)
        db.session.add(transferencia)
        db.session.flush()
        motivo = f'Transferencia {transferencia.id}' + (f': {datos.motivo}' if datos.motivo else '')
        registrar_movimiento(origen, 'SALIDA', datos.cantidad, usuario, motivo=f'{motivo} -> {destino_comercio.nombre_comercio}',
                             referencia=f'transferencia:{transferencia.id}')
        registrar_movimiento(destino, 'ENTRADA', datos.cantidad, usuario,
                             motivo=f'{motivo} <- {origen.comercio.nombre_comercio}',
                             referencia=f'transferencia:{transferencia.id}')
    except ReglaNegocioError:
        db.session.rollback()
        raise
    db.session.commit()
    db.session.refresh(transferencia)
    return transferencia_a_dict(transferencia)


@srv.ruta('/comercios/<uuid:comercio_id>/transferencias', 'GET', resumen='Transferencias de una sucursal',
          etiqueta='Sucursales', permisos=['inventario.gestionar', 'comercios.ver_todos'], raiz_xml='transferencias')
def listar_transferencias(comercio_id):
    comercio = _comercio(comercio_id, editar=False)
    renglones = db.session.query(InventarioComercio.id).filter_by(comercio_id=comercio.id)
    lista = (TransferenciaInventario.query
             .filter(db.or_(TransferenciaInventario.origen_id.in_(renglones),
                            TransferenciaInventario.destino_id.in_(renglones)))
             .order_by(TransferenciaInventario.created_at.desc()).limit(100).all())
    return {'comercio_id': str(comercio.id), 'transferencias': [transferencia_a_dict(t) for t in lista]}


@srv.ruta('/mis-sucursales', 'GET', resumen='Inventario por sucursal', etiqueta='Sucursales',
          permisos=['inventario.gestionar'], consulta=SucursalesConsulta, raiz_xml='sucursales')
def mis_sucursales(q):
    """Los comercios del usuario con su resumen; con `producto_id`, cuánto tiene cada sucursal de ese producto."""
    usuario = usuario_actual()
    comercios = Comercio.query.filter_by(usuario_id=usuario.id, activo=True).order_by(Comercio.nombre_comercio).all()
    sucursales, total = [], 0
    for c in comercios:
        renglones = InventarioComercio.query.filter_by(comercio_id=c.id, activo=True).all()
        del_producto = next((r for r in renglones if r.producto_id == q.producto_id), None) if q.producto_id else None
        if del_producto:
            total += del_producto.existencia
        sucursales.append({'comercio_id': str(c.id), 'comercio': c.nombre_comercio,
                           'zona': c.zona.nombre if c.zona else None, 'productos': len(renglones),
                           'bajo': sum(1 for r in renglones if r.estado == 'BAJO'),
                           'agotado': sum(1 for r in renglones if r.estado == 'AGOTADO'),
                           'existencia_producto': del_producto.existencia if del_producto else None,
                           'estado_producto': del_producto.estado if del_producto else None})
    return {'producto_id': q.producto_id, 'total_producto': total if q.producto_id else None, 'sucursales': sucursales}
