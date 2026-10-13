"""Utilidades compartidas por las pruebas de integración (URL, usuarios, cliente con token)."""
import os
import time
from pathlib import Path

import requests

HOST = os.environ.get('PRUEBAS_HOST', 'http://localhost')
PUERTOS = {'seguridad': 8101, 'comercios': 8102, 'catalogo': 8103, 'inventario': 8104,
           'precios': 8105, 'pedidos': 8106, 'analisis': 8107, 'notificaciones': 8108}
WEB = os.environ.get('PRUEBAS_WEB', f'{HOST}:5000')
RAIZ = Path(__file__).resolve().parents[2]
NS = 'https://abastored.mx/esquemas/v1'

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
    return f'{HOST}:{PUERTOS[servicio]}'


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
