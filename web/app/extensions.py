from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import redis

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, inicie sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

redis_client = None
mongo_client = None


def init_redis(app):
    global redis_client
    redis_client = redis.Redis.from_url(app.config['REDIS_URL'], decode_responses=True)
    return redis_client
