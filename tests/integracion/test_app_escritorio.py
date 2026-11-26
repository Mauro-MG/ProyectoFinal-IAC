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

from apoyo import HOST, MODO, RAIZ, sesion_de

sys.path.insert(0, str(RAIZ / 'apps' / 'escritorio'))

from abastored_escritorio.cliente import Cliente, ContratoInvalido, ErrorServicio  # noqa: E402

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


@pytest.mark.parametrize('email, clave, modulos', [
    ('coordinador@test.mx', 'Password123!', {'Validación de comercios', 'Verificación de proveedores', 'Precios',
                                             'Cobertura y brechas', 'Recomendaciones de surtido', 'Reportes',
                                             'Mi actividad'}),
    ('proveedor@test.mx', 'Password123!', {'Pedidos recibidos', 'Precios', 'Importar archivos', 'Reportes',
                                           'Mi actividad'}),
    ('admin@abastored.mx', 'Admin123!', {'Validación de comercios', 'Verificación de proveedores', 'Precios',
                                         'Cobertura y brechas', 'Recomendaciones de surtido', 'Catálogo maestro',
                                         'Configuración de zonas', 'Importar archivos', 'Reportes', 'Mi actividad'}),
])
def test_cada_rol_ve_sus_modulos_y_cargan_sin_errores(qt, tmp_path, monkeypatch, email, clave, modulos):
    from PySide6.QtCore import QThreadPool

    from abastored_escritorio.bitacora import Bitacora
    from abastored_escritorio.ui import comun, principal

    errores = []
    monkeypatch.setattr(comun, 'mostrar_error', lambda _padre, error: errores.append(error))
    bitacora = Bitacora(tmp_path / 'bitacora.sqlite3')
    cliente = _cliente(email, clave)
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


# ---------------------------------------------------------------- administración desde el escritorio (XML)

@pytest.fixture(scope='module')
def administrador():
    return _cliente('admin@abastored.mx', 'Admin123!')


def test_catalogo_alta_edicion_y_baja_de_producto_en_xml(administrador):
    import uuid
    categorias = administrador.get('catalogo', '/categorias', incluir_inactivas='true').datos['categorias']
    nombre = f'Producto escritorio {uuid.uuid4().hex[:6]}'
    datos = {'nombre': nombre, 'categoria_id': categorias[0]['id'], 'unidad_medida': 'pieza', 'codigo_barras': None,
             'es_canasta_basica': False, 'descripcion': 'Alta desde la app de escritorio', 'marca_id': None,
             'clave_estandar': None}
    alta = administrador.peticion('catalogo', 'POST', '/productos', raiz='producto_entrada', datos=datos)
    assert alta.status == 201 and alta.datos['nombre'] == nombre
    cambio = administrador.peticion('catalogo', 'PUT', f"/productos/{alta.datos['id']}", raiz='producto_entrada',
                                    datos={**datos, 'unidad_medida': 'kg'})
    assert cambio.datos['unidad_medida'] == 'kg'
    with pytest.raises(ErrorServicio) as repetido:     # la regla de negocio la aplica ms-catalogo
        administrador.peticion('catalogo', 'POST', '/productos', raiz='producto_entrada',
                               datos={**datos, 'unidad_medida': 'kg'})
    assert repetido.value.status == 409
    assert administrador.peticion('catalogo', 'DELETE', f"/productos/{alta.datos['id']}").status == 200


def test_categoria_se_desactiva_y_se_reactiva(administrador):
    categorias = administrador.get('catalogo', '/categorias', incluir_inactivas='true').datos['categorias']
    ultima = categorias[-1]
    r = administrador.peticion('catalogo', 'PATCH', f"/categorias/{ultima['id']}", raiz='categoria_cambio',
                               datos={'activa': False})
    assert r.datos['activa'] is False
    assert ultima['id'] not in {c['id'] for c in administrador.get('catalogo', '/categorias').datos['categorias']}
    r = administrador.peticion('catalogo', 'PATCH', f"/categorias/{ultima['id']}", raiz='categoria_cambio',
                               datos={'activa': True})
    assert r.datos['activa'] is True


def test_configuracion_de_zona_en_xml(administrador):
    import uuid
    nombre = f'Zona escritorio {uuid.uuid4().hex[:5]}'
    alta = administrador.peticion('geolocalizacion', 'POST', '/zonas', raiz='zona_entrada', datos={
        'nombre': nombre, 'municipio': 'Apodaca', 'estado': 'Nuevo León', 'latitud_centro': 25.79,
        'longitud_centro': -100.18, 'radio_km': 1.5, 'poblacion': 12000})
    assert alta.status == 201
    cambio = administrador.peticion('geolocalizacion', 'PATCH', f"/zonas/{alta.datos['id']}", raiz='zona_cambio',
                                    datos={'radio_km': 2.0, 'activa': False})
    assert cambio.datos['radio_km'] == 2.0
    todas = administrador.get('geolocalizacion', '/zonas', incluir_inactivas='true').datos['zonas']
    assert any(z['id'] == alta.datos['id'] and z['activa'] is False for z in todas)
    # El radio máximo (20 km) está en el XSD: el cliente rechaza la petición antes de enviarla
    with pytest.raises(ContratoInvalido, match='radio_km'):
        administrador.peticion('geolocalizacion', 'POST', '/zonas', raiz='zona_entrada', datos={
            'nombre': nombre + 'x', 'municipio': 'Apodaca', 'latitud_centro': 25.79, 'longitud_centro': -100.18,
            'radio_km': 50, 'poblacion': 1})


def test_exportar_e_imprimir_oportunidades(qt, tmp_path, monkeypatch):
    """Exportación específica de oportunidades de abasto a PDF y CSV, auditada en ms-auditoria."""
    from abastored_escritorio.bitacora import Bitacora
    from abastored_escritorio.ui import comun
    from abastored_escritorio.ui.cobertura import OPORTUNIDADES, Cobertura

    errores = []
    monkeypatch.setattr(comun, 'mostrar_error', lambda _padre, error: errores.append(error))
    analista = _cliente('analista@test.mx')
    pantalla = Cobertura(analista, Bitacora(tmp_path / 'b.sqlite3'))
    datos = analista.get('analisis', '/analisis/oportunidades', limite=20).datos['oportunidades']
    assert datos, 'no hay oportunidades de abasto en los datos de prueba'
    pantalla.oportunidades.cambiar(datos)
    pdf = pantalla.guardar(str(tmp_path / 'oportunidades.pdf'), 'Oportunidades de abasto', OPORTUNIDADES,
                           pantalla.oportunidades, 'pdf')
    csv_ = pantalla.guardar(str(tmp_path / 'oportunidades.csv'), 'Oportunidades de abasto', OPORTUNIDADES,
                            pantalla.oportunidades, 'csv')
    assert open(pdf, 'rb').read(4) == b'%PDF'
    lineas = open(csv_, encoding='utf-8-sig').read().splitlines()
    assert lineas[0].startswith('Zona,Producto') and len(lineas) == len(datos) + 1
    documento = comun.documento_tabla('Oportunidades de abasto', OPORTUNIDADES, datos)
    assert 'Oportunidades de abasto' in documento.toPlainText() and documento.pageCount() >= 1
    import time as _t
    from PySide6.QtCore import QThreadPool
    limite = _t.time() + 20
    while QThreadPool.globalInstance().activeThreadCount() and _t.time() < limite:
        qt.processEvents()
        _t.sleep(0.05)
    qt.processEvents()
    assert not errores, errores
    eventos = sesion_de('auditor').get('auditoria', '/eventos', params={'entidad': 'Oportunidadesdeabasto',
                                                                         'por_pagina': 5}).json()
    assert any('escritorio' in (e.get('servicio') or '') or 'PDF' in e['descripcion'] for e in eventos['eventos'])
