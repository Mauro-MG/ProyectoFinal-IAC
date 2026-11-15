"""
ms-busqueda: búsqueda unificada para web, Android y escritorio.

Servicio de CONSULTA: no es dueño de tablas. Lee productos (ms-catalogo), comercios
(ms-comercios), inventario (ms-inventario) y proveedores y su catálogo (ms-proveedores) con
consultas de sólo lectura, optimizadas para clientes:

- Texto sin acentos ni mayúsculas (translate + lower) y relevancia: coincidencia exacta 100,
  al inicio del nombre 80, al inicio de una palabra 60, en cualquier parte 40, en la
  descripción o categoría 20.
- Filtros combinados (zona, categoría, municipio, canasta básica, con existencia), orden por
  relevancia, nombre o distancia (PostGIS) y paginación.
- Resultados en Redis 60 s por versión de inventario (`analisis:version`).
- Sugerencias (autocompletar) con nombres de productos y categorías y las búsquedas más
  populares (sorted set `busqueda:populares` en Redis).
- Cada búsqueda se reporta a ms-demanda (con token de servicio), para medir los productos
  buscados y no encontrados. Si ms-demanda no responde, la búsqueda no se afecta.
"""
import hashlib
import json
from pathlib import Path

from flask import current_app
from redis.exceptions import RedisError
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, sobre_lista
from abasto_api.clientes import llamar
from abasto_api.formatos import compatible_json
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.servicios.cache import CLAVE_VERSION

from esquemas import BuscarConsulta, CONTRATOS_XML, OfertasConsulta, SugerenciasConsulta

srv = Servicio('busqueda', 'Búsqueda',
               'Búsqueda unificada de productos, comerciantes, proveedores y ofertas: texto sin acentos, filtros '
               'combinados, paginación, ordenamiento, sugerencias y consultas optimizadas para web, Android y escritorio.',
               xsd=Path(__file__).parent / 'xsd' / 'busqueda.xsd', contratos=CONTRATOS_XML)
app = srv.app

POPULARES = 'busqueda:populares'
ACENTOS = "translate(lower({}), 'áéíóúüñ', 'aeiouun')"


def normalizar(texto):
    return texto.lower().translate(str.maketrans('áéíóúüñ', 'aeiouun')).strip()


def relevancia(columna, extra=None):
    """Expresión SQL de relevancia para :t (texto normalizado)."""
    c = ACENTOS.format(columna)
    sql = (f"CASE WHEN {c} = :t THEN 100 WHEN {c} LIKE :t || '%' THEN 80 WHEN {c} LIKE '% ' || :t || '%' THEN 60 "
           f"WHEN {c} LIKE '%' || :t || '%' THEN 40")
    if extra:
        sql += f" WHEN {ACENTOS.format(extra)} LIKE '%' || :t || '%' THEN 20"
    return sql + ' ELSE 0 END'


def _distancia(alias, q):
    if q.latitud is None or q.longitud is None:
        return 'NULL::float'
    return f'ST_Distance({alias}.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1000'


def buscar_productos(q, parametros):
    filtros = []
    if q.categoria_id:
        filtros.append('p.categoria_id = :categoria')
    if q.solo_canasta:
        filtros.append('p.es_canasta_basica')
    rel = relevancia('p.nombre', "p.descripcion || ' ' || cat.nombre")
    return (f"SELECT 'producto' AS tipo, p.id::text AS id, p.nombre, cat.nombre AS detalle, NULL AS zona, "
            f'NULL AS municipio, {rel} AS relevancia, NULL::float AS distancia_km, '
            f'(SELECT sum(i.existencia) FROM inventario_comercio i JOIN comercios c ON c.id = i.comercio_id '
            f"   WHERE i.producto_id = p.id AND i.activo AND c.estado_registro = 'VERIFICADO' "
            f'   {"AND c.zona_id = :zona" if q.zona_id else ""}) AS existencia, '
            f'(SELECT min(i.precio_venta) FROM inventario_comercio i JOIN comercios c ON c.id = i.comercio_id '
            f"   WHERE i.producto_id = p.id AND i.activo AND i.existencia > 0 AND c.estado_registro = 'VERIFICADO' "
            f'   {"AND c.zona_id = :zona" if q.zona_id else ""}) AS precio '
            f'FROM productos_maestros p JOIN categorias cat ON cat.id = p.categoria_id '
            f'WHERE p.activo AND {rel} > 0 {"AND " + " AND ".join(filtros) if filtros else ""}')


def buscar_comercios(q, parametros):
    """Comercios verificados cuyo nombre coincide, o que venden un producto que coincide."""
    filtros = ["c.activo", "c.estado_registro = 'VERIFICADO'"]
    if q.zona_id:
        filtros.append('c.zona_id = :zona')
    if q.municipio:
        filtros.append('c.municipio = :municipio')
    producto = (f'(SELECT max({relevancia("p.nombre")}) - 30 FROM inventario_comercio i '
                f'JOIN productos_maestros p ON p.id = i.producto_id WHERE i.comercio_id = c.id AND i.activo '
                f'{"AND i.existencia > 0" if q.con_existencia else ""})')
    rel = f'GREATEST({relevancia("c.nombre_comercio", "c.colonia")}, COALESCE({producto}, 0))'
    if q.con_existencia:
        rel = f'COALESCE({producto}, 0)'
    return (f"SELECT 'comercio' AS tipo, c.id::text AS id, c.nombre_comercio AS nombre, c.colonia AS detalle, "
            f'z.nombre AS zona, c.municipio, {rel} AS relevancia, {_distancia("c", q)} AS distancia_km, '
            f'NULL::numeric AS existencia, NULL::numeric AS precio '
            f'FROM comercios c LEFT JOIN zonas_municipales z ON z.id = c.zona_id '
            f'WHERE {" AND ".join(filtros)} AND {rel} > 0')


def buscar_proveedores(q, parametros):
    filtros = ['pr.activo', "pr.estado_verificacion = 'VERIFICADO'"]
    if q.zona_id:
        filtros.append('EXISTS (SELECT 1 FROM proveedor_zonas pz WHERE pz.proveedor_id = pr.id AND pz.zona_id = :zona)')
    if q.municipio:
        filtros.append('pr.municipio = :municipio')
    rel = relevancia('pr.nombre_empresa', 'pr.descripcion')
    return (f"SELECT 'proveedor' AS tipo, pr.id::text AS id, pr.nombre_empresa AS nombre, pr.descripcion AS detalle, "
            f'NULL AS zona, pr.municipio, {rel} AS relevancia, {_distancia("pr", q)} AS distancia_km, '
            f'NULL::numeric AS existencia, NULL::numeric AS precio '
            f'FROM proveedores pr WHERE {" AND ".join(filtros)} AND {rel} > 0')


def reportar_a_demanda(q, encontrados):
    """Sólo búsquedas de productos; best effort."""
    try:
        llamar('demanda', 'POST', '/api/v1/demanda/busquedas', permisos_servicio=['demanda.registrar'],
               json={'texto': q.q[:120], 'zona_id': q.zona_id, 'resultados': encontrados, 'origen': 'busqueda',
                     'producto_id': None}, timeout=1)
    except ErrorApi:
        current_app.logger.info('ms-demanda no registró la búsqueda (no disponible).')


def recordar_popular(texto):
    try:
        pipe = extensiones.redis_client.pipeline()
        pipe.zincrby(POPULARES, 1, texto)
        pipe.expire(POPULARES, 60 * 60 * 24 * 30)
        pipe.execute()
    except RedisError:
        pass


@srv.ruta('/buscar', 'GET', resumen='Búsqueda unificada', etiqueta='Búsqueda', publico=True, consulta=BuscarConsulta,
          raiz_xml='busqueda', limite=120)
def buscar(q):
    """Productos, comercios verificados y proveedores verificados en una sola lista ordenada. `conteos` dice cuántos
    hay de cada tipo para mostrar pestañas en el cliente. `orden=distancia` requiere latitud y longitud."""
    if q.orden == 'distancia' and (q.latitud is None or q.longitud is None):
        raise ErrorApi(422, 'faltan_coordenadas', 'Para ordenar por distancia envía latitud y longitud.')
    texto = normalizar(q.q)
    recordar_popular(texto)
    parametros = {'t': texto, 'zona': q.zona_id, 'categoria': q.categoria_id, 'municipio': q.municipio,
                  'lat': q.latitud, 'lon': q.longitud}
    try:
        version = extensiones.redis_client.get(CLAVE_VERSION) or '0'
        clave = f"busqueda:v{version}:{hashlib.md5(json.dumps(q.model_dump(exclude={'origen'}), default=str, sort_keys=True).encode()).hexdigest()[:16]}"
        guardado = extensiones.redis_client.get(clave)
        if guardado:
            return {**json.loads(guardado), 'origen': 'cache'}
    except RedisError:
        clave = None

    partes = {'productos': buscar_productos, 'comercios': buscar_comercios, 'proveedores': buscar_proveedores}
    elegidas = partes if q.tipo == 'todos' else {q.tipo: partes[q.tipo]}
    union = ' UNION ALL '.join(f'({f(q, parametros)})' for f in elegidas.values())
    conteos = {k: 0 for k in partes}
    for fila in db.session.execute(text(f'SELECT tipo, count(*) AS n FROM ({union}) r GROUP BY tipo'), parametros):
        conteos[f'{fila.tipo}s' if fila.tipo != 'proveedor' else 'proveedores'] = fila.n
    orden = {'relevancia': 'relevancia DESC, nombre', 'nombre': 'nombre',
             'distancia': 'distancia_km NULLS LAST, relevancia DESC'}[q.orden]
    filas = db.session.execute(text(f'SELECT * FROM ({union}) r ORDER BY {orden} LIMIT :limite OFFSET :desp'),
                               {**parametros, 'limite': q.por_pagina, 'desp': (q.pagina - 1) * q.por_pagina}).all()
    resultados = [{'tipo': f.tipo, 'id': f.id, 'nombre': f.nombre, 'detalle': f.detalle, 'zona': f.zona,
                   'municipio': f.municipio, 'relevancia': float(f.relevancia),
                   'distancia_km': round(float(f.distancia_km), 3) if f.distancia_km is not None else None,
                   'existencia': float(f.existencia) if f.existencia is not None else None,
                   'precio': float(f.precio) if f.precio is not None else None} for f in filas]
    total = sum(conteos[k] for k in elegidas)
    if q.tipo in ('todos', 'productos') and q.pagina == 1:
        reportar_a_demanda(q, sum(1 for r in resultados if r['tipo'] == 'producto' and (r['existencia'] or 0) > 0))
    resultado = {'q': q.q, 'tipo': q.tipo, 'conteos': conteos,
                 **sobre_lista(resultados, total, q.pagina, q.por_pagina, 'resultados')}
    if clave:
        try:
            extensiones.redis_client.setex(clave, 60, json.dumps(compatible_json(resultado)))
        except RedisError:
            pass
    return {**resultado, 'origen': 'postgres'}


@srv.ruta('/buscar/ofertas', 'GET', resumen='Buscar ofertas de mayoreo', etiqueta='Búsqueda',
          permisos=['proveedores.consultar', 'pedidos.crear'], consulta=OfertasConsulta, raiz_xml='ofertas')
def buscar_ofertas(q):
    """Ofertas de proveedores verificados para productos que coinciden con el texto. Con `zona_id` marca si el
    proveedor entrega ahí."""
    rel = relevancia('p.nombre')
    filtros = ['cp.activo', 'pr.activo', "pr.estado_verificacion = 'VERIFICADO'", f'{rel} > 0']
    if q.con_existencia:
        filtros.append('cp.existencia_disponible > 0')
    if q.precio_max:
        filtros.append('cp.precio_mayoreo <= :precio_max')
    base = (f'FROM catalogo_proveedor cp JOIN proveedores pr ON pr.id = cp.proveedor_id '
            f'JOIN productos_maestros p ON p.id = cp.producto_id WHERE {" AND ".join(filtros)}')
    parametros = {'t': normalizar(q.q), 'precio_max': q.precio_max, 'zona': q.zona_id}
    total = db.session.execute(text(f'SELECT count(*) {base}'), parametros).scalar()
    orden = {'relevancia': 'relevancia DESC, cp.precio_mayoreo', 'precio': 'cp.precio_mayoreo, relevancia DESC',
             'tiempo_entrega': 'pr.tiempo_entrega_dias, cp.precio_mayoreo'}[q.orden]
    filas = db.session.execute(text(
        f'SELECT cp.id, p.id AS producto_id, p.nombre AS producto, pr.id::text AS proveedor_id, pr.nombre_empresa, '
        f'cp.precio_mayoreo, cp.cantidad_minima, cp.existencia_disponible, pr.tiempo_entrega_dias, {rel} AS relevancia, '
        f'EXISTS (SELECT 1 FROM proveedor_zonas pz WHERE pz.proveedor_id = pr.id AND pz.zona_id = :zona) AS cubre '
        f'{base} ORDER BY {orden} LIMIT :limite OFFSET :desp'),
        {**parametros, 'limite': q.por_pagina, 'desp': (q.pagina - 1) * q.por_pagina}).all()
    ofertas = [{'oferta_id': f.id, 'producto_id': f.producto_id, 'producto': f.producto, 'proveedor_id': f.proveedor_id,
                'proveedor': f.nombre_empresa, 'precio_mayoreo': float(f.precio_mayoreo),
                'cantidad_minima': float(f.cantidad_minima), 'existencia_disponible': float(f.existencia_disponible),
                'tiempo_entrega_dias': f.tiempo_entrega_dias, 'cubre_zona': f.cubre if q.zona_id else None,
                'relevancia': float(f.relevancia)} for f in filas]
    return {'q': q.q, **sobre_lista(ofertas, total, q.pagina, q.por_pagina, 'ofertas')}


@srv.ruta('/sugerencias', 'GET', resumen='Autocompletar', etiqueta='Sugerencias', publico=True,
          consulta=SugerenciasConsulta, raiz_xml='sugerencias', limite=240)
def sugerencias(q):
    """Nombres de productos y categorías que empiezan con el texto (o una de sus palabras), y búsquedas populares
    que lo contienen."""
    texto = normalizar(q.q)
    filas = db.session.execute(text(
        f"(SELECT 'producto' AS tipo, id::text AS id, nombre AS texto, {relevancia('nombre')} AS r "
        f"   FROM productos_maestros WHERE activo AND {relevancia('nombre')} >= 60) "
        f"UNION ALL (SELECT 'categoria', id::text, nombre, {relevancia('nombre')} "
        f"   FROM categorias WHERE {relevancia('nombre')} >= 60) ORDER BY r DESC, texto LIMIT :limite"),
        {'t': texto, 'limite': q.limite}).all()
    lista = [{'texto': f.texto, 'tipo': f.tipo, 'id': f.id} for f in filas]
    try:
        vistos = {normalizar(s['texto']) for s in lista}
        for popular in extensiones.redis_client.zrevrange(POPULARES, 0, 200):
            if len(lista) >= q.limite:
                break
            if texto in popular and popular not in vistos:
                lista.append({'texto': popular, 'tipo': 'popular', 'id': None})
    except RedisError:
        pass
    return {'q': q.q, 'sugerencias': lista[:q.limite]}


@srv.ruta('/populares', 'GET', resumen='Búsquedas más frecuentes (30 días)', etiqueta='Sugerencias', publico=True,
          raiz_xml='populares')
def populares():
    try:
        filas = extensiones.redis_client.zrevrange(POPULARES, 0, 19, withscores=True)
    except RedisError:
        filas = []
    return {'populares': [{'texto': t, 'busquedas': int(n)} for t, n in filas]}
