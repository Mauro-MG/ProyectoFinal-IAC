"""
Servicios de la entrega final (8109-8124) y su integración con los originales.

Cada prueba recorre un flujo de negocio a través de varios servicios y comprueba que el dato
cambió SÓLO en el servicio dueño (p. ej. una venta descuenta el inventario por la API de
ms-inventario y la traza en ms-auditoria muestra ambos servicios).
"""
import io
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

from abasto_dominio.registro_servicios import NOMBRES
from apoyo import url


@pytest.fixture(scope='module')
def minorista(api):
    return api('minorista')


@pytest.fixture(scope='module')
def comercio(minorista):
    return next(c for c in minorista.get('comercios', '/comercios').json()['items'] if c['zona_id'])


def renglon_con_existencia(minorista, comercio, minimo=3):
    renglones = minorista.get('inventario', f"/comercios/{comercio['id']}/inventario",
                              params={'por_pagina': 200}).json()['renglones']
    return next(r for r in renglones if r['existencia'] >= minimo and r['precio_venta'])


# ---------------------------------------------------------------- ms-monitoreo

def test_monitoreo_ve_los_24_servicios_arriba(api):
    """El registro único tiene 24 servicios y todos responden su /health con sus tres bases."""
    r = api('admin').get('monitoreo', '/estado', timeout=30)
    assert r.status_code == 200, r.text[:300]
    datos = r.json()
    assert datos['total'] == len(NOMBRES) == 24
    caidos = [s['servicio'] for s in datos['servicios'] if s['estado'] != 'ok']
    assert not caidos, caidos


def test_monitoreo_bases_y_metricas(api):
    admin = api('admin')
    bases = {b['nombre']: b for b in admin.get('monitoreo', '/bases-datos').json()['bases']}
    assert {bases[n]['estado'] for n in ('postgres', 'mongodb', 'redis')} == {'ok'}
    metricas = admin.get('monitoreo', '/metricas', params={'horas': 1}).json()['servicios']
    assert any(m['servicio'] == 'seguridad' and m['peticiones'] > 0 for m in metricas)
    r = admin.post('monitoreo', '/alertas/evaluaciones', timeout=30)
    assert r.status_code == 200 and r.json()['nuevas'] == 0, r.text[:300]


# ---------------------------------------------------------------- ms-ventas + ms-inventario + ms-auditoria

def test_venta_descuenta_inventario_y_se_rastrea(minorista, comercio, api):
    renglon = renglon_con_existencia(minorista, comercio)
    id_cliente = str(uuid.uuid4())
    r = minorista.post('ventas', '/ventas', json={
        'comercio_id': comercio['id'], 'metodo_pago': 'EFECTIVO', 'origen': 'android', 'id_cliente': id_cliente,
        'partidas': [{'inventario_id': renglon['id'], 'cantidad': 1}]})
    assert r.status_code == 201, r.text
    venta = r.json()
    assert venta['folio'].startswith('V-') and venta['total'] > 0
    correlation_id = r.headers['X-Correlation-ID']

    despues = minorista.get('inventario', f"/inventario/{renglon['id']}").json()
    assert despues['existencia'] == renglon['existencia'] - 1
    assert despues['movimientos'][0]['referencia'] == f"venta:{venta['id']}#1"

    # La misma venta reenviada desde la app no se registra ni descuenta otra vez
    r = minorista.post('ventas', '/ventas', json={
        'comercio_id': comercio['id'], 'id_cliente': id_cliente, 'partidas': [{'inventario_id': renglon['id'], 'cantidad': 1}]})
    assert r.status_code == 200 and r.json()['duplicada'] is True
    assert minorista.get('inventario', f"/inventario/{renglon['id']}").json()['existencia'] == despues['existencia']

    # Devolución: regresa al inventario por ms-inventario
    r = minorista.post('ventas', f"/ventas/{venta['id']}/devoluciones", json={'motivo': 'Prueba de devolución'})
    assert r.status_code == 201 and r.json()['estado'] == 'DEVUELTA', r.text
    assert minorista.get('inventario', f"/inventario/{renglon['id']}").json()['existencia'] == renglon['existencia']

    # Traza distribuida: la petición pasó por ms-ventas y ms-inventario y ambos registraron sus cambios
    traza = api('auditor').get('auditoria', f'/trazas/{correlation_id}').json()
    assert {'ms-ventas', 'ms-inventario'} <= set(traza['servicios']), traza['servicios']
    entidades = {p['entidad'] for p in traza['pasos'] if p['tipo'] == 'evento'}
    assert {'Venta', 'InventarioComercio'} <= entidades

    comprobante = minorista.get('ventas', f"/ventas/{venta['id']}/comprobante").json()
    assert len(comprobante['huella_sha256']) == 64 and 'sin validez fiscal' in comprobante['texto']


def test_venta_sin_existencia_no_se_registra(minorista, comercio):
    renglon = renglon_con_existencia(minorista, comercio, minimo=0)
    r = minorista.post('ventas', '/ventas', json={
        'comercio_id': comercio['id'], 'partidas': [{'inventario_id': renglon['id'], 'cantidad': renglon['existencia'] + 1000}]})
    assert r.status_code == 409 and r.json()['error']['codigo'] == 'inventario_insuficiente'
    assert minorista.get('inventario', f"/inventario/{renglon['id']}").json()['existencia'] == renglon['existencia']


def test_reserva_impide_vender_lo_apartado(minorista, comercio):
    renglon = renglon_con_existencia(minorista, comercio)
    r = minorista.post('inventario', f"/inventario/{renglon['id']}/reservas",
                       json={'cantidad': renglon['existencia'], 'motivo': 'Prueba', 'minutos': 5})
    assert r.status_code == 201, r.text
    reserva = r.json()
    try:
        r = minorista.post('inventario', f"/inventario/{renglon['id']}/movimientos",
                           json={'tipo': 'SALIDA', 'cantidad': 1, 'motivo': 'Prueba con reserva'})
        assert r.status_code == 409 and 'reservad' in r.json()['error']['mensaje']
    finally:
        assert minorista.delete('inventario', f"/reservas/{reserva['id']}").status_code == 200


# ---------------------------------------------------------------- ms-sincronizacion

def test_lote_offline_con_duplicados_y_conflicto(minorista, comercio):
    renglon = renglon_con_existencia(minorista, comercio)
    lote = {'lote_id': str(uuid.uuid4()), 'dispositivo_id': 'pruebas-integracion', 'plataforma': 'android',
            'operaciones': [
                {'operacion_id': str(uuid.uuid4()), 'tipo': 'movimiento_inventario',
                 'realizada': datetime.now(timezone.utc).isoformat(),
                 'datos': {'inventario_id': renglon['id'], 'tipo_movimiento': 'ENTRADA', 'cantidad': 2,
                           'motivo': 'Recibido sin conexión'}},
                {'operacion_id': str(uuid.uuid4()), 'tipo': 'precio',
                 'realizada': datetime.now(timezone.utc).isoformat(),
                 'version_base': (datetime.now(timezone.utc) - timedelta(days=3650)).isoformat(),
                 'datos': {'inventario_id': renglon['id'], 'precio': 1.11}},
            ]}
    r = minorista.post('sincronizacion', '/lotes', json=lote)
    assert r.status_code == 200, r.text
    resultado = {o['tipo']: o for o in r.json()['resultados']}
    assert resultado['movimiento_inventario']['estado'] == 'aplicada'
    # El renglón cambió en el servidor después de version_base: gana el servidor
    assert resultado['precio']['estado'] == 'conflicto'

    # Reenviar el mismo lote no vuelve a aplicar la entrada
    existencia = minorista.get('inventario', f"/inventario/{renglon['id']}").json()['existencia']
    r = minorista.post('sincronizacion', '/lotes', json=lote)
    assert r.status_code == 200
    assert minorista.get('inventario', f"/inventario/{renglon['id']}").json()['existencia'] == existencia
    assert minorista.get('sincronizacion', f"/lotes/{lote['lote_id']}").json()['aplicadas'] == 1


# ---------------------------------------------------------------- ms-documentos

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


def test_documento_valida_tipo_real_y_control_de_acceso(minorista, comercio, api):
    datos = {'categoria': 'foto_comercio', 'entidad': 'comercio', 'entidad_id': comercio['id']}
    falso = minorista.post('documentos', '/documentos', data=datos,
                           files={'archivo': ('foto.png', io.BytesIO(b'MZ\x90\x00 no soy imagen'), 'image/png')})
    assert falso.status_code == 415 and falso.json()['error']['codigo'] == 'tipo_no_coincide'

    r = minorista.post('documentos', '/documentos', data=datos,
                       files={'archivo': ('fachada.png', io.BytesIO(PNG), 'image/png')})
    assert r.status_code == 201, r.text
    documento = r.json()
    assert minorista.get('documentos', f"/documentos/{documento['id']}/contenido").content == PNG
    # Otro comerciante no lo ve; la coordinación municipal sí (comercios.ver_todos)
    assert api('comerciante').get('documentos', f"/documentos/{documento['id']}").status_code == 403
    assert api('coordinador').get('documentos', f"/documentos/{documento['id']}").status_code == 200

    r = minorista.put('comercios', f"/comercios/{comercio['id']}/foto", json={'documento_id': documento['id']})
    assert r.status_code == 200 and documento['id'] in r.json()['foto_url']


# ---------------------------------------------------------------- ms-geolocalizacion, ms-busqueda, ms-demanda

def test_geocodificacion_y_cercanos(api):
    r = requests.get(url('geolocalizacion', '/geocodificar'),
                     params={'direccion': 'Calle Hidalgo 200, col. Obispado', 'municipio': 'Monterrey'}, timeout=10)
    assert r.status_code == 200 and r.json()['colonia']['nombre'] == 'Obispado', r.text
    r = requests.post(url('geolocalizacion', '/coordenadas/validacion'), json={'latitud': 0, 'longitud': 0}, timeout=10)
    assert r.status_code == 200 and r.json()['valida'] is False
    zona = requests.get(url('geolocalizacion', '/zonas'), timeout=10).json()['zonas'][0]
    r = api('analista').get('geolocalizacion', '/cercanos', params={
        'latitud': zona['latitud_centro'], 'longitud': zona['longitud_centro'], 'radio_km': 5})
    assert r.status_code == 200 and r.json()['total'] >= 1
    distancias = [c['distancia_km'] for c in r.json()['resultados']]
    assert distancias == sorted(distancias)


def test_busqueda_unificada_y_demanda_no_satisfecha(api):
    r = requests.get(url('busqueda', '/buscar'), params={'q': 'ARROZ'}, timeout=10)
    assert r.status_code == 200 and r.json()['conteos']['productos'] >= 1
    assert r.json()['resultados'][0]['relevancia'] >= 60
    sugerencias = requests.get(url('busqueda', '/sugerencias'), params={'q': 'arr'}, timeout=10).json()
    assert any('Arroz' in s['texto'] for s in sugerencias['sugerencias'])

    inexistente = f'producto-inexistente-{uuid.uuid4().hex[:6]}'
    requests.get(url('busqueda', '/buscar'), params={'q': inexistente, 'tipo': 'productos'}, timeout=10)
    faltantes = api('analista').get('demanda', '/demanda/no-satisfecha', params={'dias': 1, 'limite': 200}).json()
    assert any(p['texto'] == inexistente for p in faltantes['productos'])


def test_estimacion_de_demanda(api):
    r = api('analista').get('demanda', '/demanda/estimacion', params={'producto_id': 1, 'horizonte_dias': 7})
    assert r.status_code == 200, r.text
    assert len(r.json()['estimacion']) == 7 and all(p['minimo'] <= p['unidades'] <= p['maximo']
                                                     for p in r.json()['estimacion'])


# ---------------------------------------------------------------- ms-configuracion

def test_configuracion_valida_rango_y_publica_parametros(api):
    admin = api('admin')
    r = admin.put('configuracion', '/parametros/COMISION_PEDIDO_PCT', json={'valor': '150'})
    assert r.status_code == 422 and r.json()['error']['codigo'] == 'fuera_de_rango'
    publicos = requests.get(url('configuracion', '/parametros/publicos'), timeout=10).json()
    assert 'APP_VERSION' in {p['clave'] for p in publicos['parametros']}
    assert api('minorista').get('configuracion', '/parametros').status_code == 403


# ---------------------------------------------------------------- ms-reportes, ms-integraciones

def test_reporte_excel_del_inventario(minorista, comercio):
    r = minorista.post('reportes', '/reportes', json={'tipo': 'inventario', 'formato': 'xlsx',
                                                      'filtros': {'comercio_id': comercio['id']}}, timeout=30)
    assert r.status_code == 201, r.text
    archivo = minorista.get('reportes', f"/reportes/{r.json()['id']}/archivo")
    assert archivo.status_code == 200 and archivo.content[:2] == b'PK'   # .xlsx es un ZIP


def test_importacion_simulada_reporta_errores_por_fila(minorista, comercio):
    csv = ('producto,existencia,stock_minimo,precio_venta\n'
           'Arroz blanco 1 kg,20,5,32.50\n'
           'Producto que no existe,5,1,10\n'
           'Arroz blanco 1 kg,-3,1,32\n').encode()
    r = minorista.post('integraciones', '/importaciones', timeout=30,
                       data={'destino': 'inventario', 'comercio_id': comercio['id'], 'simulacion': 'true'},
                       files={'archivo': ('inventario.csv', io.BytesIO(csv), 'text/csv')})
    assert r.status_code == 201, r.text
    lote = r.json()
    assert (lote['filas'], lote['validas'], lote['aplicadas'], lote['con_error']) == (3, 1, 0, 2)
    assert {e['fila'] for e in lote['errores']} == {3, 4}


# ---------------------------------------------------------------- ms-proveedores, ms-abastecimiento

def test_cotizacion_consolidada_hasta_pedido(minorista, comercio, api):
    """Solicitud consolidada -> cotización del proveedor -> comparación -> adjudicación -> orden -> pedido."""
    renglon = renglon_con_existencia(minorista, comercio, minimo=0)
    ofertas = minorista.get('proveedores', '/ofertas', params={'producto_id': renglon['producto_id'],
                                                               'zona_id': comercio['zona_id']}).json()['ofertas']
    oferta = next((o for o in ofertas if o['cubre_zona'] and o['proveedor'].startswith('Distribuidora Regia')), None)
    if not oferta:
        pytest.skip('Omitida: la Distribuidora Regia no ofrece ese producto en la zona del comercio')
    cantidad = max(oferta['cantidad_minima'], round(oferta['pedido_minimo'] / oferta['precio_mayoreo']) + 1)
    r = minorista.post('abastecimiento', '/solicitudes', json={
        'comercio_id': comercio['id'], 'titulo': 'Prueba de integración', 'consolidada': True,
        'necesidades': [{'producto_id': renglon['producto_id'], 'cantidad': cantidad}]})
    assert r.status_code == 201, r.text
    solicitud = r.json()

    proveedor = api('dueno_regia')
    r = proveedor.post('abastecimiento', f"/solicitudes/{solicitud['id']}/cotizaciones", json={
        'tiempo_entrega_dias': 1, 'vigencia': (date.today() + timedelta(days=5)).isoformat(),
        'partidas': [{'producto_id': renglon['producto_id'], 'precio_unitario': oferta['precio_mayoreo'],
                      'cantidad_disponible': cantidad * 2}]})
    assert r.status_code == 201, r.text
    cotizacion = r.json()

    comparacion = minorista.get('abastecimiento', f"/solicitudes/{solicitud['id']}/comparacion").json()
    assert comparacion['cotizaciones'][0]['cotizacion_id'] == cotizacion['id']
    assert comparacion['cotizaciones'][0]['cobertura_pct'] == 100

    r = minorista.post('abastecimiento', f"/solicitudes/{solicitud['id']}/adjudicacion",
                       json={'cotizacion_id': cotizacion['id']})
    assert r.status_code == 201, r.text
    orden = r.json()['ordenes'][0]
    r = minorista.post('abastecimiento', f"/ordenes/{orden['id']}/pedido")
    assert r.status_code == 200 and r.json()['estado'] == 'CONVERTIDA', r.text
    pedido = minorista.get('pedidos', f"/pedidos/{r.json()['pedido_id']}").json()
    assert pedido['estado'] == 'BORRADOR' and pedido['proveedor_id'] == oferta['proveedor_id']


def test_proveedor_no_verificado_no_aparece_a_comercios(api):
    proveedores = api('minorista').get('proveedores', '/proveedores', params={'por_pagina': 100}).json()['proveedores']
    assert proveedores and all(p['estado_verificacion'] == 'VERIFICADO' for p in proveedores)
    assert api('coordinador').get('proveedores', '/proveedores', params={'estado_verificacion': 'PENDIENTE'}).status_code == 200


# ---------------------------------------------------------------- ms-entregas + ms-pedidos + ms-proveedores + ms-inventario

def test_entrega_con_qr_mueve_existencias_en_los_servicios_duenos(minorista, comercio, api):
    """Pedido aceptado -> entrega programada -> salida (ms-proveedores descuenta su existencia) -> confirmación con
    el código QR (ms-pedidos recibe y ms-inventario da la entrada) -> evaluación del proveedor."""
    proveedor = api('dueno_regia')
    renglones = minorista.get('inventario', f"/comercios/{comercio['id']}/inventario",
                              params={'por_pagina': 200}).json()['renglones']
    oferta = renglon = None
    for r in renglones:
        ofertas = minorista.get('proveedores', '/ofertas', params={'producto_id': r['producto_id'],
                                                                   'zona_id': comercio['zona_id']}).json()['ofertas']
        oferta = next((o for o in ofertas if o['cubre_zona'] and o['proveedor'].startswith('Distribuidora Regia')
                       and o['existencia_disponible'] >= max(o['cantidad_minima'],
                                                             o['pedido_minimo'] / o['precio_mayoreo'] + 1)), None)
        if oferta:
            renglon = r
            break
    if not oferta:
        pytest.skip('Omitida: la Distribuidora Regia no tiene existencia suficiente para un pedido de prueba')
    cantidad = max(oferta['cantidad_minima'], int(oferta['pedido_minimo'] / oferta['precio_mayoreo']) + 1)
    # ms-pedidos reutiliza el borrador abierto entre el comercio y el proveedor: se cancela el que haya dejado otra prueba
    borradores = minorista.get('pedidos', '/pedidos', params={'estado': 'BORRADOR', 'comercio_id': comercio['id'],
                                                              'por_pagina': 100}).json()['pedidos']
    for b in borradores:
        if b['proveedor_id'] == oferta['proveedor_id']:
            minorista.post('pedidos', f"/pedidos/{b['id']}/acciones/cancelar", json={'comentario': 'Limpieza de prueba'})
    r = minorista.post('pedidos', '/pedidos', json={'comercio_id': comercio['id'], 'proveedor_id': oferta['proveedor_id'],
                                                    'partidas': [{'producto_id': oferta['producto_id'], 'cantidad': cantidad}]})
    assert r.status_code == 201, r.text
    pedido = r.json()
    assert [p['cantidad'] for p in pedido['partidas']] == [cantidad], pedido['partidas']
    assert minorista.post('pedidos', f"/pedidos/{pedido['id']}/acciones/enviar").status_code == 200, pedido
    assert proveedor.post('pedidos', f"/pedidos/{pedido['id']}/acciones/aceptar").status_code == 200

    r = proveedor.post('entregas', '/entregas', json={'pedido_id': pedido['id'], 'responsable_nombre': 'Repartidor prueba',
                                                      'vehiculo': 'NL-00-000'})
    assert r.status_code == 201 and r.json()['estado'] == 'ASIGNADA', r.text
    entrega = r.json()
    codigo = proveedor.get('entregas', f"/entregas/{entrega['id']}/qr").json()['codigo']
    assert minorista.get('entregas', f"/entregas/{entrega['id']}/qr").status_code == 403   # el comercio no ve el código

    r = proveedor.post('entregas', f"/entregas/{entrega['id']}/salida", json={'comentario': 'Sale de bodega'})
    assert r.status_code == 200 and r.json()['estado'] == 'EN_RUTA', r.text
    assert r.json()['estado_pedido'] == 'ENVIADO_A_COMERCIO'
    despues = minorista.get('proveedores', '/ofertas', params={'producto_id': oferta['producto_id']}).json()['ofertas']
    assert next(o for o in despues if o['id'] == oferta['id'])['existencia_disponible'] == oferta['existencia_disponible'] - cantidad

    malo = minorista.post('entregas', f"/entregas/{entrega['id']}/confirmacion",
                          json={'codigo': 'ZZZZZZZZ', 'recibido_por': 'Encargada'})
    assert malo.status_code == 422
    r = minorista.post('entregas', f"/entregas/{entrega['id']}/confirmacion",
                       json={'codigo': codigo, 'recibido_por': 'Encargada', 'comentario': 'Completo'})
    assert r.status_code == 200 and r.json()['estado'] == 'ENTREGADA', r.text
    assert r.json()['estado_pedido'] == 'ENTREGADO'
    actual = minorista.get('inventario', f"/inventario/{renglon['id']}").json()
    entrada = next(m for m in actual['movimientos'] if m['referencia'] and m['referencia'].startswith(f"pedido:{pedido['id']}"))
    assert entrada['tipo'] == 'ENTRADA' and entrada['pedido_id'] == pedido['id']

    r = minorista.post('proveedores', f"/proveedores/{oferta['proveedor_id']}/evaluaciones",
                       json={'pedido_id': pedido['id'], 'calificacion': 5, 'puntualidad': 5, 'comentario': 'Prueba'})
    assert r.status_code == 201, r.text
    assert minorista.post('proveedores', f"/proveedores/{oferta['proveedor_id']}/evaluaciones",
                          json={'pedido_id': pedido['id'], 'calificacion': 4}).status_code == 409
