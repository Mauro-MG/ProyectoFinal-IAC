import redis
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

# Se inicializan en app/__init__.py
redis_client = None
mongo_client = None


def init_redis(app):
    global redis_client
    redis_client = redis.Redis.from_url(
        app.config['REDIS_URL'],
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    return redis_client
