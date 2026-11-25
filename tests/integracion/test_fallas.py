"""
Fallas y recuperación (SOLO en el entorno local: detiene o congela contenedores).

- PostgreSQL caído: 503 claro (no 500), nada a medias, y al volver la misma venta se registra una sola vez.
- MongoDB caído: la operación de negocio sigue (el evento de auditoría queda en PostgreSQL) y al volver se
  concilia la bitácora centralizada.
- Un servicio del que depende otro está caído: ms-ventas responde 503 y no registra la venta.
- Un servicio del que depende otro está congelado (timeout): ms-ventas se rinde a los pocos segundos y, al
  reintentar con el mismo id_cliente, el inventario se descuenta UNA sola vez aunque ms-inventario haya
  terminado la primera petición después del timeout.
"""
import subprocess
import time
import uuid

import pytest
import requests

from apoyo import base, esperar_salud


def _sql(consulta):
    r = subprocess.run(['docker', 'exec', 'abastored-postgres', 'psql', '-U', 'abastored_admin', '-d', 'abastored',
                        '-Atc', consulta], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def _esperar_contenedor_sano(nombre, segundos=90):
    limite = time.time() + segundos
    while time.time() < limite:
        estado = subprocess.run(['docker', 'inspect', '-f', '{{.State.Health.Status}}', nombre],
                                capture_output=True, text=True).stdout.strip()
        if estado == 'healthy':
            return True
        time.sleep(2)
    return False


def _esperar_listo(servicio, segundos=90):
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            if requests.get(f'{base(servicio)}/health/ready', timeout=3).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


@pytest.fixture
def renglon(api):
    """Un renglón del minorista con existencia suficiente; al final se deja la existencia como estaba."""
    minorista = api('minorista')
    comercio = minorista.get('comercios', '/comercios').json()['items'][0]['id']
    renglones = minorista.get('inventario', f'/comercios/{comercio}/inventario', params={'por_pagina': 200}).json()
    r = next(x for x in renglones['renglones'] if x['existencia'] >= 5 and x['precio_venta'])
    yield minorista, comercio, r
    minorista.post('inventario', f"/inventario/{r['id']}/movimientos",
                   json={'tipo': 'AJUSTE', 'cantidad': r['existencia'], 'motivo': 'Restablecer prueba de fallas'})


def _existencia(minorista, renglon_id):
    return minorista.get('inventario', f'/inventario/{renglon_id}').json()['existencia']


def _venta(comercio, renglon_id, id_cliente):
    return {'comercio_id': comercio, 'origen': 'android', 'id_cliente': id_cliente,
            'partidas': [{'inventario_id': renglon_id, 'cantidad': 1}]}


def test_postgres_caido_503_sin_cambios_y_al_volver_se_registra_una_vez(renglon, docker):
    minorista, comercio, r = renglon
    id_cliente = uuid.uuid4().hex
    assert docker('stop', 'abastored-postgres').returncode == 0
    try:
        respuesta = minorista.post('ventas', '/ventas', json=_venta(comercio, r['id'], id_cliente))
        assert respuesta.status_code == 503, respuesta.text[:300]
        assert respuesta.json()['error']['codigo'] in ('base_datos_no_disponible', 'servicio_no_disponible')
        assert int(respuesta.headers.get('Retry-After', '0')) > 0 or 'no respondió' in respuesta.text
        consulta = minorista.get('inventario', f'/comercios/{comercio}/inventario')
        assert consulta.status_code == 503 and consulta.json()['error']['codigo'] == 'base_datos_no_disponible'
        assert requests.get(f"{base('ventas')}/health/ready", timeout=10).status_code == 503
        assert requests.get(f"{base('ventas')}/health/live", timeout=10).status_code == 200   # no hay que reiniciarlo
    finally:
        assert docker('start', 'abastored-postgres').returncode == 0
        assert _esperar_contenedor_sano('abastored-postgres'), 'PostgreSQL no volvió'
        assert _esperar_listo('ventas') and _esperar_listo('inventario')

    assert _sql(f"SELECT count(*) FROM ventas WHERE id_cliente = '{id_cliente}'") == '0'   # nada a medias
    assert _existencia(minorista, r['id']) == r['existencia']
    # La app reintenta la misma venta: se registra una vez y el segundo reintento responde la existente
    assert minorista.post('ventas', '/ventas', json=_venta(comercio, r['id'], id_cliente)).status_code == 201
    repetida = minorista.post('ventas', '/ventas', json=_venta(comercio, r['id'], id_cliente))
    assert repetida.status_code == 200 and repetida.json()['duplicada'] is True
    assert _sql(f"SELECT count(*) FROM ventas WHERE id_cliente = '{id_cliente}'") == '1'
    assert _existencia(minorista, r['id']) == r['existencia'] - 1


def test_mongodb_caido_la_operacion_sigue_y_la_auditoria_se_concilia(renglon, api, docker):
    minorista, _, r = renglon
    assert docker('stop', 'abastored-mongo').returncode == 0
    try:
        respuesta = minorista.post('inventario', f"/inventario/{r['id']}/movimientos",
                                   json={'tipo': 'ENTRADA', 'cantidad': 2, 'motivo': 'Prueba con MongoDB caído'})
        assert respuesta.status_code == 201, respuesta.text[:300]
        salud = requests.get(f"{base('inventario')}/health/ready", timeout=10).json()
        assert salud['estado'] == 'degradado'                       # MongoDB es opcional para ms-inventario
    finally:
        assert docker('start', 'abastored-mongo').returncode == 0
        assert _esperar_contenedor_sano('abastored-mongo'), 'MongoDB no volvió'
        assert _esperar_listo('auditoria')

    assert _existencia(minorista, r['id']) == r['existencia'] + 2       # PostgreSQL sí guardó el movimiento
    admin = api('admin')
    conciliacion = admin.post('auditoria', '/conciliacion', json={'dias': 1})
    assert conciliacion.status_code == 200, conciliacion.text[:300]
    assert conciliacion.json()['copiados'] >= 1                         # el evento que faltaba en la bitácora
    assert admin.post('auditoria', '/conciliacion', json={'dias': 1}).json()['faltaban'] == 0


def test_servicio_del_que_depende_caido_503_y_sin_venta(renglon, docker):
    minorista, comercio, r = renglon
    id_cliente = uuid.uuid4().hex
    assert docker('stop', 'ms-inventario').returncode == 0
    try:
        inicio = time.perf_counter()
        respuesta = minorista.post('ventas', '/ventas', json=_venta(comercio, r['id'], id_cliente))
        assert respuesta.status_code == 503
        assert respuesta.json()['error']['codigo'] == 'servicio_no_disponible'
        assert 'ms-inventario' in respuesta.json()['error']['mensaje']
        assert time.perf_counter() - inicio < 6                      # falla rápido (DNS y conexión de 1-3 s)
    finally:
        assert docker('start', 'ms-inventario').returncode == 0
        assert esperar_salud('inventario') and _esperar_listo('inventario')
    assert _sql(f"SELECT count(*) FROM ventas WHERE id_cliente = '{id_cliente}'") == '0'
    assert _existencia(minorista, r['id']) == r['existencia']


def test_servicio_lento_timeout_y_el_reintento_no_descuenta_dos_veces(renglon, docker):
    minorista, comercio, r = renglon
    id_cliente = uuid.uuid4().hex
    assert docker('pause', 'ms-inventario').returncode == 0          # congelado: acepta la conexión y no responde
    try:
        inicio = time.perf_counter()
        respuesta = minorista.post('ventas', '/ventas', json=_venta(comercio, r['id'], id_cliente))
        duracion = time.perf_counter() - inicio
        assert respuesta.status_code == 503 and respuesta.json()['error']['codigo'] == 'servicio_no_disponible'
        assert duracion < 8, f'ms-ventas esperó {duracion:.1f} s'      # MS_TIMEOUT_SEGUNDOS (3 s) + margen
    finally:
        assert docker('unpause', 'ms-inventario').returncode == 0
    time.sleep(3)          # ms-inventario termina ahora la petición que tenía pendiente (ya sin nadie esperando)
    assert _sql(f"SELECT count(*) FROM ventas WHERE id_cliente = '{id_cliente}'") == '0'

    # La app no recibió confirmación y reintenta la misma venta (mismo id_cliente)
    reintento = minorista.post('ventas', '/ventas', json=_venta(comercio, r['id'], id_cliente))
    assert reintento.status_code == 201, reintento.text[:300]
    assert _sql(f"SELECT count(*) FROM ventas WHERE id_cliente = '{id_cliente}'") == '1'
    assert _existencia(minorista, r['id']) == r['existencia'] - 1, 'el inventario se descontó más de una vez'
