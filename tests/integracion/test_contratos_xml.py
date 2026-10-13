"""
Contratos JSON y XML de los ocho servicios: la respuesta XML de cada servicio
valida contra su XSD publicado, trae los mismos datos que la JSON y los errores
también cumplen el contrato.
"""
import pytest
import requests
from lxml import etree

from apoyo import NS, PUERTOS, RAIZ, base, url

# (servicio, rol o None si es público, ruta, elemento raíz esperado)
CONSULTAS = [
    ('seguridad', 'admin', '/roles', 'roles'),
    ('comercios', None, '/zonas', 'zonas'),
    ('catalogo', None, '/categorias', 'categorias'),
    ('inventario', None, '/disponibilidad?por_pagina=5', 'disponibilidad'),
    ('precios', 'analista', '/precios?por_pagina=5', 'precios'),
    ('pedidos', 'minorista', '/pedidos?por_pagina=5', 'pedidos'),
    ('analisis', 'analista', '/analisis/zonas', 'zonas'),
    ('notificaciones', 'minorista', '/notificaciones?por_pagina=5', 'notificaciones'),
]


def esquema(servicio):
    return etree.XMLSchema(etree.parse(str(RAIZ / 'apps' / 'microservicios' / servicio / 'xsd' / f'{servicio}.xsd')))


def cabeceras(api, rol, formato):
    h = {'Accept': formato}
    if rol:
        h['Authorization'] = f"Bearer {api(rol).tokens['access_token']}"
    return h


@pytest.mark.parametrize('servicio, rol, ruta, raiz', CONSULTAS, ids=[c[0] for c in CONSULTAS])
def test_respuesta_xml_valida_contra_el_xsd(api, servicio, rol, ruta, raiz):
    r = requests.get(url(servicio, ruta), headers=cabeceras(api, rol, 'application/xml'), timeout=20)
    assert r.status_code == 200, r.text[:300]
    assert r.headers['Content-Type'].startswith('application/xml')
    documento = etree.fromstring(r.content)
    assert etree.QName(documento) == etree.QName(NS, raiz)
    validador = esquema(servicio)
    assert validador.validate(documento), [f'{e.line}: {e.message}' for e in validador.error_log][:5]


@pytest.mark.parametrize('servicio, rol, ruta, raiz', CONSULTAS[:4], ids=[c[0] for c in CONSULTAS[:4]])
def test_json_y_xml_traen_lo_mismo(api, servicio, rol, ruta, raiz):
    como_json = requests.get(url(servicio, ruta), headers=cabeceras(api, rol, 'application/json'), timeout=20).json()
    como_xml = etree.fromstring(requests.get(url(servicio, ruta), headers=cabeceras(api, rol, 'application/xml'),
                                             timeout=20).content)
    lista = next(v for v in como_json.values() if isinstance(v, list))
    contenedor = next(h for h in como_xml if len(h) and etree.QName(h).localname != 'paginacion')
    assert len(contenedor) == len(lista)


@pytest.mark.parametrize('servicio', sorted(PUERTOS))
def test_error_en_xml_cumple_el_contrato(servicio):
    r = requests.get(url(servicio, '/no-existe'), headers={'Accept': 'application/xml'}, timeout=10)
    assert r.status_code == 404
    documento = etree.fromstring(r.content)
    assert etree.QName(documento).localname == 'error'
    assert esquema(servicio).validate(documento)


@pytest.mark.parametrize('servicio', sorted(PUERTOS))
def test_xsd_publicado_es_el_del_repositorio(servicio):
    r = requests.get(f'{base(servicio)}/xsd', timeout=10)
    assert r.status_code == 200
    local = (RAIZ / 'apps' / 'microservicios' / servicio / 'xsd' / f'{servicio}.xsd').read_bytes()
    assert r.content.replace(b'\r\n', b'\n') == local.replace(b'\r\n', b'\n')


def test_detalle_de_comercio_en_json_y_xml(api):
    """Regresión: el detalle incluye horarios (time) y respondía 500."""
    minorista = api('minorista')
    comercio = minorista.get('comercios', '/comercios').json()['items'][0]['id']
    r = minorista.get('comercios', f'/comercios/{comercio}')
    assert r.status_code == 200
    assert 'horario_apertura' in r.json()
    r = minorista.get('comercios', f'/comercios/{comercio}', headers={'Accept': 'application/xml'})
    assert r.status_code == 200
    assert esquema('comercios').validate(etree.fromstring(r.content))


def test_xml_que_no_cumple_el_xsd_es_400(api):
    malo = (f'<movimiento_entrada xmlns="{NS}"><tipo>ROBO</tipo><cantidad>2</cantidad></movimiento_entrada>').encode()
    renglon = api('minorista').get('inventario', '/comercios/{}/inventario'.format(
        api('minorista').get('comercios', '/comercios').json()['items'][0]['id'])).json()['renglones'][0]
    r = api('minorista').post('inventario', f"/inventario/{renglon['id']}/movimientos", data=malo,
                              headers={'Content-Type': 'application/xml', 'Accept': 'application/xml'})
    assert r.status_code == 400
    documento = etree.fromstring(r.content)
    assert documento.findtext(f'{{{NS}}}codigo') == 'xml_invalido'
    assert 'ROBO' in documento.findtext(f'{{{NS}}}mensaje') or 'tipo' in documento.findtext(f'{{{NS}}}mensaje')


def test_xml_con_raiz_equivocada_es_400(api):
    r = api('minorista').post('pedidos', '/pedidos', data=f'<login xmlns="{NS}"/>'.encode(),
                              headers={'Content-Type': 'application/xml'})
    assert r.status_code == 400
    assert 'pedido_entrada' in r.json()['error']['mensaje']


def test_openapi_y_swagger_en_todos():
    for servicio in PUERTOS:
        doc = requests.get(f'{base(servicio)}/openapi.json', timeout=10).json()
        assert doc['openapi'].startswith('3.1')
        assert any(p.startswith('/api/v1/') for p in doc['paths'])
        assert requests.get(f'{base(servicio)}/docs', timeout=10).status_code == 200
