"""
Registro de comercios, ubicación y validación por el coordinador municipal.

Las listas y el detalle se leen de la base; el registro, la edición, la baja y
la validación los hace ms-comercios (dueño de la tabla), que asigna la zona con
ms-geolocalizacion, audita, avisa al dueño e invalida la caché de análisis.
"""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from abasto_dominio.extensiones import db
from app.formularios import ComercioForm
from app.microservicios import escribir
from abasto_dominio.modelos import Comercio, ZonaMunicipal
from app.permisos import permiso_requerido

# Campos del contrato de ms-comercios que esta pantalla no captura: en la edición se mandan con su valor
# actual porque el PUT reemplaza el comercio completo
CAMPOS_SIN_FORMULARIO = ('dias_operacion', 'giro', 'email_contacto', 'rfc', 'razon_social', 'regimen_fiscal')


def puede_ver_comercio(comercio):
    return comercio.usuario_id == current_user.id or current_user.tiene_permiso('comercios.ver_todos')


def puede_editar_comercio(comercio):
    return comercio.usuario_id == current_user.id or current_user.tiene_permiso('catalogos.gestionar')


def _opciones_zona(form):
    zonas = ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.municipio, ZonaMunicipal.nombre).all()
    form.zona_id.choices = [(0, 'Asignar según la ubicación')] + [(z.id, str(z)) for z in zonas]
    return zonas


def _comercio_json(form, actual=None):
    datos = {campo: getattr(form, campo).data for campo in (
        'nombre_comercio', 'tipo_comercio', 'direccion', 'colonia', 'municipio', 'estado', 'latitud', 'longitud',
        'telefono_comercio', 'horario_apertura', 'horario_cierre', 'descripcion')}
    datos = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in datos.items()}
    # Sin zona elegida, ms-comercios la asigna según la ubicación (RN-016)
    datos['zona_id'] = form.zona_id.data or None
    if actual:
        datos.update({c: getattr(actual, c) for c in CAMPOS_SIN_FORMULARIO})
    return datos


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
        comercio = escribir('comercios', 'POST', '/comercios', json=_comercio_json(form))
        if comercio is not None:
            if not comercio.get('zona_id'):
                flash('No encontramos una zona para esa ubicación; un coordinador la asignará al validar.', 'alerta')
            flash('Comercio registrado. Ahora elige los productos que vendes.', 'ok')
            return redirect(url_for('inventario_agregar', comercio_id=comercio['id']))
    return render_template('comercios/formulario.html', form=form, titulo='Registrar comercio', zonas=zonas)


@app.route('/comercios/<uuid:id>')
@login_required
def comercio_detalle(id):
    comercio = db.get_or_404(Comercio, id)
    if not puede_ver_comercio(comercio):
        abort(403)
    from app.rutas.archivos import CATEGORIAS_COMERCIO, archivos_de_comercio
    lista, fuente = archivos_de_comercio(comercio)
    return render_template('comercios/detalle.html', comercio=comercio,
                           puede_editar=puede_editar_comercio(comercio),
                           archivos=lista, fuente_archivos=fuente, categorias_archivo=CATEGORIAS_COMERCIO,
                           fotos=[a for a in lista if (a.get('tipo_mime') or '').startswith('image/')])


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
        if escribir('comercios', 'PUT', f'/comercios/{id}', json=_comercio_json(form, comercio),
                    exito='Cambios guardados.') is not None:
            return redirect(url_for('comercio_detalle', id=id))
    return render_template('comercios/formulario.html', form=form, titulo='Editar comercio', zonas=zonas)


@app.route('/comercios/<uuid:id>/desactivar', methods=['POST'])
@login_required
def comercio_desactivar(id):
    comercio = db.get_or_404(Comercio, id)
    if not puede_editar_comercio(comercio):
        abort(403)
    if escribir('comercios', 'DELETE', f'/comercios/{id}', exito='Comercio dado de baja.') is None:
        return redirect(url_for('comercio_detalle', id=id))
    return redirect(url_for('comercios_lista'))


@app.route('/comercios/<uuid:id>/validar', methods=['POST'])
@login_required
@permiso_requerido('comercios.validar')
def comercio_validar(id):
    comercio = db.get_or_404(Comercio, id)
    nuevo = request.form.get('estado')
    if nuevo not in ('VERIFICADO', 'RECHAZADO', 'SUSPENDIDO'):
        abort(400)
    escribir('comercios', 'PATCH', f'/comercios/{id}/validacion',
             json={'estado': nuevo, 'observaciones': (request.form.get('motivo') or '').strip() or None},
             exito=f'{comercio.nombre_comercio} quedó como {nuevo.lower()}.')
    return redirect(request.referrer or url_for('comercio_detalle', id=id))
