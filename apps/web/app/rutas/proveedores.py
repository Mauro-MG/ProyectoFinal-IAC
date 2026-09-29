"""
Proveedores.

Para el comerciante: ¿quién me vende este producto, a qué precio, en qué
cantidad y con qué condiciones?
Para el proveedor: sus datos, zonas de entrega y catálogo mayorista.
"""
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from app.extensions import db
from app.formularios import OfertaForm, ProveedorForm
from app.models import (CatalogoProveedor, InventarioComercio, PrecioMayoreo, ProductoMaestro, Proveedor,
                        ZonaMunicipal)
from app.permisos import permiso_requerido
from app.rutas.inventario import comercios_del_usuario
from app.servicios.auditoria import registrar_evento
from app.servicios.cache import invalidar_analisis
from app.servicios.precios import ofertas_producto

CAMPOS_PROVEEDOR = ('nombre_empresa', 'rfc', 'pedido_minimo', 'tiempo_entrega_dias', 'condiciones_venta')


def _comercio_seleccionado(comercios):
    comercio_id = request.args.get('comercio_id')
    return next((c for c in comercios if str(c.id) == comercio_id), comercios[0] if comercios else None)


# ---------------------------------------------------------------- consulta (comerciante / analista)

@app.route('/proveedores')
@login_required
@permiso_requerido('proveedores.consultar')
def proveedores_lista():
    comercios = comercios_del_usuario() if current_user.tiene_permiso('pedidos.crear') else []
    comercio = _comercio_seleccionado(comercios)
    zona_id = request.args.get('zona_id', type=int) or (comercio.zona_id if comercio else None)

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre_empresa).all()
    if zona_id:
        proveedores = [p for p in proveedores if p.cubre_zona(zona_id)]
    productos = dict(db.session.query(CatalogoProveedor.proveedor_id, db.func.count(CatalogoProveedor.id))
                     .filter_by(activo=True).group_by(CatalogoProveedor.proveedor_id).all())
    return render_template('proveedores/lista.html', proveedores=proveedores, productos=productos,
                           comercios=comercios, comercio=comercio, zona_id=zona_id,
                           catalogo_productos=ProductoMaestro.query.filter_by(activo=True)
                                                               .order_by(ProductoMaestro.nombre).all(),
                           zonas=ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre).all())


@app.route('/proveedores/<uuid:id>')
@login_required
@permiso_requerido('proveedores.consultar', 'proveedor.catalogo')
def proveedor_detalle(id):
    proveedor = db.get_or_404(Proveedor, id)
    if not current_user.tiene_permiso('proveedores.consultar') and proveedor.usuario_id != current_user.id:
        abort(403)
    comercios = comercios_del_usuario() if current_user.tiene_permiso('pedidos.crear') else []
    comercio = _comercio_seleccionado(comercios)
    ofertas = (CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id, activo=True)
               .join(ProductoMaestro).order_by(ProductoMaestro.nombre).all())
    return render_template('proveedores/detalle.html', proveedor=proveedor, ofertas=ofertas,
                           comercios=comercios, comercio=comercio)


@app.route('/proveedores/buscar')
@login_required
@permiso_requerido('proveedores.consultar')
def proveedores_por_producto():
    producto = db.session.get(ProductoMaestro, request.args.get('producto_id', type=int) or 0)
    comercios = comercios_del_usuario() if current_user.tiene_permiso('pedidos.crear') else []
    comercio = _comercio_seleccionado(comercios)

    ofertas, renglon = [], None
    if producto:
        ofertas = ofertas_producto(producto.id, comercio.zona_id if comercio else None)
        if comercio:
            renglon = InventarioComercio.query.filter_by(comercio_id=comercio.id, producto_id=producto.id,
                                                         activo=True).first()
    return render_template('proveedores/buscar.html', producto=producto, ofertas=ofertas, renglon=renglon,
                           comercios=comercios, comercio=comercio,
                           productos=ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre).all())


# ---------------------------------------------------------------- lado del proveedor

@app.route('/mi-empresa', methods=['GET', 'POST'])
@login_required
@permiso_requerido('proveedor.catalogo')
def mi_empresa():
    proveedor = current_user.proveedor
    form = ProveedorForm(obj=proveedor)
    zonas = ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.municipio, ZonaMunicipal.nombre).all()
    form.zonas.choices = [(z.id, str(z)) for z in zonas]
    if request.method == 'GET':
        form.zonas.data = [z.id for z in proveedor.zonas] if proveedor else []
        if not proveedor:
            form.email_contacto.data = current_user.email

    if form.validate_on_submit():
        antes = {c: getattr(proveedor, c) for c in CAMPOS_PROVEEDOR} if proveedor else None
        if not proveedor:
            proveedor = Proveedor(usuario_id=current_user.id)
            db.session.add(proveedor)
        zonas_elegidas = [z for z in zonas if z.id in form.zonas.data]
        del form.zonas  # la relación se asigna aparte
        form.populate_obj(proveedor)
        proveedor.zonas = zonas_elegidas
        db.session.flush()
        registrar_evento(current_user.id, 'ACTUALIZACION' if antes else 'CREACION', 'Proveedor', proveedor.id,
                         f'Datos del proveedor {proveedor.nombre_empresa}', datos_anteriores=antes,
                         datos_nuevos={**{c: getattr(proveedor, c) for c in CAMPOS_PROVEEDOR},
                                       'zonas': [z.nombre for z in zonas_elegidas]})
        db.session.commit()
        invalidar_analisis()
        flash('Datos guardados.', 'ok')
        return redirect(url_for('mi_catalogo'))
    return render_template('proveedores/mi_empresa.html', form=form, proveedor=proveedor)


def _proveedor_actual():
    if not current_user.proveedor:
        flash('Primero captura los datos de tu empresa.', 'info')
        return None
    return current_user.proveedor


@app.route('/mi-catalogo', methods=['GET', 'POST'])
@login_required
@permiso_requerido('proveedor.catalogo')
def mi_catalogo():
    proveedor = _proveedor_actual()
    if not proveedor:
        return redirect(url_for('mi_empresa'))

    ofrecidos = {o.producto_id for o in proveedor.catalogo if o.activo}
    form = OfertaForm()
    form.producto_id.choices = [(p.id, f'{p.nombre} ({p.unidad_medida})') for p in
                                ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre)
                                if p.id not in ofrecidos]

    if form.validate_on_submit():
        oferta = CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id,
                                                   producto_id=form.producto_id.data).first()
        if not oferta:
            oferta = CatalogoProveedor(proveedor_id=proveedor.id, producto_id=form.producto_id.data)
            db.session.add(oferta)
        oferta.activo = True
        oferta.precio_mayoreo = form.precio_mayoreo.data
        oferta.cantidad_minima = form.cantidad_minima.data
        oferta.existencia_disponible = form.existencia_disponible.data or 0
        db.session.flush()
        db.session.add(PrecioMayoreo(proveedor_id=proveedor.id, producto_id=oferta.producto_id,
                                     precio=oferta.precio_mayoreo))
        registrar_evento(current_user.id, 'CREACION', 'CatalogoProveedor', oferta.id,
                         f'{proveedor.nombre_empresa} ofrece {oferta.producto.nombre}',
                         datos_nuevos={'precio_mayoreo': oferta.precio_mayoreo,
                                       'cantidad_minima': oferta.cantidad_minima,
                                       'existencia_disponible': oferta.existencia_disponible})
        db.session.commit()
        invalidar_analisis()
        flash('Producto agregado a tu catálogo.', 'ok')
        return redirect(url_for('mi_catalogo'))

    ofertas = (CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id, activo=True)
               .join(ProductoMaestro).order_by(ProductoMaestro.nombre).all())
    return render_template('proveedores/mi_catalogo.html', proveedor=proveedor, ofertas=ofertas, form=form)


@app.route('/mi-catalogo/<int:id>', methods=['POST'])
@login_required
@permiso_requerido('proveedor.catalogo')
def mi_catalogo_editar(id):
    oferta = db.get_or_404(CatalogoProveedor, id)
    if not current_user.proveedor or oferta.proveedor_id != current_user.proveedor.id:
        abort(403)

    if request.form.get('accion') == 'retirar':
        oferta.activo = False
        registrar_evento(current_user.id, 'ELIMINACION', 'CatalogoProveedor', oferta.id,
                         f'Se retiró {oferta.producto.nombre} del catálogo mayorista')
        db.session.commit()
        invalidar_analisis()
        flash(f'{oferta.producto.nombre} ya no aparece en tu catálogo.', 'ok')
        return redirect(url_for('mi_catalogo'))

    try:
        precio = Decimal(request.form['precio_mayoreo'])
        minima = Decimal(request.form['cantidad_minima'])
        existencia = Decimal(request.form['existencia_disponible'])
        if precio <= 0 or minima <= 0 or existencia < 0:
            raise ValueError
    except (KeyError, ArithmeticError, ValueError):
        flash('Revisa los valores: precio y venta mínima deben ser mayores a cero.', 'error')
        return redirect(url_for('mi_catalogo'))

    antes = {'precio_mayoreo': oferta.precio_mayoreo, 'cantidad_minima': oferta.cantidad_minima,
             'existencia_disponible': oferta.existencia_disponible}
    if precio != oferta.precio_mayoreo:
        db.session.add(PrecioMayoreo(proveedor_id=oferta.proveedor_id, producto_id=oferta.producto_id, precio=precio))
    oferta.precio_mayoreo, oferta.cantidad_minima, oferta.existencia_disponible = precio, minima, existencia
    registrar_evento(current_user.id, 'ACTUALIZACION', 'CatalogoProveedor', oferta.id,
                     f'Actualización de {oferta.producto.nombre}', datos_anteriores=antes,
                     datos_nuevos={'precio_mayoreo': precio, 'cantidad_minima': minima,
                                   'existencia_disponible': existencia})
    db.session.commit()
    invalidar_analisis()
    flash(f'{oferta.producto.nombre} actualizado.', 'ok')
    return redirect(url_for('mi_catalogo'))
