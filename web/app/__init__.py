"""
Sistema web de AbastoRed (monolito Flask).

La aplicación se crea una sola vez en este módulo. Cada archivo de app/rutas/
importa `app` y registra sus vistas con @app.route, agrupadas por proceso de
negocio (inventario, pedidos, análisis...). La lógica que no depende de HTTP
vive en app/servicios/ para poder reutilizarla después en los microservicios.
"""
import os
from uuid import UUID

from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient

from app import extensions
from app.config import DevelopmentConfig, ProductionConfig
from app.extensions import csrf, db, init_redis, login_manager

app = Flask(__name__)
app.config.from_object(ProductionConfig if os.environ.get('FLASK_ENV') == 'production' else DevelopmentConfig)

db.init_app(app)
csrf.init_app(app)
login_manager.init_app(app)
init_redis(app)
extensions.mongo_client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=1000)


@login_manager.user_loader
def cargar_usuario(user_id):
    from app.models import Usuario
    try:
        return db.session.get(Usuario, UUID(user_id))
    except ValueError:
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
    admin, analisis, api, auditoria, auth, catalogo, comercios, inventario,
    panel, pedidos, precios, proveedores, publico, reportes,
)
