"""Mecanismo común de sesión: JWT firmado + sesión viva en Redis + lista de revocados."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from abasto_dominio import extensiones, sesiones
from abasto_dominio.sesiones import ErrorSesion


def usuario_falso(permisos=('pedidos.crear',), proveedor_id=None):
    return SimpleNamespace(id=uuid4(), nombre_completo='Juan Pérez', proveedor=None, proveedor_id=proveedor_id,
                           rol=SimpleNamespace(nombre='Comerciante Informal', permisos=list(permisos)))


@pytest.fixture
def entorno(app_flask, redis_falso):
    return redis_falso


def test_emitir_registra_sesion_y_refresh(entorno):
    usuario = usuario_falso()
    tokens = sesiones.emitir_tokens(usuario, origen='api', ip='10.0.0.1')

    claims = sesiones.validar_token(tokens['access_token'])
    assert claims['sub'] == str(usuario.id)
    assert claims['permisos'] == ['pedidos.crear']
    assert claims['tipo'] == 'acceso'
    assert entorno.exists(f"sesion:{tokens['jti']}")
    assert entorno.sismember(f'sesiones_usuario:{usuario.id}', tokens['jti'])
    assert entorno.exists(f"refresh:{tokens['refresh_token']}")
    # La sesión dura lo mismo que el token de acceso (8 h)
    assert 0 < entorno.ttl(f"sesion:{tokens['jti']}") <= 8 * 3600


def test_operador_lleva_proveedor_en_el_token(entorno):
    empresa = uuid4()
    tokens = sesiones.emitir_tokens(usuario_falso(proveedor_id=empresa), con_refresh=False)
    assert sesiones.validar_token(tokens['access_token'])['proveedor_id'] == str(empresa)
    assert 'refresh_token' not in tokens


def test_revocar_invalida_el_token(entorno):
    tokens = sesiones.emitir_tokens(usuario_falso())
    claims = sesiones.validar_token(tokens['access_token'])
    sesiones.revocar(claims)

    with pytest.raises(ErrorSesion) as error:
        sesiones.validar_token(tokens['access_token'])
    assert error.value.codigo == 'token_revocado'
    assert error.value.codigo_http == 401
    # El jti revocado sólo se guarda lo que le quedaba de vida al token
    assert entorno.ttl(f"jwt:revocado:{claims['jti']}") <= 8 * 3600


def test_sesion_borrada_en_redis_ya_no_sirve(entorno):
    tokens = sesiones.emitir_tokens(usuario_falso())
    entorno.delete(f"sesion:{tokens['jti']}")
    with pytest.raises(ErrorSesion) as error:
        sesiones.validar_token(tokens['access_token'])
    assert error.value.codigo == 'sesion_inactiva'


def test_token_expirado(app_flask, entorno):
    ahora = datetime.now(timezone.utc)
    vencido = jwt.encode({'sub': 'x', 'jti': uuid4().hex, 'tipo': 'acceso', 'rol': 'r', 'permisos': [],
                          'iat': ahora - timedelta(hours=9), 'exp': ahora - timedelta(hours=1)},
                         app_flask.config['JWT_SECRET_KEY'], algorithm='HS256')
    with pytest.raises(ErrorSesion) as error:
        sesiones.validar_token(vencido)
    assert error.value.codigo == 'token_expirado'


@pytest.mark.parametrize('token', ['no-es-un-jwt', 'a.b.c'])
def test_token_mal_formado(entorno, token):
    with pytest.raises(ErrorSesion) as error:
        sesiones.validar_token(token)
    assert error.value.codigo == 'token_invalido'


def test_token_firmado_con_otro_secreto(entorno):
    ajeno = jwt.encode({'sub': 'x', 'jti': 'abc', 'tipo': 'acceso', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
                       'otro-secreto-que-no-es-el-del-sistema-123', algorithm='HS256')
    with pytest.raises(ErrorSesion):
        sesiones.validar_token(ajeno)


def test_refresh_se_rota_y_no_se_reutiliza(entorno, monkeypatch):
    usuario = usuario_falso()
    usuario.activo = True
    monkeypatch.setattr(extensiones.db.session, 'get', lambda modelo, id: usuario, raising=False)
    primeros = sesiones.emitir_tokens(usuario)

    nuevos = sesiones.renovar(primeros['refresh_token'])
    assert nuevos['jti'] != primeros['jti']
    # El acceso anterior queda revocado y el refresh usado ya no sirve
    with pytest.raises(ErrorSesion):
        sesiones.validar_token(primeros['access_token'])
    with pytest.raises(ErrorSesion) as error:
        sesiones.renovar(primeros['refresh_token'])
    assert error.value.codigo == 'refresh_invalido'
    assert sesiones.validar_token(nuevos['access_token'])


def test_cerrar_sesion_tambien_anula_el_refresh(entorno, monkeypatch):
    """Sin esto, alguien con el refresh podría sacar tokens nuevos después del logout."""
    usuario = usuario_falso()
    usuario.activo = True
    monkeypatch.setattr(extensiones.db.session, 'get', lambda modelo, id: usuario, raising=False)
    tokens = sesiones.emitir_tokens(usuario)
    sesiones.revocar(sesiones.validar_token(tokens['access_token']))

    assert not entorno.exists(f"refresh:{tokens['refresh_token']}")
    with pytest.raises(ErrorSesion) as error:
        sesiones.renovar(tokens['refresh_token'])
    assert error.value.codigo == 'refresh_invalido'


def test_revocar_todas_las_sesiones_de_un_usuario(entorno):
    usuario = usuario_falso()
    tokens = [sesiones.emitir_tokens(usuario, origen=o) for o in ('web', 'api', 'api')]
    assert len(sesiones.sesiones_activas(usuario.id)) == 3

    assert sesiones.revocar_todas(usuario.id) == 3
    for t in tokens:
        with pytest.raises(ErrorSesion):
            sesiones.validar_token(t['access_token'])
        assert not entorno.exists(f"refresh:{t['refresh_token']}")
    assert sesiones.sesiones_activas(usuario.id) == []


def test_token_de_servicio_es_corto_y_tiene_permisos_acotados(entorno):
    token = sesiones.token_servicio('pedidos', ['notificaciones.crear'], minutos=5)
    claims = sesiones.validar_token(token)
    assert claims['tipo'] == 'servicio'
    assert claims['sub'] == 'servicio:pedidos'
    assert claims['permisos'] == ['notificaciones.crear']
    assert claims['exp'] - claims['iat'] == 300


def test_bloqueo_tras_cinco_intentos_fallidos(entorno):
    email = 'alguien@test.mx'
    for _ in range(sesiones.MAX_INTENTOS - 1):
        sesiones.registrar_intento_fallido(email)
    assert not sesiones.login_bloqueado(email)
    sesiones.registrar_intento_fallido(email)
    assert sesiones.login_bloqueado(email)
    sesiones.limpiar_intentos(email)
    assert not sesiones.login_bloqueado(email)


def test_sin_redis_responde_503(app_flask, monkeypatch):
    class RedisCaido:
        def __getattr__(self, nombre):
            def falla(*args, **kwargs):
                raise RedisConnectionError('Redis caído')
            return falla
    monkeypatch.setattr(extensiones, 'redis_client', RedisCaido())
    token = jwt.encode({'sub': 'x', 'jti': 'abc', 'tipo': 'acceso', 'rol': 'r', 'permisos': [],
                        'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
                       app_flask.config['JWT_SECRET_KEY'], algorithm='HS256')
    with pytest.raises(ErrorSesion) as error:
        sesiones.validar_token(token)
    assert error.value.codigo_http == 503
    assert sesiones.sesion_activa('abc') is None  # el web sigue con su sesión de Flask
