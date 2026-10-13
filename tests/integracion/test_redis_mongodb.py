"""
Uso real de Redis (caché con versión e invalidación, contadores) y de MongoDB
(upsert con índice único, agregaciones, documentos ligados a PostgreSQL),
comprobado a través de los servicios.
"""
import pytest
import requests

from apoyo import url


def test_cache_de_disponibilidad_se_invalida_al_mover_inventario(api):
    params = {'por_pagina': 5, 'texto': 'a'}
    requests.get(url('inventario', '/disponibilidad'), params=params, timeout=10)  # calienta la caché
    assert requests.get(url('inventario', '/disponibilidad'), params=params, timeout=10).json()['origen'] == 'cache'

    minorista = api('minorista')
    comercio = minorista.get('comercios', '/comercios').json()['items'][0]['id']
    renglon = minorista.get('inventario', f'/comercios/{comercio}/inventario').json()['renglones'][0]
    r = minorista.post('inventario', f"/inventario/{renglon['id']}/movimientos",
                       json={'tipo': 'ENTRADA', 'cantidad': 1, 'motivo': 'Prueba de invalidación de caché'})
    assert r.status_code == 201

    # El movimiento incrementa analisis:version, así que la siguiente consulta vuelve a PostgreSQL
    assert requests.get(url('inventario', '/disponibilidad'), params=params, timeout=10).json()['origen'] == 'postgres'


def test_cache_de_zonas(api):
    requests.get(url('comercios', '/zonas'), timeout=10)
    assert requests.get(url('comercios', '/zonas'), timeout=10).json()['origen'] == 'cache'


def test_snapshot_diario_de_precios_es_idempotente(api):
    """Upsert sobre el índice único (fecha, comercio, producto): correr dos veces no duplica documentos."""
    analista = api('analista')
    primero = analista.post('precios', '/precios/snapshots')
    segundo = analista.post('precios', '/precios/snapshots')
    assert primero.status_code == segundo.status_code == 201
    assert primero.json()['documentos'] == segundo.json()['documentos'] > 0

    producto = api('minorista').get('inventario', '/comercios/{}/inventario'.format(
        api('minorista').get('comercios', '/comercios').json()['items'][0]['id'])).json()['renglones'][0]['producto_id']
    r = analista.get('precios', '/precios/snapshots/tendencia', params={'producto_id': producto})
    assert r.status_code == 200
    dias = [p['fecha'] for p in r.json()['puntos']] if 'puntos' in r.json() else r.json()
    assert dias


def test_ejecucion_de_analisis_y_evolucion(api):
    analista = api('analista')
    r = analista.post('analisis', '/analisis/ejecuciones')
    assert r.status_code == 201
    assert len(r.json()['id']) == 24  # ObjectId de MongoDB
    r = analista.get('analisis', '/analisis/ejecuciones/evolucion', params={'dias': 1})
    assert r.status_code == 200
    assert r.json()['datos'], 'La agregación con $unwind debe regresar al menos el corte de hoy'
    assert {'zona_id', 'zona', 'dia', 'indice_acceso', 'ejecuciones'} <= set(r.json()['datos'][0])


def test_resumen_de_notificaciones_por_agregacion(api):
    r = api('minorista').get('notificaciones', '/notificaciones/resumen')
    assert r.status_code == 200
    filas = r.json()['tipos'] if 'tipos' in r.json() else r.json()['resumen']
    assert all(f['no_leidas'] <= f['total'] for f in filas)


def test_marcar_leida_actualiza_el_contador_de_redis(api):
    minorista = api('minorista')
    lista = minorista.get('notificaciones', '/notificaciones', params={'solo_no_leidas': 'true', 'por_pagina': 1}).json()
    if not lista['notificaciones']:
        pytest.skip('No hay notificaciones sin leer')
    antes = minorista.get('notificaciones', '/notificaciones/contador').json()['no_leidas']
    r = minorista.patch('notificaciones', f"/notificaciones/{lista['notificaciones'][0]['id']}", json={'leida': True})
    assert r.status_code == 200
    assert minorista.get('notificaciones', '/notificaciones/contador').json()['no_leidas'] == antes - 1


def test_notificacion_ajena_no_se_ve(api):
    propia = api('minorista').get('notificaciones', '/notificaciones', params={'por_pagina': 1}).json()['notificaciones']
    if not propia:
        pytest.skip('La minorista no tiene notificaciones')
    r = api('comerciante').get('notificaciones', f"/notificaciones/{propia[0]['id']}")
    assert r.status_code == 404


def test_actividad_de_servicios_desde_la_bitacora(api):
    r = api('admin').get('seguridad', '/actividad', params={'horas': 1})
    assert r.status_code == 200
    servicios = {s['servicio']: s for s in r.json()['servicios']}
    assert {'pedidos', 'inventario', 'seguridad'} <= set(servicios)
    assert all(s['contador_hoy'] >= 1 for s in servicios.values())
