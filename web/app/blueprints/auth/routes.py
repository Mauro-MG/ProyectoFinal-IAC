import jwt
from datetime import datetime, timedelta
from hashlib import sha256
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from redis.exceptions import RedisError
from app.extensions import db, redis_client
from app.models.usuario import Usuario
from app.models.rol import Rol
from app.blueprints.auth.forms import LoginForm, RegistroForm, RecuperarForm
from app.utils.audit import registrar_evento

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.panel'))
    
    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(email=form.email.data, activo=True).first()
        if usuario and usuario.check_password(form.password.data):
            login_user(usuario)
            usuario.ultimo_acceso = datetime.utcnow()
            db.session.commit()
            
            # Generate JWT
            token = jwt.encode({
                'user_id': str(usuario.id),
                'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
            }, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')
            session['jwt_token'] = token
            
            registrar_evento(usuario.id, 'LOGIN', 'Usuario', usuario.id, 'Inicio de sesión exitoso')
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard.panel'))
        else:
            flash('Correo electrónico o contraseña incorrectos', 'danger')
            
    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    user_id = current_user.id
    token = session.get('jwt_token')
    if token:
        token_hash = sha256(token.encode('utf-8')).hexdigest()
        try:
            redis_client.setex(
                f"jwt:blacklist:{token_hash}",
                int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds()),
                "true",
            )
        except RedisError:
            current_app.logger.warning('No se pudo registrar el JWT revocado en Redis.')
        session.pop('jwt_token', None)
    
    logout_user()
    registrar_evento(user_id, 'LOGOUT', 'Usuario', user_id, 'Cierre de sesión')
    flash('Has cerrado sesión exitosamente', 'success')
    return redirect(url_for('public.index'))

@auth_bp.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.panel'))
    
    form = RegistroForm()
    if form.validate_on_submit():
        if Usuario.query.filter_by(email=form.email.data).first():
            flash('El correo electrónico ya está registrado', 'danger')
            return render_template('auth/registro.html', form=form)
            
        rol_comerciante = Rol.query.filter_by(nombre='Comerciante Informal').first()
        if not rol_comerciante:
            flash('Error de configuración del sistema: Rol no encontrado', 'danger')
            return redirect(url_for('public.index'))
            
        usuario = Usuario(
            email=form.email.data,
            nombre=form.nombre.data,
            apellido_paterno=form.apellido_paterno.data,
            rol_id=rol_comerciante.id
        )
        usuario.set_password(form.password.data)
        
        db.session.add(usuario)
        db.session.commit()
        
        registrar_evento(usuario.id, 'CREACION', 'Usuario', usuario.id, 'Registro de nuevo usuario')
        
        flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/registro.html', form=form)

@auth_bp.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    form = RecuperarForm()
    if form.validate_on_submit():
        flash('Si el correo existe en nuestro sistema, recibirás instrucciones para recuperar tu contraseña', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/recuperar.html', form=form)
