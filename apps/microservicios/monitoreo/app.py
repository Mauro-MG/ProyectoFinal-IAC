"""
ms-monitoreo: estado, métricas y alertas de los 24 microservicios y de las bases de datos.

- Salud: consulta en paralelo el /health de cada servicio del registro único
  (abasto_dominio.registro_servicios) por la red interna de Docker. Un servicio que no
  responde no retrasa a los demás (tiempo de espera de 2 s por servicio).
- Bases de datos: latencia, versión, conexiones y tamaño de PostgreSQL, MongoDB y Redis.
- Métricas: pipeline de agregación sobre `bitacora_peticiones` (MongoDB): peticiones, errores,
  latencia promedio, p95 y máxima por servicio; y los contadores del día que lleva cada
  servicio en Redis (`contador:<servicio>:peticiones:<día>`).
- Alertas de infraestructura (colección `alertas_infraestructura`, de la que es DUEÑO):
  servicio caído, base de datos caída, latencia p95 o tasa de errores 5xx por encima del
  umbral configurado en ms-configuracion (MONITOREO_LATENCIA_ALERTA_MS, MONITOREO_ERRORES_ALERTA_PCT).
  Una alerta se abre una sola vez y se cierra sola cuando la condición desaparece.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bson import ObjectId
from flask import current_app, g
from pymongo import DESCENDING
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado
from abasto_dominio import extensiones, registro_servicios
from abasto_dominio.extensiones import db
from abasto_dominio.servicios.notificaciones import notificar
from abasto_dominio.servicios.parametros import parametro

from esquemas import AlertaCierre, AlertasConsulta, CONTRATOS_XML, MetricasConsulta

srv = Servicio('monitoreo', 'Monitoreo',
               'Estado de los microservicios, comprobaciones de salud y disponibilidad, métricas operativas (fallas y '
               'latencia), disponibilidad de las bases de datos y alertas de infraestructura.',
               xsd=Path(__file__).parent / 'xsd' / 'monitoreo.xsd', contratos=CONTRATOS_XML,
               opcionales=())  # MongoDB es crítica: es dueño de colecciones ahí
app = srv.app


def _alertas():
    return extensiones.mongo_db()['alertas_infraestructura']


def revisar_servicio(nombre, base, timeout=2):
    puerto, descripcion = registro_servicios.SERVICIOS[nombre]
    datos = {'servicio': f'ms-{nombre}', 'puerto_desarrollo': puerto, 'descripcion': descripcion, 'dependencias': []}
    inicio = time.perf_counter()
    try:
        respuesta = requests.get(f'{base}/health', timeout=timeout)
        cuerpo = respuesta.json()
        caidas = [d for d in cuerpo.get('dependencias', []) if d.get('estado') != 'ok']
        estado = 'ok' if respuesta.status_code == 200 else ('degradado' if len(caidas) < len(cuerpo.get('dependencias', [1])) else 'caido')
        return {**datos, 'estado': estado, 'http': respuesta.status_code, 'version': cuerpo.get('version'),
                'tiempo_ms': round((time.perf_counter() - inicio) * 1000, 1), 'dependencias': cuerpo.get('dependencias', [])}
    except (requests.RequestException, ValueError) as error:
        return {**datos, 'estado': 'sin_respuesta', 'error': error.__class__.__name__,
                'tiempo_ms': round((time.perf_counter() - inicio) * 1000, 1)}


def estado_general():
    bases = {n: current_app.config[f'MS_{n.upper()}_URL'] for n in registro_servicios.NOMBRES}
    with ThreadPoolExecutor(max_workers=len(bases)) as grupo:
        servicios = list(grupo.map(lambda n: revisar_servicio(n, bases[n]), bases))
    ok = sum(1 for s in servicios if s['estado'] == 'ok')
    degradados = sum(1 for s in servicios if s['estado'] == 'degradado')
    return {'revisado': datetime.now(timezone.utc), 'total': len(servicios), 'ok': ok, 'degradados': degradados,
            'caidos': len(servicios) - ok - degradados, 'disponibilidad_pct': round(ok * 100 / len(servicios), 1),
            'servicios': servicios}


def _medir(funcion):
    inicio = time.perf_counter()
    try:
        extra = funcion()
        return {'estado': 'ok', 'latencia_ms': round((time.perf_counter() - inicio) * 1000, 1), **extra}
    except Exception as error:  # noqa: BLE001 - se reporta cualquier falla de la base
        db.session.rollback()
        return {'estado': 'caido', 'detalle': str(error).splitlines()[0][:200]}


def bases_de_datos():
    def postgres():
        fila = db.session.execute(text(
            "SELECT split_part(version(), ' ', 2) AS v, (SELECT count(*) FROM pg_stat_activity) AS c, "
            'pg_database_size(current_database()) / 1048576.0 AS mb')).one()
        return {'version': fila.v, 'conexiones': fila.c, 'tamano_mb': round(float(fila.mb), 1)}

    def mongo():
        estado = extensiones.mongo_db().command('dbStats')
        servidor = extensiones.mongo_client.server_info()
        return {'version': servidor.get('version'), 'tamano_mb': round(estado.get('dataSize', 0) / 1048576, 1)}

    def redis():
        info = extensiones.redis_client.info()
        return {'version': info.get('redis_version'), 'conexiones': info.get('connected_clients'),
                'tamano_mb': round(info.get('used_memory', 0) / 1048576, 1)}

    return [{'nombre': 'postgres', **_medir(postgres)}, {'nombre': 'mongodb', **_medir(mongo)},
            {'nombre': 'redis', **_medir(redis)}]


def metricas(horas, servicio=None):
    filtro = {'fecha': {'$gte': datetime.now(timezone.utc) - timedelta(hours=horas)}}
    if servicio:
        filtro['servicio'] = servicio
    filas = list(extensiones.mongo_db()['bitacora_peticiones'].aggregate([
        {'$match': filtro},
        {'$group': {'_id': '$servicio', 'peticiones': {'$sum': 1},
                    'errores_cliente': {'$sum': {'$cond': [{'$and': [{'$gte': ['$status', 400]},
                                                                     {'$lt': ['$status', 500]}]}, 1, 0]}},
                    'errores_servidor': {'$sum': {'$cond': [{'$gte': ['$status', 500]}, 1, 0]}},
                    'xml': {'$sum': {'$cond': [{'$eq': ['$formato', 'xml']}, 1, 0]}},
                    'prom': {'$avg': '$duracion_ms'}, 'max': {'$max': '$duracion_ms'},
                    'duraciones': {'$push': '$duracion_ms'}, 'ultima': {'$max': '$fecha'}}},
        {'$sort': {'_id': 1}},
    ], allowDiskUse=True))
    dia = datetime.now(timezone.utc).strftime('%Y%m%d')
    contadores = {}
    try:
        pipe = extensiones.redis_client.pipeline()
        for f in filas:
            pipe.get(f"contador:{f['_id']}:peticiones:{dia}")
            pipe.get(f"contador:{f['_id']}:errores:{dia}")
        valores = pipe.execute()
        for i, f in enumerate(filas):
            contadores[f['_id']] = (int(valores[2 * i] or 0), int(valores[2 * i + 1] or 0))
    except Exception:  # noqa: BLE001 - sin Redis se reportan en cero
        pass
    resultado = []
    for f in filas:
        duraciones = sorted(d for d in f['duraciones'] if d is not None)
        p95 = duraciones[min(int(len(duraciones) * 0.95), len(duraciones) - 1)] if duraciones else None
        hoy = contadores.get(f['_id'], (0, 0))
        resultado.append({
            'servicio': f['_id'], 'peticiones': f['peticiones'], 'errores_cliente': f['errores_cliente'],
            'errores_servidor': f['errores_servidor'],
            'tasa_error_servidor_pct': round(f['errores_servidor'] * 100 / f['peticiones'], 2) if f['peticiones'] else 0,
            'latencia_prom_ms': round(f['prom'] or 0, 1), 'latencia_p95_ms': p95, 'latencia_max_ms': f['max'] or 0,
            'respuestas_xml': f['xml'], 'ultima': f['ultima'], 'peticiones_hoy': hoy[0], 'errores_hoy': hoy[1]})
    return resultado


def alerta_a_dict(d):
    return {'id': str(d['_id']), 'servicio': d['servicio'], 'regla': d['regla'], 'severidad': d['severidad'],
            'mensaje': d['mensaje'], 'valor': d.get('valor'), 'umbral': d.get('umbral'), 'activa': d['activa'],
            'fecha': d['fecha'], 'actualizada': d.get('actualizada'), 'cerrada': d.get('cerrada'),
            'comentario': d.get('comentario')}


def evaluar_alertas():
    """Calcula las condiciones actuales, abre las alertas nuevas y cierra las que ya no se cumplen."""
    ahora = datetime.now(timezone.utc)
    condiciones = {}   # (servicio, regla) -> (severidad, mensaje, valor, umbral)
    for s in estado_general()['servicios']:
        if s['estado'] in ('caido', 'sin_respuesta'):
            condiciones[(s['servicio'], 'servicio_caido')] = ('critica', f"{s['servicio']} no responde ({s.get('error') or s.get('http')}).", None, None)
        elif s['estado'] == 'degradado':
            caidas = ', '.join(d['nombre'] for d in s['dependencias'] if d.get('estado') != 'ok')
            condiciones[(s['servicio'], 'dependencia_caida')] = ('critica', f"{s['servicio']} sin acceso a: {caidas}.", None, None)
    for b in bases_de_datos():
        if b['estado'] != 'ok':
            condiciones[(b['nombre'], 'base_caida')] = ('critica', f"{b['nombre']} no responde: {b.get('detalle')}", None, None)
    latencia = float(parametro('MONITOREO_LATENCIA_ALERTA_MS'))
    errores = float(parametro('MONITOREO_ERRORES_ALERTA_PCT'))
    for m in metricas(1):
        if m['peticiones'] >= 20 and m['latencia_p95_ms'] and m['latencia_p95_ms'] > latencia:
            condiciones[(f"ms-{m['servicio']}", 'latencia_alta')] = (
                'advertencia', f"Latencia p95 de ms-{m['servicio']} en la última hora: {m['latencia_p95_ms']} ms.",
                m['latencia_p95_ms'], latencia)
        if m['peticiones'] >= 20 and m['tasa_error_servidor_pct'] > errores:
            condiciones[(f"ms-{m['servicio']}", 'errores_5xx')] = (
                'critica', f"{m['tasa_error_servidor_pct']} % de respuestas 5xx en ms-{m['servicio']} la última hora.",
                m['tasa_error_servidor_pct'], errores)

    abiertas = {(a['servicio'], a['regla']): a for a in _alertas().find({'activa': True})}
    nuevas, vigentes, resueltas = [], 0, 0
    for llave, (severidad, mensaje, valor, umbral) in condiciones.items():
        if llave in abiertas:
            vigentes += 1
            _alertas().update_one({'_id': abiertas[llave]['_id']},
                                  {'$set': {'actualizada': ahora, 'mensaje': mensaje, 'valor': valor}})
        else:
            documento = {'servicio': llave[0], 'regla': llave[1], 'severidad': severidad, 'mensaje': mensaje,
                         'valor': valor, 'umbral': umbral, 'activa': True, 'fecha': ahora, 'actualizada': ahora}
            documento['_id'] = _alertas().insert_one(documento).inserted_id
            nuevas.append(documento)
    for llave, alerta in abiertas.items():
        if llave not in condiciones:
            resueltas += 1
            _alertas().update_one({'_id': alerta['_id']}, {'$set': {
                'activa': False, 'cerrada': ahora, 'comentario': 'Se cerró sola: la condición ya no se cumple.'}})
    criticas = [a for a in nuevas if a['severidad'] == 'critica']
    if criticas:
        administradores = [str(f.id) for f in db.session.execute(text(
            "SELECT u.id FROM usuarios u JOIN roles r ON r.id = u.rol_id "
            "WHERE r.permisos ? 'servicios.monitorear' AND u.activo"))]
        notificar(administradores, 'sistema', f'{len(criticas)} alerta(s) crítica(s) de infraestructura',
                  '; '.join(a['mensaje'] for a in criticas)[:900], url='/monitoreo/servicios', prioridad='alta',
                  origen='monitoreo')
    return {'revisado': ahora, 'nuevas': len(nuevas), 'vigentes': vigentes, 'resueltas': resueltas,
            'alertas': [alerta_a_dict(a) for a in nuevas]}


# ---------------------------------------------------------------- rutas

@srv.ruta('/estado', 'GET', resumen='Estado de los 24 microservicios', etiqueta='Salud',
          permisos=['servicios.monitorear'], raiz_xml='estado')
def estado():
    """Revisa en paralelo el /health de cada servicio. `degradado`: responde pero le falla alguna base de datos."""
    return estado_general()


@srv.ruta('/estado/publico', 'GET', resumen='Disponibilidad general (sin detalle)', etiqueta='Salud', publico=True,
          raiz_xml='estado')
def estado_publico():
    """Para la página de estado de las apps: sólo cuántos servicios están arriba, sin errores internos."""
    general = estado_general()
    return {**general, 'servicios': [{k: s.get(k) for k in ('servicio', 'puerto_desarrollo', 'descripcion', 'estado')}
                                     | {'dependencias': []} for s in general['servicios']]}


@srv.ruta('/estado/<nombre>', 'GET', resumen='Estado de un servicio', etiqueta='Salud',
          permisos=['servicios.monitorear'], raiz_xml='servicio')
def estado_servicio(nombre):
    nombre = nombre.removeprefix('ms-')
    if nombre not in registro_servicios.SERVICIOS:
        raise no_encontrado(f'El servicio ms-{nombre}')
    return revisar_servicio(nombre, current_app.config[f'MS_{nombre.upper()}_URL'])


@srv.ruta('/bases-datos', 'GET', resumen='PostgreSQL, MongoDB y Redis', etiqueta='Salud',
          permisos=['servicios.monitorear'], raiz_xml='bases_datos')
def estado_bases():
    return {'revisado': datetime.now(timezone.utc), 'bases': bases_de_datos()}


@srv.ruta('/metricas', 'GET', resumen='Peticiones, errores y latencia por servicio', etiqueta='Métricas',
          permisos=['servicios.monitorear'], consulta=MetricasConsulta, raiz_xml='metricas')
def ver_metricas(q):
    """Agregación sobre bitacora_peticiones (MongoDB, 30 días) más los contadores del día en Redis."""
    return {'horas': q.horas, 'servicios': metricas(q.horas, q.servicio)}


@srv.ruta('/metricas/<nombre>/serie', 'GET', resumen='Serie por hora de un servicio', etiqueta='Métricas',
          permisos=['servicios.monitorear'], consulta=MetricasConsulta, raiz_xml='serie')
def serie(nombre, q):
    """Peticiones, errores 5xx y latencia promedio por hora (para graficar con Highcharts)."""
    nombre = nombre.removeprefix('ms-')
    filas = extensiones.mongo_db()['bitacora_peticiones'].aggregate([
        {'$match': {'servicio': nombre, 'fecha': {'$gte': datetime.now(timezone.utc) - timedelta(hours=q.horas)}}},
        {'$group': {'_id': {'$dateTrunc': {'date': '$fecha', 'unit': 'hour'}}, 'peticiones': {'$sum': 1},
                    'errores': {'$sum': {'$cond': [{'$gte': ['$status', 500]}, 1, 0]}},
                    'latencia': {'$avg': '$duracion_ms'}}},
        {'$sort': {'_id': 1}}])
    return {'servicio': f'ms-{nombre}', 'horas': q.horas, 'puntos': [
        {'hora': f['_id'], 'peticiones': f['peticiones'], 'errores': f['errores'],
         'latencia_prom_ms': round(f['latencia'] or 0, 1)} for f in filas]}


@srv.ruta('/alertas', 'GET', resumen='Alertas de infraestructura', etiqueta='Alertas',
          permisos=['servicios.monitorear'], consulta=AlertasConsulta, raiz_xml='alertas')
def listar_alertas(q):
    filtro = {'activa': True} if q.activas else {}
    if q.servicio:
        filtro['servicio'] = q.servicio
    documentos = list(_alertas().find(filtro).sort('fecha', DESCENDING).limit(q.limite))
    return {'total': len(documentos), 'alertas': [alerta_a_dict(d) for d in documentos]}


@srv.ruta('/alertas/evaluaciones', 'POST', resumen='Evaluar las reglas de alerta ahora', etiqueta='Alertas',
          permisos=['servicios.monitorear'], raiz_xml='evaluacion')
def evaluar():
    """Abre alertas por servicio caído o degradado, base de datos caída, latencia p95 alta o errores 5xx, y cierra
    las que ya no aplican. Las críticas nuevas se avisan a los administradores (ms-notificaciones). En producción
    se invoca cada minuto con Cloud Scheduler."""
    return evaluar_alertas()


@srv.ruta('/alertas/<id>/cierre', 'POST', resumen='Cerrar una alerta a mano', etiqueta='Alertas',
          permisos=['servicios.monitorear'], cuerpo=AlertaCierre, raiz_xml='alerta', entrada_xml='alerta_cierre',
          ejemplo_entrada={'comentario': 'Se reinició el contenedor'})
def cerrar_alerta(id, datos):
    try:
        oid = ObjectId(id)
    except Exception:  # noqa: BLE001
        raise no_encontrado('La alerta')
    alerta = _alertas().find_one({'_id': oid})
    if not alerta:
        raise no_encontrado('La alerta')
    if not alerta['activa']:
        raise ErrorApi(409, 'alerta_cerrada', 'La alerta ya estaba cerrada.')
    cambios = {'activa': False, 'cerrada': datetime.now(timezone.utc),
               'comentario': datos.comentario or f"Cerrada por {g.claims.get('nombre')}"}
    _alertas().update_one({'_id': oid}, {'$set': cambios})
    return alerta_a_dict({**alerta, **cambios})
