"""
Monitoreo con verificación automática (contenedor monitor-verificador) y su comportamiento cuando
fallan dependencias, incluidas las del propio monitor. Las pruebas que detienen contenedores
requieren el CLI de Docker en el anfitrión.
"""
import time

import requests

from apoyo import base, esperar_salud, sesion_de


def _esperar(condicion, segundos=90, cada=3):
    limite = time.time() + segundos
    while time.time() < limite:
        valor = condicion()
        if valor:
            return valor
        time.sleep(cada)
    return None


def _disponibilidad():
    r = sesion_de('admin').get('monitoreo', '/disponibilidad')
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _servicio(datos, nombre):
    return next(s for s in datos['servicios'] if s['servicio'] == nombre)


def test_verificacion_automatica_con_historial():
    """Sin que nadie la invoque, el verificador registra rondas: hay historial reciente de los 24 servicios."""
    datos = _disponibilidad()
    assert datos['fuente'] == 'historial', datos['avisos']
    assert len(datos['servicios']) == 24
    edad = time.time() - time.mktime(time.strptime(datos['ultima_verificacion'][:19], '%Y-%m-%dT%H:%M:%S'))
    assert abs(edad) < datos['intervalo_segundos'] * 3 + 6 * 3600 + 60   # tolerancia de zona horaria del host
    documentos = _servicio(datos, 'ms-documentos')
    assert documentos['verificaciones_24h'] >= 1 and documentos['disponibilidad_24h_pct'] is not None
    historial = sesion_de('admin').get('monitoreo', '/disponibilidad/historial', params={'servicio': 'documentos',
                                                                                       'horas': 1}).json()
    assert historial['puntos'] and {'fecha', 'estado', 'latencia_ms'} <= set(historial['puntos'][-1])


def test_liveness_y_readiness_son_distintos(docker):
    """Con el bucket caído ms-documentos sigue VIVO (no hay que reiniciarlo) pero NO LISTO (503)."""
    assert docker('stop', 'abastored-gcs-emulador').returncode == 0
    try:
        assert requests.get(f"{base('documentos')}/health/live", timeout=10).status_code == 200
        listo = requests.get(f"{base('documentos')}/health/ready", timeout=30)
        assert listo.status_code == 503 and listo.json()['estado'] == 'caido'
        # MongoDB opcional en un servicio que no es dueño de colecciones ahí: «degradado», no «caído»
        catalogo = requests.get(f"{base('catalogo')}/health/ready", timeout=10).json()
        assert {d['nombre']: d['critica'] for d in catalogo['dependencias']}['mongodb'] is False

        # El verificador detecta la falla sola y señala la dependencia responsable
        def detectado():
            s = _servicio(_disponibilidad(), 'ms-documentos')
            return s if s['estado'] == 'caido' else None
        documentos = _esperar(detectado)
        assert documentos, 'el verificador no detectó la caída del almacenamiento'
        assert documentos['responsable'] == 'storage' and 'storage' in (documentos['ultimo_error'] or '')
        # La misma ronda evalúa las alertas: se abre una por el servicio y otra por el almacenamiento caído
        def alertas():
            activas = sesion_de('admin').get('monitoreo', '/alertas', params={'activas': 'true'}).json()['alertas']
            return {(a['servicio'], a['regla']) for a in activas} >= {('ms-documentos', 'servicio_caido'),
                                                                     ('storage', 'base_caida')}
        assert _esperar(alertas, segundos=60), 'no se abrieron las alertas'
    finally:
        assert docker('start', 'abastored-gcs-emulador').returncode == 0
    assert _esperar(lambda: _servicio(_disponibilidad(), 'ms-documentos')['estado'] == 'ok'), 'no se recuperó'


def test_el_monitor_informa_aunque_caiga_su_mongodb(docker):
    """Sin MongoDB (su base de historial), el monitor responde con la última verificación guardada en Redis."""
    assert docker('stop', 'abastored-mongo').returncode == 0
    try:
        def desde_redis():
            datos = _disponibilidad()
            return datos if datos['fuente'] == 'ultima_verificacion' else None
        datos = _esperar(desde_redis, segundos=60)
        assert datos, 'el monitor no cayó a la última verificación en Redis'
        assert any('MongoDB' in a for a in datos['avisos'])
        # Los servicios dueños de colecciones en MongoDB aparecen caídos con MongoDB como responsable
        assert _esperar(lambda: _servicio(_disponibilidad(), 'ms-auditoria')['responsable'] == 'mongodb', segundos=90)
    finally:
        assert docker('start', 'abastored-mongo').returncode == 0
        assert esperar_salud('auditoria', segundos=120)
    assert _esperar(lambda: _disponibilidad()['fuente'] == 'historial', segundos=90)


def test_sin_redis_ni_mongodb_el_estado_publico_responde_en_vivo(docker):
    """Sin Redis no se pueden validar sesiones (las rutas protegidas responden 401/503), pero el estado público
    del monitor revisa en vivo y señala a Redis como responsable; el verificador sigue registrando en su log."""
    assert docker('stop', 'abastored-redis', 'abastored-mongo').returncode == 0
    try:
        def en_vivo():
            r = requests.get(f"{base('monitoreo')}/api/v1/estado/publico", timeout=30)
            return r.json() if r.status_code == 200 and r.json()['caidos'] >= 20 else None
        estado = _esperar(en_vivo, segundos=60)
        assert estado, 'el estado público no respondió'
        time.sleep(35)
        bitacora = docker('logs', '--since', '60s', 'monitor-verificador')
        assert 'solo log' in bitacora.stdout + bitacora.stderr or 'VERIFICACION' in bitacora.stdout + bitacora.stderr
    finally:
        assert docker('start', 'abastored-mongo', 'abastored-redis').returncode == 0
        assert esperar_salud('seguridad', segundos=120) and esperar_salud('monitoreo', segundos=120)
