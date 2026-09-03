import os
from uuid import UUID
from flask import Flask, jsonify, render_template
from app.config import DevelopmentConfig, ProductionConfig
from app.extensions import db, init_redis, login_manager

def create_app(config_class=DevelopmentConfig):
    app = Flask(__name__)
    
    if os.environ.get('FLASK_ENV') == 'production':
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    init_redis(app)
    
    # Initialize Mongo
    from pymongo import MongoClient
    from app import extensions
    app.mongo_client = MongoClient(app.config['MONGO_URI'])
    extensions.mongo_client = app.mongo_client

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.usuario import Usuario
        try:
            return db.session.get(Usuario, UUID(user_id))
        except ValueError:
            return None

    # Register Blueprints
    from app.blueprints.public.routes import public_bp
    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.dashboard.routes import dashboard_bp
    from app.blueprints.comercios.routes import comercios_bp
    from app.blueprints.productos.routes import productos_bp
    from app.blueprints.precios.routes import precios_bp
    from app.blueprints.auditoria.routes import auditoria_bp
    from app.blueprints.api.routes import api_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(comercios_bp, url_prefix='/comercios')
    app.register_blueprint(productos_bp, url_prefix='/productos')
    app.register_blueprint(precios_bp, url_prefix='/precios')
    app.register_blueprint(auditoria_bp, url_prefix='/auditoria')
    app.register_blueprint(api_bp, url_prefix='/api')

    @app.route('/health')
    def health():
        return jsonify(status='ok', service='abastored-web'), 200

    # Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    # Context processors
    @app.context_processor
    def inject_user():
        from flask_login import current_user
        return dict(current_user=current_user)

    return app
