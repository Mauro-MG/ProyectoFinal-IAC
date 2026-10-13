"""
Recuperación ante fallas: con ms-notificaciones detenido, los demás servicios
siguen operando y los avisos no se pierden (se guardan directo en MongoDB);
al volver el servicio, el usuario los ve. El web también sigue respondiendo.
Requiere el CLI de Docker (detiene y arranca el contenedor).
"""
import requests

from apoyo import WEB, esperar_salud


def test_aviso_no_se_pierde_con_notificaciones_caido(api, docker):
    minorista = api('minorista')
    comercio = minorista.get('comercios', '/comercios').json()['items'][0]['id']
    renglones = minorista.get('inventario', f'/comercios/{comercio}/inventario', params={'por_pagina': 200}).json()['renglones']
    renglon = next(r for r in renglones if r['existencia'] > r['stock_minimo'])
    antes = minorista.get('notificaciones', '/notificaciones', params={'tipo': 'stock_bajo', 'por_pagina': 1}).json()
    total_antes = antes['paginacion']['total']

    assert docker('stop', 'ms-notificaciones').returncode == 0
    try:
        # Venta que deja el producto en stock bajo: ms-inventario intenta avisar y el servicio no responde
        r = minorista.post('inventario', f"/inventario/{renglon['id']}/movimientos",
                           json={'tipo': 'SALIDA', 'cantidad': renglon['existencia'] - renglon['stock_minimo'] + 1,
                                 'motivo': 'Prueba de resiliencia'})
        assert r.status_code == 201, 'La operación de negocio no debe fallar porque falte el servicio de avisos'

        # El web sigue funcionando y lee las notificaciones directo de MongoDB
        assert requests.get(f'{WEB}/health', timeout=10).status_code == 200
        assert requests.get(f'{WEB}/login', timeout=10).status_code == 200
    finally:
        assert docker('start', 'ms-notificaciones').returncode == 0
        assert esperar_salud('notificaciones'), 'ms-notificaciones no volvió a estar sano'

    despues = minorista.get('notificaciones', '/notificaciones', params={'tipo': 'stock_bajo', 'por_pagina': 1}).json()
    assert despues['paginacion']['total'] == total_antes + 1
    assert renglon['producto'] in despues['notificaciones'][0]['titulo']

    # Se restablece la existencia para no afectar otras corridas
    minorista.post('inventario', f"/inventario/{renglon['id']}/movimientos",
                   json={'tipo': 'AJUSTE', 'cantidad': renglon['existencia'], 'motivo': 'Restablecer prueba'})


def test_salud_reporta_dependencia_caida(docker):
    """Con Redis detenido, /health de un servicio lo reporta y las rutas protegidas responden 503 (no 500)."""
    assert docker('stop', 'abastored-redis').returncode == 0
    try:
        r = requests.get('http://localhost:8106/health', timeout=10)
        assert r.status_code == 503
        caidas = [d['nombre'] for d in r.json()['dependencias'] if d['estado'] != 'ok']
        assert caidas == ['redis']
        r = requests.get('http://localhost:8106/api/v1/pedidos', headers={'Authorization': 'Bearer x.y.z'}, timeout=10)
        assert r.status_code in (401, 503)
    finally:
        assert docker('start', 'abastored-redis').returncode == 0
        for _ in range(30):
            if requests.get('http://localhost:8106/health', timeout=10).status_code == 200:
                break
