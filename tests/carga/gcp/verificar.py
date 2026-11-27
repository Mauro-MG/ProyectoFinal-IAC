"""
Comprobación funcional y de consistencia contra el despliegue, por HTTPS (antes y después de la carga).

    python tests/carga/gcp/verificar.py <prefijo> <carpeta_resultados> [--muestras 5] [--consistencia]

En cada muestra (cada 20 s): estado de los 24 servicios (ms-monitoreo), web público, búsqueda, una consulta XML
del analista y una del comerciante, con su latencia. Después, UNA escritura controlada: una venta con id_cliente
fijo que se envía dos veces; la segunda debe devolver la misma venta (duplicada) y el inventario debe bajar
exactamente 1.

Con --consistencia revisa TODOS los datos de prueba del prefijo: por cada renglón,
existencia_inicial - existencia_actual = suma de las SALIDAS, que no haya id_cliente repetidos y que cada venta
aceptada (201/200) en los ventas_enviadas.csv indicados con --ventas exista exactamente una vez en la base. Escribe verificacion.json (sin tokens).
"""
import argparse
import csv
import json
import statistics
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

from comun import CA, HOST, clasificar, leer_sesiones, url

p = argparse.ArgumentParser()
p.add_argument('prefijo')
p.add_argument('destino')
p.add_argument('--muestras', type=int, default=5)
p.add_argument('--consistencia', action='store_true')
p.add_argument('--ventas', action='append', default=[], help='ventas_enviadas.csv de las corridas del prefijo')
args = p.parse_args()
DESTINO = Path(args.destino)
DESTINO.mkdir(parents=True, exist_ok=True)
S = leer_sesiones(args.prefijo)
web = requests.Session()
web.verify = CA


def cliente(cuenta):
    s = requests.Session()
    s.verify = CA
    s.headers['Authorization'] = f'Bearer {cuenta["token"]}'
    return s


com = cliente(S['com'][0])
ana = cliente(S['ana'][0])
aud = cliente(S['aud'][0])
comercio0 = S['com'][0]['comercio']


def medir(sesion, metodo, destino, **kw):
    inicio = time.perf_counter()
    for _ in range(4):
        try:
            r = sesion.request(metodo, destino, timeout=30, **kw)
        except requests.RequestException as error:
            return {'status': 0, 'categoria': clasificar(0, None, error), 'ms': None, 'detalle': str(error)[:200]}
        if r.status_code != 429:
            break
        time.sleep(int(r.headers.get('Retry-After', 2)) + 1)
    return {'status': r.status_code, 'categoria': clasificar(r.status_code, r.headers),
            'ms': round((time.perf_counter() - inicio) * 1000, 1), 'respuesta': r}


CONSULTAS = {
    'web GET /': (web, 'GET', HOST + '/', {}),
    'web GET /disponibilidad': (web, 'GET', HOST + '/disponibilidad', {}),
    'busqueda GET /buscar': (web, 'GET', url('busqueda', '/buscar?q=arroz'), {}),
    'analisis GET /analisis/zonas [xml]': (ana, 'GET', url('analisis', '/analisis/zonas'),
                                           {'headers': {'Accept': 'application/xml'}}),
    'inventario GET /comercios/{id}/inventario': (com, 'GET', url('inventario', f'/comercios/{comercio0}/inventario'), {}),
    'auditoria GET /eventos': (aud, 'GET', url('auditoria', '/eventos?por_pagina=50'), {}),
}

resultado = {'prefijo': args.prefijo, 'host': HOST, 'inicio': datetime.now().astimezone().isoformat(timespec='seconds'),
             'muestras': [], 'escritura_controlada': None, 'consistencia': None}
for n in range(args.muestras):
    if n:
        time.sleep(20)
    muestra = {'hora': datetime.now().astimezone().isoformat(timespec='seconds'), 'consultas': {}}
    e = medir(web, 'GET', url('monitoreo', '/estado/publico'))
    if e['status'] == 200:
        d = e['respuesta'].json()
        muestra['servicios'] = {'total': d['total'], 'ok': d['ok'], 'degradados': d['degradados'],
                                'caidos': d['caidos'],
                                'no_ok': [s['servicio'] for s in d['servicios'] if s['estado'] != 'ok']}
    else:
        muestra['servicios'] = {'error': e['status']}
    for nombre, (sesion, metodo, destino, kw) in CONSULTAS.items():
        m = medir(sesion, metodo, destino, **kw)
        if nombre.endswith('[xml]') and m['status'] == 200 and 'xml' not in m['respuesta'].headers.get('Content-Type', ''):
            m['categoria'] = 'falla_contrato'
        muestra['consultas'][nombre] = {k: v for k, v in m.items() if k != 'respuesta'}
    resultado['muestras'].append(muestra)
    estados = {k: v['status'] for k, v in muestra['consultas'].items()}
    print(f"muestra {n + 1}: servicios {muestra['servicios']} · {estados}", flush=True)

# --------------------------------------------------------------- escritura controlada (idempotencia)
renglon = S['com'][0]['renglones'][0]
antes = com.get(url('inventario', f'/inventario/{renglon["id"]}'), timeout=30).json()['existencia']
cuerpo = {'comercio_id': comercio0, 'origen': 'android', 'id_cliente': f'verif-{uuid.uuid4().hex[:16]}',
          'partidas': [{'inventario_id': renglon['id'], 'cantidad': 1,
                        **({} if renglon.get('precio') else {'precio_unitario': 20})}]}
primera = com.post(url('ventas', '/ventas'), json=cuerpo, timeout=30)
segunda = com.post(url('ventas', '/ventas'), json=cuerpo, timeout=30)
despues = com.get(url('inventario', f'/inventario/{renglon["id"]}'), timeout=30).json()['existencia']
resultado['escritura_controlada'] = {
    'inventario_id': renglon['id'], 'existencia_antes': antes, 'existencia_despues': despues,
    'primera_status': primera.status_code, 'segunda_status': segunda.status_code,
    'segunda_duplicada': segunda.ok and segunda.json().get('duplicada') is True,
    'misma_venta': primera.ok and segunda.ok and primera.json()['id'] == segunda.json()['id'],
    'descuento': float(antes) - float(despues),
}
resultado['escritura_controlada']['correcta'] = (primera.status_code == 201 and segunda.status_code == 200
                                                 and resultado['escritura_controlada']['segunda_duplicada']
                                                 and resultado['escritura_controlada']['descuento'] == 1)
print('escritura controlada:', resultado['escritura_controlada'], flush=True)


# --------------------------------------------------------------- consistencia de todos los datos de prueba
def todas(sesion, servicio, camino, clave, por_pagina):
    pagina, items = 1, []
    while True:
        r = medir(sesion, 'GET', url(servicio, f'{camino}{"&" if "?" in camino else "?"}pagina={pagina}'
                                               f'&por_pagina={por_pagina}'))
        r['respuesta'].raise_for_status()
        d = r['respuesta'].json()
        items += d[clave]
        if pagina >= d['paginacion']['paginas']:
            return items
        pagina += 1
        time.sleep(0.15)


if args.consistencia:
    problemas, renglones, ventas_total, ids = [], 0, 0, Counter()
    for cuenta in S['com']:
        s = cliente(cuenta)
        ventas = todas(s, 'ventas', f'/ventas?comercio_id={cuenta["comercio"]}', 'ventas', 100)
        ventas_total += len(ventas)
        ids.update(v['id_cliente'] for v in ventas if v['id_cliente'])
        for r in cuenta['renglones']:
            renglones += 1
            actual = float(medir(s, 'GET', url('inventario', f'/inventario/{r["id"]}'))['respuesta'].json()['existencia'])
            movs = todas(s, 'inventario', f'/inventario/{r["id"]}/movimientos?tipo=SALIDA', 'movimientos', 200)
            salidas = sum(float(m['cantidad']) for m in movs)
            if abs((r['existencia_inicial'] - actual) - salidas) > 1e-6:
                problemas.append({'inventario_id': r['id'], 'inicial': r['existencia_inicial'], 'actual': actual,
                                  'suma_salidas': salidas})
        time.sleep(0.2)
    repetidos = [k for k, v in ids.items() if v > 1]
    aceptadas = set()
    for archivo in map(Path, args.ventas):
        with open(archivo, encoding='utf-8') as f:
            for fila in csv.DictReader(f):
                if fila['status'] in ('200', '201'):
                    aceptadas.add(fila['id_cliente'])
    faltantes = [i for i in aceptadas if ids.get(i, 0) != 1]
    resultado['consistencia'] = {
        'comercios': len(S['com']), 'renglones': renglones, 'ventas_en_base': ventas_total,
        'renglones_con_descuento_inconsistente': problemas, 'id_cliente_repetidos': repetidos,
        'ventas_aceptadas_en_la_carga': len(aceptadas), 'aceptadas_sin_exactamente_un_registro': faltantes[:50],
        'correcta': not problemas and not repetidos and not faltantes,
    }
    print('consistencia:', {k: (v if not isinstance(v, list) else len(v))
                            for k, v in resultado['consistencia'].items()}, flush=True)

lat = [c['ms'] for m in resultado['muestras'] for c in m['consultas'].values() if c['ms'] and c['categoria'] == 'ok']
resultado['latencia_consultas_ms'] = {'n': len(lat), 'mediana': statistics.median(lat) if lat else None,
                                      'max': max(lat) if lat else None}
resultado['fin'] = datetime.now().astimezone().isoformat(timespec='seconds')
(DESTINO / 'verificacion.json').write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=str),
                                         encoding='utf-8')
print('Resultado en', DESTINO / 'verificacion.json')
