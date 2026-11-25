"""
Ejecuta las pruebas de AbastoRed de forma reproducible y genera su reporte.

    python scripts/ejecutar_pruebas.py                    unitarias + integración
    python scripts/ejecutar_pruebas.py --solo unitarias    sólo unitarias (no necesitan Docker)
    python scripts/ejecutar_pruebas.py --solo integracion  sólo integración (sistema levantado)

1. Crea el entorno virtual .venv si no existe e instala las dependencias de las
   pruebas (bibliotecas del proyecto + tests/requirements.txt). Sólo reinstala
   si cambiaron los archivos de dependencias.
2. Registra el ambiente: fecha, sistema operativo, versiones de Python, pytest y
   Docker, commit de git y estado de los contenedores.
3. Corre pytest y clasifica cada prueba como aprobada, fallida, error, omitida
   (faltó algo del ambiente) o no aplica (no tiene sentido en ese ambiente).
4. Escribe en reportes/<fecha>/ y en docs/pruebas/ (última corrida):
   reporte.html, resultados.json, junit.xml y salida.txt.

El código de salida es el de pytest (0 = todas las ejecutadas aprobaron).
"""
import argparse
import hashlib
import html
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
VENV = RAIZ / '.venv'
DEPENDENCIAS = [RAIZ / 'tests' / 'requirements.txt', RAIZ / 'libs' / 'abasto_dominio' / 'pyproject.toml',
                RAIZ / 'libs' / 'abasto_api' / 'pyproject.toml',
                RAIZ / 'apps' / 'escritorio' / 'requirements.txt']   # PySide6: pruebas de la app de escritorio
ESTADOS = ('aprobada', 'fallida', 'error', 'omitida', 'no_aplica')
NOMBRES = {'aprobada': 'Aprobadas', 'fallida': 'Fallidas', 'error': 'Con error', 'omitida': 'Omitidas',
           'no_aplica': 'No aplican'}


def python_del_venv():
    # Dentro del contenedor de pruebas las dependencias ya vienen instaladas en la imagen
    if os.environ.get('PRUEBAS_SIN_VENV') == '1':
        return Path(sys.executable)
    # Windows (python.org), Linux/macOS y Python de MSYS2 en Windows (bin/python.exe)
    for candidato in (VENV / 'Scripts' / 'python.exe', VENV / 'bin' / 'python', VENV / 'bin' / 'python.exe'):
        if candidato.exists():
            return candidato
    return None


def preparar_entorno():
    python = python_del_venv()
    if not python:
        print(f'Creando entorno virtual en {VENV} …')
        subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
        python = python_del_venv()
    if os.environ.get('PRUEBAS_SIN_VENV') == '1':
        return python
    huella = hashlib.sha256(b''.join(p.read_bytes() for p in DEPENDENCIAS)).hexdigest()
    marca = VENV / '.dependencias_pruebas'
    if not marca.exists() or marca.read_text() != huella:
        print('Instalando dependencias de las pruebas …')
        subprocess.run([str(python), '-m', 'pip', 'install', '-q', '--disable-pip-version-check',
                        '-e', str(RAIZ / 'libs' / 'abasto_dominio'), '-e', str(RAIZ / 'libs' / 'abasto_api'),
                        '-r', str(RAIZ / 'tests' / 'requirements.txt'),
                        '-r', str(RAIZ / 'apps' / 'escritorio' / 'requirements.txt')], check=True)
        marca.write_text(huella)
    return python


def salida_de(*comando):
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=30, cwd=RAIZ, encoding='utf-8',
                           errors='replace')
        return r.stdout.strip() or r.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return f'no disponible ({error.__class__.__name__})'


def ambiente(python, comando):
    contenedores = []
    for linea in salida_de('docker', 'compose', 'ps', '--format', '{{.Name}}|{{.Status}}').splitlines():
        if '|' in linea:
            nombre, estado = linea.split('|', 1)
            contenedores.append({'nombre': nombre, 'estado': estado})
    cambios = salida_de('git', 'status', '--porcelain')
    return {
        'fecha': datetime.now().isoformat(timespec='seconds'),
        'comando': comando,
        'sistema_operativo': f'{platform.system()} {platform.release()} ({platform.machine()})',
        'python': salida_de(str(python), '--version'),
        'pytest': salida_de(str(python), '-m', 'pytest', '--version'),
        'docker': salida_de('docker', '--version'),
        'docker_compose': salida_de('docker', 'compose', 'version', '--short'),
        'git_rama': salida_de('git', 'rev-parse', '--abbrev-ref', 'HEAD'),
        'git_commit': salida_de('git', 'rev-parse', '--short', 'HEAD'),
        'git_cambios_sin_commit': len([l for l in cambios.splitlines() if l.strip()]) if 'no disponible' not in cambios else None,
        'modo_pruebas': os.environ.get('PRUEBAS_MODO', 'gateway'),
        'host_pruebas': os.environ.get('PRUEBAS_HOST', 'https://localhost'),
        'contenedores': contenedores,
    }


def reporte_html(datos):
    amb, res = datos['ambiente'], datos['resumen']
    color = {'aprobada': '#237a4b', 'fallida': '#b3322a', 'error': '#b3322a', 'omitida': '#9a6400',
             'no_aplica': '#5f6b64'}
    e = lambda t: html.escape(str(t if t is not None else ''))  # noqa: E731
    cifras = ''.join(f'<div class="cifra"><b style="color:{color[k]}">{res[k]}</b>{NOMBRES[k]}</div>' for k in ESTADOS)
    filas_amb = ''.join(f'<tr><th>{e(k.replace("_", " "))}</th><td>{e(v)}</td></tr>'
                        for k, v in amb.items() if k != 'contenedores')
    filas_cont = ''.join(f'<tr><td>{e(c["nombre"])}</td><td>{e(c["estado"])}</td></tr>' for c in amb['contenedores'])
    filas = []
    for p in datos['pruebas']:
        detalle = f'<details><summary>ver</summary><pre>{e(p["detalle"])}</pre></details>' if p['detalle'] else ''
        filas.append(f'<tr><td><code>{e(p["id"])}</code><div class="tenue">{e(p["descripcion"])}</div></td>'
                     f'<td style="color:{color[p["estado"]]};font-weight:600">{e(NOMBRES[p["estado"]][:-1])}</td>'
                     f'<td class="num">{p["duracion_s"]:.2f} s</td><td>{detalle}</td></tr>')
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Reporte de pruebas</title><style>
body{{margin:0;font:14px/1.5 system-ui,'Segoe UI',sans-serif;color:#1d2420}} main{{max-width:1150px;margin:0 auto;padding:24px 16px}}
h1{{margin:0 0 4px}} h2{{margin:32px 0 8px;border-bottom:2px solid #1d2420}} .tenue{{color:#5f6b64;font-size:12px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #dedcd4;padding:4px 6px;text-align:left;vertical-align:top}}
th{{background:#f7f6f2;white-space:nowrap}} .num{{text-align:right;white-space:nowrap}} pre{{white-space:pre-wrap;font-size:12px;background:#f1efe8;padding:8px}}
.cifras{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}} .cifra{{border:1px solid #dedcd4;border-radius:8px;padding:10px 14px;min-width:110px}}
.cifra b{{display:block;font-size:1.6rem}}</style></head><body><main>
<h1>AbastoRed · Reporte de pruebas</h1>
<p class="tenue">Generado con <code>{e(amb['comando'])}</code> el {e(amb['fecha'])}.</p>
<div class="cifras"><div class="cifra"><b>{res['total']}</b>Pruebas</div>{cifras}</div>
<p>Se ejecutaron {res['ejecutadas']} pruebas (aprobadas, fallidas o con error); {res['omitida']} se omitieron por el
ambiente y {res['no_aplica']} no aplican en este ambiente. El motivo de cada una aparece en su detalle.</p>
<h2>Ambiente</h2><table>{filas_amb}</table>
<h2>Contenedores al momento de la corrida</h2><table><tr><th>Contenedor</th><th>Estado</th></tr>{filas_cont}</table>
<h2>Resultado por prueba</h2>
<table><tr><th>Prueba</th><th>Estado</th><th>Duración</th><th>Evidencia</th></tr>{''.join(filas)}</table>
</main></body></html>"""


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding='utf-8', errors='replace')  # acentos en la consola de Windows
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--solo', choices=('unitarias', 'integracion'))
    args = parser.parse_args()
    comando = os.environ.get('PRUEBAS_COMANDO') or (
        'python scripts/ejecutar_pruebas.py' + (f' --solo {args.solo}' if args.solo else ''))

    python = preparar_entorno()
    marca = datetime.now().strftime('%Y%m%d-%H%M%S')
    carpeta = RAIZ / 'reportes' / f'pruebas_{marca}'
    carpeta.mkdir(parents=True)
    datos_amb = ambiente(python, comando)

    objetivo = ['tests/' + args.solo] if args.solo else ['tests/unitarias', 'tests/integracion']
    entorno = {**os.environ, 'PRUEBAS_RESULTADOS': str(carpeta / 'pytest.json'), 'PYTHONIOENCODING': 'utf-8'}
    print(f'\nEjecutando: pytest {" ".join(objetivo)}\n')
    inicio = time.time()
    with open(carpeta / 'salida.txt', 'w', encoding='utf-8') as salida:
        proceso = subprocess.Popen([str(python), '-m', 'pytest', *objetivo, '-p', 'no:cacheprovider', '-rA', '-v',
                                    f'--junitxml={carpeta / "junit.xml"}'], cwd=RAIZ, env=entorno,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                   errors='replace')
        for linea in proceso.stdout:
            salida.write(linea)
            if ' PASSED' in linea or ' FAILED' in linea or ' SKIPPED' in linea or ' ERROR' in linea or linea.startswith('='):
                print(linea, end='')
        codigo = proceso.wait()

    pytest_json = json.loads((carpeta / 'pytest.json').read_text(encoding='utf-8'))
    pruebas = pytest_json['pruebas']
    resumen = {k: sum(1 for p in pruebas if p['estado'] == k) for k in ESTADOS}
    resumen.update(total=len(pruebas), ejecutadas=resumen['aprobada'] + resumen['fallida'] + resumen['error'],
                   duracion_s=round(time.time() - inicio, 1), codigo_salida=codigo)
    datos = {'ambiente': datos_amb, 'resumen': resumen, 'pruebas': pruebas}
    (carpeta / 'resultados.json').write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    (carpeta / 'reporte.html').write_text(reporte_html(datos), encoding='utf-8')
    (carpeta / 'pytest.json').unlink()

    # La última corrida completa queda versionada como evidencia
    if not args.solo:
        destino = RAIZ / 'docs' / 'pruebas'
        destino.mkdir(parents=True, exist_ok=True)
        for nombre in ('reporte.html', 'resultados.json', 'junit.xml', 'salida.txt'):
            shutil.copy(carpeta / nombre, destino / nombre)

    print('\nResumen: ' + ' · '.join(f'{NOMBRES[k]}: {resumen[k]}' for k in ESTADOS) + f' · Total: {resumen["total"]}')
    print(f'Reporte: {carpeta / "reporte.html"}')
    return codigo


if __name__ == '__main__':
    sys.exit(main())
