"""Configuración y utilidades compartidas por los scripts de carga contra el despliegue (HTTPS + gateway)."""
import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
HOST = os.environ.get('ABASTO_HOST', 'https://localhost').rstrip('/')
# Certificado PÚBLICO del gateway desplegado (no la llave). Se usa como autoridad de confianza: la verificación
# TLS sigue activa y falla si el servidor presenta otro certificado.
CA = os.environ.get('ABASTO_CA', str(RAIZ / 'apps' / 'infra' / 'gcp' / 'certificado_gateway_gcp.crt'))
PRIVADO = RAIZ / 'tests' / 'carga' / 'resultados' / 'gcp' / 'privado'     # tokens: fuera de git


def ruta(servicio, camino):
    """Ruta pública del microservicio a través del gateway: /ms/<servicio>/api/v1<camino>."""
    return f'/ms/{servicio}/api/v1{camino}'


def url(servicio, camino):
    return HOST + ruta(servicio, camino)


def archivo_sesiones(prefijo):
    return PRIVADO / f'sesiones_{prefijo}.json'


def leer_sesiones(prefijo):
    return json.loads(archivo_sesiones(prefijo).read_text(encoding='utf-8'))


def clasificar(status, encabezados=None, excepcion=None):
    """Categoría de una respuesta para separar éxitos, límites, reglas de negocio y fallas reales."""
    if not status:
        nombre = f'{type(excepcion).__name__} {excepcion}'.lower()
        return 'timeout' if 'timeout' in nombre else 'conexion'
    encabezados = encabezados or {}
    if status < 400:
        return 'ok'
    if status == 429:
        if encabezados.get('X-Limitado-Por') == 'gateway':
            return '429_gateway'
        return '429_servicio' if 'X-RateLimit-Limit' in encabezados else '429_otro'
    if status == 409:
        return '409_negocio'
    if status in (401, 403):
        return '401_403'
    if status >= 500:
        return '5xx'
    return '4xx_otro'


CATEGORIAS = ('ok', '429_gateway', '429_servicio', '429_otro', '409_negocio', '401_403', '4xx_otro', '5xx',
              'timeout', 'conexion', 'falla_contrato')
