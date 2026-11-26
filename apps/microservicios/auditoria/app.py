"""
ms-auditoria: bitácora centralizada y trazabilidad de operaciones distribuidas.

Fuentes:
- PostgreSQL `auditoria_eventos`: cada servicio agrega el evento en la MISMA transacción de su
  operación (libs/abasto_dominio/servicios/auditoria.py); la tabla es de sólo inserción.
  Es la única tabla en la que escriben varios servicios, y sólo con INSERT (ver
  docs/propiedad_de_datos.md); nadie la modifica ni la borra.
- MongoDB `eventos_auditoria`: al confirmarse la transacción, el evento se copia aquí con el
  servicio, el X-Correlation-ID, el método y la ruta, y la lista de campos cambiados. Este
  servicio es el DUEÑO de esa colección: la consulta y es el único que la corrige
  (conciliación) o le agrega eventos de clientes externos (POST /eventos).
- MongoDB `bitacora_peticiones`: cada petición a cada servicio (la escribe abasto_api).

Con el X-Correlation-ID se reconstruye la traza completa: qué servicios atendieron la
operación, en qué orden, cuánto tardó cada uno y qué datos cambió cada uno.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bson import ObjectId
from flask import g, request
from pymongo import ASCENDING, DESCENDING

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, sobre_lista
from abasto_dominio import extensiones
from abasto_dominio.modelos import AuditoriaEvento
from abasto_dominio.servicios.auditoria import COLECCION, cambios as calcular_cambios

from esquemas import (CONTRATOS_XML, ConciliacionEntrada, EventoEntrada, EventosConsulta, RegistrosConsulta,
                      ResumenConsulta)

srv = Servicio('auditoria', 'Auditoría',
               'Bitácora centralizada de operaciones sensibles (usuario, servicio, fecha, identificador de '
               'correlación y cambios realizados), consulta por filtros y trazabilidad de operaciones distribuidas.',
               xsd=Path(__file__).parent / 'xsd' / 'auditoria.xsd', contratos=CONTRATOS_XML,
               opcionales=())  # MongoDB es crítica: es dueño de colecciones ahí
app = srv.app


def _eventos():
    return extensiones.mongo_db()[COLECCION]


def _texto(valor):
    if valor is None or isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False, default=str)


def _cambios(lista):
    return [{'campo': c['campo'], 'antes': _texto(c.get('antes')), 'despues': _texto(c.get('despues'))}
            for c in lista or []]


def evento_a_dict(d):
    return {'id': str(d['_id']), 'id_postgres': d.get('id_postgres'), 'fecha': d['fecha'],
            'servicio': d.get('servicio'), 'correlation_id': d.get('correlation_id'), 'usuario_id': d.get('usuario_id'),
            'rol': d.get('rol'), 'tipo_evento': d['tipo_evento'], 'entidad': d['entidad'],
            'entidad_id': d.get('entidad_id'), 'descripcion': d.get('descripcion'), 'metodo': d.get('metodo'),
            'ruta': d.get('ruta'), 'ip': d.get('ip'), 'cambios': _cambios(d.get('cambios'))}


def _fecha(valor, fin=False):
    if not valor:
        return None
    try:
        dia = datetime.strptime(valor, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        raise ErrorApi(400, 'fecha_invalida', 'Las fechas deben tener formato AAAA-MM-DD.')
    return dia + timedelta(days=1) if fin else dia


def _fecha_local(valor):
    # PostgreSQL guarda created_at sin zona, en hora de Monterrey (ver docker-compose.yml)
    if not valor:
        return datetime.now(timezone.utc)
    try:
        return valor.replace(tzinfo=ZoneInfo('America/Monterrey'))
    except ZoneInfoNotFoundError:
        return valor.replace(tzinfo=timezone(timedelta(hours=-6)))


# ---------------------------------------------------------------- consulta

@srv.ruta('/eventos', 'GET', resumen='Bitácora centralizada (MongoDB)', etiqueta='Bitácora',
          permisos=['auditoria.ver'], consulta=EventosConsulta, raiz_xml='eventos')
def listar_eventos(q):
    """Filtros combinables por servicio, usuario, entidad, tipo, correlation_id, texto y fechas. Más recientes
    primero."""
    filtro = {}
    for campo in ('servicio', 'usuario_id', 'entidad', 'entidad_id', 'tipo_evento', 'correlation_id'):
        if getattr(q, campo):
            filtro[campo] = getattr(q, campo)
    if q.texto:
        filtro['descripcion'] = {'$regex': q.texto.replace('.', r'\.'), '$options': 'i'}
    rango = {k: v for k, v in (('$gte', _fecha(q.desde)), ('$lt', _fecha(q.hasta, fin=True))) if v}
    if rango:
        filtro['fecha'] = rango
    total = _eventos().count_documents(filtro)
    cursor = (_eventos().find(filtro).sort('fecha', DESCENDING)
              .skip((q.pagina - 1) * q.por_pagina).limit(q.por_pagina))
    return sobre_lista([evento_a_dict(d) for d in cursor], total, q.pagina, q.por_pagina, 'eventos')


@srv.ruta('/eventos/<id>', 'GET', resumen='Un evento con sus datos anteriores y nuevos', etiqueta='Bitácora',
          permisos=['auditoria.ver'], raiz_xml='evento')
def obtener_evento(id):
    try:
        documento = _eventos().find_one({'_id': ObjectId(id)})
    except Exception:  # noqa: BLE001 - id con formato inválido
        documento = None
    if not documento:
        raise no_encontrado('El evento')
    return evento_a_dict(documento)


@srv.ruta('/registros', 'GET', resumen='Registros de PostgreSQL (fuente de verdad)', etiqueta='Bitácora',
          permisos=['auditoria.ver'], consulta=RegistrosConsulta, raiz_xml='registros')
def registros(q):
    """La tabla inmutable auditoria_eventos, con los datos completos antes y después de cada cambio."""
    consulta = AuditoriaEvento.query
    for campo in ('entidad', 'entidad_id', 'tipo_evento', 'usuario_id'):
        if getattr(q, campo):
            consulta = consulta.filter(getattr(AuditoriaEvento, campo) == getattr(q, campo))
    if q.desde:
        consulta = consulta.filter(AuditoriaEvento.created_at >= _fecha(q.desde).replace(tzinfo=None))
    if q.hasta:
        consulta = consulta.filter(AuditoriaEvento.created_at < _fecha(q.hasta, fin=True).replace(tzinfo=None))
    resultado = paginar(consulta.order_by(AuditoriaEvento.created_at.desc()), q.pagina, q.por_pagina, lambda e: {
        'id': e.id, 'fecha': e.created_at, 'usuario_id': str(e.usuario_id) if e.usuario_id else None,
        'tipo_evento': e.tipo_evento, 'entidad': e.entidad, 'entidad_id': e.entidad_id, 'descripcion': e.descripcion,
        'datos_anteriores': e.datos_anteriores, 'datos_nuevos': e.datos_nuevos,
        'ip': str(e.ip_address) if e.ip_address else None})
    resultado['registros'] = resultado.pop('items')
    return resultado


@srv.ruta('/trazas/<correlation_id>', 'GET', resumen='Traza completa de una operación distribuida',
          etiqueta='Trazabilidad', permisos=['auditoria.ver', 'servicios.monitorear'], raiz_xml='traza')
def traza(correlation_id):
    """Une, en orden de tiempo, las peticiones (bitacora_peticiones) y los cambios de datos (eventos_auditoria) que
    llevan el mismo X-Correlation-ID. Ejemplo: registrar una venta pasa por ms-ventas y ms-inventario; aquí se ve
    cada petición, su código y tiempo, y qué cambió cada servicio."""
    peticiones = list(extensiones.mongo_db()['bitacora_peticiones']
                      .find({'correlation_id': correlation_id}).sort('fecha', ASCENDING))
    eventos = list(_eventos().find({'correlation_id': correlation_id}).sort('fecha', ASCENDING))
    if not peticiones and not eventos:
        raise no_encontrado('Ese correlation_id')
    pasos = [{'fecha': p['fecha'], 'tipo': 'peticion', 'servicio': f"ms-{p['servicio']}", 'metodo': p.get('metodo'),
              'ruta': p.get('ruta'), 'status': p.get('status'), 'duracion_ms': p.get('duracion_ms'),
              'usuario_id': p.get('usuario_id')} for p in peticiones]
    pasos += [{'fecha': e['fecha'], 'tipo': 'evento', 'servicio': e.get('servicio'), 'metodo': e.get('metodo'),
               'ruta': e.get('ruta'), 'usuario_id': e.get('usuario_id'), 'entidad': e['entidad'],
               'entidad_id': e.get('entidad_id'), 'tipo_evento': e['tipo_evento'], 'descripcion': e.get('descripcion'),
               'cambios': _cambios(e.get('cambios'))} for e in eventos]
    # La petición se registra al terminar; el evento, al confirmar la transacción (antes): se ordena por fecha y,
    # a igual segundo, el evento después de la petición que lo originó no importa para la lectura.
    pasos.sort(key=lambda p: p['fecha'])
    duraciones = [p['duracion_ms'] for p in pasos if p.get('duracion_ms') is not None]
    return {'correlation_id': correlation_id, 'servicios': sorted({p['servicio'] for p in pasos if p['servicio']}),
            'peticiones': len(peticiones), 'eventos': len(eventos),
            'duracion_total_ms': round(max(duraciones), 1) if duraciones else None, 'pasos': pasos}


@srv.ruta('/entidades/<entidad>/<entidad_id>/historial', 'GET', resumen='Historial de cambios de un registro',
          etiqueta='Trazabilidad', permisos=['auditoria.ver'], raiz_xml='historial')
def historial(entidad, entidad_id):
    """Todos los eventos de un registro (p. ej. PedidoAbasto + su UUID) en orden cronológico."""
    documentos = list(_eventos().find({'entidad': entidad, 'entidad_id': entidad_id}).sort('fecha', ASCENDING)
                      .limit(500))
    return {'entidad': entidad, 'entidad_id': entidad_id, 'total': len(documentos),
            'eventos': [evento_a_dict(d) for d in documentos]}


@srv.ruta('/resumen', 'GET', resumen='Eventos por servicio y tipo (agregación MongoDB)', etiqueta='Bitácora',
          permisos=['auditoria.ver'], consulta=ResumenConsulta, raiz_xml='resumen')
def resumen(q):
    desde = datetime.now(timezone.utc) - timedelta(days=q.dias)
    filas = list(_eventos().aggregate([
        {'$match': {'fecha': {'$gte': desde}}},
        {'$group': {'_id': {'servicio': '$servicio', 'tipo_evento': '$tipo_evento'}, 'total': {'$sum': 1},
                    'usuarios': {'$addToSet': '$usuario_id'}, 'ultimo': {'$max': '$fecha'}}},
        {'$sort': {'total': -1}},
    ]))
    return {'dias': q.dias, 'total': sum(f['total'] for f in filas), 'renglones': [
        {'servicio': f['_id'].get('servicio'), 'tipo_evento': f['_id']['tipo_evento'], 'total': f['total'],
         'usuarios': len([u for u in f['usuarios'] if u]), 'ultimo': f['ultimo']} for f in filas]}


# ---------------------------------------------------------------- registro externo y conciliación

@srv.ruta('/eventos', 'POST', resumen='Registrar un evento de un cliente o sistema externo', etiqueta='Registro',
          cuerpo=EventoEntrada, status=201, limite=60, raiz_xml='evento', entrada_xml='evento_entrada',
          ejemplo_entrada={'tipo_evento': 'LECTURA', 'entidad': 'ReporteInventario', 'descripcion':
                           'Exportó el inventario a Excel desde la app de escritorio', 'origen': 'escritorio'})
def registrar(datos):
    """Para operaciones sensibles que ocurren fuera de los servicios (p. ej. una exportación hecha sin conexión en
    la app de escritorio, o una exportación del web). Basta un token válido porque el usuario del evento es siempre
    el del token: no se puede registrar a nombre de otro. Límite: 60 por minuto por usuario."""
    claims = g.claims
    documento = {
        'id_postgres': None, 'servicio': datos.origen if claims.get('tipo') == 'acceso' else claims.get('origen'),
        'correlation_id': g.correlation_id, 'metodo': request.method, 'ruta': request.path, 'rol': claims.get('rol'),
        'usuario_id': claims.get('sub') if claims.get('tipo') == 'acceso' else None,
        'tipo_evento': datos.tipo_evento, 'entidad': datos.entidad, 'entidad_id': datos.entidad_id,
        'descripcion': datos.descripcion, 'cambios': [], 'datos_anteriores': None, 'datos_nuevos': datos.datos,
        'ip': request.remote_addr, 'fecha': datetime.now(timezone.utc),
    }
    documento['_id'] = _eventos().insert_one(documento).inserted_id
    return evento_a_dict(documento)


@srv.ruta('/conciliacion', 'POST', resumen='Copiar a MongoDB los eventos que falten', etiqueta='Registro',
          permisos=['servicios.monitorear'], cuerpo=ConciliacionEntrada, raiz_xml='conciliacion',
          entrada_xml='conciliacion_entrada', ejemplo_entrada={'dias': 7})
def conciliar(datos):
    """Si MongoDB estuvo caído cuando un servicio confirmó su transacción, el evento existe en PostgreSQL pero no en
    la bitácora centralizada. Esta operación los encuentra (por id_postgres) y los copia, marcados como
    `servicio: conciliacion`."""
    desde = datetime.now() - timedelta(days=datos.dias)
    registros_pg = AuditoriaEvento.query.filter(AuditoriaEvento.created_at >= desde).all()
    copiados_ids = {d['id_postgres'] for d in _eventos().find(
        {'id_postgres': {'$in': [e.id for e in registros_pg]}}, {'id_postgres': 1})}
    faltantes = [e for e in registros_pg if e.id not in copiados_ids]
    if faltantes:
        _eventos().insert_many([{
            'id_postgres': e.id, 'servicio': 'conciliacion', 'correlation_id': None, 'metodo': None, 'ruta': None,
            'rol': None, 'usuario_id': str(e.usuario_id) if e.usuario_id else None, 'tipo_evento': e.tipo_evento,
            'entidad': e.entidad, 'entidad_id': e.entidad_id, 'descripcion': e.descripcion,
            'cambios': calcular_cambios(e.datos_anteriores, e.datos_nuevos), 'datos_anteriores': e.datos_anteriores,
            'datos_nuevos': e.datos_nuevos, 'ip': str(e.ip_address) if e.ip_address else None,
            'fecha': _fecha_local(e.created_at)}
            for e in faltantes], ordered=False)
    return {'dias': datos.dias, 'revisados': len(registros_pg), 'faltaban': len(faltantes), 'copiados': len(faltantes)}
