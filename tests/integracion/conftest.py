"""
Pruebas de integración: se ejecutan contra el sistema levantado con
`docker compose up -d` (los ocho servicios, el web y las tres bases de datos).

    pytest tests/integracion -v

Las URL salen de variables de entorno (PRUEBAS_HOST, por omisión
http://localhost con los puertos que publica docker-compose). Si ms-seguridad no
responde, todo se omite.
"""
import os
import re
import shutil
import subprocess

import pytest
import requests

from apoyo import RAIZ, base, sesion_de


def pytest_collection_modifyitems(config, items):
    try:
        requests.get(f'{base("seguridad")}/health/live', timeout=3)
    except requests.RequestException:
        omitir = pytest.mark.skip(reason='El sistema no está levantado (docker compose up -d).')
        for item in items:
            if 'integracion' in str(item.fspath):
                item.add_marker(omitir)


@pytest.fixture(scope='session')
def api():
    """api('comerciante') -> cliente con sesión reutilizada durante toda la corrida."""
    return sesion_de


@pytest.fixture(scope='session')
def secreto_jwt():
    """Para fabricar un token con la firma correcta. Sale del entorno o del .env local."""
    if os.environ.get('JWT_SECRET_KEY'):
        return os.environ['JWT_SECRET_KEY']
    env = RAIZ / '.env'
    if env.exists():
        m = re.search(r'^JWT_SECRET_KEY=(.+)$', env.read_text(encoding='utf-8'), re.M)
        if m:
            return m.group(1).strip()
    pytest.skip('Sin JWT_SECRET_KEY para fabricar el token.')


@pytest.fixture(scope='session')
def docker():
    """Para las pruebas de resiliencia (detener y arrancar contenedores)."""
    if not shutil.which('docker'):
        pytest.skip('Docker CLI no disponible.')

    def ejecutar(*args):
        return subprocess.run(['docker', *args], capture_output=True, text=True, timeout=120)
    return ejecutar
