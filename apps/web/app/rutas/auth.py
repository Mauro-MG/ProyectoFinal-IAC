"""
Inicio de sesión, registro y recuperación de acceso.

El web no valida contraseñas ni escribe usuarios: todo lo hace ms-seguridad
(dueño de la tabla usuarios), que además lleva el bloqueo por intentos, emite
el JWT y registra la auditoría. El web guarda ese JWT en su sesión y lo manda
en cada llamada a los microservicios.
"""
from uuid import UUID

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from abasto_dominio import sesiones
from app import app
from abasto_dominio.extensiones import db
from app.formularios import LoginForm, RecuperarForm, RegistroForm, RestablecerForm
from app.microservicios import ServicioNoDisponible, llamar
from abasto_dominio.modelos import Usuario


def _destino_seguro(destino):
    # Evita redirecciones a otros sitios mediante ?next=
    return destino if destino and destino.startswith('/') and not destino.startswith('//') else None


def _abrir_sesion(datos):
    """Respuesta de ms-seguridad (login o registro) -> sesión de Flask con el JWT del usuario."""
    usuario = db.session.get(Usuario, UUID(datos['usuario']['id']))
    login_user(usuario)
    session['jwt_token'] = datos['access_token']
    session['jwt_jti'] = sesiones.decodificar(datos['access_token'])['jti']  # para detectar si la revocan
    return usuario


def _sin_servicio(plantilla, form):
    flash('El servicio de seguridad no está disponible. Intenta en un momento.', 'error')
    return render_template(plantilla, form=form), 503


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('panel'))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            respuesta = llamar('seguridad', 'POST', '/auth/login', publico=True,
                               json={'email': form.email.data.strip().lower(), 'password': form.password.data,
                                     'origen': 'web'})
        except ServicioNoDisponible:
            return _sin_servicio('auth/login.html', form)
        if respuesta.ok:
            _abrir_sesion(respuesta.datos)
            return redirect(_destino_seguro(request.args.get('next')) or url_for('panel'))
        flash(respuesta.mensaje_error, 'error')
        return render_template('auth/login.html', form=form), 429 if respuesta.status in (423, 429) else 200
    return render_template('auth/login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    # ms-seguridad revoca el token (sesión en Redis y lista de revocados) y audita el cierre
    try:
        llamar('seguridad', 'POST', '/auth/logout')
    except ServicioNoDisponible:
        current_app.logger.warning('No se pudo revocar el JWT de la sesión web; vence solo a las 8 h.')
    session.pop('jwt_token', None)
    session.pop('jwt_jti', None)
    logout_user()
    flash('Cerraste sesión.', 'ok')
    return redirect(url_for('index'))


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('panel'))

    form = RegistroForm()
    if form.validate_on_submit():
        try:
            respuesta = llamar('seguridad', 'POST', '/auth/registro', publico=True, json={
                'email': form.email.data.strip().lower(), 'password': form.password.data,
                'nombre': form.nombre.data.strip(), 'apellido_paterno': form.apellido_paterno.data.strip(),
                'telefono': form.telefono.data or None, 'perfil': form.perfil.data, 'origen': 'web'})
        except ServicioNoDisponible:
            return _sin_servicio('auth/registro.html', form)
        if not respuesta.ok:
            flash(respuesta.mensaje_error, 'error')
            return render_template('auth/registro.html', form=form)

        usuario = _abrir_sesion(respuesta.datos)
        # Siguiente paso natural: dar de alta el comercio o los datos del proveedor
        if usuario.rol.nombre == 'Proveedor':
            flash('Cuenta creada. Captura los datos de tu empresa para empezar a recibir pedidos.', 'ok')
            return redirect(url_for('mi_empresa'))
        flash('Cuenta creada. Ahora registra tu comercio.', 'ok')
        return redirect(url_for('comercio_nuevo'))

    return render_template('auth/registro.html', form=form)


@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    form = RecuperarForm()
    if form.validate_on_submit():
        try:
            # Aún no hay servidor de correo: ms-seguridad escribe el enlace en su bitácora
            # (docker compose logs ms-seguridad). Responde igual exista o no la cuenta.
            respuesta = llamar('seguridad', 'POST', '/auth/recuperacion', publico=True,
                               json={'email': form.email.data.strip().lower()})
        except ServicioNoDisponible:
            return _sin_servicio('auth/recuperar.html', form)
        if respuesta.status == 429:
            flash(respuesta.mensaje_error, 'error')
            return render_template('auth/recuperar.html', form=form), 429
        flash('Si el correo está registrado, recibirás un enlace para restablecer tu contraseña. '
              'Es válido por 30 minutos.', 'info')
        return redirect(url_for('login'))
    return render_template('auth/recuperar.html', form=form)


@app.route('/restablecer/<token>', methods=['GET', 'POST'])
def restablecer(token):
    form = RestablecerForm()
    if form.validate_on_submit():
        try:
            respuesta = llamar('seguridad', 'POST', '/auth/recuperacion/confirmacion', publico=True,
                               json={'token': token, 'password': form.password.data})
        except ServicioNoDisponible:
            return _sin_servicio('auth/restablecer.html', form)
        if respuesta.ok:
            flash('Contraseña actualizada. Ya puedes iniciar sesión.', 'ok')
            return redirect(url_for('login'))
        flash(respuesta.mensaje_error, 'error')
        return redirect(url_for('recuperar'))
    return render_template('auth/restablecer.html', form=form)
