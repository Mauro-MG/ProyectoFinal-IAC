"""
Administración: usuarios, roles/permisos y parámetros del sistema.

Las pantallas leen de la base (solo lectura) y los cambios van al servicio dueño:
usuarios y roles a ms-seguridad, parámetros a ms-configuracion. Cada servicio
valida, audita, cierra las sesiones afectadas e invalida sus cachés.
"""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from abasto_dominio.extensiones import db
from app.formularios import UsuarioAdminForm
from app.microservicios import escribir
from abasto_dominio.modelos import ConfiguracionSistema, Rol, Usuario
from app.permisos import PERMISOS, permiso_requerido


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
        cambios = {k: v for k, v in (('rol_id', form.rol_id.data), ('activo', form.activo.data))
                   if v != getattr(usuario, k)}
        if not cambios:
            flash('No hubo cambios.', 'ok')
            return redirect(url_for('usuarios_lista'))
        # ms-seguridad no deja que uno se cambie el rol o se desactive a sí mismo, y cierra las
        # sesiones del usuario (sus tokens llevan el rol y los permisos anteriores)
        if escribir('seguridad', 'PATCH', f'/usuarios/{id}', json=cambios,
                    exito='Usuario actualizado. Se cerraron sus sesiones abiertas.') is None:
            return redirect(url_for('usuario_editar', id=id))
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
            if sorted(rol.permisos or []) != sorted(nuevos):
                if escribir('seguridad', 'PUT', f'/roles/{rol.id}/permisos', json={'permisos': nuevos}) is None:
                    return redirect(url_for('roles'))
                cambios += 1
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
            # ms-configuracion valida el tipo y el rango, audita e invalida las cachés de parámetros y análisis
            if escribir('configuracion', 'PUT', f'/parametros/{p.clave}', json={'valor': valor}) is None:
                return redirect(url_for('configuracion'))
            cambios += 1
        flash(f'{cambios} parámetro(s) actualizados.' if cambios else 'No hubo cambios.', 'ok')
        return redirect(url_for('configuracion'))
    return render_template('admin/configuracion.html', parametros=parametros)
