"""
ms-precios: precio al consumidor, validación de precios atípicos, comparación, promociones y estadísticas.

Es DUEÑO de: precios_comercio (historial al consumidor) y promociones. Cambia también la columna
inventario_comercio.precio_venta (el precio vigente del renglón): es la única columna de esa tabla
que escribe y está documentado como excepción en docs/propiedad_de_datos.md. Lee precios_mayoreo
(de ms-proveedores) para comparar.
MongoDB: snapshots_precios (fotografía diaria agregada por zona, producto y sector).
Redis: promedio regional de 7 días (`precio_promedio:zona:{z}:producto:{p}`, 4 h).
"""
from pathlib import Path
from datetime import date, timedelta
from uuid import UUID

from flask import g
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, sobre_lista, tiene, usuario_actual
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, InventarioComercio, PrecioComercio, ProductoMaestro, Promocion
from abasto_dominio.servicios import historicos
from abasto_dominio.servicios import precios as servicio_precios
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.inventario import actualizar_precio, promedio_zona
from abasto_dominio.servicios.notificaciones import notificar

from esquemas import (CONTRATOS_XML, ComparacionConsulta, EstadisticasConsulta, HistorialConsulta, PrecioEntrada,
                      PromocionEntrada, PromocionesConsulta, SerieConsulta, SnapshotsConsulta, TendenciaConsulta,
                      ValidacionPrecio)

srv = Servicio('precios', 'Precios',
               'Actualización rápida del precio al consumidor con validación de precios atípicos (RN-001), '
               'revisión humana de precios pendientes, comparación consumidor vs. mayoreo, tendencias y '
               'fotografías diarias de precios en MongoDB.',
               xsd=Path(__file__).parent / 'xsd' / 'precios.xsd', contratos=CONTRATOS_XML)
app = srv.app


def precio_a_dict(p):
    return {'id': p.id, 'comercio_id': str(p.comercio_id), 'comercio': p.comercio.nombre_comercio,
            'producto_id': p.producto_id, 'producto': p.producto.nombre, 'precio': p.precio,
            'precio_anterior': p.precio_anterior, 'estado_validacion': p.estado_validacion, 'activo': p.activo,
            'metodo_captura': p.metodo_captura, 'notas': p.notas, 'fecha': p.fecha_registro}


@srv.ruta('/inventario/<int:id>/precio', 'PUT', resumen='Actualización rápida de precio', etiqueta='Precio al consumidor',
          permisos=['inventario.gestionar'], cuerpo=PrecioEntrada, raiz_xml='cambio_precio',
          entrada_xml='precio_entrada',
          ejemplo_entrada={'precio': 27.5, 'metodo_captura': 'MOVIL'},
          ejemplo_salida={'inventario_id': 12, 'producto': 'Leche entera 1 L', 'precio_anterior': 28.0, 'precio': 27.5,
                          'estado_validacion': 'VALIDADO', 'promedio_zona_7_dias': 28.31})
def cambiar_precio(id, datos):
    """Si el precio sale del 10 %–150 % del promedio de la zona en 7 días queda PENDIENTE_VALIDACION
    (no entra a la comparación) y se avisa al comerciante. Responde 200 en ambos casos; revisa `estado_validacion`."""
    renglon = db.session.get(InventarioComercio, id)
    if not renglon or not renglon.activo:
        raise no_encontrado('El renglón de inventario')
    if str(renglon.comercio.usuario_id) != g.claims['sub'] and not tiene('catalogos.gestionar'):
        raise prohibido('El comercio no es tuyo.')
    anterior = renglon.precio_venta
    estado = actualizar_precio(renglon, datos.precio, usuario_actual(), metodo_captura=datos.metodo_captura)
    if estado == 'SIN_CAMBIO':
        raise ErrorApi(409, 'sin_cambio', 'El precio es igual al actual.')
    db.session.commit()
    promedio = _promedio_zona(renglon)
    return {'inventario_id': renglon.id, 'producto': renglon.producto.nombre, 'precio_anterior': anterior,
            'precio': renglon.precio_venta, 'estado_validacion': estado, 'promedio_zona_7_dias': promedio}


def _promedio_zona(renglon):
    if not renglon.comercio.zona_id:
        return None
    promedio = promedio_zona(renglon.comercio.zona_id, renglon.producto_id)
    return round(float(promedio), 2) if promedio else None


@srv.ruta('/precios', 'GET', resumen='Historial de precios al consumidor', etiqueta='Precio al consumidor',
          permisos=['precios.consultar', 'inventario.gestionar'], consulta=HistorialConsulta, raiz_xml='precios')
def historial(q):
    consulta = PrecioComercio.query.join(Comercio)
    if q.comercio_id:
        try:
            consulta = consulta.filter(PrecioComercio.comercio_id == UUID(q.comercio_id))
        except ValueError:
            raise ErrorApi(400, 'parametro_invalido', 'comercio_id debe ser un UUID.')
    if q.producto_id:
        consulta = consulta.filter(PrecioComercio.producto_id == q.producto_id)
    if q.estado_validacion:
        consulta = consulta.filter(PrecioComercio.estado_validacion == q.estado_validacion)
    if not tiene('precios.consultar'):
        consulta = consulta.filter(Comercio.usuario_id == UUID(g.claims['sub']))
    resultado = paginar(consulta.order_by(PrecioComercio.fecha_registro.desc()), q.pagina, q.por_pagina, precio_a_dict)
    resultado['precios'] = resultado.pop('items')
    return resultado


@srv.ruta('/precios/pendientes', 'GET', resumen='Precios pendientes de validación', etiqueta='Validación de precios',
          permisos=['comercios.validar'], raiz_xml='precios')
def pendientes():
    """Proceso de revisión humana: precios atípicos que esperan que la coordinación los valide o descarte."""
    lista = (PrecioComercio.query.filter_by(estado_validacion='PENDIENTE_VALIDACION', activo=True)
             .order_by(PrecioComercio.fecha_registro.desc()).limit(200).all())
    return {'total': len(lista), 'precios': [precio_a_dict(p) for p in lista]}


@srv.ruta('/precios/<int:id>/validacion', 'PATCH', resumen='Validar o descartar un precio atípico',
          etiqueta='Validación de precios', permisos=['comercios.validar'], cuerpo=ValidacionPrecio,
          raiz_xml='precio', entrada_xml='validacion_precio',
          ejemplo_entrada={'decision': 'VALIDAR', 'comentario': 'Confirmado por teléfono: oferta de temporada'})
def validar_precio(id, datos):
    precio = db.session.get(PrecioComercio, id)
    if not precio:
        raise no_encontrado('El precio')
    if precio.estado_validacion != 'PENDIENTE_VALIDACION' or not precio.activo:
        raise ErrorApi(409, 'ya_revisado', 'Ese precio ya fue revisado.')
    if datos.decision == 'VALIDAR':
        precio.estado_validacion = 'VALIDADO'
    else:
        precio.activo = False
    precio.notas = ((precio.notas or '') + f' | Revisión: {datos.decision}. {datos.comentario or ""}').strip()
    registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'PrecioComercio', precio.id,
                     f'Precio de {precio.producto.nombre} en {precio.comercio.nombre_comercio}: {datos.decision}',
                     datos_nuevos={'decision': datos.decision, 'comentario': datos.comentario})
    db.session.commit()
    invalidar_analisis()
    notificar(precio.comercio.usuario_id, 'precio_atipico', f'Precio de {precio.producto.nombre} revisado',
              f'Resultado: {"validado" if datos.decision == "VALIDAR" else "descartado"}. {datos.comentario or ""}',
              entidad={'tipo': 'precio', 'id': str(precio.id)}, origen='precios')
    return precio_a_dict(precio)


@srv.ruta('/precios/comparacion', 'GET', resumen='Comparación consumidor vs. mayoreo', etiqueta='Comparación',
          permisos=['precios.consultar'], consulta=ComparacionConsulta, raiz_xml='comparacion',
         )
def comparacion(q):
    """Mínimo, promedio, máximo y muestras por producto, zona y sector (consumidor) y por proveedor (mayoreo);
    el resumen une ambos y estima el margen bruto. Sólo precios VALIDADO."""
    hasta = q.hasta or date.today()
    desde = q.desde or hasta - timedelta(days=30)
    if desde > hasta:
        raise ErrorApi(422, 'rango_invalido', '`desde` no puede ser posterior a `hasta`.')
    if q.proveedor_id:
        try:
            UUID(q.proveedor_id)
        except ValueError:
            raise ErrorApi(400, 'parametro_invalido', 'proveedor_id debe ser un UUID.')
    filtros = {**q.model_dump(), 'desde': desde, 'hasta': hasta, 'hasta_exclusivo': hasta + timedelta(days=1)}
    consumidor = servicio_precios.precios_consumidor(filtros) if q.tipo in ('ambos', 'consumidor') else []
    mayoreo = servicio_precios.precios_mayoreo(filtros) if q.tipo in ('ambos', 'mayoreo') else []
    fila = lambda r: {k: v for k, v in r._asdict().items()}  # noqa: E731
    return {
        'desde': desde, 'hasta': hasta,
        'resumen': servicio_precios.resumen_por_producto(consumidor, mayoreo),
        'consumidor': [fila(r) for r in consumidor],
        'mayoreo': [{**fila(r), 'proveedor_id': str(r.proveedor_id)} for r in mayoreo],
    }


@srv.ruta('/precios/tendencia', 'GET', resumen='Tendencia semanal de un producto', etiqueta='Comparación',
          permisos=['precios.consultar'], consulta=TendenciaConsulta, raiz_xml='tendencia')
def tendencia(q):
    if not db.session.get(ProductoMaestro, q.producto_id):
        raise no_encontrado('El producto')
    datos = servicio_precios.tendencia_semanal(q.producto_id, q.semanas)
    return {'producto_id': q.producto_id, 'categorias': datos['categorias'],
            'series': [{'nombre': s['name'], 'datos': s['data']} for s in datos['series']]}


# ---------------------------------------------------------------- snapshots en MongoDB

@srv.ruta('/precios/snapshots', 'POST', resumen='Generar fotografía diaria de precios', etiqueta='Históricos (MongoDB)',
          permisos=['catalogos.gestionar', 'analisis.ver'], status=201, raiz_xml='snapshot')
def generar_snapshot():
    """Agrega en PostgreSQL los precios de los últimos 7 días y hace upsert en MongoDB (una fotografía por día,
    zona, producto y sector; índice único). Repetirlo el mismo día actualiza en lugar de duplicar."""
    return historicos.generar_snapshot_precios()


@srv.ruta('/precios/snapshots', 'GET', resumen='Consultar fotografías de precios', etiqueta='Históricos (MongoDB)',
          permisos=['precios.consultar'], consulta=SnapshotsConsulta, raiz_xml='snapshots')
def consultar_snapshots(q):
    items, total = historicos.consultar_snapshots(q.producto_id, q.zona_id, q.sector, q.desde, q.pagina, q.por_pagina)
    return sobre_lista(items, total, q.pagina, q.por_pagina, 'snapshots')


@srv.ruta('/precios/snapshots/tendencia', 'GET', resumen='Serie de un producto (pipeline de agregación)',
          etiqueta='Históricos (MongoDB)', permisos=['precios.consultar'], consulta=SerieConsulta,
          raiz_xml='tendencia_snapshots')
def serie_snapshots(q):
    return {'producto_id': q.producto_id, 'zona_id': q.zona_id,
            'tendencia': historicos.tendencia_snapshots(q.producto_id, q.zona_id)}


# ---------------------------------------------------------------- promociones

def promocion_a_dict(p):
    r = p.inventario
    normal = r.precio_venta
    return {'id': p.id, 'inventario_id': r.id, 'comercio_id': str(r.comercio_id), 'comercio': r.comercio.nombre_comercio,
            'producto_id': r.producto_id, 'producto': r.producto.nombre, 'precio_normal': normal,
            'precio_promocional': p.precio_promocional,
            'descuento_pct': round(float((normal - p.precio_promocional) * 100 / normal), 1) if normal else None,
            'inicio': p.inicio, 'fin': p.fin, 'descripcion': p.descripcion,
            'vigente': p.activa and p.inicio <= date.today() <= p.fin, 'activa': p.activa}


@srv.ruta('/promociones', 'POST', resumen='Crear una promoción', etiqueta='Promociones',
          permisos=['inventario.gestionar'], cuerpo=PromocionEntrada, status=201, raiz_xml='promocion',
          entrada_xml='promocion_entrada',
          ejemplo_entrada={'inventario_id': 120, 'precio_promocional': 27.5, 'inicio': '2026-11-15',
                           'fin': '2026-11-22', 'descripcion': 'Buen Fin'})
def crear_promocion(datos):
    """El precio promocional debe ser menor al precio de venta y no puede haber dos promociones del mismo producto que
    se traslapen. ms-ventas aplica la promoción vigente al registrar una venta."""
    renglon = db.session.get(InventarioComercio, datos.inventario_id)
    if not renglon or not renglon.activo:
        raise no_encontrado('El renglón de inventario')
    if str(renglon.comercio.usuario_id) != g.claims['sub']:
        raise prohibido('El comercio no es tuyo.')
    if datos.fin < datos.inicio:
        raise ErrorApi(422, 'fechas_invalidas', 'La fecha de fin no puede ser anterior al inicio.')
    if datos.fin < date.today():
        raise ErrorApi(422, 'fechas_invalidas', 'La promoción ya habría terminado.')
    if renglon.precio_venta and datos.precio_promocional >= renglon.precio_venta:
        raise ErrorApi(422, 'precio_no_promocional', f'Debe ser menor al precio de venta (${renglon.precio_venta}).')
    traslape = Promocion.query.filter(Promocion.inventario_id == renglon.id, Promocion.activa.is_(True),
                                      Promocion.inicio <= datos.fin, Promocion.fin >= datos.inicio).first()
    if traslape:
        raise ErrorApi(409, 'promocion_traslapada', f'Ya hay una promoción del {traslape.inicio} al {traslape.fin}.')
    promocion = Promocion(usuario_id=UUID(g.claims['sub']), **datos.model_dump())
    db.session.add(promocion)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'Promocion', promocion.id,
                     f'Promoción de {renglon.producto.nombre}: ${datos.precio_promocional}', datos_nuevos=datos.model_dump())
    db.session.commit()
    invalidar_analisis()
    return promocion_a_dict(promocion)


@srv.ruta('/promociones', 'GET', resumen='Promociones', etiqueta='Promociones', publico=True,
          consulta=PromocionesConsulta, raiz_xml='promociones')
def listar_promociones(q):
    """Públicas: sólo de comercios verificados. Por omisión, las vigentes hoy."""
    consulta = (Promocion.query.join(InventarioComercio).join(Comercio)
                .filter(Promocion.activa.is_(True), Comercio.activo.is_(True), Comercio.estado_registro == 'VERIFICADO'))
    if q.vigentes:
        consulta = consulta.filter(Promocion.inicio <= date.today(), Promocion.fin >= date.today())
    if q.comercio_id:
        try:
            consulta = consulta.filter(Comercio.id == UUID(q.comercio_id))
        except ValueError:
            raise ErrorApi(400, 'parametro_invalido', 'comercio_id debe ser un UUID.')
    if q.zona_id:
        consulta = consulta.filter(Comercio.zona_id == q.zona_id)
    if q.producto_id:
        consulta = consulta.filter(InventarioComercio.producto_id == q.producto_id)
    lista = consulta.order_by(Promocion.fin).limit(200).all()
    return {'total': len(lista), 'promociones': [promocion_a_dict(p) for p in lista]}


@srv.ruta('/promociones/<int:id>', 'DELETE', resumen='Terminar una promoción', etiqueta='Promociones',
          permisos=['inventario.gestionar'], raiz_xml='promocion')
def terminar_promocion(id):
    promocion = db.session.get(Promocion, id)
    if not promocion or not promocion.activa:
        raise no_encontrado('La promoción')
    if str(promocion.inventario.comercio.usuario_id) != g.claims['sub']:
        raise prohibido('La promoción es de otro comercio.')
    promocion.activa = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'Promocion', promocion.id, 'Promoción terminada')
    db.session.commit()
    invalidar_analisis()
    return promocion_a_dict(promocion)


# ---------------------------------------------------------------- estadísticas

@srv.ruta('/precios/estadisticas', 'GET', resumen='Estadísticas de precio por municipio, zona o producto',
          etiqueta='Estadísticas', permisos=['precios.consultar', 'analisis.ver'], consulta=EstadisticasConsulta,
          raiz_xml='estadisticas')
def estadisticas(q):
    """Sobre el historial de precios VALIDADOS de los últimos `dias`: mínimo, promedio, máximo, desviación estándar y
    variación, y el precio de mayoreo más bajo del producto para comparar."""
    grupo = {'municipio': 'c.municipio', 'zona': 'z.nombre', 'producto': 'p.nombre'}[q.agrupar]
    filas = db.session.execute(text(
        f'SELECT {grupo} AS grupo, '
        f'{"p.id" if q.agrupar == "producto" or q.producto_id else "NULL::int"} AS producto_id, '
        f'{"p.nombre" if q.agrupar == "producto" or q.producto_id else "NULL"} AS producto, '
        'count(*) AS registros, count(DISTINCT pc.comercio_id) AS comercios, min(pc.precio) AS minimo, '
        'avg(pc.precio) AS promedio, max(pc.precio) AS maximo, stddev_samp(pc.precio) AS desviacion, '
        '(SELECT min(cp.precio_mayoreo) FROM catalogo_proveedor cp WHERE cp.activo AND cp.producto_id = '
        f'{"p.id" if q.agrupar == "producto" or q.producto_id else "NULL"}) AS mayoreo '
        'FROM precios_comercio pc JOIN comercios c ON c.id = pc.comercio_id '
        'JOIN productos_maestros p ON p.id = pc.producto_id LEFT JOIN zonas_municipales z ON z.id = c.zona_id '
        "WHERE pc.estado_validacion = 'VALIDADO' AND pc.fecha_registro >= :desde "
        f'{"AND p.id = :producto" if q.producto_id else ""} '
        f'GROUP BY {grupo}{", p.id, p.nombre" if q.agrupar == "producto" or q.producto_id else ""} '
        'ORDER BY promedio DESC'), {'desde': date.today() - timedelta(days=q.dias), 'producto': q.producto_id}).all()
    renglones = []
    for f in filas:
        promedio = float(f.promedio)
        renglones.append({'grupo': f.grupo or 'Sin zona', 'producto_id': f.producto_id, 'producto': f.producto,
                          'registros': f.registros, 'comercios': f.comercios, 'minimo': float(f.minimo),
                          'promedio': round(promedio, 2), 'maximo': float(f.maximo),
                          'desviacion': round(float(f.desviacion), 2) if f.desviacion is not None else None,
                          'variacion_pct': round((float(f.maximo) - float(f.minimo)) * 100 / promedio, 1) if promedio else None,
                          'mayoreo_minimo': float(f.mayoreo) if f.mayoreo is not None else None})
    return {'agrupar': q.agrupar, 'producto_id': q.producto_id, 'dias': q.dias, 'renglones': renglones}
