"""
Configuración de la aplicación de escritorio.

Orden de prioridad (el primero que tenga el valor gana):
  1. Variables de entorno: ABASTORED_GATEWAY, ABASTORED_CA, ABASTORED_CARPETA, ABASTORED_TIMEOUT.
  2. %APPDATA%\\AbastoRed\\abastored.ini   (ajustes del usuario)
  3. abastored.ini junto al ejecutable    (lo pone el instalador)
  4. Valores por omisión (desarrollo: https://localhost y el certificado de infra/certs del repositorio).

Formato del .ini:
    [servidor]
    gateway = https://abastored.ejemplo.mx
    certificado = certificados\\gateway.crt     ; opcional; relativo al .ini o ruta completa
"""
import configparser
import os
import sys
from pathlib import Path

CONGELADA = getattr(sys, 'frozen', False)          # ejecutable generado por el instalador
DIRECTORIO_APP = Path(sys.executable).parent if CONGELADA else Path(__file__).resolve().parent
RAIZ_REPO = None if CONGELADA else Path(__file__).resolve().parents[3]


def _ini():
    valores = {}
    usuario = Path(os.environ.get('APPDATA', Path.home())) / 'AbastoRed' / 'abastored.ini'
    for archivo in (DIRECTORIO_APP / 'abastored.ini', usuario):      # el del usuario sobrescribe al instalado
        if archivo.exists():
            lector = configparser.ConfigParser()
            lector.read(archivo, encoding='utf-8')
            for clave, valor in lector.items('servidor') if lector.has_section('servidor') else []:
                if clave == 'certificado' and valor and not Path(valor).is_absolute():
                    valor = str(archivo.parent / valor)
                valores[clave] = valor
    return valores


_INI = _ini()

# Dirección del gateway HTTPS. La aplicación no se conecta a ninguna base de datos.
GATEWAY = os.environ.get('ABASTORED_GATEWAY') or _INI.get('gateway') or 'https://localhost'
TIEMPO_ESPERA = float(os.environ.get('ABASTORED_TIMEOUT') or _INI.get('tiempo_espera') or 20)

# Carpeta local: bitácora de actividades (SQLite) y reportes descargados
CARPETA_LOCAL = Path(os.environ.get('ABASTORED_CARPETA') or _INI.get('carpeta') or Path.home() / 'AbastoRed')


def certificado():
    """Certificado del gateway en el que se confía; si no hay, los certificados del sistema."""
    candidatos = [os.environ.get('ABASTORED_CA'), _INI.get('certificado')]
    if RAIZ_REPO:
        candidatos.append(RAIZ_REPO / 'infra' / 'certs' / 'abastored.crt')
    for ruta in candidatos:
        if ruta and Path(ruta).exists():
            return Path(ruta)
    return True   # True: autoridades de certificación del sistema (gateway con certificado público)
