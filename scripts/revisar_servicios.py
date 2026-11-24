"""
Revisión rápida de los microservicios sin levantar Docker:

    python scripts/revisar_servicios.py              todos
    python scripts/revisar_servicios.py ventas ...   sólo esos

Para cada servicio: regenera su XSD desde esquemas.py, importa app.py (detecta errores de
sintaxis o de importación), cuenta sus rutas y valida su OpenAPI con openapi-spec-validator.
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SERVICIOS = RAIZ / 'apps' / 'microservicios'

PRUEBA = r'''
import sys
sys.path.insert(0, '.')
import app
from openapi_spec_validator import validate
cliente = app.app.test_client()
respuesta = cliente.get('/openapi.json')
validate(respuesta.get_json())
sin_contrato = [r['regla'] for r in app.srv.rutas if r['respuesta'] is None]
print(f"{len(app.srv.rutas)} rutas, OpenAPI válido" + (f"; sin contrato de salida: {sin_contrato}" if sin_contrato else ''))
'''


def main(nombres):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    nombres = nombres or sorted(p.name for p in SERVICIOS.iterdir() if (p / 'app.py').exists())
    fallas = 0
    for nombre in nombres:
        carpeta = SERVICIOS / nombre
        xsd = subprocess.run([sys.executable, '-m', 'abasto_api.contratos', str(carpeta)], capture_output=True, text=True)
        prueba = subprocess.run([sys.executable, '-c', PRUEBA], cwd=carpeta, capture_output=True, text=True,
                                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, encoding='utf-8')
        ok = xsd.returncode == 0 and prueba.returncode == 0
        fallas += not ok
        detalle = prueba.stdout.strip() if ok else (xsd.stderr + prueba.stderr).strip().splitlines()[-1:]
        print(f"{'ok   ' if ok else 'FALLA'} ms-{nombre:<16} {detalle}")
        if not ok:
            print((xsd.stderr + prueba.stderr)[-2500:])
    return 1 if fallas else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
