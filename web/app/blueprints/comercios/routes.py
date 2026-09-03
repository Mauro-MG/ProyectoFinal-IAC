from flask import Blueprint, abort, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.comercio import Comercio
from app.blueprints.comercios.forms import ComercioForm
from app.utils.audit import registrar_evento
from app.utils.decorators import role_required

comercios_bp = Blueprint('comercios', __name__)


def puede_gestionar_comercio(comercio):
    return (
        current_user.rol.nombre in ['Administrador General', 'Coordinador Municipal']
        or comercio.usuario_id == current_user.id
    )

@comercios_bp.route('/')
@login_required
def lista():
    page = request.args.get('page', 1, type=int)
    if current_user.rol.nombre in ['Administrador General', 'Coordinador Municipal']:
        query = Comercio.query.filter_by(activo=True)
    else:
        query = Comercio.query.filter_by(usuario_id=current_user.id, activo=True)
        
    comercios_pag = query.paginate(page=page, per_page=20)
    return render_template('comercios/lista.html', comercios=comercios_pag)

@comercios_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@role_required('Administrador General', 'Coordinador Municipal', 'Comerciante Informal', 'Minorista Formal', 'Proveedor')
def nuevo():
    form = ComercioForm()
    if form.validate_on_submit():
        comercio = Comercio(
            usuario_id=current_user.id,
            nombre_comercio=form.nombre_comercio.data,
            tipo_comercio=form.tipo_comercio.data,
            direccion=form.direccion.data,
            municipio=form.municipio.data,
            estado=form.estado.data
        )
        db.session.add(comercio)
        db.session.commit()
        
        registrar_evento(current_user.id, 'CREACION', 'Comercio', comercio.id, f'Creado comercio {comercio.nombre_comercio}')
        flash('Comercio creado exitosamente', 'success')
        return redirect(url_for('comercios.lista'))
        
    return render_template('comercios/formulario.html', form=form, title="Nuevo Comercio")

@comercios_bp.route('/<uuid:id>')
@login_required
def detalle(id):
    comercio = Comercio.query.get_or_404(id)
    if not puede_gestionar_comercio(comercio):
        abort(403)
    return render_template('comercios/detalle.html', comercio=comercio)


@comercios_bp.route('/<uuid:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    comercio = Comercio.query.get_or_404(id)
    if not puede_gestionar_comercio(comercio):
        abort(403)

    form = ComercioForm(obj=comercio)
    if form.validate_on_submit():
        datos_anteriores = {
            'nombre_comercio': comercio.nombre_comercio,
            'tipo_comercio': comercio.tipo_comercio,
            'municipio': comercio.municipio,
            'estado': comercio.estado,
        }
        comercio.nombre_comercio = form.nombre_comercio.data
        comercio.tipo_comercio = form.tipo_comercio.data
        comercio.direccion = form.direccion.data
        comercio.municipio = form.municipio.data
        comercio.estado = form.estado.data
        db.session.commit()

        registrar_evento(
            current_user.id,
            'ACTUALIZACION',
            'Comercio',
            comercio.id,
            f'Actualizado comercio {comercio.nombre_comercio}',
            datos_anteriores=datos_anteriores,
            datos_nuevos={
                'nombre_comercio': comercio.nombre_comercio,
                'tipo_comercio': comercio.tipo_comercio,
                'municipio': comercio.municipio,
                'estado': comercio.estado,
            },
        )
        flash('Comercio actualizado exitosamente', 'success')
        return redirect(url_for('comercios.detalle', id=comercio.id))

    return render_template('comercios/formulario.html', form=form, title="Editar Comercio")


@comercios_bp.route('/<uuid:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    comercio = Comercio.query.get_or_404(id)
    if not puede_gestionar_comercio(comercio):
        abort(403)

    comercio.activo = False
    db.session.commit()
    registrar_evento(current_user.id, 'ELIMINACION', 'Comercio', comercio.id, f'Desactivado comercio {comercio.nombre_comercio}')
    flash('Comercio desactivado exitosamente', 'success')
    return redirect(url_for('comercios.lista'))
