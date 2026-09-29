"""Comparación de precios al consumidor (formal / informal) y de mayoreo."""
from datetime import date, datetime, timedelta
from uuid import UUID

from flask import render_template, request
from flask_login import login_required

from app import app
from app.models import Categoria, Proveedor, ProductoMaestro, ZonaMunicipal
from app.permisos import permiso_requerido
from app.servicios import precios as servicio


def _fecha(texto, por_omision):
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return por_omision


def filtros_desde_request():
    hoy = date.today()
    desde = _fecha(request.args.get('desde'), hoy - timedelta(days=30))
    hasta = _fecha(request.args.get('hasta'), hoy)
    try:
        proveedor = str(UUID(request.args['proveedor_id'])) if request.args.get('proveedor_id') else None
    except ValueError:
        proveedor = None
    return {
        'producto_id': request.args.get('producto_id', type=int),
        'categoria_id': request.args.get('categoria_id', type=int),
        'zona_id': request.args.get('zona_id', type=int),
        'municipio': request.args.get('municipio') or None,
        'sector': request.args.get('sector') if request.args.get('sector') in ('Formal', 'Informal') else None,
        'proveedor_id': proveedor,
        'tipo': request.args.get('tipo', 'ambos'),
        'desde': desde,
        'hasta': hasta,
        'hasta_exclusivo': hasta + timedelta(days=1),
    }


@app.route('/precios')
@login_required
@permiso_requerido('precios.consultar')
def comparacion():
    filtros = filtros_desde_request()
    consumidor = servicio.precios_consumidor(filtros) if filtros['tipo'] in ('ambos', 'consumidor') else []
    mayoreo = servicio.precios_mayoreo(filtros) if filtros['tipo'] in ('ambos', 'mayoreo') else []
    # Filtrar por proveedor sólo tiene sentido para mayoreo
    if filtros['proveedor_id'] and filtros['tipo'] == 'ambos':
        consumidor = []

    tendencia = servicio.tendencia_semanal(filtros['producto_id']) if filtros['producto_id'] else None
    zonas = ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre).all()
    return render_template(
        'precios/comparacion.html', filtros=filtros, consumidor=consumidor, mayoreo=mayoreo,
        resumen=servicio.resumen_por_producto(consumidor, mayoreo), tendencia=tendencia,
        productos=ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre).all(),
        categorias=Categoria.query.filter_by(activa=True).order_by(Categoria.orden).all(),
        zonas=zonas, municipios=sorted({z.municipio for z in zonas}),
        proveedores=Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre_empresa).all())
