"""
Mecanismo común de autenticación: el mismo JWT y la misma sesión en Redis valen
(o dejan de valer) en todos los servicios al mismo tiempo.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
import requests

from apoyo import PUERTOS, SESIONES, Api, base, iniciar_sesion, url

SERVICIOS_PROTEGIDOS = [
    ('seguridad', '/auth/sesion'), ('comercios', '/comercios'), ('inventario', '/comercios/00000000-0000-0000-0000-000000000000/inventario'),
    ('precios', '/precios'), ('pedidos', '/pedidos'), ('analisis', '/analisis/zonas'), ('notificaciones', '/notificaciones'),
    ('catalogo', '/mi-catalogo'),
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
    """120 peticiones por minuto por usuario y servicio (RATE_LIMIT_POR_MINUTO)."""
    sesion = Api('auditor')
    codigos = []
    for _ in range(130):
        r = sesion.get('notificaciones', '/notificaciones/contador')
        codigos.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codigos
    assert r.json()['error']['codigo'] == 'limite_excedido'
    assert int(r.headers['Retry-After']) > 0
    # Los demás servicios no se ven afectados: el límite es por servicio
    assert sesion.get('pedidos', '/pedidos', params={'por_pagina': 1}).status_code == 200


def test_health_es_publico_y_reporta_dependencias():
    for servicio in PUERTOS:
        r = requests.get(f'{base(servicio)}/health', timeout=10)
        assert r.status_code == 200, servicio
        datos = r.json()
        assert datos['estado'] == 'ok'
        assert {d['nombre'] for d in datos['dependencias']} >= {'redis'}
