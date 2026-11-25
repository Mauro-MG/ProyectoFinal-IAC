"""
ms-recomendaciones: recomendación de surtido explicada y medición de resultados.

Es DUEÑO de la colección `recomendaciones_emitidas` (MongoDB). Lee (sin escribir) el
inventario, las brechas por zona (abasto_dominio.servicios.analisis) y pide a ms-demanda las
búsquedas no satisfechas de la zona.

Regla (RN-003): se recomienda un producto si el comercio no lo vende, su cobertura en la zona
es menor a UMBRAL_COBERTURA_RECOMENDACION, hay demanda (canasta básica, ventas en la zona o
búsquedas no satisfechas) y al menos un proveedor que entrega en la zona lo tiene disponible.

Puntaje = (100 - cobertura) + 20 si es de canasta básica + ventas/5 (máx. 20)
          + 5 por proveedor (máx. 15) + 2 por búsqueda no satisfecha (máx. 20).
Prioridad: alta >= 110, media >= 80, baja el resto. Cada recomendación trae `explicacion`:
los factores que sumaron puntos, con sus números.

Medición: cada recomendación emitida se guarda una vez al día por comercio y producto. Una
recomendación se considera ADOPTADA si después de emitirla el comercio agregó el producto a su
inventario, y EXITOSA si además registró ventas (salidas) del producto.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import g
from pymongo import ReturnDocument
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado, prohibido, tiene
from abasto_api.clientes import llamar
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio
from abasto_dominio.servicios import analisis
from abasto_dominio.servicios.parametros import parametro

from esquemas import CONTRATOS_XML, RecomendacionesConsulta, RespuestaEntrada, ResultadosConsulta, ZonaConsulta

srv = Servicio('recomendaciones', 'Recomendaciones',
               'Recomendación de productos y surtido por zona según demanda, historial de ventas, inventario y '
               'precios; priorización, explicación de cada recomendación y medición de resultados.',
               xsd=Path(__file__).parent / 'xsd' / 'recomendaciones.xsd', contratos=CONTRATOS_XML,
               opcionales=())  # MongoDB es crítica: es dueño de colecciones ahí
app = srv.app


def _emitidas():
    return extensiones.mongo_db()['recomendaciones_emitidas']


def _comercio(comercio_id):
    comercio = db.session.get(Comercio, comercio_id)
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    if str(comercio.usuario_id) != g.claims['sub'] and not tiene('analisis.ver'):
        raise prohibido('Sólo puedes consultar recomendaciones de tus comercios.')
    return comercio


def busquedas_no_satisfechas(zona_id):
    """{producto_id: búsquedas sin resultado en la zona, 30 días}, preguntando a ms-demanda.
    Si ms-demanda no responde, la recomendación se calcula sin ese factor (no falla)."""
    try:
        respuesta = llamar('demanda', 'GET', '/api/v1/demanda/no-satisfecha', permisos_servicio=['demanda.ver'],
                           params={'zona_id': zona_id, 'dias': 30, 'limite': 200})
        if respuesta.ok:
            return {r['producto_id']: r['busquedas'] for r in respuesta.json().get('productos', [])
                    if r.get('producto_id')}, 'ms-demanda'
    except ErrorApi:
        pass
    return {}, 'no_disponible'


def prioridad_de(puntaje):
    return 'alta' if puntaje >= 110 else 'media' if puntaje >= 80 else 'baja'


def explicar(fila, busquedas, umbral):
    razones = [{'factor': 'cobertura', 'peso': round(100 - fila['cobertura'], 1),
                'detalle': f"Sólo {fila['con_disponibilidad']} de {fila['comercios_analizados']} comercios de tu zona lo "
                           f"tienen disponible (cobertura {fila['cobertura']} %, umbral {umbral} %)."}]
    if fila['canasta_basica']:
        razones.append({'factor': 'canasta_basica', 'peso': 20, 'detalle': 'Es producto de la canasta básica.'})
    if fila['ventas']:
        razones.append({'factor': 'ventas_zona', 'peso': round(min(fila['ventas'] / 5, 20), 1),
                        'detalle': f"En tu zona se vendieron {fila['ventas']:g} unidades en los últimos "
                                   f"{int(parametro('DIAS_DEMANDA'))} días."})
    if busquedas:
        razones.append({'factor': 'busquedas', 'peso': min(busquedas * 2, 20),
                        'detalle': f'{busquedas} búsquedas de este producto en tu zona no encontraron dónde comprarlo.'})
    razones.append({'factor': 'proveedores', 'peso': min(fila['proveedores'] * 5, 15),
                    'detalle': f"{fila['proveedores']} proveedor(es) te lo entregan" +
                               (f", desde ${fila['precio_mayoreo_min']:.2f} de mayoreo." if fila['precio_mayoreo_min'] else '.')})
    if fila.get('margen_estimado') is not None:
        razones.append({'factor': 'margen', 'peso': 0,
                        'detalle': f"Margen estimado {fila['margen_estimado']} % contra el precio promedio de la zona."})
    return razones


def calcular(comercio):
    """Lista de recomendaciones con prioridad y explicación (sin guardar)."""
    umbral = parametro('UMBRAL_COBERTURA_RECOMENDACION')
    busquedas, fuente = busquedas_no_satisfechas(comercio.zona_id)
    vende = {i.producto_id for i in comercio.inventario if i.activo}
    base = {r['producto_id']: r for r in analisis.recomendaciones(comercio)}
    # Productos que sólo aparecen por búsquedas no satisfechas (la regla base exige ventas o canasta básica)
    for fila in analisis.brechas(zona_id=comercio.zona_id):
        pid = fila['producto_id']
        if pid in base or pid in vende or not busquedas.get(pid):
            continue
        if fila['cobertura'] < umbral and fila['proveedores']:
            base[pid] = {**fila, 'motivo': 'Lo buscan y no lo encuentran', 'margen_estimado': None, 'puntaje': 0}
    lista = []
    for fila in base.values():
        extra = min(busquedas.get(fila['producto_id'], 0) * 2, 20)
        puntaje = round((100 - fila['cobertura']) + (20 if fila['canasta_basica'] else 0)
                        + min(fila['ventas'] / 5, 20) + min(fila['proveedores'] * 5, 15) + extra)
        lista.append({
            'producto_id': fila['producto_id'], 'producto': fila['producto'], 'canasta_basica': fila['canasta_basica'],
            'prioridad': prioridad_de(puntaje), 'puntaje': puntaje, 'motivo': fila['motivo'],
            'explicacion': explicar(fila, busquedas.get(fila['producto_id'], 0), umbral),
            'cobertura': fila['cobertura'], 'ventas': fila['ventas'],
            'busquedas_no_satisfechas': busquedas.get(fila['producto_id'], 0), 'proveedores': fila['proveedores'],
            'precio_mayoreo_min': fila['precio_mayoreo_min'], 'precio_promedio': fila['precio_promedio'],
            'margen_estimado': fila['margen_estimado']})
    lista.sort(key=lambda r: -r['puntaje'])
    return lista, umbral, fuente


def registrar_emision(comercio, lista):
    """Una emisión por comercio, producto y día; regresa {producto_id: respuesta previa}."""
    hoy = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    respuestas = {}
    for r in lista:
        documento = _emitidas().find_one_and_update(
            {'comercio_id': str(comercio.id), 'producto_id': r['producto_id'], 'dia': hoy},
            {'$setOnInsert': {'zona_id': comercio.zona_id, 'producto': r['producto'], 'motivo': r['motivo'],
                              'prioridad': r['prioridad'], 'puntaje': r['puntaje'],
                              'emitida': datetime.now(timezone.utc), 'respuesta': None}},
            upsert=True, return_document=ReturnDocument.AFTER)
        respuestas[r['producto_id']] = documento.get('respuesta')
    return respuestas


# ---------------------------------------------------------------- rutas

@srv.ruta('/recomendaciones/<uuid:comercio_id>', 'GET', resumen='Recomendaciones de surtido explicadas',
          etiqueta='Recomendaciones', permisos=['recomendaciones.ver', 'analisis.ver'],
          consulta=RecomendacionesConsulta, raiz_xml='recomendaciones')
def recomendar(comercio_id, q):
    """Ordenadas por puntaje, con prioridad y los factores que explican cada una. Cuando las consulta el dueño del
    comercio, quedan registradas para medir después si las adoptó."""
    comercio = _comercio(comercio_id)
    if not comercio.zona_id:
        raise ErrorApi(409, 'sin_zona', 'El comercio no tiene zona asignada; captura su ubicación.')
    lista, umbral, fuente = calcular(comercio)
    if q.prioridad:
        lista = [r for r in lista if r['prioridad'] == q.prioridad]
    lista = lista[:q.limite]
    if str(comercio.usuario_id) == g.claims['sub']:
        respuestas = registrar_emision(comercio, lista)
        for r in lista:
            r['respuesta'] = respuestas.get(r['producto_id'])
    return {'comercio_id': str(comercio.id), 'zona': comercio.zona.nombre, 'umbral_cobertura': umbral,
            'generadas': datetime.now(timezone.utc), 'fuente_demanda': fuente, 'recomendaciones': lista}


@srv.ruta('/recomendaciones/<uuid:comercio_id>/respuestas', 'POST', resumen='Aceptar, descartar o posponer',
          etiqueta='Recomendaciones', permisos=['recomendaciones.ver'], cuerpo=RespuestaEntrada, status=201,
          raiz_xml='respuesta', entrada_xml='respuesta_entrada',
          ejemplo_entrada={'producto_id': 7, 'respuesta': 'aceptada'})
def responder(comercio_id, datos):
    comercio = _comercio(comercio_id)
    if str(comercio.usuario_id) != g.claims['sub']:
        raise prohibido('Sólo el dueño del comercio responde sus recomendaciones.')
    ahora = datetime.now(timezone.utc)
    resultado = _emitidas().find_one_and_update(
        {'comercio_id': str(comercio.id), 'producto_id': datos.producto_id},
        {'$set': {'respuesta': datos.respuesta, 'motivo_respuesta': datos.motivo, 'respondida': ahora}},
        sort=[('emitida', -1)])
    if not resultado:
        raise ErrorApi(409, 'sin_recomendacion', 'Ese producto no se le ha recomendado a este comercio.')
    return {'comercio_id': str(comercio.id), 'producto_id': datos.producto_id, 'respuesta': datos.respuesta,
            'registrada': ahora}


def _adopciones(comercio_id, emitidas):
    """Para cada producto: fecha en que entró al inventario y unidades vendidas desde entonces."""
    if not emitidas:
        return {}
    filas = db.session.execute(text(
        "SELECT i.producto_id, i.created_at, COALESCE(sum(m.cantidad) FILTER (WHERE m.tipo = 'SALIDA'), 0) AS vendidas "
        'FROM inventario_comercio i LEFT JOIN movimientos_inventario m ON m.inventario_id = i.id '
        'WHERE i.comercio_id = :c AND i.producto_id = ANY(:p) GROUP BY i.id'),
        {'c': comercio_id, 'p': list({e['producto_id'] for e in emitidas})}).all()
    return {f.producto_id: (f.created_at, float(f.vendidas)) for f in filas}


def _local_utc(valor):
    return valor.replace(tzinfo=timezone(timedelta(hours=-6))).astimezone(timezone.utc) if valor else None


@srv.ruta('/recomendaciones/<uuid:comercio_id>/resultados', 'GET', resumen='¿Funcionaron mis recomendaciones?',
          etiqueta='Resultados', permisos=['recomendaciones.ver', 'analisis.ver'], consulta=ResultadosConsulta,
          raiz_xml='resultados')
def resultados(comercio_id, q):
    comercio = _comercio(comercio_id)
    desde = datetime.now(timezone.utc) - timedelta(days=q.dias)
    emitidas = list(_emitidas().find({'comercio_id': str(comercio.id), 'emitida': {'$gte': desde}}).sort('emitida', 1))
    primera = {}
    for e in emitidas:   # la primera emisión de cada producto en el periodo
        primera.setdefault(e['producto_id'], e)
    adopciones = _adopciones(comercio.id, list(primera.values()))
    lista = []
    for pid, e in primera.items():
        alta, vendidas = adopciones.get(pid, (None, 0.0))
        alta_utc = _local_utc(alta)
        adoptada = bool(alta_utc and alta_utc >= e['emitida'])
        lista.append({'producto_id': pid, 'producto': e.get('producto', ''), 'emitida': e['emitida'],
                      'prioridad': e['prioridad'], 'respuesta': e.get('respuesta'), 'adoptada': adoptada,
                      'fecha_adopcion': alta_utc if adoptada else None,
                      'unidades_vendidas': vendidas if adoptada else 0.0})
    adoptadas = sum(1 for r in lista if r['adoptada'])
    return {'comercio_id': str(comercio.id), 'dias': q.dias, 'emitidas': len(lista),
            'aceptadas': sum(1 for r in lista if r['respuesta'] == 'aceptada'), 'adoptadas': adoptadas,
            'con_ventas': sum(1 for r in lista if r['unidades_vendidas'] > 0),
            'tasa_adopcion_pct': round(adoptadas * 100 / len(lista), 1) if lista else 0.0,
            'unidades_vendidas': sum(r['unidades_vendidas'] for r in lista), 'resultados': lista}


@srv.ruta('/recomendaciones/efectividad', 'GET', resumen='Efectividad global por motivo', etiqueta='Resultados',
          permisos=['analisis.ver'], consulta=ResultadosConsulta, raiz_xml='efectividad')
def efectividad(q):
    """Para el analista: qué tipo de recomendación se adopta más."""
    desde = datetime.now(timezone.utc) - timedelta(days=q.dias)
    emitidas = list(_emitidas().find({'emitida': {'$gte': desde}}))
    por_comercio = {}
    for e in emitidas:
        por_comercio.setdefault(e['comercio_id'], {}).setdefault(e['producto_id'], e)
    motivos, total, adoptadas_total = {}, 0, 0
    for comercio_id, productos in por_comercio.items():
        adopciones = _adopciones(comercio_id, list(productos.values()))
        for pid, e in productos.items():
            alta = _local_utc(adopciones.get(pid, (None, 0))[0])
            adoptada = bool(alta and alta >= e['emitida'])
            m = motivos.setdefault(e.get('motivo', 'otro'), [0, 0])
            m[0] += 1
            m[1] += adoptada
            total += 1
            adoptadas_total += adoptada
    return {'dias': q.dias, 'comercios': len(por_comercio), 'emitidas': total, 'adoptadas': adoptadas_total,
            'tasa_adopcion_pct': round(adoptadas_total * 100 / total, 1) if total else 0.0,
            'motivos': [{'motivo': k, 'emitidas': v[0], 'adoptadas': v[1],
                         'tasa_adopcion_pct': round(v[1] * 100 / v[0], 1)} for k, v in
                        sorted(motivos.items(), key=lambda x: -x[1][0])]}


@srv.ruta('/recomendaciones/zonas/<int:zona_id>', 'GET', resumen='Qué conviene surtir en una zona',
          etiqueta='Recomendaciones', permisos=['analisis.ver', 'recomendaciones.ver'], consulta=ZonaConsulta,
          raiz_xml='zona')
def por_zona(zona_id, q):
    """Productos con brecha en la zona y proveedores que los entregan; útil para un comercio nuevo o para el
    coordinador municipal."""
    filas = analisis.brechas(zona_id=zona_id)
    if not filas and not db.session.execute(text('SELECT 1 FROM zonas_municipales WHERE id = :z'), {'z': zona_id}).first():
        raise no_encontrado('La zona')
    candidatos = [f for f in filas if f['proveedores'] and f['cobertura'] < parametro('UMBRAL_COBERTURA_RECOMENDACION')]
    for f in candidatos:
        f['puntaje'] = round((100 - f['cobertura']) + (20 if f['canasta_basica'] else 0) + min(f['ventas'] / 5, 20)
                             + min(f['proveedores'] * 5, 15))
    candidatos.sort(key=lambda f: -f['puntaje'])
    return {'zona_id': zona_id, 'productos': [
        {'producto_id': f['producto_id'], 'producto': f['producto'], 'canasta_basica': f['canasta_basica'],
         'cobertura': f['cobertura'], 'brecha': f['nivel'], 'ventas': f['ventas'], 'proveedores': f['proveedores'],
         'puntaje': f['puntaje']} for f in candidatos[:q.limite]]}
