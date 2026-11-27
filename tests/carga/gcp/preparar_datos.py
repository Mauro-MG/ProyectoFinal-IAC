"""
Datos exclusivos de una corrida, creados por la API pública (HTTPS + gateway) con las cuentas del prefijo:
cada comerciante da de alta SU comercio y agrega 4 productos con existencia amplia y precio de venta.

    python tests/carga/gcp/preparar_datos.py <prefijo>

- Existencia inicial por renglón: EXISTENCIA (100 000 por omisión). Las ventas de la carga son de 1 unidad, así
  que nunca se agota el stock por descuido y un 409 en la carga sería un problema real, no de preparación.
- Va despacio (RITMO peticiones/s, 5 por omisión) para no consumir el límite por IP del gateway y no mezclar la
  preparación con la medición.
- Guarda comercio e inventario de cada cuenta en el archivo privado de sesiones y un manifiesto SIN tokens en
  tests/carga/resultados/gcp/preparacion_<prefijo>.json.
"""
import json
import os
import random
import sys
import time
from datetime import datetime

import requests

from comun import CA, HOST, archivo_sesiones, clasificar, leer_sesiones, url

PREFIJO = sys.argv[1]
EXISTENCIA = int(os.environ.get('EXISTENCIA', 100000))
RITMO = float(os.environ.get('RITMO', 5))
PRODUCTOS = list(range(1, 29))
# Centros de las 6 zonas municipales sembradas (db/postgres/03_seeds.sql); el desvío de ±0.004° (~450 m) queda
# dentro del radio de 2 km, así que cada comercio recibe zona (sin zona, recomendaciones responde 409 sin_zona).
PUNTOS = [(25.6714, -100.3095, 'Monterrey'), (25.8200, -100.5900, 'García'), (25.7950, -100.3400, 'General Escobedo'),
          (25.7800, -100.1900, 'Apodaca'), (25.6780, -100.2300, 'Guadalupe'), (25.6750, -100.4700, 'Santa Catarina')]

sesiones = leer_sesiones(PREFIJO)
rng = random.Random(PREFIJO)
http = requests.Session()
http.verify = CA
conteo = {}
ultimo = 0.0


def pedir(metodo, servicio, camino, token, **kw):
    global ultimo
    espera = 1 / RITMO - (time.monotonic() - ultimo)
    if espera > 0:
        time.sleep(espera)
    for intento in range(4):
        ultimo = time.monotonic()
        r = http.request(metodo, url(servicio, camino), headers={'Authorization': f'Bearer {token}'}, timeout=30,
                         **kw)
        categoria = clasificar(r.status_code, r.headers)
        conteo[categoria] = conteo.get(categoria, 0) + 1
        if r.status_code != 429:
            return r
        time.sleep(int(r.headers.get('Retry-After', 2)) + 1)
    return r


inicio = time.time()
for i, cuenta in enumerate(sesiones['com'], 1):
    if cuenta.get('comercio'):
        continue
    lat, lon, municipio = PUNTOS[i % len(PUNTOS)]
    r = pedir('POST', 'comercios', '/comercios', cuenta['token'], json={
        'nombre_comercio': f'Puesto carga {PREFIJO} {i:03d}', 'tipo_comercio': 'INFORMAL_TIANGUIS',
        'direccion': f'Comercio de prueba de carga {PREFIJO}', 'municipio': municipio,
        'latitud': round(lat + rng.uniform(-0.004, 0.004), 6), 'longitud': round(lon + rng.uniform(-0.004, 0.004), 6)})
    if r.status_code != 201:
        sys.exit(f'{cuenta["email"]}: alta de comercio {r.status_code} {r.text[:300]}')
    comercio = r.json()['id']
    if not r.json().get('zona_id'):
        sys.exit(f'{cuenta["email"]}: el comercio quedó sin zona ({lat}, {lon}); revisa PUNTOS')
    renglones = []
    for producto in rng.sample(PRODUCTOS, 4):
        r = pedir('POST', 'inventario', f'/comercios/{comercio}/inventario', cuenta['token'], json={
            'producto_id': producto, 'existencia': EXISTENCIA, 'stock_minimo': 5, 'stock_maximo': EXISTENCIA * 2,
            'precio_venta': round(rng.uniform(15, 60), 2)})
        if r.status_code != 201:
            sys.exit(f'{cuenta["email"]}: inventario {producto} {r.status_code} {r.text[:300]}')
        d = r.json()
        renglones.append({'id': d['id'], 'producto_id': producto, 'existencia_inicial': EXISTENCIA,
                          'precio': d.get('precio_venta'), 'aviso': d.get('aviso')})
    cuenta['comercio'], cuenta['renglones'] = comercio, renglones
    archivo_sesiones(PREFIJO).write_text(json.dumps(sesiones), encoding='utf-8')
    print(f'{i:3d}/{len(sesiones["com"])} {comercio}', flush=True)

sin_precio = sum(1 for c in sesiones['com'] for r in c['renglones'] if not r['precio'])
manifiesto = {
    'prefijo': PREFIJO, 'host': HOST, 'fecha': datetime.now().astimezone().isoformat(timespec='seconds'),
    'duracion_s': round(time.time() - inicio, 1), 'existencia_inicial_por_renglon': EXISTENCIA,
    'cuentas': {k: len(sesiones[k]) for k in ('com', 'ana', 'aud')},
    'comercios': len(sesiones['com']), 'renglones': sum(len(c['renglones']) for c in sesiones['com']),
    'renglones_sin_precio': sin_precio, 'respuestas_preparacion': conteo,
    'comercios_ids': [c['comercio'] for c in sesiones['com']],
}
destino = archivo_sesiones(PREFIJO).parent.parent / f'preparacion_{PREFIJO}.json'
destino.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({k: v for k, v in manifiesto.items() if k != 'comercios_ids'}, ensure_ascii=False))
