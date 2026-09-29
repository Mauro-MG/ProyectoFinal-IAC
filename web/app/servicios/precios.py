"""
Comparación de precios al consumidor (formal vs. informal) y de mayoreo.

Sólo se consideran precios VALIDADO (RN-001) dentro del rango de fechas.
"""
from collections import defaultdict

from sqlalchemy import case, cast, func

from app.extensions import db
from app.models import (CatalogoProveedor, Categoria, Comercio, PrecioComercio, PrecioMayoreo, ProductoMaestro,
                        Proveedor, ZonaMunicipal, proveedor_zonas)

SECTOR = case(
    (cast(Comercio.tipo_comercio, db.String).like('FORMAL%'), 'Formal'),
    (cast(Comercio.tipo_comercio, db.String).like('INFORMAL%'), 'Informal'),
    else_='Mayorista',
)


def _filtrar_productos(consulta, filtros):
    if filtros.get('producto_id'):
        consulta = consulta.filter(ProductoMaestro.id == filtros['producto_id'])
    if filtros.get('categoria_id'):
        consulta = consulta.filter(ProductoMaestro.categoria_id == filtros['categoria_id'])
    return consulta


def precios_consumidor(filtros):
    consulta = (db.session.query(
                    ProductoMaestro.id.label('producto_id'),
                    ProductoMaestro.nombre.label('producto'),
                    Categoria.nombre.label('categoria'),
                    ZonaMunicipal.nombre.label('zona'),
                    ZonaMunicipal.municipio.label('municipio'),
                    SECTOR.label('sector'),
                    func.min(PrecioComercio.precio).label('minimo'),
                    func.avg(PrecioComercio.precio).label('promedio'),
                    func.max(PrecioComercio.precio).label('maximo'),
                    func.count(PrecioComercio.id).label('muestras'),
                    func.count(func.distinct(PrecioComercio.comercio_id)).label('comercios'))
                .join(ProductoMaestro, PrecioComercio.producto_id == ProductoMaestro.id)
                .join(Categoria, ProductoMaestro.categoria_id == Categoria.id)
                .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
                .join(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
                .filter(PrecioComercio.activo.is_(True),
                        PrecioComercio.estado_validacion == 'VALIDADO',
                        PrecioComercio.fecha_registro >= filtros['desde'],
                        PrecioComercio.fecha_registro < filtros['hasta_exclusivo']))
    consulta = _filtrar_productos(consulta, filtros)
    if filtros.get('zona_id'):
        consulta = consulta.filter(ZonaMunicipal.id == filtros['zona_id'])
    if filtros.get('municipio'):
        consulta = consulta.filter(ZonaMunicipal.municipio == filtros['municipio'])
    if filtros.get('sector'):
        consulta = consulta.filter(SECTOR == filtros['sector'])
    return (consulta
            .group_by(ProductoMaestro.id, ProductoMaestro.nombre, Categoria.nombre,
                      ZonaMunicipal.nombre, ZonaMunicipal.municipio, SECTOR)
            .order_by(ProductoMaestro.nombre, ZonaMunicipal.nombre, SECTOR)
            .all())


def precios_mayoreo(filtros):
    consulta = (db.session.query(
                    ProductoMaestro.id.label('producto_id'),
                    ProductoMaestro.nombre.label('producto'),
                    Proveedor.id.label('proveedor_id'),
                    Proveedor.nombre_empresa.label('proveedor'),
                    func.min(PrecioMayoreo.precio).label('minimo'),
                    func.avg(PrecioMayoreo.precio).label('promedio'),
                    func.max(PrecioMayoreo.precio).label('maximo'),
                    func.count(PrecioMayoreo.id).label('muestras'))
                .join(ProductoMaestro, PrecioMayoreo.producto_id == ProductoMaestro.id)
                .join(Proveedor, PrecioMayoreo.proveedor_id == Proveedor.id)
                .filter(PrecioMayoreo.fecha_registro >= filtros['desde'],
                        PrecioMayoreo.fecha_registro < filtros['hasta_exclusivo']))
    consulta = _filtrar_productos(consulta, filtros)
    if filtros.get('proveedor_id'):
        consulta = consulta.filter(Proveedor.id == filtros['proveedor_id'])
    if filtros.get('zona_id'):
        # Sólo proveedores que entregan en la zona
        consulta = consulta.filter(Proveedor.id.in_(
            db.session.query(proveedor_zonas.c.proveedor_id).filter(proveedor_zonas.c.zona_id == filtros['zona_id'])))
    return (consulta
            .group_by(ProductoMaestro.id, ProductoMaestro.nombre, Proveedor.id, Proveedor.nombre_empresa)
            .order_by(ProductoMaestro.nombre, func.avg(PrecioMayoreo.precio))
            .all())


def resumen_por_producto(consumidor, mayoreo):
    """
    Une ambas consultas por producto: promedio formal, informal, mayoreo y el
    margen bruto estimado (precio promedio al consumidor vs. mejor precio de mayoreo).
    """
    acumulado = defaultdict(lambda: {'Formal': [0, 0], 'Informal': [0, 0], 'mayoreo': []})
    nombres = {}
    for f in consumidor:
        if f.sector in ('Formal', 'Informal'):
            suma = acumulado[f.producto_id][f.sector]
            suma[0] += float(f.promedio) * f.muestras
            suma[1] += f.muestras
        nombres[f.producto_id] = f.producto
    for f in mayoreo:
        acumulado[f.producto_id]['mayoreo'].append(float(f.promedio))
        nombres[f.producto_id] = f.producto

    resumen = []
    for producto_id, datos in acumulado.items():
        formal = datos['Formal'][0] / datos['Formal'][1] if datos['Formal'][1] else None
        informal = datos['Informal'][0] / datos['Informal'][1] if datos['Informal'][1] else None
        muestras = datos['Formal'][1] + datos['Informal'][1]
        consumidor_prom = ((datos['Formal'][0] + datos['Informal'][0]) / muestras) if muestras else None
        mayoreo_min = min(datos['mayoreo']) if datos['mayoreo'] else None
        resumen.append({
            'producto_id': producto_id,
            'producto': nombres[producto_id],
            'formal': formal,
            'informal': informal,
            'diferencia_pct': ((informal - formal) * 100 / formal) if formal and informal else None,
            'mayoreo_min': mayoreo_min,
            'margen_pct': ((consumidor_prom - mayoreo_min) * 100 / consumidor_prom)
                          if consumidor_prom and mayoreo_min else None,
        })
    return sorted(resumen, key=lambda r: r['producto'])


def tendencia_semanal(producto_id, semanas=8):
    """Promedio semanal formal, informal y mayoreo para la gráfica de tendencias."""
    semana_c = func.date_trunc('week', PrecioComercio.fecha_registro)
    consumidor = (db.session.query(semana_c, SECTOR, func.avg(PrecioComercio.precio))
                  .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
                  .filter(PrecioComercio.producto_id == producto_id,
                          PrecioComercio.estado_validacion == 'VALIDADO',
                          PrecioComercio.fecha_registro >= func.now() - func.make_interval(0, 0, semanas))
                  .group_by(semana_c, SECTOR).all())
    semana_m = func.date_trunc('week', PrecioMayoreo.fecha_registro)
    mayoreo = (db.session.query(semana_m, func.avg(PrecioMayoreo.precio))
               .filter(PrecioMayoreo.producto_id == producto_id,
                       PrecioMayoreo.fecha_registro >= func.now() - func.make_interval(0, 0, semanas))
               .group_by(semana_m).all())

    series = defaultdict(dict)
    for semana, sector, promedio in consumidor:
        series[sector][semana.date()] = round(float(promedio), 2)
    for semana, promedio in mayoreo:
        series['Mayoreo'][semana.date()] = round(float(promedio), 2)

    fechas = sorted({f for datos in series.values() for f in datos})
    return {
        'categorias': [f.strftime('%d/%m') for f in fechas],
        'series': [{'name': nombre, 'data': [series[nombre].get(f) for f in fechas]}
                   for nombre in ('Formal', 'Informal', 'Mayoreo') if nombre in series],
    }


def ofertas_producto(producto_id, zona_id=None):
    """¿Quién me vende este producto, a qué precio, en qué cantidad y con qué condiciones?"""
    consulta = (CatalogoProveedor.query
                .join(Proveedor)
                .filter(CatalogoProveedor.producto_id == producto_id,
                        CatalogoProveedor.activo.is_(True),
                        Proveedor.activo.is_(True)))
    ofertas = consulta.all()
    for oferta in ofertas:
        oferta.cubre_zona = oferta.proveedor.cubre_zona(zona_id) if zona_id else None
    # Primero los que entregan en la zona y tienen existencia, luego por precio.
    # El plan de pago del proveedor no altera el orden (sólo muestra la etiqueta).
    ofertas.sort(key=lambda o: (not o.cubre_zona if zona_id else False,
                                o.existencia_disponible <= 0,
                                o.precio_mayoreo))
    return ofertas
