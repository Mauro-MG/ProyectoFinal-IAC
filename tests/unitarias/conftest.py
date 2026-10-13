"""
Pruebas unitarias: no necesitan Docker. Redis se reemplaza por fakeredis (en
memoria) y MongoDB se simula caído, así se prueba la lógica de las
bibliotecas compartidas sin bases de datos reales.
"""
import fakeredis
import pytest
from flask import Flask
from pymongo.errors import ServerSelectionTimeoutError

from abasto_dominio import extensiones
from abasto_dominio.configuracion import ConfiguracionBase


@pytest.fixture
def redis_falso(monkeypatch):
    cliente = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(extensiones, 'redis_client', cliente)
    return cliente


@pytest.fixture
def sin_mongo(monkeypatch):
    def caido():
        raise ServerSelectionTimeoutError('MongoDB no disponible en pruebas unitarias')
    monkeypatch.setattr(extensiones, 'mongo_db', caido)


@pytest.fixture
def app_flask():
    """Contexto de Flask con la configuración común (secreto JWT, vigencias)."""
    app = Flask('pruebas')
    app.config.from_object(ConfiguracionBase)
    app.config['JWT_SECRET_KEY'] = 'secreto-de-pruebas-unitarias-con-32-bytes'
    with app.app_context():
        yield app
