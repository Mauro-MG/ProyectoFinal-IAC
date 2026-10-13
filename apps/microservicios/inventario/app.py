"""
ms-inventario: catálogo de cada comercio, existencias, movimientos e importación CSV.

PostgreSQL: inventario_comercio (estado calculado por columna generada),
movimientos_inventario, precios_comercio (precio inicial al dar de alta).
MongoDB: importaciones (resultado de cada carga CSV) y GridFS (el archivo importado).
Redis: bloqueo distribuido `bloqueo:importacion:{comercio}` durante una importación,
caché de disponibilidad pública (`inventario:v{n}:disponibilidad:{filtros}`, 2 min).
Avisa a ms-notificaciones cuando un producto queda en stock bajo o agotado.
"""
from pathlib import Path
import hashlib
import json
from uuid import UUID

from flask import g, request
from redis.exceptions import RedisError

from abasto_api.formatos import compatible_json
from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene, usuario_actual
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import (Categoria, Comercio, InventarioComercio, MovimientoInventario, ProductoMaestro,
                                    ZonaMunicipal)
from abasto_dominio.servicios import analisis, importaciones
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import CLAVE_VERSION
from abasto_dominio.servicios.inventario import agregar_al_catalogo, quitar_del_catalogo, registrar_movimiento

from esquemas import (CONTRATOS_XML, DisponibilidadConsulta, InventarioConsulta, LimitesEntrada,
                      MovimientoEntrada, MovimientosConsulta, RenglonEntrada)

srv = Servicio('inventario', 'Inventario',
               'Catálogo de productos de cada comercio, existencias con stock mínimo y máximo, movimientos de '
               'entrada, salida y ajuste, faltantes, importación masiva por CSV y disponibilidad pública.',
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
            'usuario_id': str(m.usuario_id) if m.usuario_id else None, 'fecha': m.created_at}


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


@srv.ruta('/comercios/<uuid:comercio_id>/inventario', 'POST', resumen='Agregar producto al catálogo del comercio',
          etiqueta='Inventario', permisos=['inventario.gestionar'], cuerpo=RenglonEntrada, status=201,
          raiz_xml='renglon', entrada_xml='renglon_entrada',
          ejemplo_entrada={'producto_id': 19, 'existencia': 12, 'stock_minimo': 6, 'stock_maximo': 36,
                           'precio_venta': 28.5})
def agregar_producto(comercio_id, datos):
    """La existencia inicial queda como movimiento de ENTRADA y el precio entra al historial (RN-009, RN-001)."""
    comercio = _comercio(comercio_id)
    producto = db.session.get(ProductoMaestro, datos.producto_id)
    if not producto or not producto.activo:
        raise ErrorApi(422, 'producto_inexistente', 'El producto no existe en el catálogo maestro.')
    renglon = agregar_al_catalogo(comercio, producto, usuario_actual(), datos.existencia, datos.stock_minimo,
                                  datos.stock_maximo, datos.precio_venta)
    db.session.commit()
    return renglon_a_dict(renglon)


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
    movimiento = registrar_movimiento(renglon, datos.tipo, datos.cantidad, usuario_actual(), motivo=datos.motivo)
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
    resultado = importaciones.importar_inventario(comercio, archivo.read(), archivo.filename, usuario_actual())
    db.session.commit()
    return resultado


@srv.ruta('/comercios/<uuid:comercio_id>/importaciones', 'GET', resumen='Historial de importaciones',
          etiqueta='Importación', permisos=['importaciones.ejecutar', 'comercios.ver_todos'], raiz_xml='importaciones')
def historial_importaciones(comercio_id):
    comercio = _comercio(comercio_id, editar=False)
    return {'comercio_id': str(comercio.id), 'importaciones': importaciones.historial(comercio.id)}


# ---------------------------------------------------------------- disponibilidad pública

@srv.ruta('/disponibilidad', 'GET', resumen='Disponibilidad pública', etiqueta='Disponibilidad', publico=True,
          consulta=DisponibilidadConsulta, raiz_xml='disponibilidad', limite=60)
def disponibilidad(q):
    """Sólo comercios VERIFICADOS (RN-015) y sin datos personales. Caché de 2 minutos en Redis, invalidada por
    cualquier cambio de inventario (misma versión que la caché de análisis)."""
    try:
        version = extensiones.redis_client.get(CLAVE_VERSION) or '0'
        clave = f"inventario:v{version}:disponibilidad:{hashlib.md5(json.dumps(q.model_dump(), sort_keys=True).encode()).hexdigest()[:12]}"
        guardado = extensiones.redis_client.get(clave)
        if guardado:
            return {**json.loads(guardado), 'origen': 'cache'}
    except RedisError:
        clave = None

    consulta = (db.session.query(InventarioComercio, Comercio, ProductoMaestro, ZonaMunicipal)
                .join(Comercio, InventarioComercio.comercio_id == Comercio.id)
                .join(ProductoMaestro, InventarioComercio.producto_id == ProductoMaestro.id)
                .outerjoin(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
                .filter(InventarioComercio.activo.is_(True), Comercio.activo.is_(True),
                        Comercio.estado_registro == 'VERIFICADO'))
    if q.producto_id:
        consulta = consulta.filter(ProductoMaestro.id == q.producto_id)
    if q.texto:
        consulta = consulta.filter(ProductoMaestro.nombre.ilike(f'%{q.texto}%'))
    if q.zona_id:
        consulta = consulta.filter(Comercio.zona_id == q.zona_id)
    if q.categoria_id:
        consulta = consulta.filter(ProductoMaestro.categoria_id == q.categoria_id)
    if q.con_existencia:
        consulta = consulta.filter(InventarioComercio.existencia > 0)
    resultado = paginar(consulta.order_by(ProductoMaestro.nombre, InventarioComercio.existencia.desc()),
                        q.pagina, q.por_pagina, lambda fila: {
                            'producto_id': fila[2].id, 'producto': fila[2].nombre, 'unidad_medida': fila[2].unidad_medida,
                            'comercio': fila[1].nombre_comercio, 'sector': fila[1].sector,
                            'zona': fila[3].nombre if fila[3] else None, 'existencia': fila[0].existencia,
                            'estado': fila[0].estado, 'precio': fila[0].precio_venta, 'actualizado': fila[0].updated_at})
    resultado['renglones'] = resultado.pop('items')
    if clave:
        try:
            extensiones.redis_client.setex(clave, 120, json.dumps(compatible_json(resultado)))
        except RedisError:
            pass
    return {**resultado, 'origen': 'postgres'}
