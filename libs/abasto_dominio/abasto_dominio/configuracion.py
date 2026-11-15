"""
Configuración común leída de variables de entorno (ver .env.example).

Los secretos (contraseñas y llaves) se leen de archivos montados por Docker
en /run/secrets cuando existe la variable <NOMBRE>_FILE; así no viajan en el
.env ni aparecen en «docker inspect». En producción (ENTORNO=produccion) el
arranque falla si algún secreto falta o conserva un valor de ejemplo.
"""
import os
from datetime import timedelta
from urllib.parse import quote_plus

from abasto_dominio import registro_servicios as _registro

PRODUCCION = os.environ.get('ENTORNO', 'desarrollo') == 'produccion'
_INSEGUROS = ('change', 'example', 'ejemplo', 'dev-key', 'postgres', 'password')


def secreto(nombre, por_omision=None):
    """Valor de un secreto: archivo de <nombre>_FILE, si no la variable <nombre>, si no el valor por omisión."""
    archivo = os.environ.get(f'{nombre}_FILE')
    if archivo:
        with open(archivo, encoding='utf-8') as f:
            valor = f.read().strip()
    else:
        valor = os.environ.get(nombre, por_omision)
    if PRODUCCION and (not valor or len(valor) < 16 or any(p in valor.lower() for p in _INSEGUROS)):
        raise RuntimeError(f'{nombre}: falta o es un valor de ejemplo; genera los secretos con '
                           f'python scripts/preparar_entorno.py')
    return valor


def _postgres_uri():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    user = quote_plus(os.environ.get('POSTGRES_USER', 'postgres'))
    password = quote_plus(secreto('POSTGRES_PASSWORD', 'postgres'))
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    database = os.environ.get('POSTGRES_DB', 'abastored')
    return f'postgresql://{user}:{password}@{host}:{port}/{database}'


def _mongo_uri():
    if os.environ.get('MONGO_URI'):
        return os.environ['MONGO_URI']
    user = os.environ.get('MONGO_USER')
    password = secreto('MONGO_PASSWORD')
    host = os.environ.get('MONGO_HOST', 'localhost')
    port = os.environ.get('MONGO_PORT', '27017')
    database = os.environ.get('MONGO_DB', 'abastored')
    if user and password:
        return f'mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}?authSource=admin'
    return f'mongodb://{host}:{port}/{database}'


def _redis_url():
    if os.environ.get('REDIS_URL'):
        return os.environ['REDIS_URL']
    password = secreto('REDIS_PASSWORD')
    host = os.environ.get('REDIS_HOST', 'localhost')
    port = os.environ.get('REDIS_PORT', '6379')
    auth = f':{quote_plus(password)}@' if password else ''
    return f'redis://{auth}{host}:{port}/0'


class ConfiguracionBase:
    SECRET_KEY = secreto('SECRET_KEY', 'dev-key-change-in-prod')
    SQLALCHEMY_DATABASE_URI = _postgres_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    REDIS_URL = _redis_url()
    MONGO_URI = _mongo_uri()
    MONGO_DB = os.environ.get('MONGO_DB', 'abastored')

    # Mismo secreto en el web y en todos los servicios: un token sirve en cualquiera
    JWT_SECRET_KEY = secreto('JWT_SECRET_KEY', 'jwt-key-change-in-prod')

    # Detrás del gateway HTTPS: cookies sólo por HTTPS y sin acceso desde JavaScript
    SESSION_COOKIE_SECURE = os.environ.get('COOKIES_SEGURAS', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES_HOURS', '8')))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES_DAYS', '7')))

    PRECIO_PROMEDIO_TTL_SEGUNDOS = int(os.environ.get('PRECIO_PROMEDIO_TTL_SEGUNDOS', '14400'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_ARCHIVO_MB', '10')) * 1024 * 1024

    MS_TIMEOUT_SEGUNDOS = float(os.environ.get('MS_TIMEOUT_SEGUNDOS', '3'))


# Direcciones internas de los 24 microservicios (red de Docker): MS_<NOMBRE>_URL,
# con la variable de entorno del mismo nombre como sustituto (p. ej. para desarrollo).
for _nombre in _registro.NOMBRES:
    setattr(ConfiguracionBase, f'MS_{_nombre.upper()}_URL',
            os.environ.get(f'MS_{_nombre.upper()}_URL', _registro.url_interna(_nombre)))
