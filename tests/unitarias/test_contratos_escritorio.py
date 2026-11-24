"""La app de escritorio convierte XML <-> datos siguiendo el XSD del servicio (sin modelos escritos a mano)."""
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'apps' / 'escritorio'))

from abastored_escritorio.contratos import NS, Contrato, ContratoInvalido  # noqa: E402


@pytest.fixture(scope='module')
def comercios():
    return Contrato.desde_xsd('comercios', (RAIZ / 'apps/microservicios/comercios/xsd/comercios.xsd').read_bytes())


def _xml(texto):
    return etree.fromstring(f'<comercios xmlns="{NS}">{texto}</comercios>'.encode())


def test_lista_con_un_solo_elemento_sigue_siendo_lista(comercios):
    doc = _xml('<paginacion><pagina>1</pagina><por_pagina>20</por_pagina><total>1</total><paginas>1</paginas>'
               '</paginacion><items><item><id>a</id><nombre_comercio>Tienda</nombre_comercio>'
               '<tipo_comercio>FORMAL_ABARROTES</tipo_comercio><sector>Formal</sector><direccion>x</direccion>'
               '<municipio>García</municipio><estado>Nuevo León</estado><estado_registro>PENDIENTE</estado_registro>'
               '<usuario_id>u</usuario_id><latitud>25.8</latitud><zona_id>2</zona_id></item></items>')
    comercios.validar(doc)
    datos = comercios.a_datos(doc)
    assert isinstance(datos['items'], list) and len(datos['items']) == 1
    item = datos['items'][0]
    assert item['zona_id'] == 2 and item['latitud'] == Decimal('25.8')   # tipos tomados del XSD
    assert datos['paginacion']['total'] == 1


def test_lista_vacia(comercios):
    doc = _xml('<paginacion><pagina>1</pagina><por_pagina>20</por_pagina><total>0</total><paginas>0</paginas>'
               '</paginacion><items/>')
    assert comercios.a_datos(doc)['items'] == []


def test_peticion_valida_contra_el_xsd(comercios):
    elemento = comercios.a_xml('validacion_entrada', {'estado': 'VERIFICADO', 'observaciones': None})
    assert etree.QName(elemento).localname == 'validacion_entrada'
    assert elemento.find(f'{{{NS}}}observaciones') is None        # los None se omiten
    with pytest.raises(ContratoInvalido):
        comercios.a_xml('validacion_entrada', {'estado': 'APROBADO'})   # no es un estado del contrato


def test_tipos_por_contexto_y_errores():
    auditoria = Contrato.desde_xsd('auditoria', (RAIZ / 'apps/microservicios/auditoria/xsd/auditoria.xsd').read_bytes())
    error = etree.fromstring(f'<error xmlns="{NS}"><codigo>x</codigo><mensaje>m</mensaje><status>404</status>'
                             f'<ruta>/r</ruta><correlation_id>c</correlation_id>'
                             f'<fecha>2026-11-15T08:00:00+00:00</fecha></error>'.encode())
    auditoria.validar(error)
    datos = auditoria.a_datos(error)
    assert datos['status'] == 404 and isinstance(datos['fecha'], datetime)
