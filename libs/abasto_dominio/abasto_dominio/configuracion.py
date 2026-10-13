"""Configuración común leída de variables de entorno (ver .env.example)."""
import os
from datetime import timedelta
from urllib.parse import quote_plus


def _postgres_uri():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    user = quote_plus(os.environ.get('POSTGRES_USER', 'postgres'))
    password = quote_plus(os.environ.get('POSTGRES_PASSWORD', 'postgres'))
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    database = os.environ.get('POSTGRES_DB', 'abastored')
    return f'postgresql://{user}:{password}@{host}:{port}/{database}'


def _mongo_uri():
    if os.environ.get('MONGO_URI'):
        return os.environ['MONGO_URI']
    user = os.environ.get('MONGO_USER')
    password = os.environ.get('MONGO_PASSWORD')
    host = os.environ.get('MONGO_HOST', 'localhost')
    port = os.environ.get('MONGO_PORT', '27017')
    database = os.environ.get('MONGO_DB', 'abastored')
    if user and password:
        return f'mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}?authSource=admin'
    return f'mongodb://{host}:{port}/{database}'


def _redis_url():
    if os.environ.get('REDIS_URL'):
        return os.environ['REDIS_URL']
    password = os.environ.get('REDIS_PASSWORD')
    host = os.environ.get('REDIS_HOST', 'localhost')
    port = os.environ.get('REDIS_PORT', '6379')
    auth = f':{quote_plus(password)}@' if password else ''
    return f'redis://{auth}{host}:{port}/0'


class ConfiguracionBase:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-prod')
    SQLALCHEMY_DATABASE_URI = _postgres_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    REDIS_URL = _redis_url()
    MONGO_URI = _mongo_uri()
    MONGO_DB = os.environ.get('MONGO_DB', 'abastored')

    # Mismo secreto en el web y en todos los servicios: un token sirve en cualquiera
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-key-change-in-prod')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES_HOURS', '8')))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES_DAYS', '7')))

    PRECIO_PROMEDIO_TTL_SEGUNDOS = int(os.environ.get('PRECIO_PROMEDIO_TTL_SEGUNDOS', '14400'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_ARCHIVO_MB', '10')) * 1024 * 1024

    # Direcciones internas de los microservicios (red de Docker)
    MS_SEGURIDAD_URL = os.environ.get('MS_SEGURIDAD_URL', 'http://ms-seguridad:8000')
    MS_COMERCIOS_URL = os.environ.get('MS_COMERCIOS_URL', 'http://ms-comercios:8000')
    MS_CATALOGO_URL = os.environ.get('MS_CATALOGO_URL', 'http://ms-catalogo:8000')
    MS_INVENTARIO_URL = os.environ.get('MS_INVENTARIO_URL', 'http://ms-inventario:8000')
    MS_PRECIOS_URL = os.environ.get('MS_PRECIOS_URL', 'http://ms-precios:8000')
    MS_PEDIDOS_URL = os.environ.get('MS_PEDIDOS_URL', 'http://ms-pedidos:8000')
    MS_ANALISIS_URL = os.environ.get('MS_ANALISIS_URL', 'http://ms-analisis:8000')
    MS_NOTIFICACIONES_URL = os.environ.get('MS_NOTIFICACIONES_URL', 'http://ms-notificaciones:8000')
    MS_TIMEOUT_SEGUNDOS = float(os.environ.get('MS_TIMEOUT_SEGUNDOS', '3'))
