import os
from datetime import timedelta
from urllib.parse import quote_plus


def _build_postgres_uri():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']

    user = quote_plus(os.environ.get('POSTGRES_USER', 'postgres'))
    password = quote_plus(os.environ.get('POSTGRES_PASSWORD', 'postgres'))
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    database = os.environ.get('POSTGRES_DB', 'abastored')
    return f'postgresql://{user}:{password}@{host}:{port}/{database}'


def _build_mongo_uri():
    if os.environ.get('MONGO_URI'):
        return os.environ['MONGO_URI']

    user = os.environ.get('MONGO_USER')
    password = os.environ.get('MONGO_PASSWORD')
    host = os.environ.get('MONGO_HOST', 'localhost')
    port = os.environ.get('MONGO_PORT', '27017')
    database = os.environ.get('MONGO_DB', 'abastored')

    if user and password:
        return (
            f'mongodb://{quote_plus(user)}:{quote_plus(password)}@'
            f'{host}:{port}/{database}?authSource=admin'
        )
    return f'mongodb://{host}:{port}/{database}'


def _build_redis_url():
    if os.environ.get('REDIS_URL'):
        return os.environ['REDIS_URL']

    password = os.environ.get('REDIS_PASSWORD')
    host = os.environ.get('REDIS_HOST', 'localhost')
    port = os.environ.get('REDIS_PORT', '6379')
    auth = f':{quote_plus(password)}@' if password else ''
    return f'redis://{auth}{host}:{port}/0'

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-prod')
    SQLALCHEMY_DATABASE_URI = _build_postgres_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = _build_redis_url()
    MONGO_URI = _build_mongo_uri()
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-key-change-in-prod')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES_HOURS', '8')))
    PRECIO_PROMEDIO_TTL_SEGUNDOS = int(os.environ.get('PRECIO_PROMEDIO_TTL_SEGUNDOS', '14400'))

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
