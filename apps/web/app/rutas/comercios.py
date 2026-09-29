"""Registro de comercios, ubicación y validación por el coordinador municipal."""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from app.extensions import db
from app.formularios import ComercioForm
from app.models import Comercio, ZonaMunicipal
from app.permisos import permiso_requerido
from app.servicios.auditoria import registrar_evento
from app.servicios.cache import invalidar_analisis
from app.servicios.geo import zona_para_punto

CAMPOS_AUDITADOS = ('nombre_comercio', 'tipo_comercio', 'direccion', 'municipio', 'zona_id', 'latitud', 'longitud')


def puede_ver_comercio(comercio):
    return comercio.usuario_id == current_user.id or current_user.tiene_permiso('comercios.ver_todos')


def puede_editar_comercio(comercio):
    return comercio.usuario_id == current_user.id or current_user.tiene_permiso('catalogos.gestionar')


def _opciones_zona(form):
    zonas = ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.municipio, ZonaMunicipal.nombre).all()
    form.zona_id.choices = [(0, 'Asignar según la ubicación')] + [(z.id, str(z)) for z in zonas]
    return zonas


def _asignar_zona(comercio, form, zonas):
    """Si el usuario no eligió zona, se toma la zona cuyo radio contiene la ubicación."""
    comercio.zona_id = form.zona_id.data or None
    if not comercio.zona_id and comercio.latitud is not None and comercio.longitud is not None:
        zona = zona_para_punto(comercio.latitud, comercio.longitud, zonas)
        comercio.zona_id = zona.id if zona else None


def _foto(comercio):
    return {c: getattr(comercio, c) for c in CAMPOS_AUDITADOS}


@app.route('/comercios')
@login_required
@permiso_requerido('comercios.gestionar', 'comercios.ver_todos')
def comercios_lista():
    consulta = Comercio.query.filter_by(activo=True)
    if not current_user.tiene_permiso('comercios.ver_todos'):
        consulta = consulta.filter_by(usuario_id=current_user.id)

    estado = request.args.get('estado')
    zona_id = request.args.get('zona_id', type=int)
    if estado:
        consulta = consulta.filter_by(estado_registro=estado)
    if zona_id:
        consulta = consulta.filter_by(zona_id=zona_id)

    pagina = consulta.order_by(Comercio.nombre_comercio).paginate(
        page=request.args.get('page', 1, type=int), per_page=25, error_out=False)
    return render_template('comercios/lista.html', pagina=pagina, estado=estado, zona_id=zona_id,
                           zonas=ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre).all())


@app.route('/comercios/nuevo', methods=['GET', 'POST'])
@login_required
@permiso_requerido('comercios.gestionar')
def comercio_nuevo():
    form = ComercioForm()
    zonas = _opciones_zona(form)
    if form.validate_on_submit():
        comercio = Comercio(usuario_id=current_user.id, estado_registro='PENDIENTE')
        form.populate_obj(comercio)
        _asignar_zona(comercio, form, zonas)
        db.session.add(comercio)
        db.session.flush()
        registrar_evento(current_user.id, 'CREACION', 'Comercio', comercio.id,
                         f'Registro del comercio {comercio.nombre_comercio}', datos_nuevos=_foto(comercio))
        db.session.commit()
        invalidar_analisis()
        if not comercio.zona_id:
            flash('No encontramos una zona para esa ubicación; un coordinador la asignará al validar.', 'alerta')
        flash('Comercio registrado. Ahora elige los productos que vendes.', 'ok')
        return redirect(url_for('inventario_agregar', comercio_id=comercio.id))
    return render_template('comercios/formulario.html', form=form, titulo='Registrar comercio', zonas=zonas)


@app.route('/comercios/<uuid:id>')
@login_required
def comercio_detalle(id):
    comercio = db.get_or_404(Comercio, id)
    if not puede_ver_comercio(comercio):
        abort(403)
    return render_template('comercios/detalle.html', comercio=comercio,
                           puede_editar=puede_editar_comercio(comercio))


@app.route('/comercios/<uuid:id>/editar', methods=['GET', 'POST'])
@login_required
def comercio_editar(id):
    comercio = db.get_or_404(Comercio, id)
    if not puede_editar_comercio(comercio):
        abort(403)

    form = ComercioForm(obj=comercio)
    zonas = _opciones_zona(form)
    if request.method == 'GET':
        form.zona_id.data = comercio.zona_id or 0
    if form.validate_on_submit():
        antes = _foto(comercio)
        form.populate_obj(comercio)
        _asignar_zona(comercio, form, zonas)
        registrar_evento(current_user.id, 'ACTUALIZACION', 'Comercio', comercio.id,
                         f'Edición del comercio {comercio.nombre_comercio}',
                         datos_anteriores=antes, datos_nuevos=_foto(comercio))
        db.session.commit()
        invalidar_analisis()
        flash('Cambios guardados.', 'ok')
        return redirect(url_for('comercio_detalle', id=comercio.id))
    return render_template('comercios/formulario.html', form=form, titulo='Editar comercio', zonas=zonas)


@app.route('/comercios/<uuid:id>/desactivar', methods=['POST'])
@login_required
def comercio_desactivar(id):
    comercio = db.get_or_404(Comercio, id)
    if not puede_editar_comercio(comercio):
        abort(403)
    comercio.activo = False
    registrar_evento(current_user.id, 'ELIMINACION', 'Comercio', comercio.id,
                     f'Baja lógica del comercio {comercio.nombre_comercio}')
    db.session.commit()
    invalidar_analisis()
    flash('Comercio dado de baja.', 'ok')
    return redirect(url_for('comercios_lista'))


@app.route('/comercios/<uuid:id>/validar', methods=['POST'])
@login_required
@permiso_requerido('comercios.validar')
def comercio_validar(id):
    comercio = db.get_or_404(Comercio, id)
    nuevo = request.form.get('estado')
    if nuevo not in ('VERIFICADO', 'RECHAZADO', 'SUSPENDIDO'):
        abort(400)
    anterior = comercio.estado_registro
    comercio.estado_registro = nuevo
    comercio.verificado_por = current_user.id
    comercio.fecha_verificacion = db.func.now()
    registrar_evento(current_user.id, 'CAMBIO_ESTADO', 'Comercio', comercio.id,
                     f'{comercio.nombre_comercio}: {anterior} -> {nuevo}',
                     datos_anteriores={'estado_registro': anterior},
                     datos_nuevos={'estado_registro': nuevo, 'motivo': request.form.get('motivo')})
    db.session.commit()
    invalidar_analisis()
    flash(f'{comercio.nombre_comercio} quedó como {nuevo.lower()}.', 'ok')
    return redirect(request.referrer or url_for('comercio_detalle', id=comercio.id))
