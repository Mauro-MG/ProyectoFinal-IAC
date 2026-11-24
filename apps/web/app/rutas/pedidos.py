"""
Pedidos de abasto.

Las pantallas leen los pedidos de la base; crear, editar el borrador y cada
transición (enviar, aceptar, despachar, recibir...) los hace ms-pedidos. Al
despachar, ms-pedidos descuenta la existencia del proveedor con ms-proveedores
y al recibir suma la mercancía al inventario del comercio con ms-inventario.
"""
from decimal import Decimal, InvalidOperation
from uuid import UUID

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from abasto_dominio.extensiones import db
from app.microservicios import escribir
from abasto_dominio.modelos import CatalogoProveedor, Comercio, PedidoAbasto, ProductoMaestro
from app.permisos import permiso_requerido
from abasto_dominio.servicios import pedidos as flujo


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
        return None
    return cantidad if cantidad > 0 else None


@app.route('/pedidos')
@login_required
@permiso_requerido('pedidos.crear', 'pedidos.atender', 'pedidos.ver_todos')
def pedidos_lista():
    consulta = PedidoAbasto.query
    if current_user.tiene_permiso('pedidos.ver_todos'):
        vista = 'todos'
    elif current_user.tiene_permiso('pedidos.atender'):
        vista = 'recibidos'
        empresa = current_user.proveedor_vinculado  # dueño u operador del proveedor
        proveedor_id = empresa.id if empresa else None
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
    """Abre (o reutiliza) el borrador entre el comercio y el proveedor y, si viene, le agrega el producto."""
    cuerpo = {'comercio_id': str(_uuid(request.form.get('comercio_id'))),
              'proveedor_id': str(_uuid(request.form.get('proveedor_id'))), 'partidas': []}
    if request.form.get('producto_id'):
        cantidad = _cantidad(request.form.get('cantidad'))
        if cantidad is None:
            flash('Captura una cantidad mayor a cero.', 'error')
            return redirect(request.referrer or url_for('proveedores_lista'))
        cuerpo['partidas'].append({'producto_id': request.form.get('producto_id', type=int), 'cantidad': cantidad})
    pedido = escribir('pedidos', 'POST', '/pedidos', json=cuerpo)
    if pedido is None:
        return redirect(request.referrer or url_for('proveedores_lista'))
    flash(f"Producto agregado al pedido {pedido['folio']}. Revisa y confirma cuando esté completo."
          if cuerpo['partidas'] else f"Pedido {pedido['folio']} abierto. Agrega los productos.", 'ok')
    return redirect(url_for('pedido_detalle', id=pedido['id']))


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
    _pedido_visible(id)
    cantidad = _cantidad(request.form.get('cantidad'))
    if cantidad is None:
        flash('Captura una cantidad mayor a cero.', 'error')
    else:
        escribir('pedidos', 'POST', f'/pedidos/{id}/partidas',
                 json={'producto_id': request.form.get('producto_id', type=int), 'cantidad': cantidad})
    return redirect(url_for('pedido_detalle', id=id))


@app.route('/pedidos/<uuid:id>/quitar/<int:detalle_id>', methods=['POST'])
@login_required
@permiso_requerido('pedidos.crear')
def pedido_quitar(id, detalle_id):
    _pedido_visible(id)
    escribir('pedidos', 'DELETE', f'/pedidos/{id}/partidas/{detalle_id}')
    return redirect(url_for('pedido_detalle', id=id))


@app.route('/pedidos/<uuid:id>/accion/<accion>', methods=['POST'])
@login_required
def pedido_accion(id, accion):
    _pedido_visible(id)
    resultado = escribir('pedidos', 'POST', f'/pedidos/{id}/acciones/{accion}', timeout=15,
                         json={'comentario': (request.form.get('comentario') or '').strip() or None})
    if resultado is not None:
        nuevo = resultado['transicion']['a']
        mensajes = {
            'ENVIADO': 'Pedido enviado. El proveedor lo verá en su panel.',
            'ENTREGADO': 'Recepción confirmada. Las cantidades se sumaron a tu inventario.',
        }
        flash(mensajes.get(nuevo, f"El pedido quedó como: {resultado.get('estado_legible', nuevo).lower()}."), 'ok')
    return redirect(url_for('pedido_detalle', id=id))
