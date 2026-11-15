"""
ms-sincronizacion: operaciones hechas sin conexión en Android y escritorio.

Es DUEÑO de las colecciones `sincronizacion_lotes` y `sincronizacion_operaciones` (MongoDB).
NO escribe en las tablas de negocio: cada operación se aplica llamando a la API del servicio
dueño con el token del usuario (ms-inventario, ms-ventas, ms-precios, ms-pedidos, ms-demanda),
así se respetan las mismas reglas y permisos que en línea.

- Recepción de lotes en JSON o XML (validado contra el XSD).
- Identificadores únicos generados en el dispositivo: `lote_id` y `operacion_id`. Control de
  duplicados con un índice único (dispositivo_id, operacion_id): una operación ya aplicada no se
  vuelve a aplicar; se responde `duplicada` con su resultado original. Además, cada servicio
  recibe una referencia idempotente (`sync:{operacion_id}` en inventario, `id_cliente` en ventas).
- Orden: las operaciones se aplican en el orden en que se hicieron (`realizada`).
- Conflictos: para cambios de valor absoluto (precio, límites, ajuste de inventario) se compara
  `version_base` (cuándo vio el dispositivo el dato) con la última actualización en el servidor.
  Si el servidor cambió después, se aplica la política: `servidor_gana` (no se aplica y se regresa
  el valor del servidor), `cliente_gana` (se aplica) o `rechazar` (queda para revisión).
  Los movimientos ENTRADA/SALIDA son incrementales y no generan conflicto.
- Reintentos: si el servicio dueño no responde (503), la operación queda `pendiente_reintento`;
  el dispositivo reenvía el lote o llama a POST /lotes/{id}/reintentos.
- Confirmación: la respuesta trae el estado de cada operación y el id del registro en el servidor,
  para que el dispositivo marque sus registros como sincronizados.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import g
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from abasto_api import ErrorApi, Servicio, no_encontrado
from abasto_api.clientes import llamar
from abasto_dominio import extensiones
from abasto_dominio.servicios.parametros import parametro, parametro_texto

from esquemas import CONTRATOS_XML, LoteEntrada, LotesConsulta, ReintentoEntrada

srv = Servicio('sincronizacion', 'Sincronización',
               'Sincronización de operaciones offline desde Android y escritorio: recepción de lotes JSON/XML, '
               'identificadores únicos, control de duplicados, resolución de conflictos, reintentos y confirmación '
               'de registros sincronizados.',
               xsd=Path(__file__).parent / 'xsd' / 'sincronizacion.xsd', contratos=CONTRATOS_XML)
app = srv.app

MONTERREY = timezone(timedelta(hours=-6))
FINALES = ('aplicada', 'duplicada', 'conflicto', 'rechazada')
TIPOS = ('movimiento_inventario', 'venta', 'precio', 'limites_inventario', 'pedido_borrador', 'busqueda')


def _lotes():
    return extensiones.mongo_db()['sincronizacion_lotes']


def _operaciones():
    return extensiones.mongo_db()['sincronizacion_operaciones']


class Reintentar(Exception):
    pass


def _llamar(servicio, metodo, ruta, **kwargs):
    """Llamada al servicio dueño con el token del usuario; 5xx o sin respuesta -> Reintentar."""
    try:
        respuesta = llamar(servicio, metodo, f'/api/v1{ruta}', token=g.token, timeout=5, **kwargs)
    except ErrorApi:
        raise Reintentar(f'ms-{servicio} no respondió')
    if respuesta.status_code >= 500 or respuesta.status_code == 429:
        raise Reintentar(f'ms-{servicio} respondió {respuesta.status_code}')
    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}
    return respuesta.status_code, cuerpo


def _error(cuerpo):
    return (cuerpo.get('error') or {}).get('mensaje') or 'rechazada por el servicio'


def _version_renglon(inventario_id):
    """updated_at del renglón de inventario en el servidor (lo consulta en ms-inventario)."""
    status, cuerpo = _llamar('inventario', 'GET', f'/inventario/{inventario_id}')
    if status != 200:
        return None, cuerpo
    return datetime.fromisoformat(cuerpo['actualizado']) if cuerpo.get('actualizado') else None, cuerpo


def _hay_conflicto(op, inventario_id):
    if not op['version_base']:
        return False, None, None
    version, renglon = _version_renglon(inventario_id)
    if version is None:
        return False, None, renglon
    base = datetime.fromisoformat(op['version_base'])
    # El servidor guarda las fechas sin zona, en hora de Monterrey (UTC-6, sin horario de verano desde 2022).
    # Lo más seguro es que la app mande como version_base el mismo `actualizado` que recibió.
    version = version if version.tzinfo else version.replace(tzinfo=MONTERREY)
    base = base if base.tzinfo else base.replace(tzinfo=MONTERREY)
    return version > base, version, renglon


def aplicar(op, politica, plataforma):
    """Regresa (estado, mensaje, servicio, id_servidor, version_servidor)."""
    d = op['datos']
    tipo = op['tipo']
    if tipo == 'movimiento_inventario':
        if not (d.get('inventario_id') and d.get('tipo_movimiento') and d.get('cantidad') is not None):
            return 'rechazada', 'Faltan inventario_id, tipo_movimiento o cantidad.', None, None, None
        if d['tipo_movimiento'] == 'AJUSTE':
            conflicto, version, _ = _hay_conflicto(op, d['inventario_id'])
            if conflicto and politica != 'cliente_gana':
                return ('conflicto' if politica == 'servidor_gana' else 'rechazada',
                        'El inventario cambió en el servidor después de tu conteo.', 'inventario', None, version)
        status, cuerpo = _llamar('inventario', 'POST', f"/inventario/{d['inventario_id']}/movimientos", json={
            'tipo': d['tipo_movimiento'], 'cantidad': d['cantidad'], 'motivo': d.get('motivo') or f'Offline ({plataforma})',
            'referencia': f"sync:{op['operacion_id']}"})
        if status == 201:
            return 'aplicada', None, 'inventario', str(cuerpo.get('id')), None
        return 'rechazada', _error(cuerpo), 'inventario', None, None

    if tipo == 'venta':
        if not (d.get('comercio_id') and d.get('partidas')):
            return 'rechazada', 'Faltan comercio_id o partidas.', None, None, None
        status, cuerpo = _llamar('ventas', 'POST', '/ventas', json={
            'comercio_id': d['comercio_id'], 'metodo_pago': d.get('metodo_pago') or 'EFECTIVO', 'origen': plataforma,
            'id_cliente': op['operacion_id'], 'fecha_venta': op['realizada'],
            'partidas': [{k: v for k, v in p.items() if v is not None} for p in d['partidas']]})
        if status in (200, 201):
            return ('duplicada' if cuerpo.get('duplicada') else 'aplicada', cuerpo.get('folio'), 'ventas',
                    cuerpo.get('id'), None)
        return 'rechazada', _error(cuerpo), 'ventas', None, None

    if tipo in ('precio', 'limites_inventario'):
        if not d.get('inventario_id'):
            return 'rechazada', 'Falta inventario_id.', None, None, None
        conflicto, version, renglon = _hay_conflicto(op, d['inventario_id'])
        if conflicto and politica != 'cliente_gana':
            actual = (f"precio actual {renglon.get('precio_venta')}" if tipo == 'precio' else
                      f"mínimo {renglon.get('stock_minimo')}, máximo {renglon.get('stock_maximo')}")
            return ('conflicto' if politica == 'servidor_gana' else 'rechazada',
                    f'El dato cambió en el servidor ({actual}).', 'inventario', None, version)
        if tipo == 'precio':
            if not d.get('precio'):
                return 'rechazada', 'Falta precio.', None, None, None
            status, cuerpo = _llamar('precios', 'PUT', f"/inventario/{d['inventario_id']}/precio",
                                     json={'precio': d['precio']})
            servicio = 'precios'
        else:
            cambios = {k: d[k] for k in ('stock_minimo', 'stock_maximo') if d.get(k) is not None}
            if not cambios:
                return 'rechazada', 'Indica stock_minimo o stock_maximo.', None, None, None
            status, cuerpo = _llamar('inventario', 'PATCH', f"/inventario/{d['inventario_id']}", json=cambios)
            servicio = 'inventario'
        if status in (200, 201):
            return 'aplicada', 'Conflicto resuelto: gana el dispositivo.' if conflicto else None, servicio, \
                str(d['inventario_id']), None
        return 'rechazada', _error(cuerpo), servicio, None, None

    if tipo == 'pedido_borrador':
        if not (d.get('comercio_id') and d.get('proveedor_id') and d.get('partidas')):
            return 'rechazada', 'Faltan comercio_id, proveedor_id o partidas.', None, None, None
        status, cuerpo = _llamar('pedidos', 'POST', '/pedidos', json={
            'comercio_id': d['comercio_id'], 'proveedor_id': d['proveedor_id'],
            'partidas': [{'producto_id': p['producto_id'], 'cantidad': p['cantidad']} for p in d['partidas']],
            'notas': f'Capturado sin conexión ({plataforma})'})
        if status == 201:
            return 'aplicada', cuerpo.get('folio'), 'pedidos', cuerpo.get('id'), None
        return 'rechazada', _error(cuerpo), 'pedidos', None, None

    if tipo == 'busqueda':
        status, cuerpo = _llamar('demanda', 'POST', '/demanda/busquedas', json={
            'texto': d.get('texto') or '', 'producto_id': d.get('producto_id'), 'zona_id': d.get('zona_id'),
            'resultados': d.get('resultados') or 0, 'origen': plataforma})
        if status == 201:
            return 'aplicada', None, 'demanda', cuerpo.get('id'), None
        return 'rechazada', _error(cuerpo), 'demanda', None, None
    return 'rechazada', f'Tipo de operación desconocido: {tipo}', None, None, None


def procesar(lote, operaciones):
    """Aplica las operaciones no finales del lote, en orden cronológico."""
    for op in sorted(operaciones, key=lambda o: o['realizada']):
        if op['estado'] in FINALES:
            continue
        try:
            estado, mensaje, servicio, id_servidor, version = aplicar(op, lote['politica_conflictos'], lote['plataforma'])
        except Reintentar as motivo:
            estado, mensaje, servicio, id_servidor, version = 'pendiente_reintento', str(motivo), None, None, None
        _operaciones().update_one({'_id': op['_id']}, {'$set': {
            'estado': estado, 'mensaje': mensaje, 'servicio': servicio, 'id_servidor': id_servidor,
            'version_servidor': version, 'actualizado': datetime.now(timezone.utc)}, '$inc': {'intentos': 1}})
    pendientes = _operaciones().count_documents({'lote_id': lote['_id'], 'estado': 'pendiente_reintento'})
    _lotes().update_one({'_id': lote['_id']}, {'$set': {
        'terminado': datetime.now(timezone.utc) if not pendientes else None, 'actualizado': datetime.now(timezone.utc)}})


def resumen(lote):
    ops = list(_operaciones().find({'lote_id': lote['_id']}).sort('realizada', 1))
    cuenta = lambda e: sum(1 for o in ops if o['estado'] == e)  # noqa: E731
    return {'lote_id': lote['lote_id'], 'dispositivo_id': lote['dispositivo_id'], 'plataforma': lote['plataforma'],
            'recibido': lote['recibido'], 'terminado': lote.get('terminado'),
            'politica_conflictos': lote['politica_conflictos'], 'total': len(ops), 'aplicadas': cuenta('aplicada'),
            'duplicadas': cuenta('duplicada'), 'conflictos': cuenta('conflicto'), 'rechazadas': cuenta('rechazada'),
            'pendientes': cuenta('pendiente_reintento'),
            'resultados': [{'operacion_id': o['operacion_id'], 'tipo': o['tipo'], 'estado': o['estado'],
                            'mensaje': o.get('mensaje'), 'servicio': o.get('servicio'),
                            'id_servidor': o.get('id_servidor'), 'version_servidor': o.get('version_servidor'),
                            'intentos': o.get('intentos', 0)} for o in ops]}


# ---------------------------------------------------------------- rutas

@srv.ruta('/estado', 'GET', resumen='Hora del servidor y límites de sincronización', etiqueta='Sincronización',
          publico=True, raiz_xml='estado')
def estado():
    """Las apps la consultan antes de sincronizar: hora del servidor (para calcular `version_base`), máximo de
    operaciones por lote y la política de conflictos vigente."""
    return {'servidor': datetime.now(timezone.utc), 'max_operaciones': int(parametro('SINCRONIZACION_MAX_OPERACIONES')),
            'politica_conflictos': parametro_texto('SINCRONIZACION_POLITICA_CONFLICTO', 'servidor_gana'),
            'tipos': list(TIPOS)}


@srv.ruta('/lotes', 'POST', resumen='Enviar un lote de operaciones offline', etiqueta='Sincronización',
          permisos=['sincronizacion.enviar'], cuerpo=LoteEntrada, raiz_xml='lote', entrada_xml='lote_entrada',
          ejemplo_entrada={'lote_id': 'b1d4c1e2-0a6f-4f8e-9a2d-6b1f0c3d2e11', 'dispositivo_id': 'android-7f3a',
                           'plataforma': 'android', 'operaciones': [
                               {'operacion_id': '5a7c0e44-1d2b-4c3e-8f9a-0b1c2d3e4f50', 'tipo': 'venta',
                                'realizada': '2026-11-14T08:15:00-06:00', 'datos': {
                                    'comercio_id': '3122a5b1-...', 'metodo_pago': 'EFECTIVO',
                                    'partidas': [{'producto_id': 3, 'cantidad': 2}]}},
                               {'operacion_id': '6b8d1f55-2e3c-4d4f-9a0b-1c2d3e4f5061', 'tipo': 'precio',
                                'realizada': '2026-11-14T08:20:00-06:00', 'version_base': '2026-11-13T19:00:00-06:00',
                                'datos': {'inventario_id': 120, 'precio': 31.5}}]},
          limite=60)
def recibir(datos):
    """Responde 200 con el estado de cada operación. Reenviar el mismo lote es seguro: las operaciones ya aplicadas
    salen como `duplicada` y sólo se reintentan las pendientes."""
    maximo = int(parametro('SINCRONIZACION_MAX_OPERACIONES'))
    if len(datos.operaciones) > maximo:
        raise ErrorApi(413, 'lote_muy_grande', f'Máximo {maximo} operaciones por lote; divide el envío.')
    ids = [o.operacion_id for o in datos.operaciones]
    if len(set(ids)) != len(ids):
        raise ErrorApi(422, 'operacion_repetida', 'Hay operacion_id repetidos dentro del mismo lote.')
    politica = datos.politica_conflictos or parametro_texto('SINCRONIZACION_POLITICA_CONFLICTO', 'servidor_gana')
    ahora = datetime.now(timezone.utc)
    lote = _lotes().find_one_and_update(
        {'dispositivo_id': datos.dispositivo_id, 'lote_id': datos.lote_id},
        {'$setOnInsert': {'usuario_id': g.claims['sub'], 'plataforma': datos.plataforma, 'version_app': datos.version_app,
                          'politica_conflictos': politica, 'recibido': ahora, 'correlation_id': g.correlation_id}},
        upsert=True, return_document=ReturnDocument.AFTER)
    if lote['usuario_id'] != g.claims['sub']:
        raise ErrorApi(409, 'lote_ajeno', 'Ese lote_id ya lo envió otro usuario desde ese dispositivo.')
    operaciones = []
    for o in datos.operaciones:
        documento = {'lote_id': lote['_id'], 'dispositivo_id': datos.dispositivo_id, 'operacion_id': o.operacion_id,
                     'usuario_id': g.claims['sub'], 'tipo': o.tipo, 'realizada': o.realizada.isoformat(),
                     'version_base': o.version_base.isoformat() if o.version_base else None,
                     'datos': o.datos.model_dump(mode='json', exclude_none=True), 'estado': 'recibida', 'intentos': 0,
                     'recibida': ahora}
        try:
            documento['_id'] = _operaciones().insert_one(documento).inserted_id
            operaciones.append(documento)
        except DuplicateKeyError:
            previa = _operaciones().find_one({'dispositivo_id': datos.dispositivo_id, 'operacion_id': o.operacion_id})
            if previa['lote_id'] != lote['_id'] and previa['estado'] in FINALES:
                # Llegó en otro lote y ya se aplicó: en este lote se reporta como duplicada
                _operaciones().update_one({'_id': previa['_id']}, {'$set': {'reenviada_en': lote['_id']}})
            operaciones.append(previa)
    procesar(lote, [o for o in operaciones if o['lote_id'] == lote['_id']])
    resultado = resumen(lote)
    # Las que ya venían aplicadas de otro lote se agregan como duplicadas
    de_otros = [o for o in operaciones if o['lote_id'] != lote['_id']]
    for o in de_otros:
        resultado['resultados'].append({'operacion_id': o['operacion_id'], 'tipo': o['tipo'], 'estado': 'duplicada',
                                        'mensaje': f"Ya sincronizada ({o['estado']}) en un lote anterior.",
                                        'servicio': o.get('servicio'), 'id_servidor': o.get('id_servidor'),
                                        'version_servidor': o.get('version_servidor'), 'intentos': o.get('intentos', 0)})
    resultado['duplicadas'] += len(de_otros)
    resultado['total'] += len(de_otros)
    return resultado


def _mi_lote(lote_id, dispositivo_id=None):
    filtro = {'lote_id': lote_id, 'usuario_id': g.claims['sub']}
    if dispositivo_id:
        filtro['dispositivo_id'] = dispositivo_id
    lote = _lotes().find_one(filtro)
    if not lote:
        raise no_encontrado('El lote')
    return lote


@srv.ruta('/lotes/<lote_id>', 'GET', resumen='Confirmación de un lote', etiqueta='Sincronización',
          permisos=['sincronizacion.enviar'], raiz_xml='lote')
def consultar(lote_id):
    return resumen(_mi_lote(lote_id))


@srv.ruta('/lotes/<lote_id>/reintentos', 'POST', resumen='Reintentar las operaciones pendientes',
          etiqueta='Sincronización', permisos=['sincronizacion.enviar'], cuerpo=ReintentoEntrada, raiz_xml='lote',
          entrada_xml='reintento_entrada', ejemplo_entrada={})
def reintentar(lote_id, datos):
    lote = _mi_lote(lote_id)
    filtro = {'lote_id': lote['_id'], 'estado': 'pendiente_reintento'}
    if datos.operaciones:
        filtro['operacion_id'] = {'$in': datos.operaciones}
    procesar(lote, list(_operaciones().find(filtro)))
    return resumen(_lotes().find_one({'_id': lote['_id']}))


@srv.ruta('/lotes', 'GET', resumen='Mis lotes recientes', etiqueta='Sincronización',
          permisos=['sincronizacion.enviar'], consulta=LotesConsulta, raiz_xml='lotes')
def listar(q):
    filtro = {'usuario_id': g.claims['sub']}
    if q.dispositivo_id:
        filtro['dispositivo_id'] = q.dispositivo_id
    lotes = list(_lotes().find(filtro).sort('recibido', -1).limit(q.limite))
    return {'total': len(lotes), 'lotes': [resumen(lote) for lote in lotes]}
