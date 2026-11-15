"""
Catálogo del comercio e inventario.

Catálogo maestro (producto genérico) -> catálogo del comercio (lo que sí vende,
con su existencia, stock mínimo/máximo y precio).

Las pantallas leen de la base; los renglones y movimientos los escribe
ms-inventario y el precio ms-precios.
"""
import csv
import io
from decimal import Decimal, InvalidOperation

from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from app.microservicios import ServicioNoDisponible, escribir, llamar
from abasto_dominio.extensiones import db
from app.formularios import InventarioForm, MovimientoForm
from abasto_dominio.modelos import Categoria, Comercio, InventarioComercio, PrecioComercio, ProductoMaestro
from app.permisos import permiso_requerido
from abasto_dominio.servicios import analisis


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
        # Primero se revisan todas las cantidades: si alguna está mal no se manda ninguna
        renglones, errores = [], []
        for producto in (p for p in disponibles if p.id in seleccion):
            try:
                renglones.append((producto, {
                    'producto_id': producto.id,
                    'existencia': _decimal(request.form.get(f'existencia_{producto.id}')) or 0,
                    'stock_minimo': _decimal(request.form.get(f'minimo_{producto.id}')) or 0,
                    'stock_maximo': _decimal(request.form.get(f'maximo_{producto.id}')),
                    'precio_venta': _decimal(request.form.get(f'precio_{producto.id}')) or None}))
            except (ValueError, InvalidOperation):
                errores.append(f'{producto.nombre}: revisa que las cantidades sean números positivos')
        agregados = 0
        if not errores:
            # ms-inventario agrega cada renglón (existencia inicial como ENTRADA) y pide el precio a ms-precios
            for producto, cuerpo in renglones:
                renglon = escribir('inventario', 'POST', f'/comercios/{comercio.id}/inventario', json=cuerpo)
                if renglon is None:
                    errores.append(f'{producto.nombre}: no se agregó')
                else:
                    if renglon.get('aviso'):
                        flash(f"{producto.nombre}: {renglon['aviso']}", 'alerta')
                    agregados += 1
                    seleccion.remove(producto.id)
        if errores:
            for error in errores:
                flash(error, 'error')
            if agregados:
                flash(f'{agregados} producto(s) sí se agregaron.', 'ok')
            return render_template('inventario/agregar.html', comercio=comercio, productos=disponibles,
                                   seleccion=set(seleccion), datos=request.form)
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
    movimiento = escribir('inventario', 'POST', f'/inventario/{id}/movimientos',
                          json={'tipo': form.tipo.data, 'cantidad': form.cantidad.data,
                                'motivo': form.motivo.data or None})
    if movimiento is not None:
        existencia = Decimal(str(movimiento['existencia_nueva'])).normalize()
        flash(f'Movimiento registrado. Existencia actual: {existencia:f} {renglon.producto.unidad_medida}.', 'ok')
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

    # Los límites son de ms-inventario y el precio de ms-precios (historial y validación de atípicos, RN-001)
    limites = {'stock_minimo': form.stock_minimo.data, 'stock_maximo': form.stock_maximo.data}
    if limites != {'stock_minimo': renglon.stock_minimo, 'stock_maximo': renglon.stock_maximo}:
        if escribir('inventario', 'PATCH', f'/inventario/{id}', json=limites) is None:
            return redirect(url_for('inventario_item', id=id))
    precio = form.precio_venta.data
    if precio and precio != renglon.precio_venta:
        cambio = escribir('precios', 'PUT', f'/inventario/{id}/precio', json={'precio': precio})
        if cambio is None:
            return redirect(url_for('inventario_item', id=id))
        if cambio['estado_validacion'] == 'PENDIENTE_VALIDACION':
            flash('Guardado. El precio quedó pendiente de validación porque está muy lejos del promedio de tu zona.',
                  'alerta')
            return redirect(url_for('inventario_item', id=id))
    flash('Cambios guardados.', 'ok')
    return redirect(url_for('inventario_item', id=id))


@app.route('/inventario/item/<int:id>/quitar', methods=['POST'])
@login_required
@permiso_requerido('inventario.gestionar')
def inventario_quitar(id):
    renglon = _renglon_propio(id)
    escribir('inventario', 'DELETE', f'/inventario/{id}',
             exito=f'{renglon.producto.nombre} se quitó de tu catálogo. El historial se conserva.')
    return redirect(url_for('inventario', comercio_id=renglon.comercio_id))


# ---------------------------------------------------------------- importación masiva (ms-inventario)

@app.route('/inventario/<uuid:comercio_id>/importar', methods=['GET', 'POST'])
@login_required
@permiso_requerido('importaciones.ejecutar')
def inventario_importar(comercio_id):
    """
    Carga del inventario desde CSV. El archivo se reenvía a ms-inventario,
    que lo guarda en GridFS, aplica cada fila en su propio savepoint y deja el
    resultado en MongoDB (importaciones). Un bloqueo en Redis evita dos cargas
    simultáneas del mismo comercio.
    """
    comercio = _comercio_propio(comercio_id)
    resultado = None
    if request.method == 'POST':
        archivo = request.files.get('archivo')
        if not archivo or not archivo.filename:
            flash('Selecciona el archivo CSV.', 'error')
        else:
            try:
                respuesta = llamar('inventario', 'POST', f'/comercios/{comercio.id}/importaciones',
                                   files={'archivo': (archivo.filename, archivo.stream, 'text/csv')})
                if respuesta.ok:
                    resultado = respuesta.datos
                    flash(f"Importación terminada: {resultado['agregados']} agregados, "
                          f"{resultado['actualizados']} actualizados, {resultado['con_error']} con error.",
                          'ok' if not resultado['con_error'] else 'alerta')
                else:
                    flash(respuesta.mensaje_error, 'error')
            except ServicioNoDisponible:
                flash('El servicio de inventario no está disponible; intenta más tarde.', 'error')

    historial, fuente = [], 'ms-inventario'
    try:
        respuesta = llamar('inventario', 'GET', f'/comercios/{comercio.id}/importaciones')
        historial = respuesta.datos.get('importaciones', []) if respuesta.ok else []
    except ServicioNoDisponible:
        fuente = 'no disponible'
    return render_template('inventario/importar.html', comercio=comercio, resultado=resultado,
                           historial=historial, fuente=fuente)


@app.route('/inventario/<uuid:comercio_id>/plantilla.csv')
@login_required
@permiso_requerido('importaciones.ejecutar')
def inventario_plantilla(comercio_id):
    """Plantilla con el inventario actual, lista para editar y volver a subir."""
    comercio = _comercio_propio(comercio_id)
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(['producto', 'existencia', 'stock_minimo', 'stock_maximo', 'precio'])
    for r in (InventarioComercio.query.filter_by(comercio_id=comercio.id, activo=True)
              .join(ProductoMaestro).order_by(ProductoMaestro.nombre)):
        escritor.writerow([r.producto.nombre, r.existencia, r.stock_minimo, r.stock_maximo or '',
                           r.precio_venta or ''])
    return Response('﻿' + salida.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="inventario.csv"'})
