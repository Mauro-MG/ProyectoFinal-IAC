"""
Con y sin la caché de Redis en los análisis (GET /analisis/zonas y GET /analisis/mapa), con los datos masivos.

    python tests/carga/medir_cache.py [repeticiones]

«Sin caché» no apaga Redis ni toca las sesiones: antes de cada petición sube analisis:version, que es lo
que hace la aplicación cuando cambia un inventario (servicios/cache.py). Así el resultado guardado deja de
servir y el servicio recalcula en PostgreSQL. La autenticación, la sesión en Redis y la revocación se
siguen revisando en las dos variantes.
Las peticiones van por el gateway HTTPS con el token de un analista (tests/carga/resultados/sesiones.json).
"""
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[2]
GATEWAY = 'https://localhost'
CA = RAIZ / 'infra' / 'certs' / 'abastored.crt'
REDIS = ['docker', 'exec', 'abastored-redis', 'sh', '-c',
         'redis-cli -a "$(cat /run/secrets/redis_password)" --no-auth-warning INCR analisis:version']


def medir(sesion, ruta, repeticiones, invalidar):
    tiempos = []
    for _ in range(repeticiones):
        if invalidar:
            subprocess.run(REDIS, capture_output=True, check=True)
        inicio = time.perf_counter()
        r = sesion.get(f'{GATEWAY}/ms/analisis/api/v1{ruta}', timeout=60)
        tiempos.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        time.sleep(0.6)                # por debajo del límite por usuario del servicio (120/min)
    tiempos.sort()
    return {'n': len(tiempos), 'promedio_ms': round(statistics.mean(tiempos), 1),
            'mediana_ms': round(statistics.median(tiempos), 1),
            'p95_ms': round(tiempos[max(int(len(tiempos) * .95) - 1, 0)], 1), 'max_ms': round(tiempos[-1], 1)}


def main(repeticiones):
    sesiones = json.loads((RAIZ / 'tests/carga/resultados/sesiones.json').read_text(encoding='utf-8'))
    s = requests.Session()
    s.verify = str(CA)
    s.headers['Authorization'] = 'Bearer ' + sesiones['analistas'][0]['token']
    resultado = {'fecha': datetime.now().isoformat(timespec='seconds'),
                 'commit': subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True,
                                          cwd=RAIZ).stdout.strip(), 'mediciones': {}}
    for ruta in ('/analisis/zonas', '/analisis/mapa'):
        s.get(f'{GATEWAY}/ms/analisis/api/v1{ruta}', timeout=60)          # calienta
        resultado['mediciones'][ruta] = {'con_cache': medir(s, ruta, repeticiones, False),
                                         'sin_cache': medir(s, ruta, repeticiones, True)}
    destino = RAIZ / 'tests/carga/resultados' / f'{datetime.now():%Y%m%d_%H%M}_cache.json'
    destino.write_text(json.dumps(resultado, indent=2), encoding='utf-8')
    for ruta, m in resultado['mediciones'].items():
        for variante, v in m.items():
            print(f'{ruta:18} {variante:10} n={v["n"]} promedio={v["promedio_ms"]} ms  mediana={v["mediana_ms"]} ms  '
                  f'p95={v["p95_ms"]} ms  max={v["max_ms"]} ms')
    print('Resultados en', destino)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
