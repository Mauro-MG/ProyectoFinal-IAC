"""
Proveedores.

Para el comerciante: ¿quién me vende este producto, a qué precio, en qué
cantidad y con qué condiciones?
Para el proveedor: sus datos, zonas de entrega y catálogo mayorista.

Las consultas leen de la base; los datos de la empresa y el catálogo mayorista
los escribe ms-proveedores, y las cuentas de los operadores ms-seguridad.
"""
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from abasto_dominio.extensiones import db
from app.formularios import OfertaForm, OperadorForm, ProveedorForm
from app.microservicios import escribir
from abasto_dominio.modelos import (CatalogoProveedor, InventarioComercio, ProductoMaestro, Proveedor, Usuario,
                                    ZonaMunicipal)
from app.permisos import permiso_requerido
from app.rutas.inventario import comercios_del_usuario
from abasto_dominio.servicios.precios import ofertas_producto

CAMPOS_EMPRESA = ('nombre_empresa', 'rfc', 'descripcion', 'telefono_contacto', 'email_contacto', 'direccion',
                  'municipio', 'latitud', 'longitud', 'pedido_minimo', 'tiempo_entrega_dias', 'condiciones_venta')


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


# ---------------------------------------------------------------- lado del proveedor (escribe ms-proveedores)

def _empresa_json(form):
    datos = {c: getattr(form, c).data for c in CAMPOS_EMPRESA}
    datos = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in datos.items()}
    if datos['rfc']:
        datos['rfc'] = datos['rfc'].upper()
    return datos


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
        datos = _empresa_json(form)
        if proveedor:
            guardado = escribir('proveedores', 'PATCH', f'/proveedores/{proveedor.id}', json=datos)
        else:
            # Queda PENDIENTE de verificación por la coordinación municipal
            guardado = escribir('proveedores', 'POST', '/proveedores', json=datos)
        if guardado is not None and sorted(form.zonas.data) != sorted(z['id'] for z in guardado['zonas']):
            guardado = escribir('proveedores', 'PUT', f"/proveedores/{guardado['id']}/zonas",
                                json={'zonas': form.zonas.data})
        if guardado is not None:
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
        if escribir('proveedores', 'POST', '/mi-catalogo', exito='Producto agregado a tu catálogo.', json={
                'producto_id': form.producto_id.data, 'precio_mayoreo': form.precio_mayoreo.data,
                'cantidad_minima': form.cantidad_minima.data,
                'existencia_disponible': form.existencia_disponible.data or 0}) is not None:
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
        escribir('proveedores', 'DELETE', f'/mi-catalogo/{id}',
                 exito=f'{oferta.producto.nombre} ya no aparece en tu catálogo.')
        return redirect(url_for('mi_catalogo'))

    try:
        cambios = {campo: Decimal(request.form[campo])
                   for campo in ('precio_mayoreo', 'cantidad_minima', 'existencia_disponible')}
    except (KeyError, ArithmeticError, ValueError):
        flash('Revisa los valores: precio y venta mínima deben ser mayores a cero.', 'error')
        return redirect(url_for('mi_catalogo'))
    # Un cambio de precio entra al historial de precios de mayoreo en ms-proveedores
    escribir('proveedores', 'PATCH', f'/mi-catalogo/{id}', json=cambios, exito=f'{oferta.producto.nombre} actualizado.')
    return redirect(url_for('mi_catalogo'))


# ---------------------------------------------------------------- equipo del proveedor (escribe ms-seguridad)

@app.route('/mi-empresa/equipo', methods=['GET', 'POST'])
@login_required
@permiso_requerido('proveedor.equipo')
def mi_equipo():
    """
    El dueño da de alta a sus empleados con el perfil Operador de Proveedor:
    ven y atienden los pedidos de la empresa, pero no cambian precios, catálogo
    ni datos de la empresa. Las cuentas las crea ms-seguridad (dueño de usuarios).
    """
    proveedor = current_user.proveedor
    if not proveedor:
        flash('Primero registra los datos de tu empresa.', 'info')
        return redirect(url_for('mi_empresa'))
    form = OperadorForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        operador = escribir('seguridad', 'POST', '/operadores', json={
            'email': email, 'password': form.password.data, 'nombre': form.nombre.data.strip(),
            'apellido_paterno': form.apellido_paterno.data.strip(), 'telefono': form.telefono.data or None})
        if operador is not None:
            flash(f"{operador['nombre']} {operador['apellido']} ya puede entrar con {email} y la contraseña temporal.",
                  'ok')
            return redirect(url_for('mi_equipo'))
    operadores = sorted(proveedor.operadores, key=lambda u: (not u.activo, u.nombre))
    return render_template('proveedores/equipo.html', proveedor=proveedor, operadores=operadores, form=form)


@app.route('/mi-empresa/equipo/<uuid:id>/estado', methods=['POST'])
@login_required
@permiso_requerido('proveedor.equipo')
def mi_equipo_estado(id):
    operador = db.get_or_404(Usuario, id)
    if not current_user.proveedor or operador.proveedor_id != current_user.proveedor.id:
        abort(403)
    # Al darlo de baja, ms-seguridad cierra sus sesiones: deja de poder entrar al web y a la API
    escribir('seguridad', 'PATCH', f'/operadores/{id}', json={'activo': not operador.activo},
             exito=f'{operador.nombre_completo} ' + ('ya no tiene acceso.' if operador.activo
                                                    else 'puede volver a entrar.'))
    return redirect(url_for('mi_equipo'))
