"""
Proceso de negocio completo pasando sólo por los microservicios. Cada paso usa
lo que dejó el anterior (no son llamadas aisladas):

  1. La minorista entra (ms-seguridad) y consulta su comercio (ms-comercios).
  2. Vende hasta dejar un producto en stock bajo (ms-inventario) -> aviso (ms-notificaciones).
  3. El producto aparece en faltantes y en la caché de disponibilidad se nota el cambio (Redis).
  4. Busca quién se lo vende en su zona (ms-catalogo).
  5. Crea el pedido en XML, validado contra pedidos.xsd (ms-pedidos).
  6. Lo envía; el operador del proveedor recibe aviso, lo acepta y prepara; el dueño lo despacha.
  7. El proveedor no puede marcarlo como recibido (409); la minorista sí.
  8. La existencia sube exactamente lo pedido (ms-inventario).
  9. El historial junta PostgreSQL y los eventos de MongoDB; las estadísticas (agregación) lo cuentan.
 10. La bitácora de peticiones permite rastrear la creación por su X-Correlation-ID.
"""
import math
import uuid
from decimal import Decimal
import pytest
from lxml import etree

from apoyo import NS, RAIZ

XSD_PEDIDOS = etree.XMLSchema(etree.parse(str(RAIZ / 'apps/microservicios/pedidos/xsd/pedidos.xsd')))
ESTADO = {}  # lo que cada paso deja al siguiente


@pytest.fixture(scope='module')
def minorista(api):
    return api('minorista')


@pytest.fixture(scope='module')
def operador(api):
    return api('operador')


@pytest.fixture(scope='module')
def dueno(api):
    return api('dueno_regia')


def test_01_comercio_e_inventario(minorista):
    r = minorista.get('comercios', '/comercios')
    assert r.status_code == 200
    comercio = next(c for c in r.json()['items'] if c['zona_id'])
    r = minorista.get('inventario', f"/comercios/{comercio['id']}/inventario", params={'por_pagina': 200})
    assert r.status_code == 200

    # Un producto con existencia que la Distribuidora Regia entregue en su zona
    for renglon in r.json()['renglones']:
        if renglon['existencia'] <= renglon['stock_minimo']:
            continue
        ofertas = minorista.get('catalogo', '/ofertas',
                                params={'producto_id': renglon['producto_id'], 'zona_id': comercio['zona_id']}).json()
        oferta = next((o for o in ofertas['ofertas'] if o['cubre_zona'] and o['proveedor'].startswith('Distribuidora Regia')), None)
        if oferta:
            break
    else:
        pytest.fail('No hay un producto con existencia que la Distribuidora Regia entregue en la zona')
    ESTADO.update(comercio=comercio, renglon=renglon, oferta=oferta)


def test_02_venta_deja_stock_bajo_y_avisa(minorista):
    renglon = ESTADO['renglon']
    antes = minorista.get('notificaciones', '/notificaciones/contador').json()['no_leidas']
    vender = Decimal(str(renglon['existencia'])) - Decimal(str(renglon['stock_minimo'])) + 1
    r = minorista.post('inventario', f"/inventario/{renglon['id']}/movimientos",
                       json={'tipo': 'SALIDA', 'cantidad': float(vender), 'motivo': 'Venta (prueba de integración)'})
    assert r.status_code == 201, r.text
    movimiento = r.json()
    assert movimiento['existencia_nueva'] == pytest.approx(renglon['stock_minimo'] - 1)

    r = minorista.get('inventario', f"/inventario/{renglon['id']}")
    assert r.json()['estado'] in ('BAJO', 'AGOTADO')
    ESTADO['existencia_antes_del_pedido'] = r.json()['existencia']

    despues = minorista.get('notificaciones', '/notificaciones/contador').json()['no_leidas']
    assert despues == antes + 1
    ultima = minorista.get('notificaciones', '/notificaciones', params={'por_pagina': 1}).json()['notificaciones'][0]
    assert ultima['tipo'] == 'stock_bajo'
    assert renglon['producto'] in ultima['titulo']


def test_03_vender_mas_de_lo_que_hay_es_error_de_negocio(minorista):
    r = minorista.post('inventario', f"/inventario/{ESTADO['renglon']['id']}/movimientos",
                       json={'tipo': 'SALIDA', 'cantidad': 99999})
    assert r.status_code == 409
    assert r.json()['error']['codigo'] == 'regla_negocio'


def test_04_aparece_en_faltantes(minorista):
    r = minorista.get('inventario', f"/comercios/{ESTADO['comercio']['id']}/faltantes")
    assert ESTADO['renglon']['producto_id'] in {f['producto_id'] for f in r.json()['faltantes']}


def test_05_crear_pedido_en_xml(minorista):
    oferta = ESTADO['oferta']
    cantidad = max(oferta['cantidad_minima'], math.ceil((oferta['pedido_minimo'] or 0) / oferta['precio_mayoreo']) + 1)
    ESTADO['cantidad'] = cantidad
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><pedido_entrada xmlns="{NS}">'
           f"<comercio_id>{ESTADO['comercio']['id']}</comercio_id><proveedor_id>{oferta['proveedor_id']}</proveedor_id>"
           f"<partidas><partida><producto_id>{oferta['producto_id']}</producto_id><cantidad>{cantidad}</cantidad></partida></partidas>"
           f'<notas>Prueba de integración {uuid.uuid4().hex[:6]}</notas></pedido_entrada>').encode()
    assert XSD_PEDIDOS.validate(etree.fromstring(xml))

    r = minorista.post('pedidos', '/pedidos', data=xml,
                       headers={'Content-Type': 'application/xml', 'Accept': 'application/xml'})
    assert r.status_code == 201, r.text
    assert r.headers['Content-Type'].startswith('application/xml')
    respuesta = etree.fromstring(r.content)
    assert XSD_PEDIDOS.validate(respuesta), XSD_PEDIDOS.error_log
    assert respuesta.findtext(f'{{{NS}}}estado') == 'BORRADOR'
    ESTADO['pedido_id'] = respuesta.findtext(f'{{{NS}}}id')
    ESTADO['correlation_id'] = r.headers['X-Correlation-ID']


def test_06_mismo_pedido_en_json(minorista):
    r = minorista.get('pedidos', f"/pedidos/{ESTADO['pedido_id']}")
    assert r.status_code == 200
    pedido = r.json()
    assert pedido['estado'] == 'BORRADOR'
    assert pedido['partidas'][0]['cantidad'] == pytest.approx(ESTADO['cantidad'])


def test_07_enviar_avisa_al_equipo_del_proveedor(minorista, operador):
    antes = operador.get('notificaciones', '/notificaciones/contador').json()['no_leidas']
    r = minorista.post('pedidos', f"/pedidos/{ESTADO['pedido_id']}/acciones/enviar")
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'ENVIADO'
    assert operador.get('notificaciones', '/notificaciones/contador').json()['no_leidas'] == antes + 1


def test_08_operador_acepta_y_prepara(operador):
    for accion, estado in (('aceptar', 'ACEPTADO'), ('preparar', 'EN_PREPARACION')):
        r = operador.post('pedidos', f"/pedidos/{ESTADO['pedido_id']}/acciones/{accion}")
        assert r.status_code == 200, r.text
        assert r.json()['estado'] == estado


def test_09_accion_fuera_de_orden_es_409(operador):
    r = operador.post('pedidos', f"/pedidos/{ESTADO['pedido_id']}/acciones/aceptar")
    assert r.status_code == 409


def test_10_dueno_despacha(dueno):
    r = dueno.post('pedidos', f"/pedidos/{ESTADO['pedido_id']}/acciones/despachar")
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'ENVIADO_A_COMERCIO'


def test_11_proveedor_no_puede_recibir(operador):
    r = operador.post('pedidos', f"/pedidos/{ESTADO['pedido_id']}/acciones/recibir")
    assert r.status_code == 409
    assert 'no está disponible para ti' in r.json()['error']['mensaje']


def test_12_minorista_recibe_y_sube_el_inventario(minorista):
    r = minorista.post('pedidos', f"/pedidos/{ESTADO['pedido_id']}/acciones/recibir")
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'ENTREGADO'

    r = minorista.get('inventario', f"/inventario/{ESTADO['renglon']['id']}")
    assert r.json()['existencia'] == pytest.approx(ESTADO['existencia_antes_del_pedido'] + ESTADO['cantidad'])
    assert r.json()['estado'] == 'DISPONIBLE' or r.json()['existencia'] <= r.json()['stock_minimo']


def test_13_historial_postgres_y_eventos_mongodb(minorista):
    r = minorista.get('pedidos', f"/pedidos/{ESTADO['pedido_id']}/historial")
    assert r.status_code == 200
    datos = r.json()
    estados = [h['a'] for h in datos['historial']]
    assert estados[-5:] == ['ENVIADO', 'ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO', 'ENTREGADO']
    tipos = [e['estado_nuevo'] for e in datos['eventos'] if e.get('estado_nuevo')]
    assert 'ENTREGADO' in tipos  # documento en la colección eventos_pedido de MongoDB


def test_14_estadisticas_por_agregacion(api):
    r = api('analista').get('pedidos', '/estadisticas/proveedores', params={'dias': 1})
    assert r.status_code == 200
    fila = next(f for f in r.json()['proveedores'] if f['proveedor_id'] == ESTADO['oferta']['proveedor_id'])
    assert fila['entregados'] >= 1


def test_15_rastreo_por_correlation_id(api):
    r = api('admin').get('seguridad', f"/actividad/peticiones/{ESTADO['correlation_id']}")
    assert r.status_code == 200
    paso = r.json()['pasos'][0]
    assert (paso['servicio'], paso['metodo'], paso['status'], paso['formato']) == ('pedidos', 'POST', 201, 'xml')
