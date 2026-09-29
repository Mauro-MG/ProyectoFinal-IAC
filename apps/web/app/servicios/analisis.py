"""
Cobertura territorial, brechas de surtido, índice de acceso y recomendaciones.

Definiciones (todas son reglas determinísticas; los umbrales se configuran en
configuracion_sistema):

  Comercios analizados   comercios activos (verificados o pendientes) de la zona.
  Con disponibilidad     comercios de la zona con existencia > 0 del producto.
  Cobertura (%)          con disponibilidad / comercios analizados * 100.
  Nivel de brecha        ALTA < UMBRAL_BRECHA_ALTA <= MEDIA < UMBRAL_BRECHA_MEDIA
                         <= BAJA < UMBRAL_BRECHA_BAJA <= SIN_BRECHA.
  Puntos requeridos      población de la zona / HABITANTES_POR_PUNTO (demanda estimada).
  Déficit de puntos      puntos requeridos - con disponibilidad (demanda - oferta).
  Ventas                 unidades vendidas (movimientos SALIDA) en los últimos DIAS_DEMANDA.
  Índice de acceso       promedio de la cobertura de los productos de canasta básica.
"""
import math

from sqlalchemy import cast, distinct, func

from app.extensions import db
from app.models import (CatalogoProveedor, Comercio, InventarioComercio, MovimientoInventario, PrecioComercio,
                        ProductoMaestro, Proveedor, ZonaMunicipal, proveedor_zonas)
from app.servicios.cache import obtener_o_calcular
from app.servicios.geo import area_km2
from app.servicios.parametros import parametro

ESTADOS_ANALIZADOS = ('VERIFICADO', 'PENDIENTE')


def _filtro_comercios():
    return (Comercio.activo.is_(True), Comercio.estado_registro.in_(ESTADOS_ANALIZADOS))


def umbrales():
    return (parametro('UMBRAL_BRECHA_ALTA'), parametro('UMBRAL_BRECHA_MEDIA'), parametro('UMBRAL_BRECHA_BAJA'))


def clasificar_brecha(cobertura, limites):
    alta, media, baja = limites
    if cobertura < alta:
        return 'ALTA'
    if cobertura < media:
        return 'MEDIA'
    if cobertura < baja:
        return 'BAJA'
    return 'SIN_BRECHA'


def clasificar_acceso(indice, limites):
    alta, media, baja = limites
    if indice < alta:
        return 'Crítico'
    if indice < media:
        return 'Limitado'
    if indice < baja:
        return 'Aceptable'
    return 'Adecuado'


# ---------------------------------------------------------------------------
# Consultas base (una sola consulta agregada por concepto)
# ---------------------------------------------------------------------------

def _comercios_por_zona():
    filas = (db.session.query(Comercio.zona_id, func.count(Comercio.id))
             .filter(Comercio.zona_id.isnot(None), *_filtro_comercios())
             .group_by(Comercio.zona_id).all())
    return dict(filas)


def _oferta_por_zona_producto():
    filas = (db.session.query(
                Comercio.zona_id,
                InventarioComercio.producto_id,
                func.count(InventarioComercio.id).label('lo_venden'),
                func.count(InventarioComercio.id).filter(InventarioComercio.existencia > 0).label('con_existencia'),
                func.coalesce(func.sum(InventarioComercio.existencia), 0).label('existencia_total'),
                func.max(InventarioComercio.updated_at).label('ultima_actualizacion'))
             .join(Comercio, InventarioComercio.comercio_id == Comercio.id)
             .filter(InventarioComercio.activo.is_(True), *_filtro_comercios())
             .group_by(Comercio.zona_id, InventarioComercio.producto_id).all())
    return {(f.zona_id, f.producto_id): f for f in filas}


def _ventas_por_zona_producto():
    dias = parametro('DIAS_DEMANDA')
    filas = (db.session.query(Comercio.zona_id, InventarioComercio.producto_id,
                              func.sum(MovimientoInventario.cantidad))
             .select_from(MovimientoInventario)
             .join(InventarioComercio, MovimientoInventario.inventario_id == InventarioComercio.id)
             .join(Comercio, InventarioComercio.comercio_id == Comercio.id)
             .filter(MovimientoInventario.tipo == 'SALIDA',
                     MovimientoInventario.created_at >= func.now() - func.make_interval(0, 0, 0, dias))
             .group_by(Comercio.zona_id, InventarioComercio.producto_id).all())
    return {(z, p): float(total) for z, p, total in filas}


def _proveedores_por_zona_producto():
    """Proveedores que entregan en la zona y tienen existencia del producto."""
    filas = (db.session.query(proveedor_zonas.c.zona_id, CatalogoProveedor.producto_id,
                              func.count(distinct(CatalogoProveedor.proveedor_id)),
                              func.min(CatalogoProveedor.precio_mayoreo))
             .select_from(CatalogoProveedor)
             .join(Proveedor, Proveedor.id == CatalogoProveedor.proveedor_id)
             .join(proveedor_zonas, proveedor_zonas.c.proveedor_id == Proveedor.id)
             .filter(CatalogoProveedor.activo.is_(True), CatalogoProveedor.existencia_disponible > 0,
                     Proveedor.activo.is_(True))
             .group_by(proveedor_zonas.c.zona_id, CatalogoProveedor.producto_id).all())
    return {(z, p): (n, float(minimo)) for z, p, n, minimo in filas}


def _precio_promedio_por_zona_producto(dias=30):
    filas = (db.session.query(Comercio.zona_id, PrecioComercio.producto_id, func.avg(PrecioComercio.precio))
             .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
             .filter(PrecioComercio.estado_validacion == 'VALIDADO', PrecioComercio.activo.is_(True),
                     PrecioComercio.fecha_registro >= func.now() - func.make_interval(0, 0, 0, dias))
             .group_by(Comercio.zona_id, PrecioComercio.producto_id).all())
    return {(z, p): float(prom) for z, p, prom in filas}


# ---------------------------------------------------------------------------
# Brechas
# ---------------------------------------------------------------------------

def brechas(zona_id=None, categoria_id=None, producto_id=None, solo_canasta=False, nivel=None):
    zonas = ZonaMunicipal.query.filter_by(activa=True)
    if zona_id:
        zonas = zonas.filter_by(id=zona_id)
    productos = ProductoMaestro.query.filter_by(activo=True)
    if categoria_id:
        productos = productos.filter_by(categoria_id=categoria_id)
    if producto_id:
        productos = productos.filter_by(id=producto_id)
    if solo_canasta:
        productos = productos.filter_by(es_canasta_basica=True)
    productos = productos.order_by(ProductoMaestro.nombre).all()

    comercios = _comercios_por_zona()
    oferta = _oferta_por_zona_producto()
    ventas = _ventas_por_zona_producto()
    proveedores = _proveedores_por_zona_producto()
    precios = _precio_promedio_por_zona_producto()
    habitantes_por_punto = parametro('HABITANTES_POR_PUNTO')
    limites = umbrales()

    filas = []
    for zona in zonas.order_by(ZonaMunicipal.nombre):
        analizados = comercios.get(zona.id, 0)
        if not analizados:
            continue
        requeridos = math.ceil(zona.poblacion / habitantes_por_punto) if zona.poblacion else None
        for producto in productos:
            clave = (zona.id, producto.id)
            o = oferta.get(clave)
            lo_venden = o.lo_venden if o else 0
            con = o.con_existencia if o else 0
            cobertura = round(con * 100 / analizados, 1)
            n_prov, mayoreo_min = proveedores.get(clave, (0, None))
            filas.append({
                'zona_id': zona.id,
                'zona': zona.nombre,
                'municipio': zona.municipio,
                'producto_id': producto.id,
                'producto': producto.nombre,
                'canasta_basica': producto.es_canasta_basica,
                'comercios_analizados': analizados,
                'lo_venden': lo_venden,
                'con_disponibilidad': con,
                'sin_disponibilidad': analizados - con,
                'agotados': lo_venden - con,
                'existencia_total': float(o.existencia_total) if o else 0,
                'cobertura': cobertura,
                'puntos_requeridos': requeridos,
                'deficit_puntos': max(requeridos - con, 0) if requeridos else None,
                'ventas': ventas.get(clave, 0),
                'proveedores': n_prov,
                'precio_mayoreo_min': mayoreo_min,
                'precio_promedio': precios.get(clave),
                'ultima_actualizacion': o.ultima_actualizacion if o else None,
                'nivel': clasificar_brecha(cobertura, limites),
            })

    if nivel:
        filas = [f for f in filas if f['nivel'] == nivel]
    filas.sort(key=lambda f: (f['cobertura'], -f['ventas']))
    return filas


# ---------------------------------------------------------------------------
# Cobertura e índice de acceso por zona
# ---------------------------------------------------------------------------

def _calcular_indicadores_zonas():
    zonas = ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre).all()
    canasta = ProductoMaestro.query.filter_by(activo=True, es_canasta_basica=True).all()
    oferta = _oferta_por_zona_producto()
    limites = umbrales()

    es_formal = cast(Comercio.tipo_comercio, db.String).like('FORMAL%')
    por_sector = dict(
        ((z, formal), n) for z, formal, n in
        db.session.query(Comercio.zona_id, es_formal, func.count(Comercio.id))
        .filter(*_filtro_comercios())
        .group_by(Comercio.zona_id, es_formal).all()
    )
    proveedores_zona = dict(
        db.session.query(proveedor_zonas.c.zona_id, func.count(Proveedor.id))
        .join(Proveedor, Proveedor.id == proveedor_zonas.c.proveedor_id)
        .filter(Proveedor.activo.is_(True))
        .group_by(proveedor_zonas.c.zona_id).all()
    )

    resultado = []
    for zona in zonas:
        formales = por_sector.get((zona.id, True), 0)
        informales = por_sector.get((zona.id, False), 0)
        total = formales + informales
        coberturas = []
        criticos = 0
        for producto in canasta:
            o = oferta.get((zona.id, producto.id))
            cobertura = (o.con_existencia * 100 / total) if (o and total) else 0
            coberturas.append(cobertura)
            if cobertura < limites[0]:
                criticos += 1
        indice = round(sum(coberturas) / len(coberturas), 1) if coberturas and total else 0.0
        disponibles = sum(1 for (z, _), o in oferta.items() if z == zona.id and o.con_existencia > 0)
        resultado.append({
            'id': zona.id,
            'nombre': zona.nombre,
            'municipio': zona.municipio,
            'poblacion': zona.poblacion,
            'latitud': float(zona.latitud_centro),
            'longitud': float(zona.longitud_centro),
            'radio_km': float(zona.radio_km),
            'comercios': total,
            'formales': formales,
            'informales': informales,
            'proveedores': proveedores_zona.get(zona.id, 0),
            'productos_disponibles': disponibles,
            'densidad_km2': round(total / area_km2(zona.radio_km), 2),
            'habitantes_por_comercio': round(zona.poblacion / total) if total else None,
            'indice_acceso': indice,
            'canasta_critica': criticos,
            'canasta_total': len(canasta),
            'clasificacion': clasificar_acceso(indice, limites) if total else 'Sin comercios',
        })

    # Ranking: 1 = zona con peor acceso (prioridad de atención)
    for posicion, zona in enumerate(sorted(resultado, key=lambda z: z['indice_acceso']), start=1):
        zona['ranking'] = posicion
    return sorted(resultado, key=lambda z: z['ranking'])


def indicadores_zonas():
    return obtener_o_calcular('indicadores_zonas', _calcular_indicadores_zonas)


def puntos_mapa(producto_id=None):
    """Comercios y proveedores con coordenadas para el mapa de cobertura."""
    consulta = (db.session.query(Comercio, ZonaMunicipal.nombre)
                .outerjoin(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
                .filter(Comercio.latitud.isnot(None), *_filtro_comercios()))
    existencias = {}
    if producto_id:
        existencias = dict(db.session.query(InventarioComercio.comercio_id, InventarioComercio.existencia)
                           .filter_by(producto_id=producto_id, activo=True).all())
    comercios = []
    for comercio, zona in consulta:
        punto = {
            'nombre': comercio.nombre_comercio,
            'tipo': comercio.tipo_legible,
            'sector': comercio.sector,
            'zona': zona,
            'lat': float(comercio.latitud),
            'lon': float(comercio.longitud),
        }
        if producto_id:
            existencia = existencias.get(comercio.id)
            punto['existencia'] = float(existencia) if existencia is not None else None
        comercios.append(punto)

    proveedores = [{
        'nombre': p.nombre_empresa,
        'lat': float(p.latitud),
        'lon': float(p.longitud),
        'zonas': len(p.zonas),
        'plan': p.plan,
    } for p in Proveedor.query.filter(Proveedor.activo.is_(True), Proveedor.latitud.isnot(None))]
    return {'comercios': comercios, 'proveedores': proveedores}


# ---------------------------------------------------------------------------
# Recomendación de surtido y faltantes del comercio
# ---------------------------------------------------------------------------

def recomendaciones(comercio):
    """
    Recomienda un producto al comercio si:
      1. el comercio no lo vende,
      2. su cobertura en la zona es menor a UMBRAL_COBERTURA_RECOMENDACION,
      3. hay demanda estimada (es de canasta básica o tuvo ventas en la zona), y
      4. al menos un proveedor que entrega en la zona lo tiene disponible.
    """
    if not comercio.zona_id:
        return []
    umbral = parametro('UMBRAL_COBERTURA_RECOMENDACION')
    vende = {i.producto_id for i in comercio.inventario if i.activo}
    filas = brechas(zona_id=comercio.zona_id)

    ventas_zona = sorted(f['ventas'] for f in filas if f['ventas'] > 0)
    p75 = ventas_zona[int(len(ventas_zona) * 0.75)] if ventas_zona else None

    resultado = []
    for f in filas:
        if f['producto_id'] in vende or f['cobertura'] >= umbral or not f['proveedores']:
            continue
        if not (f['canasta_basica'] or f['ventas'] > 0):
            continue

        if f['lo_venden'] == 0:
            motivo = 'Nadie lo vende en tu zona'
        elif f['con_disponibilidad'] == 0:
            motivo = 'Agotado en toda la zona'
        elif f['lo_venden'] and f['agotados'] / f['lo_venden'] >= 0.5:
            motivo = 'Frecuente agotamiento'
        elif p75 and f['ventas'] >= p75:
            motivo = 'Alta demanda'
        else:
            motivo = 'Baja oferta'

        margen = None
        if f['precio_promedio'] and f['precio_mayoreo_min']:
            margen = round((f['precio_promedio'] - f['precio_mayoreo_min']) * 100 / f['precio_promedio'], 1)

        puntaje = ((100 - f['cobertura'])
                   + (20 if f['canasta_basica'] else 0)
                   + min(f['ventas'] / 5, 20)
                   + min(f['proveedores'] * 5, 15))
        resultado.append({**f, 'motivo': motivo, 'margen_estimado': margen, 'puntaje': round(puntaje)})

    resultado.sort(key=lambda r: -r['puntaje'])
    return resultado


def faltantes(comercio):
    """Productos del comercio en BAJO o AGOTADO, con los proveedores que lo pueden surtir."""
    inventario = (InventarioComercio.query
                  .filter_by(comercio_id=comercio.id, activo=True)
                  .filter(InventarioComercio.estado.in_(('BAJO', 'AGOTADO')))
                  .join(ProductoMaestro).order_by(InventarioComercio.existencia, ProductoMaestro.nombre).all())
    proveedores = _proveedores_por_zona_producto()
    return [{
        'inventario': i,
        'proveedores': proveedores.get((comercio.zona_id, i.producto_id), (0, None))[0],
        'precio_mayoreo_min': proveedores.get((comercio.zona_id, i.producto_id), (0, None))[1],
    } for i in inventario]
