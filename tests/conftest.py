"""
Registro de resultados para el reporte de pruebas (scripts/ejecutar_pruebas.py).

Por cada prueba guarda: identificador, archivo, descripción (docstring), estado,
duración y el motivo (si se omitió) o el error (si falló). Sólo escribe el
archivo cuando la variable PRUEBAS_RESULTADOS indica dónde.
"""
import json
import os
import time

_RESULTADOS = {}


def pytest_collection_modifyitems(config, items):
    for item in items:
        doc = (getattr(item, 'function', None) and item.function.__doc__) or ''
        item.user_properties.append(('descripcion', ' '.join(doc.split())))


def _estado(rep):
    if rep.skipped:
        motivo = rep.longrepr[2] if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
        motivo = motivo.removeprefix('Skipped: ')
        return ('no_aplica' if motivo.startswith('No aplica') else 'omitida'), motivo
    if rep.failed:
        return ('fallida' if rep.when == 'call' else 'error'), str(rep.longrepr)[-3000:]
    return 'aprobada', ''


def pytest_runtest_logreport(report):
    registro = _RESULTADOS.setdefault(report.nodeid, {
        'id': report.nodeid, 'archivo': report.nodeid.split('::')[0],
        'descripcion': dict(report.user_properties).get('descripcion', ''),
        'estado': 'aprobada', 'detalle': '', 'duracion_s': 0.0})
    registro['duracion_s'] = round(registro['duracion_s'] + report.duration, 3)
    if report.when == 'call' or report.skipped or report.failed:
        estado, detalle = _estado(report)
        # un error en la preparación o una omisión manda sobre el resultado de la llamada
        if registro['estado'] == 'aprobada' or estado != 'aprobada':
            registro['estado'], registro['detalle'] = estado, detalle


def pytest_sessionfinish(session, exitstatus):
    destino = os.environ.get('PRUEBAS_RESULTADOS')
    if destino:
        with open(destino, 'w', encoding='utf-8') as f:
            json.dump({'terminado': time.strftime('%Y-%m-%dT%H:%M:%S'), 'codigo_salida': int(exitstatus),
                       'pruebas': list(_RESULTADOS.values())}, f, ensure_ascii=False, indent=2)
