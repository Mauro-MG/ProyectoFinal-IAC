"""
ms-disponibilidad: ¿dónde hay este producto, cuánto y en cuánto tiempo se surte?

Servicio de CONSULTA (sólo lectura): no es dueño de ninguna tabla. Lee el inventario y las
reservas (de ms-inventario) y el catálogo mayorista (de ms-proveedores) con consultas de
sólo lectura, y guarda el resultado en Redis. Así las consultas públicas y de las apps, que
son muchas, no cargan a los servicios que escriben.

- Disponible = existencia - reservas activas (las reservas las administra ms-inventario).
- Sólo comercios VERIFICADOS y sin datos personales (RN-015).
- Caché en Redis con la misma versión que el análisis (`analisis:version`): cualquier
  movimiento de inventario la incrementa y la caché vieja deja de usarse.
- /disponibilidad/cambios: lo que cambió desde una fecha, para que Android y escritorio
  actualicen su copia local sin descargar todo.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from redis.exceptions import RedisError
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado, sobre_lista
from abasto_api.formatos import compatible_json
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.servicios.cache import CLAVE_VERSION

from esquemas import CambiosConsulta, CONTRATOS_XML, DisponibilidadConsulta, ProveedoresConsulta, ZonaConsulta

srv = Servicio('disponibilidad', 'Disponibilidad',
               'Consulta de disponibilidad de productos por comercio, zona y proveedor: cantidades disponibles, '
               'existencias reservadas y tiempo estimado de surtido; consultas agregadas y cambios para los clientes.',
               xsd=Path(__file__).parent / 'xsd' / 'disponibilidad.xsd', contratos=CONTRATOS_XML)
app = srv.app

SECTOR = ("CASE WHEN c.tipo_comercio::text LIKE 'FORMAL%' THEN 'Formal' "
          "WHEN c.tipo_comercio::text LIKE 'INFORMAL%' THEN 'Informal' ELSE 'Mayorista' END")
RESERVADO = ("COALESCE((SELECT sum(r.cantidad) FROM reservas_inventario r WHERE r.inventario_id = i.id "
             "AND r.estado = 'ACTIVA' AND r.expira_at > now()), 0)")


def _cache(nombre, parametros, calcular, ttl=120):
    try:
        version = extensiones.redis_client.get(CLAVE_VERSION) or '0'
        huella = hashlib.md5(json.dumps(parametros, sort_keys=True, default=str).encode()).hexdigest()[:12]
        clave = f'disponibilidad:v{version}:{nombre}:{huella}'
        guardado = extensiones.redis_client.get(clave)
        if guardado:
            return {**json.loads(guardado), 'origen': 'cache'}
    except RedisError:
        clave = None
    resultado = calcular()
    if clave:
        try:
            extensiones.redis_client.setex(clave, ttl, json.dumps(compatible_json(resultado)))
        except RedisError:
            pass
    return {**resultado, 'origen': 'postgres'}


def _numero(valor):
    return float(valor) if valor is not None else None


@srv.ruta('/disponibilidad', 'GET', resumen='Disponibilidad pública', etiqueta='Disponibilidad', publico=True,
          consulta=DisponibilidadConsulta, raiz_xml='disponibilidad', limite=60)
def disponibilidad(q):
    """Producto por comercio con existencia, lo reservado y lo disponible. Caché de 2 minutos en Redis."""
    def calcular():
        filtros, parametros = [], {}
        for campo, sql in (('producto_id', 'p.id = :producto_id'), ('zona_id', 'c.zona_id = :zona_id'),
                           ('categoria_id', 'p.categoria_id = :categoria_id')):
            if getattr(q, campo):
                filtros.append(sql)
                parametros[campo] = getattr(q, campo)
        if q.texto:
            filtros.append('p.nombre ILIKE :texto')
            parametros['texto'] = f'%{q.texto}%'
        if q.con_existencia:
            filtros.append('i.existencia > 0')
        base = (f'FROM inventario_comercio i JOIN comercios c ON c.id = i.comercio_id '
                f'JOIN productos_maestros p ON p.id = i.producto_id LEFT JOIN zonas_municipales z ON z.id = c.zona_id '
                f"WHERE i.activo AND c.activo AND c.estado_registro = 'VERIFICADO' "
                f'{"AND " + " AND ".join(filtros) if filtros else ""}')
        total = db.session.execute(text(f'SELECT count(*) {base}'), parametros).scalar()
        filas = db.session.execute(text(
            f'SELECT p.id AS producto_id, p.nombre AS producto, p.unidad_medida, c.id::text AS comercio_id, '
            f'c.nombre_comercio AS comercio, {SECTOR} AS sector, z.id AS zona_id, z.nombre AS zona, i.existencia, '
            f'{RESERVADO} AS reservada, i.estado, i.precio_venta AS precio, i.updated_at AS actualizado {base} '
            f'ORDER BY p.nombre, i.existencia DESC LIMIT :limite OFFSET :desplazamiento'),
            {**parametros, 'limite': q.por_pagina, 'desplazamiento': (q.pagina - 1) * q.por_pagina}).all()
        renglones = [{**f._asdict(), 'existencia': float(f.existencia), 'reservada': float(f.reservada),
                      'disponible': max(float(f.existencia) - float(f.reservada), 0), 'precio': _numero(f.precio)}
                     for f in filas]
        return sobre_lista(renglones, total, q.pagina, q.por_pagina, 'renglones')
    return _cache('lista', q.model_dump(), calcular)


@srv.ruta('/disponibilidad/comercios/<uuid:id>', 'GET', resumen='Disponibilidad de un comercio',
          etiqueta='Disponibilidad', publico=True, raiz_xml='comercio')
def por_comercio(id):
    comercio = db.session.execute(text(
        "SELECT c.id::text AS id, c.nombre_comercio, z.nombre AS zona FROM comercios c "
        "LEFT JOIN zonas_municipales z ON z.id = c.zona_id WHERE c.id = :id AND c.activo "
        "AND c.estado_registro = 'VERIFICADO'"), {'id': id}).first()
    if not comercio:
        raise no_encontrado('El comercio verificado')
    filas = db.session.execute(text(
        f'SELECT i.id AS inventario_id, p.id AS producto_id, p.nombre AS producto, p.unidad_medida, i.existencia, '
        f'{RESERVADO} AS reservada, i.estado, i.precio_venta AS precio, i.updated_at AS actualizado '
        f'FROM inventario_comercio i JOIN productos_maestros p ON p.id = i.producto_id '
        f'WHERE i.comercio_id = :id AND i.activo ORDER BY p.nombre'), {'id': id}).all()
    renglones = [{**f._asdict(), 'existencia': float(f.existencia), 'reservada': float(f.reservada),
                  'disponible': max(float(f.existencia) - float(f.reservada), 0), 'precio': _numero(f.precio)}
                 for f in filas]
    return {'comercio_id': comercio.id, 'comercio': comercio.nombre_comercio, 'zona': comercio.zona,
            'productos': len(renglones), 'agotados': sum(1 for r in renglones if r['disponible'] <= 0),
            'renglones': renglones}


@srv.ruta('/disponibilidad/zonas/<int:zona_id>', 'GET', resumen='Disponibilidad agregada de una zona',
          etiqueta='Agregados', publico=True, consulta=ZonaConsulta, raiz_xml='zona')
def por_zona(zona_id, q):
    """Por producto: cuántos comercios verificados de la zona lo tienen, cuánto hay disponible, precios, cuántos
    proveedores que entregan en la zona lo tienen en existencia y el menor tiempo de surtido."""
    zona = db.session.execute(text('SELECT id, nombre FROM zonas_municipales WHERE id = :z'), {'z': zona_id}).first()
    if not zona:
        raise no_encontrado('La zona')

    def calcular():
        filtros = []
        if q.categoria_id:
            filtros.append('p.categoria_id = :categoria')
        if q.solo_canasta:
            filtros.append('p.es_canasta_basica')
        filas = db.session.execute(text(
            f'SELECT p.id AS producto_id, p.nombre AS producto, p.es_canasta_basica AS canasta_basica, '
            f'  count(i.id) FILTER (WHERE i.existencia > 0) AS comercios, '
            f'  COALESCE(sum(GREATEST(i.existencia - {RESERVADO}, 0)), 0) AS disponible, '
            f'  min(i.precio_venta) AS precio_min, avg(i.precio_venta) AS precio_prom, '
            f'  (SELECT count(*) FROM catalogo_proveedor cp JOIN proveedores pr ON pr.id = cp.proveedor_id '
            f'     JOIN proveedor_zonas pz ON pz.proveedor_id = pr.id AND pz.zona_id = :z '
            f"     WHERE cp.producto_id = p.id AND cp.activo AND cp.existencia_disponible > 0 AND pr.activo "
            f"       AND pr.estado_verificacion = 'VERIFICADO') AS proveedores, "
            f'  (SELECT min(pr.tiempo_entrega_dias) FROM catalogo_proveedor cp JOIN proveedores pr ON pr.id = cp.proveedor_id '
            f'     JOIN proveedor_zonas pz ON pz.proveedor_id = pr.id AND pz.zona_id = :z '
            f"     WHERE cp.producto_id = p.id AND cp.activo AND cp.existencia_disponible > 0 AND pr.activo) AS tiempo "
            f'FROM productos_maestros p '
            f'LEFT JOIN inventario_comercio i ON i.producto_id = p.id AND i.activo AND i.comercio_id IN ('
            f"  SELECT id FROM comercios WHERE zona_id = :z AND activo AND estado_registro = 'VERIFICADO') "
            f'WHERE p.activo {"AND " + " AND ".join(filtros) if filtros else ""} '
            f'GROUP BY p.id ORDER BY p.es_canasta_basica DESC, p.nombre'),
            {'z': zona_id, 'categoria': q.categoria_id}).all()
        return {'zona_id': zona.id, 'zona': zona.nombre, 'productos': [
            {'producto_id': f.producto_id, 'producto': f.producto, 'canasta_basica': f.canasta_basica,
             'comercios_con_existencia': f.comercios, 'disponible_total': float(f.disponible),
             'precio_minimo': _numero(f.precio_min),
             'precio_promedio': round(float(f.precio_prom), 2) if f.precio_prom is not None else None,
             'proveedores_con_existencia': f.proveedores, 'tiempo_surtido_dias': f.tiempo} for f in filas]}
    return _cache(f'zona:{zona_id}', q.model_dump(), calcular, ttl=300)


@srv.ruta('/disponibilidad/proveedores', 'GET', resumen='¿Qué proveedor me surte y cuándo llega?',
          etiqueta='Proveedores', permisos=['proveedores.consultar', 'pedidos.crear'], consulta=ProveedoresConsulta,
          raiz_xml='proveedores')
def por_proveedor(q):
    """Existencia de mayoreo del producto por proveedor verificado, si entrega en la zona, si alcanza para la
    cantidad pedida y la fecha estimada de llegada (hoy + tiempo de entrega)."""
    if not db.session.execute(text('SELECT 1 FROM productos_maestros WHERE id = :p'), {'p': q.producto_id}).first():
        raise no_encontrado('El producto')
    filas = db.session.execute(text(
        'SELECT pr.id::text AS proveedor_id, pr.nombre_empresa AS proveedor, cp.existencia_disponible, '
        'cp.cantidad_minima, cp.precio_mayoreo, pr.tiempo_entrega_dias, '
        '  EXISTS (SELECT 1 FROM proveedor_zonas pz WHERE pz.proveedor_id = pr.id AND pz.zona_id = :z) AS cubre '
        'FROM catalogo_proveedor cp JOIN proveedores pr ON pr.id = cp.proveedor_id '
        "WHERE cp.producto_id = :p AND cp.activo AND pr.activo AND pr.estado_verificacion = 'VERIFICADO' "
        'ORDER BY cubre DESC, cp.existencia_disponible > 0 DESC, pr.tiempo_entrega_dias, cp.precio_mayoreo'),
        {'p': q.producto_id, 'z': q.zona_id}).all()
    hoy = datetime.now(timezone.utc)
    proveedores = [{
        'proveedor_id': f.proveedor_id, 'proveedor': f.proveedor, 'existencia_disponible': float(f.existencia_disponible),
        'cantidad_minima': float(f.cantidad_minima), 'precio_mayoreo': float(f.precio_mayoreo),
        'cubre_zona': f.cubre if q.zona_id else None,
        'alcanza': float(f.existencia_disponible) >= q.cantidad if q.cantidad else None,
        'tiempo_entrega_dias': f.tiempo_entrega_dias, 'fecha_estimada': hoy + timedelta(days=f.tiempo_entrega_dias)}
        for f in filas]
    utiles = [p for p in proveedores if p['existencia_disponible'] > 0 and p['cubre_zona'] is not False
              and p['alcanza'] is not False]
    return {'producto_id': q.producto_id, 'zona_id': q.zona_id,
            'total_disponible': sum(p['existencia_disponible'] for p in proveedores if p['cubre_zona'] is not False),
            'tiempo_surtido_dias': min((p['tiempo_entrega_dias'] for p in utiles), default=None),
            'proveedores': proveedores}


@srv.ruta('/disponibilidad/cambios', 'GET', resumen='Cambios desde una fecha (actualización de clientes)',
          etiqueta='Clientes', publico=True, consulta=CambiosConsulta, raiz_xml='cambios', limite=60)
def cambios(q):
    """Renglones de inventario de comercios verificados que cambiaron después de `desde` (incluye los dados de baja,
    con activo=false). Si `completo` es false hay más: pide otra vez con `desde` = `hasta` de esta respuesta."""
    if q.desde > datetime.now(q.desde.tzinfo or timezone.utc) + timedelta(minutes=5):
        raise ErrorApi(422, 'fecha_futura', '`desde` no puede estar en el futuro.')
    desde = q.desde.replace(tzinfo=None) if q.desde.tzinfo is None else q.desde
    filas = db.session.execute(text(
        f'SELECT i.id AS inventario_id, c.id::text AS comercio_id, i.producto_id, i.existencia, {RESERVADO} AS reservada, '
        f'i.estado, i.precio_venta AS precio, i.activo, i.updated_at AS actualizado '
        f'FROM inventario_comercio i JOIN comercios c ON c.id = i.comercio_id '
        f"WHERE c.estado_registro = 'VERIFICADO' AND i.updated_at > :desde "
        f'{"AND c.zona_id = :zona" if q.zona_id else ""} ORDER BY i.updated_at LIMIT :limite'),
        {'desde': desde, 'zona': q.zona_id, 'limite': q.limite + 1}).all()
    completo = len(filas) <= q.limite
    filas = filas[:q.limite]
    lista = [{**f._asdict(), 'existencia': float(f.existencia), 'reservada': float(f.reservada),
              'disponible': max(float(f.existencia) - float(f.reservada), 0), 'precio': _numero(f.precio)}
             for f in filas]
    return {'desde': q.desde, 'hasta': lista[-1]['actualizado'] if lista else q.desde, 'total': len(lista),
            'completo': completo, 'cambios': lista}
