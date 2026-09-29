import secrets
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

import jwt
from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from redis.exceptions import RedisError

from app import app, extensions
from app.extensions import db
from app.formularios import LoginForm, RecuperarForm, RegistroForm, RestablecerForm
from app.models import Rol, Usuario
from app.servicios.auditoria import registrar_evento

TTL_RECUPERACION = 30 * 60


def emitir_jwt(usuario):
    ahora = datetime.now(timezone.utc)
    return jwt.encode({
        'user_id': str(usuario.id),
        'rol': usuario.rol.nombre,
        'iat': ahora,
        'exp': ahora + current_app.config['JWT_ACCESS_TOKEN_EXPIRES'],
    }, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def clave_token_revocado(token):
    return f"jwt:blacklist:{sha256(token.encode('utf-8')).hexdigest()}"


def _destino_seguro(destino):
    # Evita redirecciones a otros sitios mediante ?next=
    return destino if destino and destino.startswith('/') and not destino.startswith('//') else None


def _iniciar_sesion(usuario):
    login_user(usuario)
    usuario.ultimo_acceso = db.func.now()
    session['jwt_token'] = emitir_jwt(usuario)
    registrar_evento(usuario.id, 'LOGIN', 'Usuario', usuario.id, 'Inicio de sesión')
    db.session.commit()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('panel'))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(email=form.email.data.strip().lower(), activo=True).first()
        if usuario and usuario.check_password(form.password.data):
            _iniciar_sesion(usuario)
            return redirect(_destino_seguro(request.args.get('next')) or url_for('panel'))
        flash('Correo o contraseña incorrectos.', 'error')
    return render_template('auth/login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    token = session.pop('jwt_token', None)
    if token:
        try:
            extensions.redis_client.setex(clave_token_revocado(token),
                                          int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds()), '1')
        except RedisError:
            current_app.logger.warning('No se pudo registrar el JWT revocado en Redis.')

    registrar_evento(current_user.id, 'LOGOUT', 'Usuario', current_user.id, 'Cierre de sesión')
    db.session.commit()
    logout_user()
    flash('Cerraste sesión.', 'ok')
    return redirect(url_for('index'))


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('panel'))

    form = RegistroForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if Usuario.query.filter_by(email=email).first():
            flash('Ya existe una cuenta con ese correo.', 'error')
            return render_template('auth/registro.html', form=form)

        rol = Rol.query.filter_by(nombre=form.perfil.data, activo=True).first_or_404()
        usuario = Usuario(email=email, nombre=form.nombre.data.strip(),
                          apellido_paterno=form.apellido_paterno.data.strip(),
                          telefono=form.telefono.data or None, rol_id=rol.id)
        usuario.set_password(form.password.data)
        db.session.add(usuario)
        db.session.flush()
        registrar_evento(usuario.id, 'CREACION', 'Usuario', usuario.id, f'Registro de cuenta ({rol.nombre})')
        _iniciar_sesion(usuario)

        # Siguiente paso natural: dar de alta el comercio o los datos del proveedor
        if rol.nombre == 'Proveedor':
            flash('Cuenta creada. Captura los datos de tu empresa para empezar a recibir pedidos.', 'ok')
            return redirect(url_for('mi_empresa'))
        flash('Cuenta creada. Ahora registra tu comercio.', 'ok')
        return redirect(url_for('comercio_nuevo'))

    return render_template('auth/registro.html', form=form)


@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    form = RecuperarForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(email=form.email.data.strip().lower(), activo=True).first()
        if usuario:
            token = secrets.token_urlsafe(32)
            try:
                extensions.redis_client.setex(f'recuperacion:{token}', TTL_RECUPERACION, str(usuario.id))
                # Aún no hay servidor de correo: el enlace se escribe en el log del contenedor web
                current_app.logger.info('Enlace de recuperación para %s: %s', usuario.email,
                                        url_for('restablecer', token=token, _external=True))
            except RedisError:
                current_app.logger.error('Redis no disponible; no se pudo generar el enlace de recuperación.')
        # Mismo mensaje exista o no el correo, para no revelar qué cuentas existen
        flash('Si el correo está registrado, recibirás un enlace para restablecer tu contraseña. '
              'Es válido por 30 minutos.', 'info')
        return redirect(url_for('login'))
    return render_template('auth/recuperar.html', form=form)


@app.route('/restablecer/<token>', methods=['GET', 'POST'])
def restablecer(token):
    try:
        usuario_id = extensions.redis_client.get(f'recuperacion:{token}')
    except RedisError:
        usuario_id = None
    usuario = db.session.get(Usuario, UUID(usuario_id)) if usuario_id else None
    if not usuario:
        flash('El enlace no es válido o ya expiró.', 'error')
        return redirect(url_for('recuperar'))

    form = RestablecerForm()
    if form.validate_on_submit():
        usuario.set_password(form.password.data)
        registrar_evento(usuario.id, 'ACTUALIZACION', 'Usuario', usuario.id, 'Contraseña restablecida')
        db.session.commit()
        try:
            extensions.redis_client.delete(f'recuperacion:{token}')
        except RedisError:
            pass
        flash('Contraseña actualizada. Ya puedes iniciar sesión.', 'ok')
        return redirect(url_for('login'))
    return render_template('auth/restablecer.html', form=form)
