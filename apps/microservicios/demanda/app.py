"""
ms-demanda: demanda histórica, tendencias, estacionalidad y estimación.

Es DUEÑO de la colección `demanda_busquedas` (MongoDB): cada búsqueda de un producto, si se
encontró o no dónde comprarlo. La registran ms-busqueda, ms-disponibilidad y las apps.

La demanda histórica se mide con las SALIDAS de inventario (ventas) que registran
ms-inventario y ms-ventas; este servicio sólo las lee y las agrega:
- por periodo (día, semana, mes), producto, zona y municipio;
- tendencia: unidades de la segunda mitad del periodo contra la primera;
- estacionalidad: índice por día de la semana y por mes (promedio del día / promedio general);
- estimación: regresión lineal sobre las unidades diarias de las últimas semanas, ajustada por
  el índice del día de la semana, con un rango de ± el error medio absoluto del ajuste.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import g
from sqlalchemy import text

from abasto_api import Servicio, no_encontrado
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db

from esquemas import (BusquedaEntrada, CONTRATOS_XML, EstimacionConsulta, HistoricaConsulta, NoSatisfechaConsulta,
                      ProductoConsulta, RegionesConsulta, TendenciasConsulta)

srv = Servicio('demanda', 'Demanda',
               'Registro y análisis de demanda histórica, tendencias y estacionalidad; productos buscados y no '
               'disponibles; estimaciones de demanda; agregaciones por región, producto y periodo.',
               xsd=Path(__file__).parent / 'xsd' / 'demanda.xsd', contratos=CONTRATOS_XML,
               opcionales=())  # MongoDB es crítica: es dueño de colecciones ahí
app = srv.app

LECTORES = ['demanda.ver', 'analisis.ver', 'recomendaciones.ver']
DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre',
         'Noviembre', 'Diciembre']
SALIDAS = ("FROM movimientos_inventario m JOIN inventario_comercio i ON i.id = m.inventario_id "
           "JOIN comercios c ON c.id = i.comercio_id WHERE m.tipo = 'SALIDA' AND m.created_at >= :desde")


def _busquedas():
    return extensiones.mongo_db()['demanda_busquedas']


def _filtros(producto_id=None, zona_id=None, municipio=None):
    sql, parametros = '', {}
    if producto_id:
        sql += ' AND i.producto_id = :producto'
        parametros['producto'] = producto_id
    if zona_id:
        sql += ' AND c.zona_id = :zona'
        parametros['zona'] = zona_id
    if municipio:
        sql += ' AND c.municipio = :municipio'
        parametros['municipio'] = municipio
    return sql, parametros


def _producto(producto_id):
    fila = db.session.execute(text('SELECT id, nombre FROM productos_maestros WHERE id = :p'), {'p': producto_id}).first()
    if not fila:
        raise no_encontrado('El producto')
    return fila


def serie_diaria(producto_id, zona_id, dias):
    """{fecha: unidades} con ceros en los días sin ventas."""
    filtro, parametros = _filtros(producto_id, zona_id)
    desde = date.today() - timedelta(days=dias - 1)
    filas = db.session.execute(text(
        f'SELECT m.created_at::date AS dia, sum(m.cantidad) AS unidades {SALIDAS} {filtro} GROUP BY 1'),
        {'desde': desde, **parametros}).all()
    valores = {f.dia: float(f.unidades) for f in filas}
    return {desde + timedelta(days=i): valores.get(desde + timedelta(days=i), 0.0) for i in range(dias)}


# ---------------------------------------------------------------- búsquedas

@srv.ruta('/demanda/busquedas', 'POST', resumen='Registrar una búsqueda', etiqueta='Búsquedas',
          permisos=['demanda.registrar', 'pedidos.crear', 'ventas.registrar', 'comercios.gestionar'],
          cuerpo=BusquedaEntrada, status=201, raiz_xml='busqueda', entrada_xml='busqueda_entrada',
          ejemplo_entrada={'texto': 'aceite 1 l', 'producto_id': 3, 'zona_id': 2, 'resultados': 0, 'origen': 'android'},
          limite=300)
def registrar_busqueda(datos):
    documento = {**datos.model_dump(), 'texto': datos.texto.lower(), 'encontrado': datos.resultados > 0,
                 'usuario_id': g.claims.get('sub') if g.claims.get('tipo') == 'acceso' else None,
                 'fecha': datetime.now(timezone.utc)}
    documento['_id'] = _busquedas().insert_one(documento).inserted_id
    return {'id': str(documento['_id']), 'texto': documento['texto'], 'producto_id': datos.producto_id,
            'zona_id': datos.zona_id, 'encontrado': documento['encontrado'], 'fecha': documento['fecha']}


@srv.ruta('/demanda/no-satisfecha', 'GET', resumen='Productos buscados y no disponibles', etiqueta='Búsquedas',
          permisos=LECTORES, consulta=NoSatisfechaConsulta, raiz_xml='no_satisfecha')
def no_satisfecha(q):
    """Agregación sobre demanda_busquedas: búsquedas sin ningún resultado, por producto (o texto)."""
    filtro = {'encontrado': False, 'fecha': {'$gte': datetime.now(timezone.utc) - timedelta(days=q.dias)}}
    if q.zona_id:
        filtro['zona_id'] = q.zona_id
    filas = list(_busquedas().aggregate([
        {'$match': filtro},
        {'$group': {'_id': {'$ifNull': ['$producto_id', '$texto']}, 'producto_id': {'$first': '$producto_id'},
                    'texto': {'$first': '$texto'}, 'busquedas': {'$sum': 1}, 'zonas': {'$addToSet': '$zona_id'},
                    'ultima': {'$max': '$fecha'}}},
        {'$sort': {'busquedas': -1}}, {'$limit': q.limite}]))
    return {'zona_id': q.zona_id, 'dias': q.dias, 'total_busquedas': sum(f['busquedas'] for f in filas),
            'productos': [{'producto_id': f['producto_id'], 'texto': f['texto'], 'busquedas': f['busquedas'],
                           'zonas': len([z for z in f['zonas'] if z]), 'ultima': f['ultima']} for f in filas]}


@srv.ruta('/demanda/productos-buscados', 'GET', resumen='Lo más buscado y qué tanto se encuentra',
          etiqueta='Búsquedas', permisos=LECTORES, consulta=NoSatisfechaConsulta, raiz_xml='buscados')
def buscados(q):
    filtro = {'fecha': {'$gte': datetime.now(timezone.utc) - timedelta(days=q.dias)}}
    if q.zona_id:
        filtro['zona_id'] = q.zona_id
    filas = _busquedas().aggregate([
        {'$match': filtro},
        {'$group': {'_id': {'$ifNull': ['$producto_id', '$texto']}, 'producto_id': {'$first': '$producto_id'},
                    'texto': {'$first': '$texto'}, 'busquedas': {'$sum': 1},
                    'encontradas': {'$sum': {'$cond': ['$encontrado', 1, 0]}}}},
        {'$sort': {'busquedas': -1}}, {'$limit': q.limite}])
    return {'dias': q.dias, 'productos': [
        {'texto': f['texto'], 'producto_id': f['producto_id'], 'busquedas': f['busquedas'],
         'encontradas': f['encontradas'], 'tasa_exito_pct': round(f['encontradas'] * 100 / f['busquedas'], 1)}
        for f in filas]}


# ---------------------------------------------------------------- histórico y tendencias

@srv.ruta('/demanda/historica', 'GET', resumen='Unidades vendidas por periodo', etiqueta='Histórico',
          permisos=LECTORES, consulta=HistoricaConsulta, raiz_xml='historica')
def historica(q):
    filtro, parametros = _filtros(q.producto_id, q.zona_id, q.municipio)
    unidad = {'dia': 'day', 'semana': 'week', 'mes': 'month'}[q.periodo]
    filas = db.session.execute(text(
        f"SELECT date_trunc('{unidad}', m.created_at)::date AS periodo, sum(m.cantidad) AS unidades, "
        f'count(*) AS movimientos, count(DISTINCT c.id) AS comercios {SALIDAS} {filtro} GROUP BY 1 ORDER BY 1'),
        {'desde': date.today() - timedelta(days=q.dias), **parametros}).all()
    serie = [{'periodo': f.periodo, 'unidades': float(f.unidades), 'movimientos': f.movimientos,
              'comercios': f.comercios} for f in filas]
    return {'producto_id': q.producto_id, 'zona_id': q.zona_id, 'periodo': q.periodo, 'dias': q.dias,
            'total_unidades': sum(p['unidades'] for p in serie), 'serie': serie}


@srv.ruta('/demanda/tendencias', 'GET', resumen='Productos que suben o bajan', etiqueta='Histórico',
          permisos=LECTORES, consulta=TendenciasConsulta, raiz_xml='tendencias')
def tendencias(q):
    """Compara las unidades de la mitad reciente del periodo contra la mitad anterior. ±10 % se considera estable."""
    filtro, parametros = _filtros(zona_id=q.zona_id)
    mitad = date.today() - timedelta(days=q.dias // 2)
    filas = db.session.execute(text(
        f'SELECT i.producto_id, p.nombre, '
        f'  COALESCE(sum(m.cantidad) FILTER (WHERE m.created_at < :mitad), 0) AS anterior, '
        f'  COALESCE(sum(m.cantidad) FILTER (WHERE m.created_at >= :mitad), 0) AS reciente '
        f'FROM movimientos_inventario m JOIN inventario_comercio i ON i.id = m.inventario_id '
        f'JOIN comercios c ON c.id = i.comercio_id JOIN productos_maestros p ON p.id = i.producto_id '
        f"WHERE m.tipo = 'SALIDA' AND m.created_at >= :desde {filtro} GROUP BY i.producto_id, p.nombre"),
        {'desde': date.today() - timedelta(days=q.dias), 'mitad': mitad, **parametros}).all()
    productos = []
    for f in filas:
        anterior, reciente = float(f.anterior), float(f.reciente)
        cambio = round((reciente - anterior) * 100 / anterior, 1) if anterior else None
        tendencia = 'nuevo' if cambio is None else 'sube' if cambio > 10 else 'baja' if cambio < -10 else 'estable'
        productos.append({'producto_id': f.producto_id, 'producto': f.nombre, 'unidades_periodo_anterior': anterior,
                          'unidades_periodo_reciente': reciente, 'cambio_pct': cambio, 'tendencia': tendencia})
    productos.sort(key=lambda p: -abs(p['cambio_pct'] if p['cambio_pct'] is not None else p['unidades_periodo_reciente']))
    return {'zona_id': q.zona_id, 'dias': q.dias, 'productos': productos[:q.limite]}


@srv.ruta('/demanda/estacionalidad', 'GET', resumen='Índice por día de la semana y por mes', etiqueta='Histórico',
          permisos=LECTORES, consulta=ProductoConsulta, raiz_xml='estacionalidad')
def estacionalidad(q):
    """Índice = promedio diario de ese día (o mes) / promedio diario general. 1.25 = se vende 25 % más."""
    producto = _producto(q.producto_id)
    serie = serie_diaria(q.producto_id, q.zona_id, q.dias)
    general = sum(serie.values()) / len(serie) if serie else 0
    por_dia, por_mes = {}, {}
    for dia, unidades in serie.items():
        por_dia.setdefault(dia.weekday(), []).append(unidades)
        por_mes.setdefault(dia.month, []).append(unidades)

    def indices(grupos, nombre):
        lista = []
        for clave in sorted(grupos):
            promedio = sum(grupos[clave]) / len(grupos[clave])
            lista.append({'clave': str(clave), 'nombre': nombre(clave), 'promedio_diario': round(promedio, 2),
                          'indice': round(promedio / general, 2) if general else 0.0})
        return lista
    return {'producto_id': producto.id, 'producto': producto.nombre, 'zona_id': q.zona_id, 'dias': q.dias,
            'promedio_diario': round(general, 2),
            'por_dia_semana': indices(por_dia, lambda k: DIAS_SEMANA[k]),
            'por_mes': indices(por_mes, lambda k: MESES[k - 1])}


@srv.ruta('/demanda/estimacion', 'GET', resumen='Estimación de demanda de los próximos días', etiqueta='Estimación',
          permisos=LECTORES, consulta=EstimacionConsulta, raiz_xml='estimacion')
def estimacion(q):
    """Regresión lineal (mínimos cuadrados) sobre las unidades diarias de `historia_dias`, multiplicada por el índice
    del día de la semana. El rango es ± el error medio absoluto del ajuste en la historia."""
    producto = _producto(q.producto_id)
    serie = serie_diaria(q.producto_id, q.zona_id, q.historia_dias)
    dias, valores = list(serie), list(serie.values())
    n = len(valores)
    xs = range(n)
    media_x, media_y = (n - 1) / 2, sum(valores) / n
    var_x = sum((x - media_x) ** 2 for x in xs)
    pendiente = sum((x - media_x) * (y - media_y) for x, y in zip(xs, valores)) / var_x if var_x else 0.0
    ordenada = media_y - pendiente * media_x
    por_dia = {}
    for d, v in serie.items():
        por_dia.setdefault(d.weekday(), []).append(v)
    indice = {k: (sum(v) / len(v)) / media_y if media_y else 1.0 for k, v in por_dia.items()}
    ajuste = [max(ordenada + pendiente * x, 0) * indice.get(dias[x].weekday(), 1.0) for x in xs]
    error = sum(abs(a - y) for a, y in zip(ajuste, valores)) / n
    estimados = []
    for paso in range(1, q.horizonte_dias + 1):
        fecha = dias[-1] + timedelta(days=paso)
        valor = max(ordenada + pendiente * (n - 1 + paso), 0) * indice.get(fecha.weekday(), 1.0)
        estimados.append({'fecha': fecha, 'unidades': round(valor, 2), 'minimo': round(max(valor - error, 0), 2),
                          'maximo': round(valor + error, 2)})
    return {'producto_id': producto.id, 'producto': producto.nombre, 'zona_id': q.zona_id,
            'metodo': f'Regresión lineal sobre {q.historia_dias} días con índice por día de la semana',
            'promedio_diario': round(media_y, 2), 'pendiente_diaria': round(pendiente, 4),
            'error_medio': round(error, 2), 'total_estimado': round(sum(e['unidades'] for e in estimados), 2),
            'estimacion': estimados}


@srv.ruta('/demanda/regiones', 'GET', resumen='Demanda por municipio o zona', etiqueta='Agregados',
          permisos=LECTORES, consulta=RegionesConsulta, raiz_xml='regiones')
def regiones(q):
    filtro, parametros = _filtros(q.producto_id)
    if q.nivel == 'zona':
        grupo, columnas = 'z.nombre, z.municipio', 'z.nombre AS region, z.municipio'
        union = 'JOIN zonas_municipales z ON z.id = c.zona_id'
    else:
        grupo, columnas, union = 'c.municipio', 'c.municipio AS region, NULL AS municipio', ''
    sql = (f'SELECT {columnas}, sum(m.cantidad) AS unidades, count(DISTINCT c.id) AS comercios, '
           f'count(DISTINCT i.producto_id) AS productos FROM movimientos_inventario m '
           f'JOIN inventario_comercio i ON i.id = m.inventario_id JOIN comercios c ON c.id = i.comercio_id {union} '
           f"WHERE m.tipo = 'SALIDA' AND m.created_at >= :desde {filtro} GROUP BY {grupo} ORDER BY unidades DESC")
    filas = db.session.execute(text(sql), {'desde': date.today() - timedelta(days=q.dias), **parametros}).all()
    return {'nivel': q.nivel, 'producto_id': q.producto_id, 'dias': q.dias, 'regiones': [
        {'region': f.region, 'municipio': f.municipio, 'unidades': float(f.unidades), 'comercios': f.comercios,
         'productos': f.productos} for f in filas]}

