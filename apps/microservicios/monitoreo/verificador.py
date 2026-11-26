"""
Verificación periódica de salud (contenedor monitor-verificador, misma imagen que ms-monitoreo).

Cada MONITOREO_INTERVALO_SEGUNDOS (ms-configuracion, 30 s por omisión) revisa los 24 servicios
con sus dependencias (PostgreSQL, Redis, MongoDB y el bucket de Cloud Storage), guarda el
historial y evalúa las alertas. No depende de que alguien abra el panel: corre solo.

Un bloqueo en Redis (monitoreo:verificador) evita que dos verificadores, por ejemplo durante un
despliegue, registren la misma ronda dos veces. Si Redis no responde, verifica igual.
"""
import logging
import signal
import sys
import time

from pymongo import ASCENDING

from app import app, verificar_y_registrar
from abasto_dominio import extensiones
from abasto_dominio.servicios.parametros import parametro

log = logging.getLogger('verificador')
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s')
seguir = True


def detener(*_):
    global seguir
    seguir = False


def preparar_indices():
    """Historial de 30 días (índice TTL) y consulta por servicio y fecha."""
    try:
        coleccion = extensiones.mongo_db()['verificaciones_salud']
        coleccion.create_index([('fecha', ASCENDING)], expireAfterSeconds=30 * 24 * 3600, name='ttl_30_dias')
        coleccion.create_index([('servicio', ASCENDING), ('fecha', ASCENDING)], name='servicio_fecha')
    except Exception as error:  # noqa: BLE001 - se reintenta en la siguiente ronda
        log.warning('Índices de verificaciones_salud pendientes: %s', error.__class__.__name__)
        return False
    return True


def intervalo():
    try:
        return max(10, int(parametro('MONITOREO_INTERVALO_SEGUNDOS')))
    except Exception:  # noqa: BLE001 - sin configuración disponible se usa el valor por omisión
        return 30


def tomar_turno(segundos):
    try:
        return bool(extensiones.redis_client.set('monitoreo:verificador', '1', nx=True, ex=max(5, segundos - 2)))
    except Exception:  # noqa: BLE001
        return True


def main():
    signal.signal(signal.SIGTERM, detener)
    signal.signal(signal.SIGINT, detener)
    with app.app_context():
        indices = preparar_indices()
        log.info('Verificador de salud iniciado')
        while seguir:
            segundos = intervalo()
            if tomar_turno(segundos):
                inicio = time.monotonic()
                try:
                    r = verificar_y_registrar()
                    log.info('Ronda: %s ok, %s degradados, %s caídos; guardado en %s; %.1f s', r['ok'], r['degradados'],
                             r['caidos'], ','.join(r['guardado_en']) or 'solo log', time.monotonic() - inicio)
                except Exception as error:  # noqa: BLE001 - una ronda fallida no detiene al verificador
                    log.error('Ronda fallida: %s: %s', error.__class__.__name__, error)
                finally:
                    extensiones.db.session.remove()
                if not indices:
                    indices = preparar_indices()
            for _ in range(segundos):
                if not seguir:
                    break
                time.sleep(1)
    log.info('Verificador detenido')


if __name__ == '__main__':
    main()
