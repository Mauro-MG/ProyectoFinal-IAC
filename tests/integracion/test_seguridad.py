"""
Mecanismo común de autenticación: el mismo JWT y la misma sesión en Redis valen
(o dejan de valer) en todos los servicios al mismo tiempo.
"""
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
import requests

from apoyo import HOST, MODO, PUERTOS, SESIONES, Api, base, iniciar_sesion, url

SERVICIOS_PROTEGIDOS = [
    ('seguridad', '/auth/sesion'), ('comercios', '/comercios'), ('inventario', '/comercios/00000000-0000-0000-0000-000000000000/inventario'),
    ('precios', '/precios'), ('pedidos', '/pedidos'), ('analisis', '/analisis/zonas'), ('notificaciones', '/notificaciones'),
    ('proveedores', '/mi-catalogo'),
]


@pytest.mark.parametrize('servicio, ruta', SERVICIOS_PROTEGIDOS)
def test_sin_token_401_en_todos(servicio, ruta):
    r = requests.get(url(servicio, ruta), timeout=10)
    assert r.status_code == 401
    assert r.json()['error']['status'] == 401


def test_token_basura_401():
    r = requests.get(url('pedidos', '/pedidos'), headers={'Authorization': 'Bearer esto.no.sirve'}, timeout=10)
    assert r.status_code == 401
    assert r.json()['error']['codigo'] == 'token_invalido'


def test_token_firmado_por_otro_401():
    falso = jwt.encode({'sub': str(uuid4()), 'jti': uuid4().hex, 'tipo': 'acceso', 'rol': 'Administrador General',
                        'permisos': ['pedidos.ver_todos'], 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
                       'un-secreto-inventado-por-un-atacante-123', algorithm='HS256')
    r = requests.get(url('pedidos', '/pedidos'), headers={'Authorization': f'Bearer {falso}'}, timeout=10)
    assert r.status_code == 401


def test_token_expirado_401(secreto_jwt):
    ahora = datetime.now(timezone.utc)
    vencido = jwt.encode({'sub': str(uuid4()), 'jti': uuid4().hex, 'tipo': 'acceso', 'rol': 'x', 'permisos': [],
                          'iat': ahora - timedelta(hours=9), 'exp': ahora - timedelta(minutes=1)},
                         secreto_jwt, algorithm='HS256')
    r = requests.get(url('analisis', '/analisis/zonas'), headers={'Authorization': f'Bearer {vencido}'}, timeout=10)
    assert r.status_code == 401
    assert r.json()['error']['codigo'] == 'token_expirado'


def test_token_bien_firmado_sin_sesion_en_redis_401(secreto_jwt):
    """Aunque la firma sea correcta, sin sesión registrada en Redis el token no sirve."""
    sin_sesion = jwt.encode({'sub': str(uuid4()), 'jti': uuid4().hex, 'tipo': 'acceso', 'rol': 'x', 'permisos': [],
                             'exp': datetime.now(timezone.utc) + timedelta(hours=1)}, secreto_jwt, algorithm='HS256')
    r = requests.get(url('pedidos', '/pedidos'), headers={'Authorization': f'Bearer {sin_sesion}'}, timeout=10)
    assert r.status_code == 401
    assert r.json()['error']['codigo'] == 'sesion_inactiva'


def test_logout_revoca_el_token_en_todos_los_servicios():
    sesion = Api('coordinador')
    refresh = sesion.tokens['refresh_token']
    assert sesion.get('analisis', '/analisis/zonas').status_code == 200
    assert sesion.get('comercios', '/comercios').status_code == 200

    assert sesion.post('seguridad', '/auth/logout').status_code == 200

    for servicio, ruta in (('analisis', '/analisis/zonas'), ('comercios', '/comercios'), ('precios', '/precios')):
        r = sesion.get(servicio, ruta)
        assert r.status_code == 401, servicio
        assert r.json()['error']['codigo'] == 'token_revocado'
    # Tampoco se puede usar el refresh de esa sesión para obtener otro token
    r = requests.post(url('seguridad', '/auth/renovar'), json={'refresh_token': refresh}, timeout=10)
    assert r.status_code == 401


def test_refresh_rota_y_el_anterior_deja_de_servir():
    tokens = iniciar_sesion('auditor')
    r = requests.post(url('seguridad', '/auth/renovar'), json={'refresh_token': tokens['refresh_token']}, timeout=10)
    assert r.status_code == 200
    nuevos = r.json()
    # El refresh ya usado no se puede reutilizar y el acceso anterior quedó revocado
    r = requests.post(url('seguridad', '/auth/renovar'), json={'refresh_token': tokens['refresh_token']}, timeout=10)
    assert r.status_code == 401
    viejo = requests.get(url('pedidos', '/pedidos'), headers={'Authorization': f"Bearer {tokens['access_token']}"}, timeout=10)
    assert viejo.status_code == 401
    nuevo = requests.get(url('pedidos', '/pedidos'), headers={'Authorization': f"Bearer {nuevos['access_token']}"}, timeout=10)
    assert nuevo.status_code == 200


def test_credenciales_incorrectas_401():
    r = requests.post(url('seguridad', '/auth/login'),
                      json={'email': f'nadie.{uuid4().hex[:6]}@test.mx', 'password': 'NoEsLaClave1'}, timeout=10)
    assert r.status_code in (401, 429)  # 429 si ya se agotó el límite de intentos por minuto


def test_rol_sin_permiso_403(api):
    r = api('analista').post('pedidos', '/pedidos', json={'comercio_id': str(uuid4()), 'proveedor_id': str(uuid4()),
                                                           'partidas': [{'producto_id': 1, 'cantidad': 1}]})
    assert r.status_code == 403


def test_recurso_de_otro_usuario_403(api):
    comercio_ajeno = api('minorista').get('comercios', '/comercios').json()['items'][0]['id']
    r = api('comerciante').get('comercios', f'/comercios/{comercio_ajeno}')
    assert r.status_code == 403


def test_administrador_cierra_las_sesiones_de_un_usuario(api):
    victima = Api('operador')
    assert victima.get('pedidos', '/pedidos').status_code == 200
    usuario_id = victima.get('seguridad', '/auth/sesion').json()['usuario_id']

    r = api('admin').delete('seguridad', f'/usuarios/{usuario_id}/sesiones')
    assert r.status_code == 200
    assert r.json()['sesiones_cerradas'] >= 1
    assert victima.get('pedidos', '/pedidos').status_code == 401
    SESIONES.pop('operador', None)  # la sesión compartida del operador también se cerró


def test_limite_de_peticiones_429():
    """120 peticiones por minuto por usuario y servicio (RATE_LIMIT_POR_MINUTO); lo aplica el microservicio."""
    sesion = Api('auditor')
    codigos = []
    for _ in range(130):
        r = sesion.get('notificaciones', '/notificaciones/contador')
        codigos.append(r.status_code)
        if r.status_code == 429:
            break
        time.sleep(0.05)  # por debajo del límite por IP del gateway (30/s): así se prueba el del servicio
    assert 429 in codigos
    assert 'X-Limitado-Por' not in r.headers, 'lo frenó el gateway, no el servicio'
    assert r.json()['error']['codigo'] == 'limite_excedido'
    assert int(r.headers['Retry-After']) > 0
    # Los demás servicios no se ven afectados: el límite es por servicio
    assert sesion.get('pedidos', '/pedidos', params={'por_pagina': 1}).status_code == 200


def test_gateway_limita_rafagas_por_ip():
    """El gateway corta ráfagas de una misma IP (30/s, 60 de margen) con el mismo formato de error JSON."""
    if MODO != 'gateway':
        pytest.skip('No aplica: sólo existe al entrar por el gateway')
    from concurrent.futures import ThreadPoolExecutor
    # /health/live no lo limitan los servicios: si aparece un 429, sólo pudo ponerlo el gateway
    with ThreadPoolExecutor(max_workers=25) as grupo:
        respuestas = list(grupo.map(lambda _: requests.get(f"{base('catalogo')}/health/live", timeout=10), range(200)))
    limitadas = [r for r in respuestas if r.status_code == 429]
    assert limitadas, 'el gateway dejó pasar 200 peticiones simultáneas'
    assert limitadas[0].headers.get('X-Limitado-Por') == 'gateway'
    assert limitadas[0].json()['error']['codigo'] == 'limite_excedido'
    assert any(r.status_code == 200 for r in respuestas)  # el margen inicial sí pasa
    time.sleep(3)  # deja recuperar el margen antes de las siguientes pruebas


def test_solo_el_gateway_esta_expuesto(docker):
    """Sólo el gateway publica puertos; las bases, el web y los servicios quedan dentro de las redes de Docker."""
    if MODO != 'gateway':
        pytest.skip('No aplica: en modo directo/interno los puertos se abren a propósito')
    salida = docker('ps', '--filter', 'name=abastored-', '--filter', 'name=ms-', '--format', '{{.Names}}|{{.Ports}}').stdout
    publicados = {nombre: puertos for nombre, puertos in (linea.split('|', 1) for linea in salida.splitlines())
                  if '->' in puertos}
    assert set(publicados) == {'abastored-gateway'}, publicados
    assert '0.0.0.0:443->443' in publicados['abastored-gateway']
    # La red de datos es interna (sin acceso desde el anfitrión ni salida a internet)
    # (el nombre de la red lleva el del proyecto de Compose, que depende de la carpeta donde se clonó)
    red = docker('inspect', '--format', '{{range $nombre, $_ := .NetworkSettings.Networks}}{{$nombre}} {{end}}',
                 'abastored-postgres').stdout.split()
    assert len(red) == 1 and red[0].endswith('_datos'), red
    assert docker('network', 'inspect', '--format', '{{.Internal}}', red[0]).stdout.strip() == 'true'
    # HTTP sólo redirige a HTTPS
    r = requests.get(HOST.replace('https://', 'http://') + '/', allow_redirects=False, timeout=10)
    assert r.status_code == 301 and r.headers['Location'].startswith('https://')


def test_health_es_publico_y_reporta_dependencias():
    for servicio in PUERTOS:
        r = requests.get(f'{base(servicio)}/health', timeout=10)
        assert r.status_code == 200, servicio
        datos = r.json()
        assert datos['estado'] == 'ok'
        assert {d['nombre'] for d in datos['dependencias']} >= {'redis'}
