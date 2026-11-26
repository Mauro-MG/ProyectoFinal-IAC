"""
Utilidades compartidas por las pruebas de integración (URL, usuarios, cliente con token).

Las pruebas llegan al sistema como lo haría un cliente real: por el gateway HTTPS
(https://localhost/ms/<servicio>/...), verificando su certificado. Variables:
    PRUEBAS_MODO   gateway (por omisión) · directo (puertos 81xx de docker-compose.dev.yml)
                   · interno (desde un contenedor de la red: http://ms-<servicio>:8000)
    PRUEBAS_HOST   dirección del gateway (por omisión https://localhost)
"""
import os
import time
from pathlib import Path

import requests

from abasto_dominio import registro_servicios

RAIZ = Path(__file__).resolve().parents[2]
NS = 'https://abastored.mx/esquemas/v1'
# Puertos internos de desarrollo (docker-compose.dev.yml); en modo gateway sólo se usa el nombre
PUERTOS = {nombre: puerto for nombre, (puerto, _) in registro_servicios.SERVICIOS.items()}
MODO = os.environ.get('PRUEBAS_MODO', 'gateway')
HOST = os.environ.get('PRUEBAS_HOST', 'https://localhost')
# Sistema en este equipo (Docker local) o remoto (p. ej. la VM de Google Cloud). Con uno remoto, las pruebas que
# detienen contenedores o consultan la base con `docker exec` no aplican: actuarían sobre el Docker local.
LOCAL = MODO != 'gateway' or HOST.split('://')[-1].split(':')[0].split('/')[0] in ('localhost', '127.0.0.1')
WEB = {'gateway': HOST, 'directo': 'http://localhost:5000', 'interno': 'http://abastored-web:5000'}[MODO]

# El gateway usa un certificado autofirmado: se confía en él explícitamente (no se desactiva la verificación)
_CERTIFICADO = RAIZ / 'infra' / 'certs' / 'abastored.crt'
if os.environ.get('PRUEBAS_CA'):
    _CERTIFICADO = Path(os.environ['PRUEBAS_CA'])     # certificado del gateway remoto (público)
if MODO == 'gateway' and _CERTIFICADO.exists() and 'REQUESTS_CA_BUNDLE' not in os.environ:
    # Autoridades públicas (certifi) + el certificado del gateway: así también se verifican las descargas
    # directas del bucket real (storage.googleapis.com) con las URL firmadas
    import certifi
    import tempfile
    _paquete = Path(tempfile.gettempdir()) / 'abastored_pruebas_ca.pem'
    _paquete.write_text(Path(certifi.where()).read_text(encoding='utf-8') + '\n'
                        + _CERTIFICADO.read_text(encoding='utf-8'), encoding='utf-8')
    os.environ['REQUESTS_CA_BUNDLE'] = str(_paquete)

USUARIOS = {
    'admin': ('admin@abastored.mx', 'Admin123!'),
    'comerciante': ('comerciante@test.mx', 'Password123!'),
    'minorista': ('minorista@test.mx', 'Password123!'),
    'proveedor': ('proveedor3@test.mx', 'Password123!'),
    'dueno_regia': ('proveedor@test.mx', 'Password123!'),   # dueño de la Distribuidora Regia
    'operador': ('operador@test.mx', 'Password123!'),       # empleado de la Distribuidora Regia
    'analista': ('analista@test.mx', 'Password123!'),
    'coordinador': ('coordinador@test.mx', 'Password123!'),
    'auditor': ('auditor@test.mx', 'Password123!'),
}

# Sesiones reutilizadas durante la corrida (el login está limitado a 10 por minuto)
SESIONES = {}


def base(servicio):
    if MODO == 'directo':
        return f'http://localhost:{PUERTOS[servicio]}'
    if MODO == 'interno':
        return f'http://ms-{servicio}:8000'
    return f'{HOST}/ms/{servicio}'


def url(servicio, ruta):
    return f'{base(servicio)}/api/v1{ruta}'


def iniciar_sesion(rol):
    """Login en ms-seguridad. Si se agotó el límite por minuto, espera lo que indique Retry-After."""
    email, clave = USUARIOS[rol]
    for _ in range(3):
        r = requests.post(url('seguridad', '/auth/login'), json={'email': email, 'password': clave}, timeout=10)
        if r.status_code != 429:
            break
        time.sleep(int(r.headers.get('Retry-After', 30)) + 1)
    assert r.status_code == 200, f'login de {rol}: {r.status_code} {r.text[:200]}'
    return r.json()


class Api:
    """Cliente con el token de un rol: Api('minorista').get('pedidos', '/pedidos', params=...)."""

    def __init__(self, rol, tokens=None):
        self.rol = rol
        self.tokens = tokens or iniciar_sesion(rol)
        self.sesion = requests.Session()
        self.sesion.headers['Authorization'] = f"Bearer {self.tokens['access_token']}"

    def __getattr__(self, metodo):
        if metodo not in ('get', 'post', 'put', 'patch', 'delete'):
            raise AttributeError(metodo)

        def llamar(servicio, ruta, **kw):
            kw.setdefault('timeout', 20)
            return self.sesion.request(metodo.upper(), url(servicio, ruta), **kw)
        return llamar


def sesion_de(rol):
    if rol not in SESIONES:
        SESIONES[rol] = Api(rol)
    return SESIONES[rol]


def esperar_salud(servicio, segundos=60):
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            if requests.get(f'{base(servicio)}/health/live', timeout=2).ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False
