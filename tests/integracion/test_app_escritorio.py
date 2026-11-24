"""
Aplicación de escritorio (apps/escritorio): cliente XML contra el sistema real y sus pantallas.

El cliente solo habla XML por el gateway y valida petición y respuesta con el XSD de cada servicio.
Las pruebas de pantallas abren la ventana sin mostrarla (Qt offscreen) y comprueban que cada módulo
carga sus datos sin errores; no aplican donde no está instalado PySide6 (p. ej. el contenedor de pruebas).
"""
import os
import sys
import time

import pytest

from apoyo import HOST, MODO, RAIZ

sys.path.insert(0, str(RAIZ / 'apps' / 'escritorio'))

from abastored_escritorio.cliente import Cliente, ErrorServicio  # noqa: E402

pytestmark = pytest.mark.skipif(MODO != 'gateway', reason='No aplica: la app de escritorio entra por el gateway HTTPS')


def _cliente(email, clave='Password123!'):
    cliente = Cliente(gateway=HOST)
    for _ in range(3):
        try:
            cliente.iniciar_sesion(email, clave)
            return cliente
        except ErrorServicio as error:
            if error.status != 429:
                raise
            time.sleep(31)
    raise AssertionError(f'No se pudo iniciar sesión con {email}')


@pytest.fixture(scope='module')
def coordinador():
    return _cliente('coordinador@test.mx')


@pytest.fixture(scope='module')
def proveedor():
    return _cliente('proveedor@test.mx')


def test_login_xml_y_permisos_del_rol(coordinador):
    assert coordinador.usuario['rol'] == 'Coordinador Municipal'
    assert coordinador.puede('comercios.validar') and not coordinador.puede('pedidos.atender')
    assert coordinador.segundos_restantes() > 3600


def test_errores_llegan_como_contrato_xml(coordinador):
    with pytest.raises(ErrorServicio) as error:
        coordinador.get('pedidos', '/pedidos')
    assert error.value.status == 403 and error.value.codigo == 'sin_permiso' and error.value.correlation_id


def test_validar_un_comercio_en_xml(coordinador):
    pendientes = coordinador.get('comercios', '/comercios', estado_registro='PENDIENTE', por_pagina=100).datos['items']
    if not pendientes:
        pytest.skip('Omitida: no hay comercios pendientes de validar')
    comercio = pendientes[-1]
    r = coordinador.peticion('comercios', 'PATCH', f"/comercios/{comercio['id']}/validacion", raiz='validacion_entrada',
                             datos={'estado': 'VERIFICADO', 'observaciones': 'Revisado desde la app de escritorio'})
    assert r.datos['estado_registro'] == 'VERIFICADO'
    assert r.correlation_id.startswith('escritorio-')


def test_reporte_pdf_se_descarga(coordinador):
    r = coordinador.peticion('reportes', 'POST', '/reportes', raiz='reporte_entrada',
                             datos={'tipo': 'cobertura', 'formato': 'pdf', 'filtros': {}})
    archivo = coordinador.peticion('reportes', 'GET', f"/reportes/{r.datos['id']}/archivo", binario=True)
    assert archivo.tipo == 'application/pdf' and archivo.contenido.startswith(b'%PDF')


def test_importacion_simulada_del_catalogo(proveedor):
    plantilla = proveedor.peticion('integraciones', 'GET', '/plantillas/catalogo_proveedor', params={'archivo': 'csv'},
                                   binario=True)
    contenido = plantilla.contenido + b'999999,,,10,1,5\r\n'      # una fila con un producto que no existe
    r = proveedor.peticion('integraciones', 'POST', '/importaciones', files={'archivo': ('catalogo.csv', contenido)},
                           form={'destino': 'catalogo_proveedor', 'simulacion': 'true'})
    lote = r.datos
    assert lote['simulacion'] is True and lote['filas'] == 2 and lote['con_error'] >= 1
    assert isinstance(lote['errores'], list)


def test_el_token_vencido_se_renueva_solo():
    cliente = _cliente('analista@test.mx')
    cliente.tokens['access_token'] = cliente.tokens['access_token'][:-4] + 'AAAA'   # firma inválida -> 401
    zonas = cliente.get('geolocalizacion', '/zonas').datos['zonas']
    assert zonas and isinstance(zonas[0]['id'], int)
    assert cliente.get('analisis', '/analisis/zonas').status == 200       # ya con el token renovado


# ---------------------------------------------------------------- pantallas (Qt sin mostrar ventanas)

@pytest.fixture(scope='module')
def qt():
    pytest.importorskip('PySide6', reason='No aplica: PySide6 no está instalado en este ambiente')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('email, modulos', [
    ('coordinador@test.mx', {'Validación de comercios', 'Verificación de proveedores', 'Precios', 'Cobertura y brechas',
                             'Reportes', 'Mi actividad'}),
    ('proveedor@test.mx', {'Pedidos recibidos', 'Precios', 'Importar archivos', 'Reportes', 'Mi actividad'}),
])
def test_cada_rol_ve_sus_modulos_y_cargan_sin_errores(qt, tmp_path, monkeypatch, email, modulos):
    from PySide6.QtCore import QThreadPool

    from abastored_escritorio.bitacora import Bitacora
    from abastored_escritorio.ui import comun, principal

    errores = []
    monkeypatch.setattr(comun, 'mostrar_error', lambda _padre, error: errores.append(error))
    bitacora = Bitacora(tmp_path / 'bitacora.sqlite3')
    cliente = _cliente(email)
    cliente.al_registrar = bitacora.peticion
    ventana = principal.VentanaPrincipal(cliente, bitacora)
    assert {ventana.menu.item(i).text() for i in range(ventana.menu.count())} == modulos
    for i in range(ventana.menu.count()):
        ventana.menu.setCurrentRow(i)
        limite = time.time() + 30
        while time.time() < limite:
            qt.processEvents()
            if QThreadPool.globalInstance().activeThreadCount() == 0:
                qt.processEvents()
                break
            time.sleep(0.05)
    ventana.close()
    assert not errores, errores
    assert any(r['tipo'] == 'peticion' and r['status'] == 200 for r in bitacora.recientes())
