"""
Construye el instalador de Windows (.msi) de la aplicación de escritorio.

    cd apps/escritorio
    python instalador/construir_instalador.py --gateway https://<servidor> [--certificado ruta.crt]

Requisitos solo en el equipo que construye: Python 3.12 (python.org) y
    pip install -r requirements.txt cx_Freeze==7.2.3
El usuario final NO necesita Python ni nada más: instala el .msi y abre «AbastoRed» desde el menú
Inicio. El .msi queda en apps/escritorio/dist/.

El instalador incluye:
  - el ejecutable con Python, PySide6, lxml y requests empaquetados;
  - abastored.ini con la dirección del gateway (el usuario puede sobrescribirla en
    %APPDATA%\\AbastoRed\\abastored.ini);
  - opcionalmente el certificado del gateway (solo el certificado PÚBLICO; nunca llaves ni secretos).
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
VERSION = '1.1.0'
# Identificador fijo del producto: las versiones nuevas reemplazan a las anteriores al instalar
CODIGO_ACTUALIZACION = '{6B1E3C2A-5D4F-4A7B-9C1E-2F3A4B5C6D7E}'


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    argumentos.add_argument('--gateway', default='https://localhost')
    argumentos.add_argument('--certificado', help='Certificado público del gateway (.crt); omítelo si el servidor '
                                                  'tiene un certificado de una autoridad reconocida')
    opciones = argumentos.parse_args()

    trabajo = RAIZ / 'build' / 'instalador'
    shutil.rmtree(trabajo, ignore_errors=True)
    (trabajo / 'certificados').mkdir(parents=True)
    ini = ['[servidor]', f'gateway = {opciones.gateway}']
    incluir = [(str(trabajo / 'abastored.ini'), 'abastored.ini')]
    if opciones.certificado:
        origen = Path(opciones.certificado)
        contenido = origen.read_text(encoding='utf-8')
        if 'PRIVATE KEY' in contenido:
            raise SystemExit('Eso es una llave privada: el instalador solo lleva el certificado público.')
        shutil.copy(origen, trabajo / 'certificados' / 'gateway.crt')
        ini.append('certificado = certificados\\gateway.crt')
        incluir.append((str(trabajo / 'certificados'), 'certificados'))
    (trabajo / 'abastored.ini').write_text('\n'.join(ini) + '\n', encoding='utf-8')

    from cx_Freeze import Executable, setup
    sys.argv = [sys.argv[0], 'bdist_msi']
    setup(
        name='AbastoRed',
        version=VERSION,
        description='AbastoRed - aplicación de escritorio (coordinación, análisis y proveedores)',
        author='Equipo 01 - UDEM',
        options={
            'build_exe': {
                'packages': ['abastored_escritorio', 'lxml', 'requests', 'certifi', 'PySide6.QtPrintSupport'],
                'includes': ['abastored_escritorio.__main__'],
                'include_files': incluir,
                'excludes': ['tkinter', 'unittest', 'pytest'],
                'build_exe': str(RAIZ / 'build' / 'exe'),
            },
            'bdist_msi': {
                'upgrade_code': CODIGO_ACTUALIZACION,
                'add_to_path': False,
                'initial_target_dir': r'[ProgramFiles64Folder]\AbastoRed',
                'summary_data': {'author': 'Equipo 01 - UDEM', 'comments': f'Gateway: {opciones.gateway}'},
                'dist_dir': str(RAIZ / 'dist'),
            },
        },
        executables=[Executable(str(RAIZ / 'iniciar.py'), base='gui', target_name='AbastoRed.exe',
                                shortcut_name='AbastoRed', shortcut_dir='ProgramMenuFolder'),
                     # De consola, para soporte: revisa configuración, TLS y contratos sin abrir ventanas
                     Executable(str(RAIZ / 'diagnostico.py'), base=None, target_name='AbastoRed-diagnostico.exe')],
    )
    for msi in (RAIZ / 'dist').glob('*.msi'):
        print(f'Instalador: {msi} ({msi.stat().st_size / 1_048_576:.1f} MB)')


if __name__ == '__main__':
    sys.path.insert(0, str(RAIZ))
    main()
