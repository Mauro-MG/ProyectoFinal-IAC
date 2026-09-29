"""
Catálogo del comercio e inventario.

Catálogo maestro (producto genérico) -> catálogo del comercio (lo que sí vende,
con su existencia, stock mínimo/máximo y precio).
"""
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from app.extensions import db
from app.formularios import InventarioForm, MovimientoForm
from app.models import Categoria, Comercio, InventarioComercio, PrecioComercio, ProductoMaestro
from app.permisos import permiso_requerido
from app.servicios import ReglaNegocioError, analisis
from app.servicios.auditoria import registrar_evento
from app.servicios.inventario import (actualizar_precio, agregar_al_catalogo, quitar_del_catalogo,
                                      registrar_movimiento)


def comercios_del_usuario():
    consulta = Comercio.query.filter_by(activo=True)
    if not current_user.tiene_permiso('catalogos.gestionar'):
        consulta = consulta.filter_by(usuario_id=current_user.id)
    return consulta.order_by(Comercio.nombre_comercio).all()


def _comercio_propio(comercio_id):
    comercio = db.get_or_404(Comercio, comercio_id)
    if comercio.usuario_id != current_user.id and not current_user.tiene_permiso('catalogos.gestionar'):
        abort(403)
    return comercio


def _renglon_propio(inventario_id):
    renglon = db.get_or_404(InventarioComercio, inventario_id)
    _comercio_propio(renglon.comercio_id)
    return renglon


def _decimal(valor, obligatorio=False):
    valor = (valor or '').strip().replace(',', '')
    if not valor:
        if obligatorio:
            raise ValueError
        return None
    numero = Decimal(valor)
    if numero < 0:
        raise ValueError
    return numero


@app.route('/inventario')
@login_required
@permiso_requerido('inventario.gestionar')
def inventario():
    comercios = comercios_del_usuario()
    if not comercios:
        flash('Primero registra tu comercio.', 'info')
        return redirect(url_for('comercio_nuevo'))

    comercio_id = request.args.get('comercio_id')
    comercio = next((c for c in comercios if str(c.id) == comercio_id), comercios[0])
    estado = request.args.get('estado')

    consulta = (InventarioComercio.query.filter_by(comercio_id=comercio.id, activo=True)
                .join(ProductoMaestro).join(Categoria))
    if estado:
        consulta = consulta.filter(InventarioComercio.estado == estado)
    renglones = consulta.order_by(Categoria.orden, ProductoMaestro.nombre).all()

    todos = InventarioComercio.query.filter_by(comercio_id=comercio.id, activo=True).all()
    resumen = {
        'productos': len(todos),
        'bajo': sum(1 for r in todos if r.estado == 'BAJO'),
        'agotado': sum(1 for r in todos if r.estado == 'AGOTADO'),
        'valor': sum((r.existencia * (r.precio_venta or 0) for r in todos), Decimal(0)),
    }
    return render_template('inventario/lista.html', comercio=comercio, comercios=comercios, renglones=renglones,
                           resumen=resumen, estado=estado, faltantes=analisis.faltantes(comercio))


@app.route('/inventario/<uuid:comercio_id>/agregar', methods=['GET', 'POST'])
@login_required
@permiso_requerido('inventario.gestionar')
def inventario_agregar(comercio_id):
    comercio = _comercio_propio(comercio_id)
    ya_vende = {r.producto_id for r in comercio.inventario if r.activo}
    disponibles = (ProductoMaestro.query.filter_by(activo=True)
                   .filter(ProductoMaestro.id.notin_(ya_vende) if ya_vende else True)
                   .join(Categoria).order_by(Categoria.orden, ProductoMaestro.nombre).all())

    if request.method == 'POST':
        seleccion = request.form.getlist('producto_id', type=int)
        if not seleccion:
            flash('Marca al menos un producto.', 'alerta')
            return redirect(request.url)
        agregados, errores = 0, []
        for producto in (p for p in disponibles if p.id in seleccion):
            try:
                existencia = _decimal(request.form.get(f'existencia_{producto.id}')) or 0
                minimo = _decimal(request.form.get(f'minimo_{producto.id}')) or 0
                maximo = _decimal(request.form.get(f'maximo_{producto.id}'))
                precio = _decimal(request.form.get(f'precio_{producto.id}'))
                agregar_al_catalogo(comercio, producto, current_user, existencia, minimo, maximo, precio)
                agregados += 1
            except (ValueError, InvalidOperation):
                errores.append(f'{producto.nombre}: revisa que las cantidades sean números positivos')
            except ReglaNegocioError as e:
                errores.append(str(e))
        if errores:
            db.session.rollback()
            for error in errores:
                flash(error, 'error')
            return render_template('inventario/agregar.html', comercio=comercio, productos=disponibles,
                                   seleccion=set(seleccion), datos=request.form)
        db.session.commit()
        flash(f'{agregados} producto(s) agregados al catálogo de {comercio.nombre_comercio}.', 'ok')
        return redirect(url_for('inventario', comercio_id=comercio.id))

    preseleccion = set(request.args.getlist('producto_id', type=int))
    return render_template('inventario/agregar.html', comercio=comercio, productos=disponibles,
                           seleccion=preseleccion, datos={})


@app.route('/inventario/item/<int:id>')
@login_required
@permiso_requerido('inventario.gestionar')
def inventario_item(id):
    renglon = _renglon_propio(id)
    return render_template(
        'inventario/item.html', renglon=renglon,
        form_edicion=InventarioForm(obj=renglon), form_movimiento=MovimientoForm(),
        movimientos=renglon.movimientos.limit(25).all(),
        precios=(PrecioComercio.query.filter_by(comercio_id=renglon.comercio_id, producto_id=renglon.producto_id)
                 .order_by(PrecioComercio.fecha_registro.desc()).limit(10).all()))


@app.route('/inventario/item/<int:id>/movimiento', methods=['POST'])
@login_required
@permiso_requerido('inventario.gestionar')
def inventario_movimiento(id):
    renglon = _renglon_propio(id)
    form = MovimientoForm()
    if not form.validate_on_submit():
        flash('Captura una cantidad válida.', 'error')
        return redirect(url_for('inventario_item', id=id))
    try:
        registrar_movimiento(renglon, form.tipo.data, form.cantidad.data, current_user, motivo=form.motivo.data or None)
        db.session.commit()
        flash(f'Movimiento registrado. Existencia actual: {renglon.existencia.normalize():f} '
              f'{renglon.producto.unidad_medida}.', 'ok')
    except ReglaNegocioError as e:
        db.session.rollback()
        flash(str(e), 'error')
    volver = request.form.get('volver', '')
    if volver.startswith('/') and not volver.startswith('//'):
        return redirect(volver)
    return redirect(url_for('inventario_item', id=id))


@app.route('/inventario/item/<int:id>/editar', methods=['POST'])
@login_required
@permiso_requerido('inventario.gestionar')
def inventario_editar(id):
    renglon = _renglon_propio(id)
    form = InventarioForm()
    if not form.validate_on_submit():
        for errores in form.errors.values():
            flash(errores[0], 'error')
        return redirect(url_for('inventario_item', id=id))

    antes = {'stock_minimo': renglon.stock_minimo, 'stock_maximo': renglon.stock_maximo}
    renglon.stock_minimo = form.stock_minimo.data
    renglon.stock_maximo = form.stock_maximo.data
    if antes != {'stock_minimo': renglon.stock_minimo, 'stock_maximo': renglon.stock_maximo}:
        registrar_evento(current_user.id, 'ACTUALIZACION', 'InventarioComercio', renglon.id,
                         f'Límites de stock de {renglon.producto.nombre}', datos_anteriores=antes,
                         datos_nuevos={'stock_minimo': renglon.stock_minimo, 'stock_maximo': renglon.stock_maximo})
    try:
        resultado = actualizar_precio(renglon, form.precio_venta.data, current_user) if form.precio_venta.data else None
        db.session.commit()
    except ReglaNegocioError as e:
        db.session.rollback()
        flash(str(e), 'error')
        return redirect(url_for('inventario_item', id=id))

    if resultado == 'PENDIENTE_VALIDACION':
        flash('Guardado. El precio quedó pendiente de validación porque está muy lejos del promedio de tu zona.',
              'alerta')
    else:
        flash('Cambios guardados.', 'ok')
    return redirect(url_for('inventario_item', id=id))


@app.route('/inventario/item/<int:id>/quitar', methods=['POST'])
@login_required
@permiso_requerido('inventario.gestionar')
def inventario_quitar(id):
    renglon = _renglon_propio(id)
    quitar_del_catalogo(renglon, current_user)
    db.session.commit()
    flash(f'{renglon.producto.nombre} se quitó de tu catálogo. El historial se conserva.', 'ok')
    return redirect(url_for('inventario', comercio_id=renglon.comercio_id))
