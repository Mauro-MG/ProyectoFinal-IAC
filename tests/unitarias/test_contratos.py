"""
Contratos XML: cada XSD guardado en apps/microservicios/<servicio>/xsd/ debe ser
idéntico al que se genera de los modelos Pydantic, y debe validar documentos
reales construidos con los mismos ejemplos que documenta Swagger.
"""
from pathlib import Path

import pytest
from lxml import etree

from abasto_api.contratos import cargar_contratos, generar_xsd
from abasto_api.formatos import NS, a_xml

RAIZ = Path(__file__).resolve().parents[2]
SERVICIOS = sorted(p.name for p in (RAIZ / 'apps' / 'microservicios').iterdir() if (p / 'esquemas.py').exists())


def xsd_de(servicio):
    return RAIZ / 'apps' / 'microservicios' / servicio / 'xsd' / f'{servicio}.xsd'


def test_hay_entre_6_y_10_servicios():
    assert 6 <= len(SERVICIOS) <= 10, SERVICIOS


@pytest.mark.parametrize('servicio', SERVICIOS)
def test_xsd_guardado_coincide_con_los_modelos(servicio):
    generado = generar_xsd(servicio, cargar_contratos(RAIZ / 'apps' / 'microservicios' / servicio))
    guardado = xsd_de(servicio).read_text(encoding='utf-8')
    assert guardado.replace('\r\n', '\n') == generado, (
        f'El XSD de {servicio} no corresponde a esquemas.py; regenéralo con '
        f'python -m abasto_api.contratos apps/microservicios/{servicio}')


@pytest.mark.parametrize('servicio', SERVICIOS)
def test_xsd_es_un_esquema_valido(servicio):
    documento = etree.parse(str(xsd_de(servicio)))
    etree.XMLSchema(documento)  # lanza XMLSchemaParseError si el esquema está mal formado
    raices = {e.get('name') for e in documento.getroot().findall('{http://www.w3.org/2001/XMLSchema}element')}
    assert {'error', 'salud', 'resultado'} <= raices  # contratos comunes en todos los servicios


def validar(servicio, xml):
    esquema = etree.XMLSchema(etree.parse(str(xsd_de(servicio))))
    documento = etree.fromstring(xml)
    assert esquema.validate(documento), [f'{e.line}: {e.message}' for e in esquema.error_log]


def test_error_estandar_valida_en_todos_los_servicios():
    error = {'error': {'codigo': 'no_encontrado', 'mensaje': 'El pedido no existe.', 'status': 404,
                       'correlation_id': 'abc123', 'detalles': [{'campo': 'id', 'mensaje': 'no existe'}]}}
    for servicio in SERVICIOS:
        validar(servicio, a_xml(error['error'], 'error'))


def test_pedido_entrada_valida_y_rechaza_cantidad_negativa():
    bueno = (f'<pedido_entrada xmlns="{NS}"><comercio_id>3122a5b1-a074-4d57-8fce-7aa9e5fc9743</comercio_id>'
             f'<proveedor_id>4122a5b1-a074-4d57-8fce-7aa9e5fc9743</proveedor_id>'
             f'<partidas><partida><producto_id>3</producto_id><cantidad>40</cantidad></partida></partidas>'
             f'</pedido_entrada>').encode()
    validar('pedidos', bueno)

    malo = bueno.replace(b'<cantidad>40</cantidad>', b'<cantidad>-1</cantidad>')
    esquema = etree.XMLSchema(etree.parse(str(xsd_de('pedidos'))))
    assert not esquema.validate(etree.fromstring(malo))


def test_movimiento_entrada_rechaza_tipo_desconocido():
    esquema = etree.XMLSchema(etree.parse(str(xsd_de('inventario'))))
    bueno = f'<movimiento_entrada xmlns="{NS}"><tipo>SALIDA</tipo><cantidad>2</cantidad></movimiento_entrada>'
    malo = bueno.replace('SALIDA', 'ROBO')
    assert esquema.validate(etree.fromstring(bueno.encode())), esquema.error_log
    assert not esquema.validate(etree.fromstring(malo.encode()))
