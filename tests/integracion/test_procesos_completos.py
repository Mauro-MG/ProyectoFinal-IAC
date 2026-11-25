"""
Tres procesos completos de punta a punta. Cada uno pasa por: un usuario con su rol, la app cliente con su
formato (Android JSON, escritorio XML, web), varios microservicios, Redis (sesión y contador de avisos),
PostgreSQL y MongoDB, auditoría, una notificación y un resultado visible; y por el bucket cuando hay archivos.

  1. Alta de un comercio: registro desde la app -> comercio con ubicación (zona por PostGIS) -> foto al bucket ->
     el coordinador lo valida desde el escritorio (XML) -> aviso al comerciante -> rastro en auditoría.
  2. Abasto: inventario bajo -> recomendación -> oferta de un proveedor -> pedido -> el proveedor acepta y despacha
     con QR -> el comercio confirma -> el inventario sube -> avisos y auditoría del pedido.
  3. Datos y análisis: el minorista importa su inventario en CSV (archivo al bucket) -> aviso -> el analista
     consulta brechas y concentraciones (XML) -> genera el reporte PDF en el bucket -> lo descarga con URL firmada.

No detiene nada: también corre contra el despliegue en Google Cloud. Con PROCESOS_EVIDENCIA=1 guarda cada paso
(servicio, formato, código HTTP y correlation_id) en docs/evidencias/procesos/.
"""
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import requests

from apoyo import HOST, RAIZ, Api, sesion_de, url

PASOS = {}
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
XML = {'Accept': 'application/xml'}


def paso(proceso, actor, cliente, descripcion, respuesta, resultado=''):
    PASOS.setdefault(proceso, []).append({
        'actor': actor, 'cliente': cliente, 'paso': descripcion, 'metodo': respuesta.request.method,
        'ruta': re.sub(r'^https?://[^/]+', '', respuesta.request.url).split('?')[0], 'status': respuesta.status_code,
        'correlation_id': respuesta.headers.get('X-Correlation-ID'), 'resultado': resultado})
    return respuesta


def _avisos(api, tipo):
    return api.get('notificaciones', '/notificaciones', params={'tipo': tipo, 'por_pagina': 5}).json()


@pytest.fixture(scope='module', autouse=True)
def guardar_evidencia():
    yield
    if os.environ.get('PROCESOS_EVIDENCIA') != '1' or not PASOS:
        return
    destino = RAIZ / 'docs' / 'evidencias' / 'procesos'
    destino.mkdir(parents=True, exist_ok=True)
    ambiente = 'gcp' if '34.135.84.31' in HOST else 'local'
    (destino / f'{datetime.now():%Y%m%d_%H%M}_{ambiente}.json').write_text(json.dumps(
        {'fecha': datetime.now().isoformat(timespec='seconds'), 'host': HOST, 'procesos': PASOS},
        indent=2, ensure_ascii=False), encoding='utf-8')


def test_proceso_1_alta_de_comercio_con_foto_y_validacion():
    p = '1. Alta de comercio'
    email = f'proceso{uuid.uuid4().hex[:8]}@prueba.mx'
    for _ in range(3):         # el registro se limita a 5 por minuto por IP: se espera lo que indique Retry-After
        registro = requests.post(url('seguridad', '/auth/registro'), timeout=20, json={
            'email': email, 'password': 'Proceso2026', 'nombre': 'Rosa', 'apellido_paterno': 'Proceso',
            'perfil': 'Comerciante Informal', 'origen': 'movil'})
        if registro.status_code != 429:
            break
        time.sleep(int(registro.headers.get('Retry-After', 30)) + 1)
    r = paso(p, 'comerciante nuevo', 'Android (JSON)', 'Registro simplificado', registro)
    assert r.status_code == 201, r.text
    comerciante = Api('comerciante', tokens=r.json())

    r = paso(p, 'comerciante', 'Android (JSON)', 'Alta del comercio con la ubicación del teléfono',
             comerciante.post('comercios', '/comercios', json={
                 'nombre_comercio': 'Puesto Rosa proceso', 'tipo_comercio': 'INFORMAL_TIANGUIS',
                 'direccion': 'Mercado Juárez, pasillo 3', 'municipio': 'Monterrey',
                 'latitud': 25.6866, 'longitud': -100.3161}))
    assert r.status_code == 201, r.text
    comercio = r.json()
    assert comercio['zona_id'] and comercio['estado_registro'] == 'PENDIENTE'
    PASOS[p][-1]['resultado'] = f"zona {comercio['zona_id']} asignada por ubicación; queda PENDIENTE"

    r = paso(p, 'comerciante', 'Android (JSON)', 'Foto del local (ms-documentos -> bucket)', comerciante.post(
        'documentos', '/documentos', files={'archivo': ('local.png', PNG, 'image/png')},
        data={'categoria': 'foto_comercio', 'entidad': 'comercio', 'entidad_id': comercio['id']}))
    assert r.status_code == 201 and r.json()['almacenamiento'] == 'gcs', r.text
    documento = r.json()
    r = paso(p, 'comerciante', 'Android (JSON)', 'Fija la foto principal (ms-comercios verifica con ms-documentos)',
             comerciante.put('comercios', f"/comercios/{comercio['id']}/foto", json={'documento_id': documento['id']}))
    assert r.status_code == 200, r.text

    coordinador = sesion_de('coordinador')
    cuerpo = ('<validacion_entrada xmlns="https://abastored.mx/esquemas/v1"><estado>VERIFICADO</estado>'
              '<observaciones>Visita en sitio (proceso integral)</observaciones></validacion_entrada>')
    r = paso(p, 'coordinador municipal', 'Escritorio (XML)', 'Valida el comercio', coordinador.patch(
        'comercios', f"/comercios/{comercio['id']}/validacion", data=cuerpo.encode(),
        headers={'Content-Type': 'application/xml', **XML}))
    assert r.status_code == 200 and '<estado_registro>VERIFICADO</estado_registro>' in r.text, r.text[:400]

    avisos = _avisos(comerciante, 'comercio')
    paso(p, 'comerciante', 'Android (JSON)', 'Recibe el aviso de validación',
         comerciante.get('notificaciones', '/notificaciones/contador'),
         f"{avisos['notificaciones'][0]['titulo'] if avisos['notificaciones'] else 'SIN AVISO'}")
    assert avisos['notificaciones'] and 'verificado' in avisos['notificaciones'][0]['titulo'].lower()

    firmada = comerciante.get('documentos', f"/documentos/{documento['id']}/url").json()['url']
    descarga = requests.get(firmada, timeout=20)
    PASOS[p].append({'actor': 'comerciante', 'cliente': 'navegador', 'paso': 'Descarga la foto con URL firmada',
                     'metodo': 'GET', 'ruta': re.sub(r'\?.*', '', re.sub(r'^https?://[^/]+', '', firmada)),
                     'status': descarga.status_code, 'correlation_id': None,
                     'resultado': f'{len(descarga.content)} bytes desde {firmada.split("/")[2]}'})
    assert descarga.status_code == 200 and descarga.content == PNG

    auditor = sesion_de('auditor')
    r = paso(p, 'auditor', 'Web (JSON)', 'Historial del comercio en la bitácora centralizada',
             auditor.get('auditoria', f"/entidades/Comercio/{comercio['id']}/historial"))
    servicios = {e['servicio'] for e in r.json()['eventos']}
    PASOS[p][-1]['resultado'] = f"{len(r.json()['eventos'])} eventos de {sorted(servicios)}"
    assert 'ms-comercios' in servicios and len(r.json()['eventos']) >= 2


def test_proceso_2_abasto_de_inventario_bajo_a_recepcion_con_qr():
    p = '2. Abasto'
    minorista, proveedor, operador = sesion_de('minorista'), sesion_de('dueno_regia'), sesion_de('operador')
    comercio = next(c for c in minorista.get('comercios', '/comercios').json()['items'] if c['zona_id'])
    renglones = minorista.get('inventario', f"/comercios/{comercio['id']}/inventario",
                              params={'por_pagina': 200}).json()['renglones']
    r = paso(p, 'minorista', 'Android (JSON)', 'Recomendaciones de abasto para su comercio',
             minorista.get('recomendaciones', f"/recomendaciones/{comercio['id']}"))
    assert r.status_code == 200
    oferta = renglon = None
    for candidato in renglones:
        ofertas = minorista.get('proveedores', '/ofertas', params={'producto_id': candidato['producto_id'],
                                                                   'zona_id': comercio['zona_id']}).json()['ofertas']
        oferta = next((o for o in ofertas if o['cubre_zona'] and o['proveedor'].startswith('Distribuidora Regia')
                       and o['existencia_disponible'] >= max(o['cantidad_minima'],
                                                             o['pedido_minimo'] / o['precio_mayoreo'] + 1)), None)
        if oferta:
            renglon = candidato
            break
    if not oferta:
        pytest.skip('Omitida: la Distribuidora Regia no tiene existencia suficiente para un pedido de prueba')
    paso(p, 'minorista', 'Android (JSON)', 'Ofertas de proveedores que surten su zona',
         minorista.get('proveedores', '/ofertas', params={'producto_id': oferta['producto_id']}),
         f"{oferta['proveedor']}: ${oferta['precio_mayoreo']} (mín. {oferta['cantidad_minima']})")
    cantidad = max(oferta['cantidad_minima'], int(oferta['pedido_minimo'] / oferta['precio_mayoreo']) + 1)
    for b in minorista.get('pedidos', '/pedidos', params={'estado': 'BORRADOR', 'comercio_id': comercio['id'],
                                                         'por_pagina': 100}).json()['pedidos']:
        if b['proveedor_id'] == oferta['proveedor_id']:
            minorista.post('pedidos', f"/pedidos/{b['id']}/acciones/cancelar", json={'comentario': 'Limpieza'})

    r = paso(p, 'minorista', 'Android (JSON)', 'Crea el pedido', minorista.post('pedidos', '/pedidos', json={
        'comercio_id': comercio['id'], 'proveedor_id': oferta['proveedor_id'],
        'partidas': [{'producto_id': oferta['producto_id'], 'cantidad': cantidad}]}))
    assert r.status_code == 201, r.text
    pedido = r.json()
    antes = _avisos(operador, 'pedido')['paginacion']['total']
    assert paso(p, 'minorista', 'Android (JSON)', 'Envía el pedido al proveedor', minorista.post(
        'pedidos', f"/pedidos/{pedido['id']}/acciones/enviar")).status_code == 200
    despues = _avisos(operador, 'pedido')
    avisos = despues['notificaciones']
    PASOS[p][-1]['resultado'] = f"aviso al equipo del proveedor: {avisos[0]['titulo'] if avisos else 'SIN AVISO'}"
    assert despues['paginacion']['total'] == antes + 1

    assert paso(p, 'proveedor', 'Web (JSON)', 'Acepta el pedido', proveedor.post(
        'pedidos', f"/pedidos/{pedido['id']}/acciones/aceptar")).status_code == 200
    r = paso(p, 'proveedor', 'Web (JSON)', 'Programa la entrega', proveedor.post('entregas', '/entregas', json={
        'pedido_id': pedido['id'], 'responsable_nombre': 'Repartidor proceso', 'vehiculo': 'NL-00-000'}))
    assert r.status_code == 201, r.text
    entrega = r.json()
    codigo = proveedor.get('entregas', f"/entregas/{entrega['id']}/qr").json()['codigo']
    assert paso(p, 'proveedor', 'Web (JSON)', 'Salida de bodega (descuenta su existencia)', proveedor.post(
        'entregas', f"/entregas/{entrega['id']}/salida", json={'comentario': 'Sale de bodega'})).status_code == 200

    r = paso(p, 'minorista', 'Android (JSON)', 'Confirma la recepción escaneando el QR del repartidor', minorista.post(
        'entregas', f"/entregas/{entrega['id']}/confirmacion",
        json={'codigo': codigo, 'recibido_por': 'Encargada', 'comentario': 'Completo'}))
    assert r.status_code == 200 and r.json()['estado_pedido'] == 'ENTREGADO', r.text
    actual = minorista.get('inventario', f"/inventario/{renglon['id']}").json()
    r = paso(p, 'minorista', 'Android (JSON)', 'Ve el inventario actualizado',
             minorista.get('inventario', f"/inventario/{renglon['id']}"),
             f"{renglon['producto']}: {renglon['existencia']} -> {actual['existencia']}")
    assert actual['existencia'] == renglon['existencia'] + cantidad

    r = paso(p, 'auditor', 'Web (JSON)', 'Historial del pedido en la bitácora centralizada',
             sesion_de('auditor').get('auditoria', f"/entidades/PedidoAbasto/{pedido['id']}/historial"))
    servicios = {e['servicio'] for e in r.json()['eventos']}
    PASOS[p][-1]['resultado'] = f"{len(r.json()['eventos'])} eventos de {sorted(servicios)}"
    assert 'ms-pedidos' in servicios


def test_proceso_3_importacion_analisis_y_reporte_en_el_bucket():
    p = '3. Importación, análisis y reporte'
    minorista = sesion_de('minorista')
    comercio = next(c for c in minorista.get('comercios', '/comercios').json()['items'] if c['zona_id'])
    renglones = minorista.get('inventario', f"/comercios/{comercio['id']}/inventario",
                              params={'por_pagina': 200}).json()['renglones'][:3]
    filas = '\n'.join(f"{r['producto']},{int(r['existencia']) + 1},{int(r['stock_minimo'])},,{r['precio_venta'] or ''}"
                      for r in renglones)
    csv = f'producto,existencia,stock_minimo,stock_maximo,precio\n{filas}\n'.encode()
    r = paso(p, 'minorista', 'Web (JSON)', 'Importa su inventario en CSV (el archivo va al bucket)', minorista.post(
        'inventario', f"/comercios/{comercio['id']}/importaciones",
        files={'archivo': ('inventario_proceso.csv', csv, 'text/csv')}))
    assert r.status_code == 201, r.text
    importacion = r.json()
    PASOS[p][-1]['resultado'] = f"{importacion.get('actualizados', importacion.get('aplicadas'))} filas aplicadas; " \
                                f"errores: {importacion.get('con_error', importacion.get('errores'))}"
    avisos = _avisos(minorista, 'importacion')['notificaciones']
    paso(p, 'minorista', 'Web (JSON)', 'Recibe el aviso de la importación',
         minorista.get('notificaciones', '/notificaciones/contador'), avisos[0]['titulo'] if avisos else 'SIN AVISO')
    assert avisos

    analista = sesion_de('analista')
    r = paso(p, 'analista', 'Escritorio (XML)', 'Brechas de surtido de la canasta básica', analista.get(
        'analisis', '/analisis/brechas', params={'canasta_basica': 'true'}, headers=XML))
    assert r.status_code == 200 and r.text.lstrip().startswith('<?xml')
    r = paso(p, 'analista', 'Escritorio (XML)', 'Concentraciones comerciales (DBSCAN)', analista.get(
        'analisis', '/analisis/agrupamientos', params={'radio_m': 400, 'minimo': 4}, headers=XML))
    assert r.status_code == 200 and '<grupos>' in r.text or '<grupos/>' in r.text
    PASOS[p][-1]['resultado'] = f"{r.text.count('<grupo>')} concentraciones"

    r = paso(p, 'analista', 'Escritorio (XML)', 'Genera el reporte de brechas en PDF (al bucket)', analista.post(
        'reportes', '/reportes', json={'tipo': 'brechas', 'formato': 'pdf'}))
    assert r.status_code == 201, r.text
    reporte = r.json()
    firmada = analista.get('reportes', f"/reportes/{reporte['id']}/url").json()['url']
    descarga = requests.get(firmada, timeout=30)
    PASOS[p].append({'actor': 'analista', 'cliente': 'Escritorio', 'paso': 'Descarga el PDF con URL firmada',
                     'metodo': 'GET', 'ruta': re.sub(r'\?.*', '', re.sub(r'^https?://[^/]+', '', firmada)),
                     'status': descarga.status_code, 'correlation_id': None,
                     'resultado': f'{len(descarga.content)} bytes desde {firmada.split("/")[2]}'})
    assert descarga.status_code == 200 and descarga.content.startswith(b'%PDF')
    assert sesion_de('minorista').get('reportes', f"/reportes/{reporte['id']}/url").status_code == 403

    r = paso(p, 'auditor', 'Web (JSON)', 'Rastro de la importación en la bitácora centralizada',
             sesion_de('auditor').get('auditoria', '/eventos', params={'entidad': 'Importacion', 'por_pagina': 5}))
    assert r.status_code == 200
