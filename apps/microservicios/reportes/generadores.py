"""
Contenido de cada reporte: (título, columnas, filas, resumen).

Cada generador sólo LEE (consultas SQL de sólo lectura o funciones de análisis del dominio) y
regresa datos planos; los formatos (PDF, CSV, Excel, JSON) se arman en formatos.py.
"""
from datetime import date, timedelta
from uuid import UUID

from flask import g
from sqlalchemy import text

from abasto_api import ErrorApi, prohibido, tiene
from abasto_dominio.extensiones import db
from abasto_dominio.servicios import analisis


def _uuid(valor, campo):
    try:
        return UUID(str(valor))
    except (TypeError, ValueError):
        raise ErrorApi(422, 'filtro_invalido', f'El filtro {campo} debe ser un UUID.')


def _mi_comercio(filtros):
    comercio_id = _uuid(filtros.get('comercio_id'), 'comercio_id')
    fila = db.session.execute(text('SELECT id, nombre_comercio, usuario_id::text AS u FROM comercios WHERE id = :c'),
                              {'c': comercio_id}).first()
    if not fila:
        raise ErrorApi(404, 'no_encontrado', 'El comercio no existe.')
    if fila.u != g.claims['sub'] and not tiene('comercios.ver_todos'):
        raise prohibido('El comercio no es tuyo.')
    return fila


def _dias(filtros, por_omision=30):
    try:
        dias = int(filtros.get('dias', por_omision))
    except (TypeError, ValueError):
        raise ErrorApi(422, 'filtro_invalido', 'dias debe ser un número.')
    if not 1 <= dias <= 366:
        raise ErrorApi(422, 'filtro_invalido', 'dias debe estar entre 1 y 366.')
    return dias


def inventario(filtros):
    comercio = _mi_comercio(filtros)
    filas = db.session.execute(text(
        'SELECT p.nombre AS producto, c.nombre AS categoria, i.existencia, i.stock_minimo, i.stock_maximo, '
        'i.precio_venta, i.estado, i.existencia * COALESCE(i.precio_venta, 0) AS valor, i.updated_at AS actualizado '
        'FROM inventario_comercio i JOIN productos_maestros p ON p.id = i.producto_id '
        'JOIN categorias c ON c.id = p.categoria_id WHERE i.comercio_id = :c AND i.activo '
        'ORDER BY i.estado = \'DISPONIBLE\', c.nombre, p.nombre'), {'c': comercio.id}).mappings().all()
    columnas = [('producto', 'Producto'), ('categoria', 'Categoría'), ('existencia', 'Existencia'),
                ('stock_minimo', 'Mínimo'), ('stock_maximo', 'Máximo'), ('precio_venta', 'Precio'),
                ('estado', 'Estado'), ('valor', 'Valor'), ('actualizado', 'Actualizado')]
    resumen = {'Productos': len(filas), 'Bajo mínimo': sum(1 for f in filas if f['estado'] == 'BAJO'),
               'Agotados': sum(1 for f in filas if f['estado'] == 'AGOTADO'),
               'Valor del inventario': round(sum(float(f['valor']) for f in filas), 2)}
    return f'Inventario de {comercio.nombre_comercio}', columnas, [dict(f) for f in filas], resumen


def ventas(filtros):
    comercio = _mi_comercio(filtros)
    dias = _dias(filtros)
    filas = db.session.execute(text(
        'SELECT v.fecha_venta::date AS dia, count(DISTINCT v.id) AS ventas, sum(d.cantidad - d.cantidad_devuelta) AS unidades, '
        'sum((d.cantidad - d.cantidad_devuelta) * d.precio_unitario) AS importe '
        'FROM ventas v JOIN detalle_ventas d ON d.venta_id = v.id WHERE v.comercio_id = :c AND v.fecha_venta >= :desde '
        'GROUP BY 1 ORDER BY 1'), {'c': comercio.id, 'desde': date.today() - timedelta(days=dias)}).mappings().all()
    columnas = [('dia', 'Día'), ('ventas', 'Ventas'), ('unidades', 'Unidades'), ('importe', 'Importe')]
    total = sum(float(f['importe'] or 0) for f in filas)
    numero = sum(f['ventas'] for f in filas)
    resumen = {'Días': dias, 'Ventas': numero, 'Importe total': round(total, 2),
               'Ticket promedio': round(total / numero, 2) if numero else 0}
    return f'Ventas de {comercio.nombre_comercio} (últimos {dias} días)', columnas, [dict(f) for f in filas], resumen


def precios(filtros):
    if not (tiene('precios.consultar') or tiene('analisis.ver')):
        raise prohibido('Necesitas precios.consultar.')
    zona = filtros.get('zona_id')
    filas = db.session.execute(text(
        'SELECT p.nombre AS producto, z.nombre AS zona, count(i.id) AS comercios, min(i.precio_venta) AS minimo, '
        'round(avg(i.precio_venta), 2) AS promedio, max(i.precio_venta) AS maximo, '
        '(SELECT min(cp.precio_mayoreo) FROM catalogo_proveedor cp WHERE cp.producto_id = p.id AND cp.activo) AS mayoreo_min '
        'FROM inventario_comercio i JOIN comercios c ON c.id = i.comercio_id JOIN productos_maestros p ON p.id = i.producto_id '
        'JOIN zonas_municipales z ON z.id = c.zona_id '
        "WHERE i.activo AND i.precio_venta IS NOT NULL AND c.estado_registro = 'VERIFICADO' "
        f'{"AND z.id = :z" if zona else ""} GROUP BY p.id, p.nombre, z.nombre ORDER BY p.nombre, z.nombre'),
        {'z': zona}).mappings().all()
    columnas = [('producto', 'Producto'), ('zona', 'Zona'), ('comercios', 'Comercios'), ('minimo', 'Mínimo'),
                ('promedio', 'Promedio'), ('maximo', 'Máximo'), ('mayoreo_min', 'Mayoreo mínimo')]
    return 'Precios al consumidor por zona', columnas, [dict(f) for f in filas], {'Renglones': len(filas)}


def pedidos(filtros):
    dias = _dias(filtros, 90)
    condicion, parametros = '', {'desde': date.today() - timedelta(days=dias)}
    if tiene('pedidos.ver_todos') or tiene('analisis.ver'):
        titulo = 'Pedidos de abasto'
    elif g.claims.get('proveedor_id'):
        condicion, parametros['p'] = 'AND pe.proveedor_id = :p', g.claims['proveedor_id']
        titulo = 'Pedidos recibidos'
    else:
        condicion, parametros['u'] = 'AND c.usuario_id = :u', g.claims['sub']
        titulo = 'Mis pedidos de abasto'
    filas = db.session.execute(text(
        "SELECT 'PED-' || lpad(pe.folio::text, 5, '0') AS folio, pe.estado::text AS estado, c.nombre_comercio AS comercio, "
        'pr.nombre_empresa AS proveedor, pe.subtotal, pe.fecha_envio, pe.fecha_entrega_real '
        'FROM pedidos_abasto pe JOIN comercios c ON c.id = pe.comercio_id JOIN proveedores pr ON pr.id = pe.proveedor_id '
        f'WHERE pe.created_at >= :desde {condicion} ORDER BY pe.created_at DESC'), parametros).mappings().all()
    columnas = [('folio', 'Folio'), ('estado', 'Estado'), ('comercio', 'Comercio'), ('proveedor', 'Proveedor'),
                ('subtotal', 'Subtotal'), ('fecha_envio', 'Enviado'), ('fecha_entrega_real', 'Entregado')]
    entregados = [f for f in filas if f['estado'] == 'ENTREGADO']
    resumen = {'Pedidos': len(filas), 'Entregados': len(entregados),
               'Monto entregado': round(sum(float(f['subtotal']) for f in entregados), 2)}
    return f'{titulo} (últimos {dias} días)', columnas, [dict(f) for f in filas], resumen


def proveedores(filtros):
    if not (tiene('analisis.ver') or tiene('proveedores.consultar') or tiene('pedidos.ver_todos')):
        raise prohibido('Necesitas analisis.ver o proveedores.consultar.')
    filas = db.session.execute(text(
        'SELECT pr.nombre_empresa AS proveedor, pr.estado_verificacion AS verificacion, pr.plan, '
        '(SELECT count(*) FROM proveedor_zonas pz WHERE pz.proveedor_id = pr.id) AS zonas, '
        '(SELECT count(*) FROM catalogo_proveedor cp WHERE cp.proveedor_id = pr.id AND cp.activo) AS productos, '
        "(SELECT count(*) FROM pedidos_abasto pe WHERE pe.proveedor_id = pr.id AND pe.estado = 'ENTREGADO') AS entregados, "
        "(SELECT count(*) FROM pedidos_abasto pe WHERE pe.proveedor_id = pr.id AND pe.estado = 'RECHAZADO') AS rechazados, "
        '(SELECT round(avg(e.calificacion), 2) FROM evaluaciones_proveedor e WHERE e.proveedor_id = pr.id) AS calificacion '
        'FROM proveedores pr WHERE pr.activo ORDER BY entregados DESC, pr.nombre_empresa')).mappings().all()
    columnas = [('proveedor', 'Proveedor'), ('verificacion', 'Verificación'), ('plan', 'Plan'), ('zonas', 'Zonas'),
                ('productos', 'Productos'), ('entregados', 'Entregados'), ('rechazados', 'Rechazados'),
                ('calificacion', 'Calificación')]
    return 'Desempeño de proveedores', columnas, [dict(f) for f in filas], {'Proveedores': len(filas)}


def cobertura(filtros):
    if not tiene('analisis.ver'):
        raise prohibido('Necesitas analisis.ver.')
    filas = analisis.indicadores_zonas()
    columnas = [('nombre', 'Zona'), ('municipio', 'Municipio'), ('poblacion', 'Población'), ('comercios', 'Comercios'),
                ('formales', 'Formales'), ('informales', 'Informales'), ('proveedores', 'Proveedores'),
                ('habitantes_por_comercio', 'Hab./comercio'), ('indice_acceso', 'Índice de acceso'),
                ('clasificacion', 'Clasificación')]
    return 'Cobertura e índice de acceso por zona', columnas, filas, {'Zonas': len(filas)}


def brechas(filtros):
    if not tiene('analisis.ver'):
        raise prohibido('Necesitas analisis.ver.')
    filas = analisis.brechas(zona_id=filtros.get('zona_id'), solo_canasta=bool(filtros.get('solo_canasta')))
    columnas = [('zona', 'Zona'), ('producto', 'Producto'), ('cobertura', 'Cobertura %'), ('nivel', 'Brecha'),
                ('con_disponibilidad', 'Con existencia'), ('comercios_analizados', 'Comercios'),
                ('proveedores', 'Proveedores'), ('ventas', 'Ventas')]
    return 'Brechas de surtido', columnas, filas, {
        'Renglones': len(filas), 'Brecha alta': sum(1 for f in filas if f['nivel'] == 'ALTA')}


TIPOS = {
    'inventario': (inventario, 'Inventario de un comercio', ['comercio_id']),
    'ventas': (ventas, 'Ventas por día de un comercio', ['comercio_id', 'dias']),
    'precios': (precios, 'Precios al consumidor por producto y zona', ['zona_id']),
    'pedidos': (pedidos, 'Pedidos de abasto (según el rol)', ['dias']),
    'proveedores': (proveedores, 'Desempeño de proveedores', []),
    'cobertura': (cobertura, 'Cobertura e índice de acceso por zona', []),
    'brechas': (brechas, 'Brechas de surtido', ['zona_id', 'solo_canasta']),
}
