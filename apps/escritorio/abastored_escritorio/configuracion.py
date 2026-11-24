"""Configuración de la aplicación de escritorio (variables de entorno opcionales)."""
import os
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[3]

# Dirección del gateway HTTPS. La aplicación no se conecta a ninguna base de datos.
GATEWAY = os.environ.get('ABASTORED_GATEWAY', 'https://localhost')
TIEMPO_ESPERA = float(os.environ.get('ABASTORED_TIMEOUT', '20'))

# Carpeta local: bitácora de actividades (SQLite) y reportes descargados
CARPETA_LOCAL = Path(os.environ.get('ABASTORED_CARPETA', Path.home() / 'AbastoRed'))


def certificado():
    """Certificado del gateway en el que se confía. Por omisión, el autofirmado del proyecto."""
    ruta = os.environ.get('ABASTORED_CA') or RAIZ_REPO / 'infra' / 'certs' / 'abastored.crt'
    return Path(ruta) if Path(ruta).exists() else True   # True: certificados del sistema
