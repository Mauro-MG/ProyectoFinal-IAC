"""
ms-precios: precio al consumidor, validación de precios atípicos, comparación y tendencias.

PostgreSQL: precios_comercio (historial al consumidor), precios_mayoreo, inventario_comercio.precio_venta.
MongoDB: snapshots_precios (fotografía diaria agregada por zona, producto y sector).
Redis: promedio regional de 7 días (`precio_promedio:zona:{z}:producto:{p}`, 4 h).
"""
from pathlib import Path
from datetime import date, timedelta
from uuid import UUID

from flask import g

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, sobre_lista, tiene, usuario_actual
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, InventarioComercio, PrecioComercio, ProductoMaestro
from abasto_dominio.servicios import historicos
from abasto_dominio.servicios import precios as servicio_precios
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.inventario import actualizar_precio, promedio_zona
from abasto_dominio.servicios.notificaciones import notificar

from esquemas import (CONTRATOS_XML, ComparacionConsulta, HistorialConsulta, PrecioEntrada, SerieConsulta,
                      SnapshotsConsulta, TendenciaConsulta, ValidacionPrecio)

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
