"""Pedidos de abasto (la lógica del flujo está en servicios/pedidos.py)."""
from decimal import Decimal, InvalidOperation
from uuid import UUID

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from app.extensions import db
from app.models import CatalogoProveedor, Comercio, PedidoAbasto, ProductoMaestro, Proveedor
from app.permisos import permiso_requerido
from app.servicios import ReglaNegocioError
from app.servicios import pedidos as flujo


def _pedido_visible(id):
    pedido = db.get_or_404(PedidoAbasto, id)
    if not flujo.puede_ver(pedido, current_user):
        abort(403)
    return pedido


def _uuid(texto):
    try:
        return UUID(texto)
    except (TypeError, ValueError):
        abort(404)


def _cantidad(texto):
    try:
        cantidad = Decimal((texto or '').strip())
    except InvalidOperation:
        raise ReglaNegocioError('Captura una cantidad válida.')
    if cantidad <= 0:
        raise ReglaNegocioError('La cantidad debe ser mayor a cero.')
    return cantidad


@app.route('/pedidos')
@login_required
@permiso_requerido('pedidos.crear', 'pedidos.atender', 'pedidos.ver_todos')
def pedidos_lista():
    consulta = PedidoAbasto.query
    if current_user.tiene_permiso('pedidos.ver_todos'):
        vista = 'todos'
    elif current_user.tiene_permiso('pedidos.atender'):
        vista = 'recibidos'
        proveedor_id = current_user.proveedor.id if current_user.proveedor else None
        # El proveedor no ve los borradores del comerciante
        consulta = consulta.filter(PedidoAbasto.proveedor_id == proveedor_id, PedidoAbasto.estado != 'BORRADOR')
    else:
        vista = 'mios'
        consulta = consulta.join(Comercio).filter(Comercio.usuario_id == current_user.id)

    estado = request.args.get('estado')
    if estado:
        consulta = consulta.filter(PedidoAbasto.estado == estado)
    pagina = consulta.order_by(PedidoAbasto.updated_at.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=25, error_out=False)
    return render_template('pedidos/lista.html', pagina=pagina, estado=estado, vista=vista)


@app.route('/pedidos/nuevo', methods=['POST'])
@login_required
@permiso_requerido('pedidos.crear')
def pedido_nuevo():
    comercio = db.get_or_404(Comercio, _uuid(request.form.get('comercio_id')))
    proveedor = db.get_or_404(Proveedor, _uuid(request.form.get('proveedor_id')))
    if comercio.usuario_id != current_user.id:
        abort(403)
    try:
        pedido = flujo.obtener_borrador(comercio, proveedor, current_user)
        if request.form.get('producto_id'):
            flujo.agregar_producto(pedido, request.form.get('producto_id', type=int),
                                   _cantidad(request.form.get('cantidad')), current_user)
        db.session.commit()
    except ReglaNegocioError as e:
        db.session.rollback()
        flash(str(e), 'error')
        return redirect(request.referrer or url_for('proveedores_lista'))
    flash(f'Producto agregado al pedido {pedido.folio_legible}. Revisa y confirma cuando esté completo.', 'ok')
    return redirect(url_for('pedido_detalle', id=pedido.id))


@app.route('/pedidos/<uuid:id>')
@login_required
def pedido_detalle(id):
    pedido = _pedido_visible(id)
    editable = pedido.estado == 'BORRADOR' and flujo.es_del_comercio(pedido, current_user)
    en_pedido = {d.producto_id for d in pedido.detalles}
    catalogo = []
    if editable:
        catalogo = (CatalogoProveedor.query.filter_by(proveedor_id=pedido.proveedor_id, activo=True)
                    .filter(CatalogoProveedor.existencia_disponible > 0)
                    .join(ProductoMaestro).order_by(ProductoMaestro.nombre).all())
        catalogo = [o for o in catalogo if o.producto_id not in en_pedido]
    return render_template('pedidos/detalle.html', pedido=pedido, editable=editable, catalogo=catalogo,
                           acciones=flujo.acciones_disponibles(pedido, current_user),
                           etiquetas=flujo.ETIQUETAS_ACCION)


@app.route('/pedidos/<uuid:id>/agregar', methods=['POST'])
@login_required
@permiso_requerido('pedidos.crear')
def pedido_agregar(id):
    pedido = _pedido_visible(id)
    if not flujo.es_del_comercio(pedido, current_user):
        abort(403)
    try:
        flujo.agregar_producto(pedido, request.form.get('producto_id', type=int),
                               _cantidad(request.form.get('cantidad')), current_user)
        db.session.commit()
    except ReglaNegocioError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return redirect(url_for('pedido_detalle', id=id))


@app.route('/pedidos/<uuid:id>/quitar/<int:detalle_id>', methods=['POST'])
@login_required
@permiso_requerido('pedidos.crear')
def pedido_quitar(id, detalle_id):
    pedido = _pedido_visible(id)
    if not flujo.es_del_comercio(pedido, current_user):
        abort(403)
    try:
        flujo.quitar_producto(pedido, detalle_id, current_user)
        db.session.commit()
    except ReglaNegocioError as e:
        db.session.rollback()
        flash(str(e), 'error')
    return redirect(url_for('pedido_detalle', id=id))


@app.route('/pedidos/<uuid:id>/accion/<accion>', methods=['POST'])
@login_required
def pedido_accion(id, accion):
    pedido = _pedido_visible(id)
    try:
        nuevo = flujo.ejecutar_accion(pedido, accion, current_user,
                                      comentario=(request.form.get('comentario') or '').strip() or None)
        db.session.commit()
    except ReglaNegocioError as e:
        db.session.rollback()
        flash(str(e), 'error')
        return redirect(url_for('pedido_detalle', id=id))

    mensajes = {
        'ENVIADO': 'Pedido enviado. El proveedor lo verá en su panel.',
        'ENTREGADO': 'Recepción confirmada. Las cantidades se sumaron a tu inventario.',
    }
    flash(mensajes.get(nuevo, f'El pedido quedó como: {pedido.estado_legible.lower()}.'), 'ok')
    return redirect(url_for('pedido_detalle', id=id))
