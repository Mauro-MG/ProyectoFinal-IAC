"""
Preferencias, plantillas y entrega por canales autorizados.

Canales:
    interno  la notificación en MongoDB que ven el web y las apps (siempre disponible)
    push     a los dispositivos registrados (Android/escritorio). Sin credenciales de Firebase el envío se
             SIMULA: queda en entregas_canal con proveedor "simulado" para poder probar el flujo completo.
    correo   también simulado hasta tener servidor de correo (avance 4).
Preferencias por usuario: qué canales recibe para cada tipo y horario de silencio (no se envía push de
noche, salvo prioridad alta). Una notificación interna nunca se pierde: el canal interno sólo se
apaga si el usuario lo pide para ese tipo y la prioridad no es alta.
"""
from datetime import datetime, timedelta, timezone
from string import Formatter

from abasto_dominio import extensiones
from abasto_dominio.servicios import notificaciones as notif

MONTERREY = timezone(timedelta(hours=-6))
CANALES = ('interno', 'push', 'correo')
POR_OMISION = {'canales': {'todos': ['interno', 'push']}, 'silencio': {'desde': 22, 'hasta': 7}}

PLANTILLAS_BASE = [
    {'clave': 'pedido_estado', 'tipo': 'pedido', 'titulo': 'Pedido {folio}: {estado}',
     'mensaje': '{comercio} / {proveedor}. {detalle}', 'prioridad': 'normal'},
    {'clave': 'stock_bajo', 'tipo': 'stock_bajo', 'titulo': '{producto}: stock bajo',
     'mensaje': 'Quedan {existencia} {unidad} en {comercio} (mínimo {minimo}).', 'prioridad': 'normal'},
    {'clave': 'entrega_en_camino', 'tipo': 'entrega', 'titulo': 'Tu pedido {folio} va en camino',
     'mensaje': '{proveedor} salió con tu pedido; llega aprox. a las {hora}.', 'prioridad': 'alta'},
    {'clave': 'recomendacion_nueva', 'tipo': 'recomendacion', 'titulo': 'Te recomendamos surtir {producto}',
     'mensaje': '{motivo}. {proveedores} proveedor(es) te lo entregan.', 'prioridad': 'normal'},
    {'clave': 'mantenimiento', 'tipo': 'sistema', 'titulo': 'Mantenimiento programado',
     'mensaje': 'El {fecha} de {inicio} a {fin} la plataforma estará en mantenimiento.', 'prioridad': 'alta'},
]


def _db():
    return extensiones.mongo_db()


def preferencias(usuario_id):
    doc = _db()['preferencias_notificacion'].find_one({'usuario_id': str(usuario_id)}) or {}
    return {'usuario_id': str(usuario_id), 'canales': doc.get('canales', POR_OMISION['canales']),
            'silencio': doc.get('silencio', POR_OMISION['silencio']), 'actualizado': doc.get('actualizado')}


def guardar_preferencias(usuario_id, canales, silencio):
    _db()['preferencias_notificacion'].update_one(
        {'usuario_id': str(usuario_id)},
        {'$set': {'canales': canales, 'silencio': silencio, 'actualizado': datetime.now(timezone.utc)}}, upsert=True)
    return preferencias(usuario_id)


def en_silencio(silencio, ahora=None):
    hora = (ahora or datetime.now(MONTERREY)).astimezone(MONTERREY).hour
    desde, hasta = silencio.get('desde'), silencio.get('hasta')
    if desde is None or hasta is None or desde == hasta:
        return False
    return desde <= hora or hora < hasta if desde > hasta else desde <= hora < hasta


def canales_para(prefs, tipo, prioridad):
    elegidos = list(prefs['canales'].get(tipo, prefs['canales'].get('todos', ['interno'])))
    if prioridad == 'alta' and 'interno' not in elegidos:
        elegidos.append('interno')            # lo urgente siempre queda en la bandeja
    if 'push' in elegidos and prioridad != 'alta' and en_silencio(prefs['silencio']):
        elegidos.remove('push')               # de noche sólo push urgentes
    return [c for c in CANALES if c in elegidos]


def _registrar_entrega(usuario_id, notificacion_id, canal, estado, detalle, proveedor='simulado'):
    _db()['entregas_canal'].insert_one({
        'usuario_id': str(usuario_id), 'notificacion_id': notificacion_id, 'canal': canal, 'estado': estado,
        'detalle': detalle, 'proveedor': proveedor, 'fecha': datetime.now(timezone.utc)})


def entregar(usuario_id, tipo, titulo, mensaje, url=None, entidad=None, prioridad='normal', origen='servicio'):
    """Crea la notificación y la entrega por los canales que el usuario tiene activos para ese tipo."""
    prefs = preferencias(usuario_id)
    canales = canales_para(prefs, tipo, prioridad)
    if 'interno' not in canales:
        # El usuario apagó el canal interno para este tipo: no se guarda en la bandeja, sólo se registra.
        _registrar_entrega(usuario_id, None, 'interno', 'omitida', 'Apagado en las preferencias del usuario', 'abastored')
        creada = None
    else:
        creada = notif.crear(usuario_id, tipo, titulo, mensaje, url, entidad, prioridad, origen)
        _registrar_entrega(usuario_id, creada['id'], 'interno', 'entregada', 'Bandeja de AbastoRed', 'abastored')
    if 'push' in canales:
        dispositivos = list(_db()['dispositivos_push'].find({'usuario_id': str(usuario_id), 'activo': True}))
        if dispositivos:
            for d in dispositivos:
                _registrar_entrega(usuario_id, creada['id'] if creada else None, 'push', 'enviada',
                                   f"{d['plataforma']} …{d['token'][-6:]}: {titulo}")
        else:
            _registrar_entrega(usuario_id, creada['id'] if creada else None, 'push', 'sin_dispositivo',
                               'El usuario no tiene dispositivos registrados')
    if 'correo' in canales:
        _registrar_entrega(usuario_id, creada['id'] if creada else None, 'correo', 'enviada', titulo)
    return creada, canales


def campos_de(texto):
    return {nombre for _, nombre, _, _ in Formatter().parse(texto) if nombre}


def plantillas():
    coleccion = _db()['plantillas_notificacion']
    if coleccion.estimated_document_count() == 0:
        coleccion.insert_many([{**p, 'creada': datetime.now(timezone.utc)} for p in PLANTILLAS_BASE])
    return list(coleccion.find({}, {'_id': 0}).sort('clave', 1))


def plantilla(clave):
    plantillas()
    return _db()['plantillas_notificacion'].find_one({'clave': clave}, {'_id': 0})
