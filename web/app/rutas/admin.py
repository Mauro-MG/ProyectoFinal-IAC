"""Administración: usuarios, roles/permisos y parámetros del sistema."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from app.extensions import db
from app.formularios import UsuarioAdminForm
from app.models import ConfiguracionSistema, Rol, Usuario
from app.permisos import PERMISOS, permiso_requerido
from app.servicios.auditoria import registrar_evento
from app.servicios.cache import invalidar_analisis


@app.route('/admin/usuarios')
@login_required
@permiso_requerido('usuarios.gestionar')
def usuarios_lista():
    rol_id = request.args.get('rol_id', type=int)
    texto = request.args.get('q', '').strip()
    consulta = Usuario.query
    if rol_id:
        consulta = consulta.filter_by(rol_id=rol_id)
    if texto:
        consulta = consulta.filter(db.or_(Usuario.email.ilike(f'%{texto}%'), Usuario.nombre.ilike(f'%{texto}%'),
                                          Usuario.apellido_paterno.ilike(f'%{texto}%')))
    return render_template('admin/usuarios.html', usuarios=consulta.order_by(Usuario.email).all(),
                           roles=Rol.query.order_by(Rol.id).all(), rol_id=rol_id, texto=texto)


@app.route('/admin/usuarios/<uuid:id>', methods=['GET', 'POST'])
@login_required
@permiso_requerido('usuarios.gestionar')
def usuario_editar(id):
    usuario = db.get_or_404(Usuario, id)
    form = UsuarioAdminForm(obj=usuario)
    form.rol_id.choices = [(r.id, r.nombre) for r in Rol.query.filter_by(activo=True).order_by(Rol.id)]
    if form.validate_on_submit():
        if usuario.id == current_user.id and (not form.activo.data or form.rol_id.data != usuario.rol_id):
            flash('No puedes desactivarte ni cambiarte de rol a ti mismo.', 'error')
            return redirect(url_for('usuario_editar', id=id))
        antes = {'rol': usuario.rol.nombre, 'activo': usuario.activo}
        form.populate_obj(usuario)
        db.session.flush()
        db.session.refresh(usuario, ['rol'])
        registrar_evento(current_user.id, 'ACTUALIZACION', 'Usuario', usuario.id, f'Cuenta {usuario.email}',
                         datos_anteriores=antes, datos_nuevos={'rol': usuario.rol.nombre, 'activo': usuario.activo})
        db.session.commit()
        flash('Usuario actualizado.', 'ok')
        return redirect(url_for('usuarios_lista'))
    return render_template('admin/usuario_form.html', form=form, usuario=usuario)


@app.route('/admin/roles', methods=['GET', 'POST'])
@login_required
@permiso_requerido('roles.gestionar')
def roles():
    lista = Rol.query.order_by(Rol.id).all()
    if request.method == 'POST':
        cambios = 0
        for rol in lista:
            nuevos = sorted(c for c in request.form.getlist(f'permisos_{rol.id}') if c in PERMISOS)
            # El administrador no puede quitarse a sí mismo la gestión de roles
            if rol.id == current_user.rol_id and 'roles.gestionar' not in nuevos:
                nuevos.append('roles.gestionar')
            if sorted(rol.permisos or []) != nuevos:
                registrar_evento(current_user.id, 'ACTUALIZACION', 'Rol', rol.id, f'Permisos del rol {rol.nombre}',
                                 datos_anteriores={'permisos': rol.permisos}, datos_nuevos={'permisos': nuevos})
                rol.permisos = nuevos
                cambios += 1
        db.session.commit()
        flash(f'Permisos actualizados en {cambios} rol(es).' if cambios else 'No hubo cambios.', 'ok')
        return redirect(url_for('roles'))
    return render_template('admin/roles.html', roles=lista, permisos=PERMISOS)


@app.route('/admin/configuracion', methods=['GET', 'POST'])
@login_required
@permiso_requerido('config.gestionar')
def configuracion():
    parametros = ConfiguracionSistema.query.order_by(ConfiguracionSistema.clave).all()
    if request.method == 'POST':
        cambios = 0
        for p in parametros:
            valor = request.form.get(p.clave, '').strip()
            if valor == (p.valor or ''):
                continue
            if p.tipo_dato in ('int', 'float'):
                try:
                    float(valor)
                except ValueError:
                    flash(f'{p.clave}: debe ser un número.', 'error')
                    db.session.rollback()
                    return redirect(url_for('configuracion'))
            registrar_evento(current_user.id, 'ACTUALIZACION', 'ConfiguracionSistema', p.clave,
                             f'Parámetro {p.clave}', datos_anteriores={'valor': p.valor}, datos_nuevos={'valor': valor})
            p.valor = valor
            p.updated_by = current_user.id
            cambios += 1
        db.session.commit()
        invalidar_analisis()
        flash(f'{cambios} parámetro(s) actualizados.' if cambios else 'No hubo cambios.', 'ok')
        return redirect(url_for('configuracion'))
    return render_template('admin/configuracion.html', parametros=parametros)
