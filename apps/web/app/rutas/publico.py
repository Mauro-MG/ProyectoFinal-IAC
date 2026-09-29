"""Portal público: disponibilidad de productos y directorio de puntos de venta."""
from flask import render_template, request
from sqlalchemy import func

from app import app
from app.extensions import db
from app.models import Categoria, Comercio, InventarioComercio, ProductoMaestro, Proveedor, ZonaMunicipal
from app.servicios.analisis import indicadores_zonas


def _disponibilidad_publica():
    """Inventario de comercios verificados; sólo se publica lo que el comercio vende."""
    return (db.session.query(InventarioComercio, Comercio, ProductoMaestro, ZonaMunicipal)
            .join(Comercio, InventarioComercio.comercio_id == Comercio.id)
            .join(ProductoMaestro, InventarioComercio.producto_id == ProductoMaestro.id)
            .outerjoin(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
            .filter(InventarioComercio.activo.is_(True),
                    Comercio.activo.is_(True),
                    Comercio.estado_registro == 'VERIFICADO'))


@app.route('/')
def index():
    base = _disponibilidad_publica()
    resumen = {
        'comercios': Comercio.query.filter_by(activo=True, estado_registro='VERIFICADO').count(),
        'productos': base.filter(InventarioComercio.existencia > 0)
                         .with_entities(func.count(func.distinct(InventarioComercio.producto_id))).scalar(),
        'proveedores': Proveedor.query.filter_by(activo=True).count(),
        'zonas': ZonaMunicipal.query.filter_by(activa=True).count(),
    }
    return render_template('publico/index.html', resumen=resumen, zonas=indicadores_zonas(),
                           categorias=Categoria.query.filter_by(activa=True).order_by(Categoria.orden).all())


@app.route('/disponibilidad')
def disponibilidad_publica():
    texto = request.args.get('q', '').strip()
    zona_id = request.args.get('zona_id', type=int)
    categoria_id = request.args.get('categoria_id', type=int)
    solo_con_existencia = request.args.get('existencia') == '1'

    consulta = _disponibilidad_publica()
    if texto:
        consulta = consulta.filter(ProductoMaestro.nombre.ilike(f'%{texto}%'))
    if zona_id:
        consulta = consulta.filter(Comercio.zona_id == zona_id)
    if categoria_id:
        consulta = consulta.filter(ProductoMaestro.categoria_id == categoria_id)
    if solo_con_existencia:
        consulta = consulta.filter(InventarioComercio.existencia > 0)

    pagina = (consulta
              .order_by(ProductoMaestro.nombre, InventarioComercio.existencia.desc(), Comercio.nombre_comercio)
              .paginate(page=request.args.get('page', 1, type=int), per_page=30, error_out=False))
    return render_template('publico/disponibilidad.html', pagina=pagina, texto=texto, zona_id=zona_id,
                           categoria_id=categoria_id, solo_con_existencia=solo_con_existencia,
                           zonas=ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre).all(),
                           categorias=Categoria.query.filter_by(activa=True).order_by(Categoria.orden).all())


@app.route('/puntos-de-venta')
def comercios_publico():
    zona_id = request.args.get('zona_id', type=int)
    consulta = Comercio.query.filter_by(activo=True, estado_registro='VERIFICADO')
    if zona_id:
        consulta = consulta.filter_by(zona_id=zona_id)
    comercios = consulta.order_by(Comercio.nombre_comercio).all()
    productos_por_comercio = dict(
        db.session.query(InventarioComercio.comercio_id, func.count(InventarioComercio.id))
        .filter(InventarioComercio.activo.is_(True), InventarioComercio.existencia > 0)
        .group_by(InventarioComercio.comercio_id).all())
    return render_template('publico/comercios.html', comercios=comercios, zona_id=zona_id,
                           productos_por_comercio=productos_por_comercio,
                           zonas=ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre).all())


@app.route('/acerca')
def acerca():
    return render_template('publico/acerca.html')
