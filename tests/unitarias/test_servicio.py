"""
Comportamiento común de todos los microservicios (clase Servicio de abasto_api),
probado con un servicio de juguete y el cliente de pruebas de Flask: versión
/api/v1, autenticación y permisos, validación, errores estándar, JSON y XML,
límite de peticiones e identificador de correlación.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from lxml import etree
from openapi_spec_validator import validate
from pydantic import Field

from abasto_api import BaseEntrada, ErrorApi, Servicio
from abasto_api.formatos import NS
from abasto_dominio import sesiones
from abasto_dominio.servicios import ReglaNegocioError


class SaludoEntrada(BaseEntrada):
    nombre: str = Field(min_length=2, max_length=40)
    veces: int = Field(1, ge=1, le=5)


srv = Servicio('demo', 'Demo', 'Servicio de juguete para pruebas', dependencias=())
srv.app.config.update(TESTING=True, JWT_SECRET_KEY='secreto-de-pruebas-unitarias-con-32-bytes')


@srv.ruta('/saludos', 'POST', resumen='Saludar', permisos=['demo.usar'], cuerpo=SaludoEntrada, status=201,
          raiz_xml='saludo', entrada_xml='saludo_entrada', limite=3)
def saludar(datos):
    if datos.nombre == 'Nadie':
        raise ReglaNegocioError('No se puede saludar a nadie.')
    return {'mensaje': ' '.join([f'Hola {datos.nombre}'] * datos.veces), 'lista': ['a', 'b']}


@srv.ruta('/publico/<int:id>', 'GET', resumen='Público', publico=True, raiz_xml='cosa')
def publico(id):
    if id == 404:
        raise ErrorApi(404, 'no_encontrado', 'La cosa no existe.')
    return {'id': id}


@pytest.fixture
def cliente(redis_falso, sin_mongo):
    return srv.app.test_client()


def token(permisos=('demo.usar',)):
    usuario = SimpleNamespace(id=uuid4(), nombre_completo='Prueba', proveedor=None, proveedor_id=None,
                              rol=SimpleNamespace(nombre='Rol de prueba', permisos=list(permisos)))
    with srv.app.app_context():
        return sesiones.emitir_tokens(usuario, con_refresh=False)['access_token']


def auth(permisos=('demo.usar',)):
    return {'Authorization': f'Bearer {token(permisos)}'}


def test_exito_json_201(cliente):
    r = cliente.post('/api/v1/saludos', json={'nombre': 'Ana', 'veces': 2}, headers=auth())
    assert r.status_code == 201
    assert r.json['mensaje'] == 'Hola Ana Hola Ana'
    assert r.headers['X-Servicio'] == 'ms-demo'


def test_exito_xml_entrada_y_salida(cliente):
    cuerpo = f'<saludo_entrada xmlns="{NS}"><nombre>Ana</nombre></saludo_entrada>'
    r = cliente.post('/api/v1/saludos', data=cuerpo, content_type='application/xml',
                     headers={**auth(), 'Accept': 'application/xml'})
    assert r.status_code == 201
    assert r.mimetype == 'application/xml'
    raiz = etree.fromstring(r.data)
    assert etree.QName(raiz).localname == 'saludo'
    assert raiz.findtext(f'{{{NS}}}mensaje') == 'Hola Ana'


def test_formato_por_parametro(cliente):
    r = cliente.get('/api/v1/publico/7?formato=xml')
    assert r.mimetype == 'application/xml'


def test_sin_token_401(cliente):
    r = cliente.post('/api/v1/saludos', json={'nombre': 'Ana'})
    assert r.status_code == 401
    assert r.json['error']['codigo'] in ('token_requerido', 'no_autenticado', 'token_invalido')


def test_sin_permiso_403(cliente):
    r = cliente.post('/api/v1/saludos', json={'nombre': 'Ana'}, headers=auth(permisos=('otra.cosa',)))
    assert r.status_code == 403


def test_validacion_422_con_detalle_por_campo(cliente):
    r = cliente.post('/api/v1/saludos', json={'nombre': 'A', 'veces': 9}, headers=auth())
    assert r.status_code == 422
    campos = {d['campo'] for d in r.json['error']['detalles']}
    assert {'nombre', 'veces'} <= campos


def test_campos_desconocidos_se_rechazan(cliente):
    r = cliente.post('/api/v1/saludos', json={'nombre': 'Ana', 'admin': True}, headers=auth())
    assert r.status_code == 422


def test_json_mal_formado_400(cliente):
    r = cliente.post('/api/v1/saludos', data='{"nombre": ', content_type='application/json', headers=auth())
    assert r.status_code == 400
    assert r.json['error']['codigo'] == 'json_invalido'


def test_tipo_no_soportado_415(cliente):
    r = cliente.post('/api/v1/saludos', data='nombre=Ana', content_type='text/plain', headers=auth())
    assert r.status_code == 415


def test_regla_de_negocio_409(cliente):
    r = cliente.post('/api/v1/saludos', json={'nombre': 'Nadie'}, headers=auth())
    assert r.status_code == 409
    assert r.json['error']['mensaje'] == 'No se puede saludar a nadie.'


def test_no_encontrado_404_en_xml(cliente):
    r = cliente.get('/api/v1/publico/404', headers={'Accept': 'application/xml'})
    assert r.status_code == 404
    raiz = etree.fromstring(r.data)
    assert etree.QName(raiz).localname == 'error'  # sin <error><error> anidado
    assert raiz.findtext(f'{{{NS}}}codigo') == 'no_encontrado'


def test_ruta_inexistente_responde_error_estandar(cliente):
    r = cliente.get('/api/v1/no-existe')
    assert r.status_code == 404
    assert r.json['error']['status'] == 404


def test_limite_de_peticiones_429(cliente):
    cabeceras = auth()
    codigos = [cliente.post('/api/v1/saludos', json={'nombre': 'Ana'}, headers=cabeceras).status_code
               for _ in range(4)]
    assert codigos == [201, 201, 201, 429]
    r = cliente.post('/api/v1/saludos', json={'nombre': 'Ana'}, headers=cabeceras)
    assert int(r.headers['Retry-After']) > 0
    assert r.headers['X-RateLimit-Remaining'] == '0'


def test_correlation_id_se_propaga(cliente):
    r = cliente.get('/api/v1/publico/1', headers={'X-Correlation-ID': 'prueba-123'})
    assert r.headers['X-Correlation-ID'] == 'prueba-123'
    assert len(cliente.get('/api/v1/publico/1').headers['X-Correlation-ID']) >= 16


def test_token_revocado_401(cliente):
    t = token()
    with srv.app.app_context():
        sesiones.revocar(sesiones.decodificar(t))
    r = cliente.post('/api/v1/saludos', json={'nombre': 'Ana'}, headers={'Authorization': f'Bearer {t}'})
    assert r.status_code == 401
    assert r.json['error']['codigo'] == 'token_revocado'


def test_openapi_documenta_la_ruta_y_sus_errores(cliente):
    doc = cliente.get('/openapi.json').json
    assert doc['openapi'] == '3.0.3'
    validate(doc)  # cumple la especificación OpenAPI 3.0 que lee Swagger UI
    operacion = doc['paths']['/api/v1/saludos']['post']
    assert {'201', '401', '403', '409', '422', '429'} <= set(operacion['responses'])
    assert 'application/xml' in operacion['requestBody']['content']


def test_health_live(cliente):
    assert cliente.get('/health/live').status_code == 200
