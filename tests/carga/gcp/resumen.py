"""
Resumen en Markdown de UNA corrida (lo llama correr_gcp.sh al terminar):  python resumen.py <carpeta>
Lee los CSV originales de la carpeta y no modifica ninguno.
"""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

D = Path(sys.argv[1])


def leer(nombre):
    try:
        with open(D / nombre, encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def n(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def r1(x):
    v = n(x)
    return '' if v is None else f'{v:.0f}'


print(f'# Resumen de la corrida `{D.name}`\n')
print('```')
print((D / 'ambiente.txt').read_text(encoding='utf-8', errors='ignore').strip())
print('```\n')

eventos = leer('eventos_guardia.csv')
if eventos:
    print('## Eventos de la guardia\n')
    for e in eventos:
        print(f"- {e['hora']} {e['evento']}")
    print()

# ---------------------------------------------------------------- por etapa (línea de tiempo de 10 s)
linea = leer('linea_tiempo.csv')
if linea:
    etapas = []
    for f in linea:
        clave = (f['fase'], f['usuarios'])
        if not etapas or etapas[-1][0] != clave:
            etapas.append((clave, []))
        etapas[-1][1].append(f)
    print('## Por etapa (ventanas de 10 s; se excluye la primera ventana de cada etapa)\n')
    print('| fase | usuarios | ventanas | pet/s | ok | 429 gateway | 429 servicio | 409 | 401/403 | 5xx | timeout+conexión |'
          ' p50 ok (mediana) | p95 ok (mediana) | p95 ok (máx) | CPU VM prom/máx | mem. disp. VM mín (MB) | CPU generador máx |')
    print('|' + '---|' * 17)
    for (fase, usuarios), filas in etapas:
        uso = filas[1:] if len(filas) > 2 else filas
        suma = lambda c: sum(int(x[c]) for x in uso)  # noqa: E731
        total = sum(int(x['peticiones']) for x in uso) or 1
        rps = statistics.mean(n(x['rps']) for x in uso)
        p50 = [n(x['p50_ok_ms']) for x in uso if n(x['p50_ok_ms']) is not None]
        p95 = [n(x['p95_ok_ms']) for x in uso if n(x['p95_ok_ms']) is not None]
        cpu = [n(x['cpu_vm_pct']) for x in uso if n(x['cpu_vm_pct']) is not None]
        mem = [n(x['mem_disp_vm_mb']) for x in uso if n(x['mem_disp_vm_mb']) is not None]
        gen = [n(x['cpu_generador_pct']) for x in uso if n(x['cpu_generador_pct']) is not None]
        pct = lambda c: f'{suma(c)} ({suma(c) / total:.1%})'  # noqa: E731
        print(f"| {fase} | {usuarios} | {len(uso)} | {rps:.1f} | {pct('ok')} | {pct('429_gateway')} | "
              f"{pct('429_servicio')} | {suma('409_negocio')} | {suma('401_403')} | {pct('5xx')} | "
              f"{suma('timeout') + suma('conexion')} | {r1(statistics.median(p50)) if p50 else '-'} | "
              f"{r1(statistics.median(p95)) if p95 else '-'} | {r1(max(p95)) if p95 else '-'} | "
              f"{(f'{statistics.mean(cpu):.0f} / {max(cpu):.0f} %') if cpu else '-'} | {r1(min(mem)) if mem else '-'} | "
              f"{r1(max(gen)) if gen else '-'} % |")
    print()

# ---------------------------------------------------------------- totales por endpoint
cat = leer('resultados_por_categoria.csv')
if cat:
    print('## Por endpoint (toda la corrida; latencias SOLO de respuestas exitosas)\n')
    print('| endpoint | total | ok | 429 gw | 429 srv | 409 | 401/403 | otros 4xx | 5xx | timeout | conexión |'
          ' contrato | prom ok | p50 ok | p95 ok | p99 ok | máx ok |')
    print('|' + '---|' * 17)
    for f in cat:
        nombre = f"**{f['endpoint']}**" if f['endpoint'] == 'TOTAL' else f['endpoint']
        print(f"| {nombre} | {f['total']} | {f['ok']} | {f['429_gateway']} | {f['429_servicio']} | "
              f"{f['409_negocio']} | {f['401_403']} | {f['4xx_otro']} | {f['5xx']} | {f['timeout']} | "
              f"{f['conexion']} | {f['falla_contrato']} | {r1(f['ok_prom_ms'])} | {r1(f['ok_p50_ms'])} | {r1(f['ok_p95_ms'])} | "
              f"{r1(f['ok_p99_ms'])} | {r1(f['ok_max_ms'])} |")
    print()

stats = [f for f in leer('locust_stats.csv') if f.get('Name') == 'Aggregated']
if stats:
    s = stats[0]
    print('## Agregado según Locust (mezcla éxitos y rechazos en los percentiles)\n')
    print(f"peticiones {s['Request Count']} · fallas {s['Failure Count']} · promedio {float(s['Average Response Time']):.0f} ms"
          f" · p50 {s['50%']} · p95 {s['95%']} · p99 {s['99%']} · máx {float(s['Max Response Time']):.0f} ms"
          f" · {float(s['Requests/s']):.2f} pet/s\n")

# ---------------------------------------------------------------- recursos de la VM y contenedores
vm, ct, alertas = [], defaultdict(list), []
try:
    for linea_vm in (D / 'muestras_vm.csv').read_text(encoding='utf-8', errors='ignore').splitlines():
        p = linea_vm.strip().split(',')
        if p[0] == 'VM' and len(p) >= 10:
            vm.append([n(x) for x in p[1:10]])
        elif p[0] == 'CT' and len(p) >= 6:
            ct[p[2]].append((n(p[3]), p[4]))
        elif p[0] == 'ALERTA':
            alertas.append(linea_vm)
except OSError:
    pass
if vm:
    cpu = [100 - v[6] for v in vm]
    print('## Recursos de la VM (muestras cada ~5 s)\n')
    print(f'- CPU usada: promedio {statistics.mean(cpu):.0f} %, máximo {max(cpu):.0f} % · steal máx {max(v[8] for v in vm):.0f} %'
          f' · carga 1 min máx {max(v[3] for v in vm):.1f}')
    print(f'- Memoria disponible: mínimo {min(v[1] for v in vm):.0f} MB · disco libre mínimo {min(v[2] for v in vm):.0f} GB')
    print(f'- Alertas de reinicio/OOM de contenedores: {len(alertas) or "ninguna"}')
    for a in alertas[:10]:
        print(f'  - `{a}`')
    oom = (D / 'oom_kernel.txt').read_text(encoding='utf-8', errors='ignore').strip() if (D / 'oom_kernel.txt').exists() else ''
    print(f'- Kernel: {oom.splitlines()[-1] if oom else "sin dato"}\n')
if ct:
    print('### Contenedores con más CPU (promedio y máximo; 100 % = 1 vCPU)\n')
    print('| contenedor | CPU prom % | CPU máx % | memoria (última muestra) |')
    print('|---|---|---|---|')
    orden = sorted(ct, key=lambda k: -statistics.mean(v[0] or 0 for v in ct[k]))
    for k in orden[:12]:
        valores = [v[0] or 0 for v in ct[k]]
        print(f'| {k} | {statistics.mean(valores):.1f} | {max(valores):.1f} | {ct[k][-1][1]} |')
    print()
