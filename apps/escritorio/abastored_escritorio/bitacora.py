"""
Registro local de actividades (SQLite en la carpeta del usuario).

Guarda cada petición que hace la aplicación (servicio, ruta, resultado y su
X-Correlation-ID) y las acciones del usuario (validó un comercio, exportó un
archivo...). Sirve para que el usuario vea qué hizo aunque no tenga conexión,
y con el correlation_id se busca la operación completa en ms-auditoria.
Las acciones sensibles además se registran en ms-auditoria (POST /eventos).
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from abastored_escritorio import configuracion

ESQUEMA = """
CREATE TABLE IF NOT EXISTS actividad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    usuario TEXT,
    tipo TEXT NOT NULL,            -- peticion | accion
    servicio TEXT,
    descripcion TEXT NOT NULL,
    status INTEGER,
    correlation_id TEXT
);
CREATE INDEX IF NOT EXISTS actividad_fecha ON actividad (fecha DESC);
"""


class Bitacora:
    def __init__(self, archivo=None):
        self.archivo = Path(archivo or configuracion.CARPETA_LOCAL / 'bitacora.sqlite3')
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self._candado = threading.Lock()
        self.usuario = None
        with self._conexion() as c:
            c.executescript(ESQUEMA)

    def _conexion(self):
        return sqlite3.connect(self.archivo)

    def _guardar(self, tipo, servicio, descripcion, status=None, correlation_id=None):
        with self._candado, self._conexion() as c:
            c.execute('INSERT INTO actividad (fecha, usuario, tipo, servicio, descripcion, status, correlation_id) '
                      'VALUES (?, ?, ?, ?, ?, ?, ?)',
                      (datetime.now().isoformat(timespec='seconds'), self.usuario, tipo, servicio, descripcion,
                       status, correlation_id))

    def peticion(self, metodo, servicio, ruta, status, correlation_id):
        self._guardar('peticion', servicio, f'{metodo} {ruta}', status, correlation_id)

    def accion(self, descripcion, servicio=None, correlation_id=None):
        self._guardar('accion', servicio, descripcion, None, correlation_id)

    def recientes(self, limite=500, solo_acciones=False):
        filtro = "WHERE tipo = 'accion'" if solo_acciones else ''
        with self._conexion() as c:
            return [dict(zip(('fecha', 'usuario', 'tipo', 'servicio', 'descripcion', 'status', 'correlation_id'), f))
                    for f in c.execute(f'SELECT fecha, usuario, tipo, servicio, descripcion, status, correlation_id '
                                       f'FROM actividad {filtro} ORDER BY id DESC LIMIT ?', (limite,))]
