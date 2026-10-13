"""Conversión JSON <-> XML y lectura segura de XML."""
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from lxml import etree

from abasto_api.formatos import NS, a_xml, compatible_json, leer_xml


def test_a_xml_usa_espacio_de_nombres_y_singulares():
    xml = a_xml({'total': 2, 'pedidos': [{'folio': 'PED-1'}, {'folio': 'PED-2'}]}, 'pedidos_lista')
    raiz = etree.fromstring(xml)
    assert etree.QName(raiz).namespace == NS
    assert xml.startswith(b"<?xml version='1.0' encoding='UTF-8'?>")
    hijos = raiz.findall(f'{{{NS}}}pedidos/{{{NS}}}pedido')
    assert [h.findtext(f'{{{NS}}}folio') for h in hijos] == ['PED-1', 'PED-2']


def test_a_xml_omite_nulos_y_convierte_tipos():
    xml = a_xml({'precio': Decimal('27.50'), 'activo': True, 'nota': None,
                 'fecha': datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc)}, 'precio')
    raiz = etree.fromstring(xml)
    assert raiz.findtext(f'{{{NS}}}precio') == '27.5'  # mismo valor que el número en JSON
    assert raiz.findtext(f'{{{NS}}}activo') == 'true'
    assert raiz.find(f'{{{NS}}}nota') is None
    assert raiz.findtext(f'{{{NS}}}fecha').startswith('2026-10-12T09:30:00')


def test_a_xml_escapa_texto():
    xml = a_xml({'nombre': 'Abarrotes "Don Pepe" <Centro> & Cía'}, 'comercio')
    assert etree.fromstring(xml).findtext(f'{{{NS}}}nombre') == 'Abarrotes "Don Pepe" <Centro> & Cía'


def test_responder_lista_con_el_nombre_de_la_raiz_conserva_el_contenedor():
    """Regresión: {"categorias": [...]} con raíz "categorias" debe quedar como el XSD lo define."""
    from flask import Flask

    from abasto_api.formatos import responder
    app = Flask('prueba')
    with app.test_request_context(headers={'Accept': 'application/xml'}):
        xml = responder({'categorias': [{'id': 1}, {'id': 2}]}, raiz='categorias').get_data()
        raiz = etree.fromstring(xml)
        assert len(raiz.findall(f'{{{NS}}}categorias/{{{NS}}}categoria')) == 2
        xml = responder({'error': {'codigo': 'x'}}, raiz='error').get_data()
        assert etree.fromstring(xml).findtext(f'{{{NS}}}codigo') == 'x'  # el error sí se desenvuelve


def test_compatible_json():
    uid = UUID('3122a5b1-a074-4d57-8fce-7aa9e5fc9743')
    assert compatible_json({'a': [Decimal('1.5'), date(2026, 1, 2), uid]}) == {'a': [1.5, '2026-01-02', str(uid)]}


def test_horas_en_json_y_xml():
    """Regresión: el horario del comercio (time) tiraba un 500 al responder el detalle."""
    assert compatible_json({'abre': time(7, 0)}) == {'abre': '07:00:00'}
    assert etree.fromstring(a_xml({'abre': time(7, 0)}, 'comercio')).findtext(f'{{{NS}}}abre') == '07:00:00'


def test_leer_xml_respeta_listas_declaradas():
    cuerpo = (f'<pedido_entrada xmlns="{NS}"><comercio_id>c1</comercio_id>'
              f'<partidas><partida><producto_id>3</producto_id><cantidad>2</cantidad></partida></partidas>'
              f'</pedido_entrada>').encode()
    datos = leer_xml(cuerpo, raiz='pedido_entrada', listas={'partidas'})
    # Una sola partida sigue siendo lista porque el campo es lista en el modelo
    assert datos == {'comercio_id': 'c1', 'partidas': [{'producto_id': '3', 'cantidad': '2'}]}


def test_leer_xml_rechaza_raiz_equivocada():
    with pytest.raises(ValueError, match='Se esperaba el elemento raíz <pedido_entrada'):
        leer_xml(f'<otra xmlns="{NS}"/>'.encode(), raiz='pedido_entrada')


def test_leer_xml_rechaza_xml_mal_formado():
    with pytest.raises(ValueError, match='XML mal formado'):
        leer_xml(b'<pedido_entrada><sin_cerrar></pedido_entrada>')


def test_leer_xml_no_resuelve_entidades_externas():
    """XXE: una entidad que apunta a un archivo local no debe leerse."""
    malicioso = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                 b'<login xmlns="' + NS.encode() + b'"><email>&x;</email></login>')
    try:
        datos = leer_xml(malicioso, raiz='login')
    except ValueError:
        return  # rechazado: también es correcto
    assert 'root:' not in (datos.get('email') or '')
