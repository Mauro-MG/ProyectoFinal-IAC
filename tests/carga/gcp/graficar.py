"""
Gráfica de una corrida a partir de su linea_tiempo.csv (requiere matplotlib):
    python tests/carga/gcp/graficar.py <carpeta_corrida> <salida.png>
Arriba: usuarios y peticiones por segundo separadas en aceptadas / 429 del gateway / 429 del servicio / 5xx y
errores de red. Abajo: p50 y p95 de las respuestas EXITOSAS y CPU de la VM.
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

filas = list(csv.DictReader(open(Path(sys.argv[1]) / 'linea_tiempo.csv', encoding='utf-8')))
t0 = float(filas[0]['t'])
x = [(float(f['t']) - t0) / 60 for f in filas]
num = lambda f, c: float(f[c]) if f[c] not in ('', None) else None  # noqa: E731
por_s = lambda c: [int(f[c]) / 10 for f in filas]  # noqa: E731

fig, (a, b) = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True, gridspec_kw={'height_ratios': [3, 2]})
a.stackplot(x, por_s('ok'), por_s('429_gateway'), por_s('429_servicio'),
            [(int(f['5xx']) + int(f['timeout']) + int(f['conexion'])) / 10 for f in filas],
            labels=['aceptadas (2xx)', '429 gateway (30/s por IP)', '429 servicio (límite por IP de /disponibilidad)',
                    '5xx / timeout / conexión'],
            colors=['#2f7d4f', '#d9822b', '#e8c547', '#b3261e'], alpha=0.9)
a.axhline(30, color='#555', lw=1, ls='--')
a.text(x[0], 30.8, 'límite del gateway: 30 peticiones/s por IP', fontsize=8, color='#444')
a.set_ylabel('peticiones/s')
a2 = a.twinx()
a2.plot(x, [int(f['usuarios']) for f in filas], color='#1f2933', lw=1.6, label='usuarios virtuales')
a2.set_ylabel('usuarios')
a2.set_ylim(0, 140)
h1, l1 = a.get_legend_handles_labels()
h2, l2 = a2.get_legend_handles_labels()
a.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=8, frameon=False)
b.plot(x, [num(f, 'p50_ok_ms') for f in filas], color='#2f7d4f', label='p50 éxitos (ms)')
b.plot(x, [num(f, 'p95_ok_ms') for f in filas], color='#1e5b3e', ls='--', label='p95 éxitos (ms)')
b.set_ylabel('ms')
b.set_ylim(0, 400)
b2 = b.twinx()
b2.plot(x, [num(f, 'cpu_vm_pct') for f in filas], color='#7a7a7a', lw=1, alpha=0.8, label='CPU VM (%)')
b2.set_ylim(0, 100)
b2.set_ylabel('CPU VM %')
h1, l1 = b.get_legend_handles_labels()
h2, l2 = b2.get_legend_handles_labels()
b.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=8, frameon=False, ncol=3)
b.set_xlabel('minutos desde el inicio')
fig.suptitle(f'AbastoRed en GCP (e2-standard-4) por HTTPS + NGINX · {Path(sys.argv[1]).name}', fontsize=11)
fig.tight_layout()
fig.savefig(sys.argv[2], dpi=130)
print('ok', sys.argv[2])
