"""Comparación de precios al consumidor (formal / informal) y de mayoreo."""
from datetime import date, datetime, timedelta
from uuid import UUID

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import app
from app.microservicios import ServicioNoDisponible, llamar
from abasto_dominio.modelos import Categoria, Proveedor, ProductoMaestro, ZonaMunicipal
from app.permisos import permiso_requerido
from abasto_dominio.servicios import precios as servicio


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


# ---------------------------------------------------------------- revisión de precios atípicos (ms-precios)

@app.route('/precios/revision')
@login_required
@permiso_requerido('comercios.validar')
def precios_revision():
    """
    Un precio fuera del 10 %-150 % del promedio de su zona queda pendiente y no
    entra a la comparación hasta que la coordinación lo valida o lo descarta.
    """
    try:
        respuesta = llamar('precios', 'GET', '/precios/pendientes')
        pendientes, disponible = respuesta.datos.get('precios', []), respuesta.ok
    except ServicioNoDisponible:
        pendientes, disponible = [], False
    return render_template('precios/revision.html', pendientes=pendientes, disponible=disponible)


@app.route('/precios/<int:id>/revision', methods=['POST'])
@login_required
@permiso_requerido('comercios.validar')
def precio_revisar(id):
    decision = request.form.get('decision')
    if decision not in ('VALIDAR', 'DESCARTAR'):
        abort(400)
    try:
        respuesta = llamar('precios', 'PATCH', f'/precios/{id}/validacion',
                           json={'decision': decision, 'comentario': request.form.get('comentario', '').strip() or None})
        if respuesta.ok:
            flash(f"Precio de {respuesta.datos['producto']} en {respuesta.datos['comercio']} "
                  f"{'validado' if decision == 'VALIDAR' else 'descartado'}. Se avisó al comerciante.", 'ok')
        else:
            flash(respuesta.mensaje_error, 'error')
    except ServicioNoDisponible:
        flash('El servicio de precios no está disponible; intenta más tarde.', 'error')
    return redirect(url_for('precios_revision'))
