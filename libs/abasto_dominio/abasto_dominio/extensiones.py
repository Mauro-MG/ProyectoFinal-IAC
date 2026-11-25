"""
Conexiones compartidas: PostgreSQL (SQLAlchemy), Redis y MongoDB.

Redis y MongoDB se crean con tiempos de espera cortos: si no responden, cada
llamada falla rápido y el código que la usa decide cómo degradar.
"""
import time

import gridfs
import redis
from flask_sqlalchemy import SQLAlchemy
from pymongo import MongoClient

db = SQLAlchemy()
redis_client = None
mongo_client = None


class PoolConCorte(redis.ConnectionPool):
    """
    Pool de Redis con corte rápido: si no se puede conectar, durante ESPERA segundos las llamadas fallan al
    instante (ConnectionError) en vez de volver a intentar la conexión. Una petición hace varias operaciones
    de Redis (sesión, límite, contadores, bitácora): sin el corte, con Redis caído, cada una esperaba su propio
    tiempo de conexión y la cola de peticiones crecía hasta 20 s (tests/carga/recuperacion.sh). El
    comportamiento hacia el usuario no cambia: la sesión no se puede verificar y el servicio responde 503.
    """
    ESPERA = 2.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.abierto_hasta = 0.0

    def get_connection(self, command_name, *keys, **options):
        if time.monotonic() < self.abierto_hasta:
            raise redis.exceptions.ConnectionError('Redis no disponible (se reintentará en unos segundos)')
        try:
            return super().get_connection(command_name, *keys, **options)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
            self.abierto_hasta = time.monotonic() + self.ESPERA
            raise


def init_app(app):
    global redis_client, mongo_client
    db.init_app(app)
    redis_client = redis.Redis(connection_pool=PoolConCorte.from_url(
        app.config['REDIS_URL'], decode_responses=True, socket_connect_timeout=1, socket_timeout=1))
    mongo_client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=1500, tz_aware=True)


def mongo_db():
    from flask import current_app
    return mongo_client[current_app.config['MONGO_DB']]


def gridfs_archivos():
    return gridfs.GridFS(mongo_db(), collection='archivos')
