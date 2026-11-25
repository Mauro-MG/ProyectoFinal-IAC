"""
Pruebas de integración: se ejecutan contra el sistema levantado con
`docker compose up -d`, entrando por el gateway HTTPS como un cliente real.

    python scripts/ejecutar_pruebas.py       (recomendado: instala dependencias y genera el reporte)
    pytest tests/integracion -v

Clasificación de las pruebas que no se ejecutan (aparece en el reporte):
    «Omitida: …»    faltó algo del ambiente (p. ej. el sistema no está levantado)
    «No aplica: …»  la prueba no tiene sentido en ese ambiente (p. ej. sin Docker CLI)
"""
import os
import shutil
import subprocess

import pytest
import requests

from apoyo import LOCAL, MODO, RAIZ, base, sesion_de


def pytest_collection_modifyitems(config, items):
    try:
        requests.get(f'{base("seguridad")}/health/live', timeout=5).raise_for_status()
    except requests.RequestException as error:
        omitir = pytest.mark.skip(reason=f'Omitida: el sistema no responde en {base("seguridad")} '
                                         f'({error.__class__.__name__}); levántalo con docker compose up -d')
        for item in items:
            if 'integracion' in str(item.fspath):
                item.add_marker(omitir)


@pytest.fixture(scope='session')
def api():
    """api('comerciante') -> cliente con sesión reutilizada durante toda la corrida."""
    return sesion_de


@pytest.fixture(scope='session')
def secreto_jwt():
    """Para fabricar un token con la firma correcta (expirado o sin sesión): se lee del secreto local."""
    if os.environ.get('JWT_SECRET_KEY'):
        return os.environ['JWT_SECRET_KEY']
    if not LOCAL:
        pytest.skip('No aplica: el sistema es remoto y su secreto JWT no está en este equipo (pásalo en '
                    'JWT_SECRET_KEY para correrlas)')
    for archivo in (RAIZ / 'secrets' / 'jwt_secret_key.txt', '/run/secrets/jwt_secret_key'):
        try:
            with open(archivo, encoding='utf-8') as f:
                return f.read().strip()
        except OSError:
            continue
    pytest.skip('Omitida: no se encontró secrets/jwt_secret_key.txt (corre scripts/preparar_entorno.py)')


@pytest.fixture(scope='session')
def docker():
    """Para las pruebas de resiliencia (detener y arrancar contenedores)."""
    if MODO == 'interno' or not shutil.which('docker'):
        pytest.skip('No aplica: requiere el CLI de Docker en el equipo anfitrión para detener contenedores')
    if not LOCAL:
        pytest.skip('No aplica: el sistema probado es remoto; no se detienen contenedores de producción')

    def ejecutar(*args):
        return subprocess.run(['docker', *args], capture_output=True, text=True, timeout=120)
    return ejecutar
