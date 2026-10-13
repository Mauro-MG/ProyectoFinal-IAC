"""
Conexiones compartidas: PostgreSQL (SQLAlchemy), Redis y MongoDB.

Redis y MongoDB se crean con tiempos de espera cortos: si no responden, cada
llamada falla rápido y el código que la usa decide cómo degradar.
"""
import gridfs
import redis
from flask_sqlalchemy import SQLAlchemy
from pymongo import MongoClient

db = SQLAlchemy()
redis_client = None
mongo_client = None


def init_app(app):
    global redis_client, mongo_client
    db.init_app(app)
    redis_client = redis.Redis.from_url(app.config['REDIS_URL'], decode_responses=True,
                                        socket_connect_timeout=1, socket_timeout=1)
    mongo_client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=1500, tz_aware=True)


def mongo_db():
    from flask import current_app
    return mongo_client[current_app.config['MONGO_DB']]


def gridfs_archivos():
    return gridfs.GridFS(mongo_db(), collection='archivos')
