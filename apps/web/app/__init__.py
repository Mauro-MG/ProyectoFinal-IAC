"""
Sistema web de AbastoRed (monolito Flask).

La aplicación se crea una sola vez en este módulo. Cada archivo de app/rutas/
importa `app` y registra sus vistas con @app.route, agrupadas por proceso de
negocio (inventario, pedidos, análisis...). La lógica que no depende de HTTP
vive en la biblioteca compartida libs/abasto_dominio, la misma que usan los
microservicios.
"""
import os
from uuid import UUID

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, logout_user

from abasto_dominio import extensiones, sesiones
from app.config import DevelopmentConfig, ProductionConfig
from app.extensions import csrf, db, login_manager

app = Flask(__name__)
app.config.from_object(ProductionConfig if os.environ.get('FLASK_ENV') == 'production' else DevelopmentConfig)

extensiones.init_app(app)
csrf.init_app(app)
login_manager.init_app(app)


@login_manager.user_loader
def cargar_usuario(user_id):
    from abasto_dominio.modelos import Usuario
    try:
        return db.session.get(Usuario, UUID(user_id))
    except ValueError:
        return None


@app.before_request
def verificar_sesion_en_redis():
    """
    Mecanismo común de sesión: si el JWT de esta sesión se revocó (cierre de
    sesión desde la API, el administrador cerró las sesiones del usuario, etc.),
    también se cierra la sesión del navegador. Si Redis no responde, el web
    sigue funcionando con la sesión de Flask.
    """
    if request.endpoint in (None, 'static', 'health') or not current_user.is_authenticated:
        return None
    jti = session.get('jwt_jti')
    if jti and sesiones.sesion_activa(jti) is False:
        logout_user()
        session.clear()
        flash('Tu sesión se cerró (desde otro dispositivo o por el administrador). Inicia sesión de nuevo.', 'alerta')
        return redirect(url_for('login'))
    return None


@app.route('/health')
def health():
    return jsonify(status='ok', service='abastored-web'), 200


@app.errorhandler(403)
def error_403(error):
    return render_template('errores/403.html'), 403


@app.errorhandler(404)
def error_404(error):
    if request.path.startswith('/api/'):
        return jsonify(error='Recurso no encontrado'), 404
    return render_template('errores/404.html'), 404


@app.errorhandler(500)
def error_500(error):
    db.session.rollback()
    return render_template('errores/500.html'), 500


# Filtros de plantilla y variables globales
from app import plantillas  # noqa: E402,F401

# Vistas del sistema web
from app.rutas import (  # noqa: E402,F401
    admin, analisis, api, archivos, auditoria, auth, catalogo, comercios, inventario, monitoreo,
    notificaciones, panel, pedidos, precios, proveedores, publico, reportes,
)
