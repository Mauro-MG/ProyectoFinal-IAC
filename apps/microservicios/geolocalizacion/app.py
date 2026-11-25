"""
ms-geolocalizacion: operaciones espaciales con PostGIS.

Es DUEÑO de: zonas_municipales y colonias. Los demás servicios le preguntan en qué zona
cae un punto (ms-comercios al registrar un comercio) en lugar de calcularlo por su cuenta.

- Zonas: consulta (con caché en Redis), alta y cambios; el área se recalcula por trigger
  (ST_Buffer sobre geography, en 02_geo.sql).
- Localizar un punto: ST_Contains contra el polígono de la zona.
- Geocodificación sin servicios externos: se busca la colonia en el catálogo `colonias`
  (texto normalizado, sin acentos) y se regresa su centro; si sólo se reconoce el municipio,
  se regresa el centro del municipio con precisión "municipio".
- Geocodificación inversa: colonia más cercana con el operador KNN de PostGIS (<->).
- Distancias: ST_Distance sobre geography (metros reales sobre el elipsoide) y Haversine
  como comparación.
- Búsqueda por radio: ST_DWithin sobre geography usando los índices GIST.
- Cobertura por municipio, colonia o zona.
"""
import json
import unicodedata
from pathlib import Path
from uuid import UUID

from flask import g
from redis.exceptions import RedisError
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import ZonaMunicipal
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.geo import area_km2, distancia_km

from esquemas import (CONTRATOS_XML, CercanosConsulta, CoberturaConsulta, DistanciaConsulta, GeocodificarConsulta,
                      PuntoConsulta, PuntoEntrada, ZonaCambio, ZonaEntrada, ZonasConsulta)

srv = Servicio('geolocalizacion', 'Geolocalización',
               'Geocodificación, validación de coordenadas, distancias, búsquedas por radio, comercios y proveedores '
               'cercanos, zonas municipales y cobertura por municipio o colonia con PostGIS.',
               xsd=Path(__file__).parent / 'xsd' / 'geolocalizacion.xsd', contratos=CONTRATOS_XML)
app = srv.app

CLAVE_ZONAS = 'geo:zonas'
# Rectángulo aproximado del área metropolitana de Monterrey
AREA_METROPOLITANA = {'lat_min': 25.45, 'lat_max': 25.95, 'lon_min': -100.70, 'lon_max': -99.95}


def normalizar(texto):
    sin_acentos = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return ' '.join(sin_acentos.lower().replace(',', ' ').replace('.', ' ').split())


def zona_a_dict(z, detalle=False):
    datos = {'id': z.id, 'nombre': z.nombre, 'municipio': z.municipio, 'estado': z.estado,
             'codigo_postal': z.codigo_postal, 'latitud_centro': float(z.latitud_centro),
             'longitud_centro': float(z.longitud_centro), 'radio_km': float(z.radio_km), 'poblacion': z.poblacion,
             'activa': z.activa}
    if detalle:
        datos.update({'area_km2': round(area_km2(float(z.radio_km)), 2),
                      'comercios': db.session.execute(text(
                          'SELECT count(*) FROM comercios WHERE zona_id = :z AND activo'), {'z': z.id}).scalar()})
    return datos


def colonia_a_dict(fila, distancia=None):
    return {'id': fila.id, 'nombre': fila.nombre, 'municipio': fila.municipio, 'codigo_postal': fila.codigo_postal,
            'latitud': float(fila.latitud), 'longitud': float(fila.longitud),
            'distancia_km': round(distancia, 3) if distancia is not None else None}


def zona_del_punto(latitud, longitud):
    """Zona cuyo polígono contiene el punto; si cae en varias, la de centro más cercano."""
    fila = db.session.execute(text(
        'SELECT id FROM zonas_municipales WHERE activa AND ST_Contains(area, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) '
        'ORDER BY ST_Distance(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, '
        '                     ST_SetSRID(ST_MakePoint(longitud_centro, latitud_centro), 4326)::geography) LIMIT 1'),
        {'lat': latitud, 'lon': longitud}).first()
    return db.session.get(ZonaMunicipal, fila.id) if fila else None


def zonas_cercanas(latitud, longitud, limite=3):
    filas = db.session.execute(text(
        'SELECT id, nombre, radio_km, ST_Distance(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, '
        '       ST_SetSRID(ST_MakePoint(longitud_centro, latitud_centro), 4326)::geography) / 1000 AS km '
        'FROM zonas_municipales WHERE activa ORDER BY km LIMIT :limite'),
        {'lat': latitud, 'lon': longitud, 'limite': limite})
    return [{'zona_id': f.id, 'zona': f.nombre, 'distancia_km': round(float(f.km), 2), 'radio_km': float(f.radio_km)}
            for f in filas]


def colonia_mas_cercana(latitud, longitud):
    # <-> usa el índice GIST (KNN); la distancia real se calcula después sobre geography
    return db.session.execute(text(
        'SELECT id, nombre, municipio, codigo_postal, latitud, longitud, '
        '       ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1000 AS km '
        'FROM colonias ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 1'),
        {'lat': latitud, 'lon': longitud}).first()


def dentro_del_area(latitud, longitud):
    a = AREA_METROPOLITANA
    return a['lat_min'] <= float(latitud) <= a['lat_max'] and a['lon_min'] <= float(longitud) <= a['lon_max']


def _invalidar_zonas():
    try:
        extensiones.redis_client.delete(CLAVE_ZONAS)
    except RedisError:
        pass
    invalidar_analisis()


# ---------------------------------------------------------------- zonas

@srv.ruta('/zonas', 'GET', resumen='Zonas municipales', etiqueta='Zonas', publico=True, raiz_xml='zonas',
          consulta=ZonasConsulta)
def listar_zonas(q):
    """Lista pública de zonas activas. Se guarda 10 minutos en Redis (`geo:zonas`); un alta o cambio la invalida.
    `incluir_inactivas=true` (configuración de zonas) lee de PostgreSQL e incluye las desactivadas."""
    if q.incluir_inactivas:
        return {'origen': 'postgres', 'zonas': [zona_a_dict(z) for z in
                                                ZonaMunicipal.query.order_by(ZonaMunicipal.municipio, ZonaMunicipal.nombre)]}
    try:
        guardado = extensiones.redis_client.get(CLAVE_ZONAS)
        if guardado:
            return {'origen': 'cache', 'zonas': json.loads(guardado)}
    except RedisError:
        pass
    zonas = [zona_a_dict(z) for z in ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre)]
    try:
        extensiones.redis_client.setex(CLAVE_ZONAS, 600, json.dumps(zonas))
    except RedisError:
        pass
    return {'origen': 'postgres', 'zonas': zonas}


@srv.ruta('/zonas/<int:id>', 'GET', resumen='Detalle de una zona', etiqueta='Zonas', publico=True, raiz_xml='zona')
def detalle_zona(id):
    zona = db.session.get(ZonaMunicipal, id)
    if not zona:
        raise no_encontrado('La zona')
    return zona_a_dict(zona, detalle=True)


@srv.ruta('/zonas', 'POST', resumen='Alta de zona', etiqueta='Zonas', permisos=['catalogos.gestionar'],
          cuerpo=ZonaEntrada, status=201, raiz_xml='zona', entrada_xml='zona_entrada',
          ejemplo_entrada={'nombre': 'García Oriente', 'municipio': 'García', 'latitud_centro': 25.79,
                           'longitud_centro': -100.55, 'radio_km': 2.5, 'poblacion': 18000})
def crear_zona(datos):
    if ZonaMunicipal.query.filter_by(nombre=datos.nombre, municipio=datos.municipio).first():
        raise ErrorApi(409, 'zona_duplicada', 'Ya existe una zona con ese nombre en el municipio.')
    zona = ZonaMunicipal(**datos.model_dump())
    db.session.add(zona)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'ZonaMunicipal', zona.id, f'Alta de la zona {zona.nombre}',
                     datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar_zonas()
    return zona_a_dict(zona, detalle=True)


@srv.ruta('/zonas/<int:id>', 'PATCH', resumen='Cambiar una zona', etiqueta='Zonas', permisos=['catalogos.gestionar'],
          cuerpo=ZonaCambio, raiz_xml='zona', entrada_xml='zona_cambio',
          ejemplo_entrada={'radio_km': 3, 'poblacion': 21000})
def cambiar_zona(id, datos):
    """Si cambian el centro o el radio, el trigger de PostGIS recalcula el polígono."""
    zona = db.session.get(ZonaMunicipal, id)
    if not zona:
        raise no_encontrado('La zona')
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise ErrorApi(422, 'sin_cambios', 'Indica al menos un campo a cambiar.')
    antes = {k: getattr(zona, k) for k in cambios}
    for campo, valor in cambios.items():
        setattr(zona, campo, valor)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'ZonaMunicipal', zona.id, f'Cambio de la zona {zona.nombre}',
                     datos_anteriores=antes, datos_nuevos=cambios)
    db.session.commit()
    _invalidar_zonas()
    return zona_a_dict(zona, detalle=True)


@srv.ruta('/zonas/localizar', 'GET', resumen='¿En qué zona cae un punto?', etiqueta='Zonas', publico=True,
          consulta=PuntoConsulta, raiz_xml='localizacion', errores=(400, 404, 422))
def localizar(q):
    """ST_Contains del punto contra el polígono de cada zona. Si no cae en ninguna responde 404 con las tres zonas
    más cercanas en `detalles`."""
    zona = zona_del_punto(q.latitud, q.longitud)
    cercanas = zonas_cercanas(q.latitud, q.longitud)
    if not zona:
        raise ErrorApi(404, 'fuera_de_zona', 'El punto no cae dentro de ninguna zona registrada.', detalles=cercanas)
    return {'zona': zona_a_dict(zona), 'metodo': 'ST_Contains', 'cercanas': cercanas}


# ---------------------------------------------------------------- geocodificación

@srv.ruta('/geocodificar', 'GET', resumen='Dirección o colonia -> coordenadas', etiqueta='Geocodificación',
          publico=True, consulta=GeocodificarConsulta, raiz_xml='geocodificacion', errores=(400, 404, 422))
def geocodificar(q):
    """Busca la colonia mencionada en el texto (sin importar acentos ni mayúsculas). Si encuentra varias, regresa
    la de nombre más largo (la más específica) y las demás en `alternativas`."""
    texto = normalizar(f'{q.direccion} {q.municipio or ""}')
    colonias = db.session.execute(text(
        'SELECT id, nombre, municipio, codigo_postal, latitud, longitud FROM colonias')).all()
    municipio_buscado = normalizar(q.municipio) if q.municipio else None
    coincidencias = [c for c in colonias if normalizar(c.nombre) in texto
                     and (not municipio_buscado or normalizar(c.municipio) == municipio_buscado)]
    coincidencias.sort(key=lambda c: -len(c.nombre))
    if coincidencias:
        elegida = coincidencias[0]
        zona = zona_del_punto(elegida.latitud, elegida.longitud)
        return {'consulta': q.direccion, 'precision': 'colonia', 'latitud': float(elegida.latitud),
                'longitud': float(elegida.longitud), 'colonia': colonia_a_dict(elegida),
                'municipio': elegida.municipio, 'zona': zona_a_dict(zona) if zona else None,
                'alternativas': [colonia_a_dict(c) for c in coincidencias[1:5]]}
    # Sólo el municipio: centro promedio de sus colonias
    por_municipio = {}
    for c in colonias:
        por_municipio.setdefault(c.municipio, []).append(c)
    for municipio, lista in por_municipio.items():
        if normalizar(municipio) in texto:
            lat = sum(float(c.latitud) for c in lista) / len(lista)
            lon = sum(float(c.longitud) for c in lista) / len(lista)
            return {'consulta': q.direccion, 'precision': 'municipio', 'latitud': round(lat, 6),
                    'longitud': round(lon, 6), 'municipio': municipio, 'zona': None,
                    'alternativas': [colonia_a_dict(c) for c in lista[:5]]}
    raise ErrorApi(404, 'sin_coincidencias', 'No se reconoció ninguna colonia ni municipio del área metropolitana.')


@srv.ruta('/geocodificacion-inversa', 'GET', resumen='Coordenadas -> colonia, municipio y zona',
          etiqueta='Geocodificación', publico=True, consulta=PuntoConsulta, raiz_xml='geocodificacion_inversa')
def inversa(q):
    colonia = colonia_mas_cercana(q.latitud, q.longitud)
    if not colonia:
        raise no_encontrado('Una colonia registrada')
    zona = zona_del_punto(q.latitud, q.longitud)
    return {'latitud': float(q.latitud), 'longitud': float(q.longitud), 'colonia': colonia_a_dict(colonia, colonia.km),
            'municipio': colonia.municipio, 'zona': zona_a_dict(zona) if zona else None}


@srv.ruta('/coordenadas/validacion', 'POST', resumen='Validar coordenadas capturadas', etiqueta='Geocodificación',
          publico=True, cuerpo=PuntoEntrada, raiz_xml='validacion', entrada_xml='punto_entrada',
          ejemplo_entrada={'latitud': 25.821, 'longitud': -100.589})
def validar_coordenadas(datos):
    """Revisa que el punto esté en el área metropolitana, que no sea (0, 0) y que caiga en una zona. No guarda
    nada; la usan las apps antes de registrar un comercio. Los rangos de latitud y longitud los valida el
    contrato (422 si están fuera)."""
    avisos = []
    if datos.latitud == 0 and datos.longitud == 0:
        avisos.append('Coordenadas (0, 0): probablemente el GPS no obtuvo ubicación.')
    dentro = dentro_del_area(datos.latitud, datos.longitud)
    if not dentro:
        avisos.append('El punto está fuera del área metropolitana de Monterrey.')
    zona = zona_del_punto(datos.latitud, datos.longitud) if dentro else None
    if dentro and not zona:
        avisos.append('El punto no cae en ninguna zona registrada; la coordinación municipal asignará una.')
    colonia = colonia_mas_cercana(datos.latitud, datos.longitud) if dentro else None
    return {'valida': dentro and not (datos.latitud == 0 and datos.longitud == 0), 'latitud': float(datos.latitud),
            'longitud': float(datos.longitud), 'dentro_area_metropolitana': dentro,
            'zona': zona_a_dict(zona) if zona else None,
            'colonia_cercana': colonia_a_dict(colonia, colonia.km) if colonia else None, 'avisos': avisos}


# ---------------------------------------------------------------- distancias y radios

@srv.ruta('/distancia', 'GET', resumen='Distancia entre dos puntos', etiqueta='Distancias', publico=True,
          consulta=DistanciaConsulta, raiz_xml='distancia')
def distancia(q):
    metros = db.session.execute(text(
        'SELECT ST_Distance(ST_SetSRID(ST_MakePoint(:lon1, :lat1), 4326)::geography, '
        '                   ST_SetSRID(ST_MakePoint(:lon2, :lat2), 4326)::geography)'),
        {'lat1': q.origen_latitud, 'lon1': q.origen_longitud, 'lat2': q.destino_latitud,
         'lon2': q.destino_longitud}).scalar()
    return {'distancia_km': round(float(metros) / 1000, 3),
            'distancia_haversine_km': round(distancia_km(q.origen_latitud, q.origen_longitud, q.destino_latitud,
                                                         q.destino_longitud), 3),
            'metodo': 'ST_Distance (geography, elipsoide WGS84)'}


@srv.ruta('/cercanos', 'GET', resumen='Comercios o proveedores dentro de un radio', etiqueta='Distancias',
          permisos=['comercios.ver_todos', 'proveedores.consultar', 'comercios.gestionar', 'analisis.ver'],
          consulta=CercanosConsulta, raiz_xml='cercanos')
def cercanos(q):
    """ST_DWithin sobre geography (usa el índice GIST). Con `producto_id`: comercios verificados que tienen
    existencia de ese producto, o proveedores verificados que lo ofrecen. Ordenados por distancia."""
    punto = 'ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography'
    parametros = {'lat': q.latitud, 'lon': q.longitud, 'radio': float(q.radio_km) * 1000, 'limite': q.limite,
                  'producto': q.producto_id}
    if q.tipo == 'comercios':
        sql = (f'SELECT c.id::text AS id, c.nombre_comercio AS nombre, c.tipo_comercio::text AS tipo, c.latitud, '
               f'c.longitud, c.zona_id, ST_Distance(c.geom::geography, {punto}) / 1000 AS km, '
               f'i.existencia, i.precio_venta AS precio '
               f'FROM comercios c '
               f'{"JOIN" if q.producto_id else "LEFT JOIN"} inventario_comercio i ON i.comercio_id = c.id '
               f'  AND i.activo AND i.producto_id = :producto AND i.existencia > 0 '
               f"WHERE c.activo AND c.estado_registro = 'VERIFICADO' AND c.geom IS NOT NULL "
               f'  AND ST_DWithin(c.geom::geography, {punto}, :radio) ORDER BY km LIMIT :limite')
    else:
        sql = (f"SELECT p.id::text AS id, p.nombre_empresa AS nombre, 'PROVEEDOR' AS tipo, p.latitud, p.longitud, "
               f'NULL::int AS zona_id, ST_Distance(p.geom::geography, {punto}) / 1000 AS km, '
               f'cp.existencia_disponible AS existencia, cp.precio_mayoreo AS precio '
               f'FROM proveedores p '
               f'{"JOIN" if q.producto_id else "LEFT JOIN"} catalogo_proveedor cp ON cp.proveedor_id = p.id '
               f'  AND cp.activo AND cp.producto_id = :producto '
               f"WHERE p.activo AND p.estado_verificacion = 'VERIFICADO' AND p.geom IS NOT NULL "
               f'  AND ST_DWithin(p.geom::geography, {punto}, :radio) ORDER BY km LIMIT :limite')
    filas = db.session.execute(text(sql), parametros).all()
    return {'latitud': float(q.latitud), 'longitud': float(q.longitud), 'radio_km': float(q.radio_km),
            'tipo': q.tipo, 'total': len(filas), 'resultados': [
                {'id': f.id, 'nombre': f.nombre, 'tipo': f.tipo, 'latitud': float(f.latitud),
                 'longitud': float(f.longitud), 'distancia_km': round(float(f.km), 3), 'zona_id': f.zona_id,
                 'existencia': f.existencia, 'precio': f.precio} for f in filas]}


@srv.ruta('/cobertura', 'GET', resumen='Cobertura comercial por municipio, colonia o zona', etiqueta='Cobertura',
          permisos=['analisis.ver', 'comercios.ver_todos'], consulta=CoberturaConsulta, raiz_xml='cobertura')
def cobertura(q):
    """Comercios activos (formales e informales) y proveedores que entregan, agrupados. Para `colonia` se asigna a
    cada comercio la colonia más cercana del catálogo (KNN con PostGIS)."""
    filtro = 'AND c.municipio = :municipio' if q.municipio else ''
    if q.nivel == 'zona':
        sql = ('SELECT z.nombre, z.municipio, z.poblacion, count(c.id) AS comercios, '
               "  count(c.id) FILTER (WHERE c.tipo_comercio::text LIKE 'FORMAL%') AS formales, "
               "  count(c.id) FILTER (WHERE c.tipo_comercio::text LIKE 'INFORMAL%') AS informales, "
               '  (SELECT count(*) FROM proveedor_zonas pz JOIN proveedores p ON p.id = pz.proveedor_id '
               "    WHERE pz.zona_id = z.id AND p.activo AND p.estado_verificacion = 'VERIFICADO') AS proveedores "
               'FROM zonas_municipales z LEFT JOIN comercios c ON c.zona_id = z.id AND c.activo '
               f'WHERE z.activa {"AND z.municipio = :municipio" if q.municipio else ""} '
               'GROUP BY z.id ORDER BY z.municipio, z.nombre')
    elif q.nivel == 'colonia':
        sql = ('SELECT col.nombre, col.municipio, NULL::int AS poblacion, count(c.id) AS comercios, '
               "  count(c.id) FILTER (WHERE c.tipo_comercio::text LIKE 'FORMAL%') AS formales, "
               "  count(c.id) FILTER (WHERE c.tipo_comercio::text LIKE 'INFORMAL%') AS informales, 0 AS proveedores "
               'FROM colonias col LEFT JOIN LATERAL ('
               '  SELECT c.* FROM comercios c WHERE c.activo AND c.geom IS NOT NULL '
               '    AND (SELECT id FROM colonias x ORDER BY x.geom <-> c.geom LIMIT 1) = col.id) c ON true '
               f'{"WHERE col.municipio = :municipio" if q.municipio else ""} '
               'GROUP BY col.id ORDER BY comercios DESC, col.municipio, col.nombre')
    else:
        sql = ('SELECT c.municipio AS nombre, NULL AS municipio, '
               '  (SELECT sum(poblacion) FROM zonas_municipales z WHERE z.municipio = c.municipio) AS poblacion, '
               '  count(*) AS comercios, '
               "  count(*) FILTER (WHERE c.tipo_comercio::text LIKE 'FORMAL%') AS formales, "
               "  count(*) FILTER (WHERE c.tipo_comercio::text LIKE 'INFORMAL%') AS informales, "
               '  (SELECT count(DISTINCT pz.proveedor_id) FROM proveedor_zonas pz '
               '     JOIN zonas_municipales z ON z.id = pz.zona_id WHERE z.municipio = c.municipio) AS proveedores '
               f'FROM comercios c WHERE c.activo {filtro} GROUP BY c.municipio ORDER BY comercios DESC')
    filas = db.session.execute(text(sql), {'municipio': q.municipio}).all()
    return {'nivel': q.nivel, 'municipio': q.municipio, 'renglones': [
        {'nombre': f.nombre, 'municipio': f.municipio, 'comercios': f.comercios, 'comercios_formales': f.formales,
         'comercios_informales': f.informales, 'proveedores_que_entregan': f.proveedores,
         'poblacion': int(f.poblacion) if f.poblacion is not None else None,
         'habitantes_por_comercio': round(int(f.poblacion) / f.comercios, 1)
         if f.poblacion and f.comercios else None} for f in filas]}
