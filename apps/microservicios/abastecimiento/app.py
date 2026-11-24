"""
ms-abastecimiento: cotizaciones, comparación de ofertas y órdenes de compra.

Es DUEÑO de: solicitudes_cotizacion, necesidades_solicitud, cotizaciones, partidas_cotizacion,
ordenes_compra y partidas_orden. Los pedidos los crea ms-pedidos (este servicio le manda la
orden con el token del comerciante); el inventario y el catálogo mayorista sólo se leen.

Flujo:
1. Un comerciante pide cotización de lo que necesita. Si es CONSOLIDADA, otros comercios de la
   misma zona suman sus necesidades y se cotiza el total (mejor precio por volumen).
2. Los proveedores verificados que entregan en la zona cotizan: precio y cantidad disponible por
   producto, tiempo de entrega y vigencia.
3. Comparación: total de cada cotización para lo solicitado, % de productos cubiertos, si cumple
   el pedido mínimo, vigencia y evaluación del proveedor; se recomienda la de mayor cobertura y,
   a igual cobertura, la de menor total.
4. Adjudicación: se genera una ORDEN DE COMPRA por cada comercio participante con sus cantidades
   y los precios cotizados.
5. Cada comerciante convierte su orden en pedido (POST /ordenes/{id}/pedido → ms-pedidos).

Además, la sugerencia de reabastecimiento toma los faltantes del comercio y propone, por producto,
el proveedor con mejor precio que entrega en la zona, agrupado por proveedor.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from flask import g
from sqlalchemy import or_, text

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene
from abasto_api.clientes import llamar
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio, InventarioComercio, Proveedor, proveedor_zonas
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.bloqueos import bloqueo
from abasto_dominio.servicios.notificaciones import notificar
from abasto_dominio.servicios.parametros import parametro

from esquemas import (AdjudicacionEntrada, CONTRATOS_XML, CotizacionEntrada, NecesidadesEntrada, OrdenesConsulta,
                      SolicitudEntrada, SolicitudesConsulta)
from modelos import (Cotizacion, NecesidadSolicitud, OrdenCompra, PartidaCotizacion, PartidaOrden,
                     SolicitudCotizacion)

srv = Servicio('abastecimiento', 'Abastecimiento',
               'Solicitud de cotizaciones, comparación de ofertas mayoristas, sugerencia de reabastecimiento, selección '
               'de proveedores, generación de órdenes de compra y consolidación de necesidades de varios comerciantes.',
               xsd=Path(__file__).parent / 'xsd' / 'abastecimiento.xsd', contratos=CONTRATOS_XML)
app = srv.app

DOS = Decimal('0.01')


def _uuid(valor, campo):
    try:
        return UUID(str(valor))
    except ValueError:
        raise ErrorApi(400, 'parametro_invalido', f'{campo} debe ser un UUID.')


def _mi_comercio(comercio_id):
    comercio = db.session.get(Comercio, _uuid(comercio_id, 'comercio_id'))
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    if str(comercio.usuario_id) != g.claims['sub']:
        raise prohibido('El comercio no es tuyo.')
    if not comercio.zona_id:
        raise ErrorApi(409, 'sin_zona', 'El comercio no tiene zona asignada.')
    return comercio


def _mi_empresa():
    empresa_id = g.claims.get('proveedor_id')
    proveedor = db.session.get(Proveedor, UUID(empresa_id)) if empresa_id else None
    if not proveedor:
        raise ErrorApi(409, 'sin_empresa', 'Tu cuenta no está ligada a un proveedor.')
    return proveedor


def mis_comercios_ids():
    return {c.id for c in Comercio.query.filter_by(usuario_id=UUID(g.claims['sub'])).all()}


def es_participante(solicitud):
    return bool(mis_comercios_ids() & {n.comercio_id for n in solicitud.necesidades}) or \
        str(solicitud.creada_por) == g.claims['sub']


def entrega_en_zona(proveedor_id, zona_id):
    return db.session.query(proveedor_zonas).filter_by(proveedor_id=proveedor_id, zona_id=zona_id).first() is not None


def _solicitud(id):
    solicitud = db.session.get(SolicitudCotizacion, id)
    if not solicitud:
        raise no_encontrado('La solicitud')
    if es_participante(solicitud) or tiene('pedidos.ver_todos'):
        return solicitud
    if tiene('abastecimiento.cotizar'):
        empresa = _mi_empresa()
        if entrega_en_zona(empresa.id, solicitud.zona_id):
            return solicitud
    raise prohibido('No participas en esa solicitud ni entregas en su zona.')


def consolidado(solicitud):
    """{producto_id: (producto, cantidad total, comercios)}"""
    total = {}
    for n in solicitud.necesidades:
        producto, cantidad, comercios = total.get(n.producto_id, (n.producto, Decimal(0), set()))
        comercios.add(n.comercio_id)
        total[n.producto_id] = (producto, cantidad + n.cantidad, comercios)
    return total


def cotizacion_a_dict(c):
    return {'id': str(c.id), 'proveedor_id': str(c.proveedor_id), 'proveedor': c.proveedor.nombre_empresa,
            'tiempo_entrega_dias': c.tiempo_entrega_dias, 'vigencia': c.vigencia, 'notas': c.notas, 'estado': c.estado,
            'fecha': c.created_at, 'partidas': [{'producto_id': p.producto_id, 'producto': p.producto.nombre,
                                                 'precio_unitario': p.precio_unitario,
                                                 'cantidad_disponible': p.cantidad_disponible} for p in c.partidas]}


def solicitud_a_dict(s, con_cotizaciones=True):
    participantes = {}
    for n in s.necesidades:
        participantes.setdefault(n.comercio_id, [n.comercio.nombre_comercio, 0])[1] += 1
    datos = {'id': str(s.id), 'folio': s.folio_legible, 'titulo': s.titulo, 'zona_id': s.zona_id,
             'zona': s.zona.nombre, 'consolidada': s.consolidada, 'estado': s.estado, 'fecha_limite': s.fecha_limite,
             'notas': s.notas, 'creada_por_mi': str(s.creada_por) == g.claims['sub'], 'fecha': s.created_at,
             'participantes': [{'comercio_id': str(k), 'comercio': v[0], 'productos': v[1]}
                               for k, v in participantes.items()],
             'necesidades': [{'producto_id': pid, 'producto': p.nombre, 'unidad_medida': p.unidad_medida,
                              'cantidad': cantidad, 'comercios': len(comercios)}
                             for pid, (p, cantidad, comercios) in consolidado(s).items()]}
    if con_cotizaciones:
        if es_participante(s) or tiene('pedidos.ver_todos'):
            datos['cotizaciones'] = [cotizacion_a_dict(c) for c in s.cotizaciones]
        else:   # un proveedor sólo ve la suya
            datos['cotizaciones'] = [cotizacion_a_dict(c) for c in s.cotizaciones
                                     if str(c.proveedor_id) == g.claims.get('proveedor_id')]
    return datos


def _agregar_necesidades(solicitud, comercio, necesidades):
    for n in necesidades:
        existente = NecesidadSolicitud.query.filter_by(solicitud_id=solicitud.id, comercio_id=comercio.id,
                                                       producto_id=n.producto_id).first()
        if existente:
            existente.cantidad = n.cantidad
        else:
            if not db.session.execute(text('SELECT 1 FROM productos_maestros WHERE id = :p AND activo'),
                                      {'p': n.producto_id}).first():
                raise ErrorApi(422, 'producto_inexistente', f'El producto {n.producto_id} no existe.')
            db.session.add(NecesidadSolicitud(solicitud_id=solicitud.id, comercio_id=comercio.id,
                                              producto_id=n.producto_id, cantidad=n.cantidad))


def _vigente_y_abierta(solicitud):
    if solicitud.estado != 'ABIERTA':
        raise ErrorApi(409, 'solicitud_no_abierta', f'La solicitud está {solicitud.estado}.')
    if solicitud.fecha_limite < datetime.now():
        raise ErrorApi(409, 'solicitud_vencida', 'Ya pasó la fecha límite de la solicitud.')


# ---------------------------------------------------------------- solicitudes

@srv.ruta('/solicitudes', 'POST', resumen='Solicitar cotización', etiqueta='Solicitudes',
          permisos=['abastecimiento.solicitar'], cuerpo=SolicitudEntrada, status=201, raiz_xml='solicitud',
          entrada_xml='solicitud_entrada',
          ejemplo_entrada={'comercio_id': '3122a5b1-...', 'titulo': 'Abarrotes de la semana', 'consolidada': True,
                           'necesidades': [{'producto_id': 1, 'cantidad': 40}, {'producto_id': 3, 'cantidad': 24}]})
def crear(datos):
    """Se avisa a los proveedores verificados que entregan en la zona del comercio."""
    comercio = _mi_comercio(datos.comercio_id)
    limite = datos.fecha_limite.replace(tzinfo=None) if datos.fecha_limite else \
        datetime.now() + timedelta(days=int(parametro('COTIZACION_DIAS_LIMITE')))
    if limite <= datetime.now():
        raise ErrorApi(422, 'fecha_invalida', 'La fecha límite debe ser futura.')
    solicitud = SolicitudCotizacion(zona_id=comercio.zona_id, creada_por=UUID(g.claims['sub']), titulo=datos.titulo,
                                    consolidada=datos.consolidada, fecha_limite=limite, notas=datos.notas)
    db.session.add(solicitud)
    db.session.flush()
    _agregar_necesidades(solicitud, comercio, datos.necesidades)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'SolicitudCotizacion', solicitud.id,
                     f'Solicitud {solicitud.folio_legible}: {datos.titulo}',
                     datos_nuevos={'consolidada': datos.consolidada, 'productos': len(datos.necesidades)})
    db.session.commit()
    proveedores = [p.usuario_id for p in Proveedor.query.join(proveedor_zonas).filter(
        proveedor_zonas.c.zona_id == comercio.zona_id, Proveedor.activo.is_(True),
        Proveedor.estado_verificacion == 'VERIFICADO')]
    notificar(proveedores, 'cotizacion', f'Nueva solicitud de cotización en {comercio.zona.nombre}',
              f'{datos.titulo}: {len(datos.necesidades)} producto(s), cierra el {limite:%d/%m/%Y %H:%M}.',
              entidad={'tipo': 'solicitud', 'id': str(solicitud.id)}, origen='abastecimiento')
    return solicitud_a_dict(solicitud)


@srv.ruta('/solicitudes/<uuid:id>/necesidades', 'POST', resumen='Sumar mis necesidades (consolidada)',
          etiqueta='Solicitudes', permisos=['abastecimiento.solicitar'], cuerpo=NecesidadesEntrada,
          raiz_xml='solicitud', entrada_xml='necesidades_entrada',
          ejemplo_entrada={'comercio_id': '5c0e...', 'necesidades': [{'producto_id': 1, 'cantidad': 20}]})
def sumar(id, datos):
    """Sólo en solicitudes consolidadas, abiertas y de la misma zona del comercio. Si el comercio ya había pedido el
    producto, se reemplaza su cantidad."""
    solicitud = db.session.get(SolicitudCotizacion, id)
    if not solicitud:
        raise no_encontrado('La solicitud')
    comercio = _mi_comercio(datos.comercio_id)
    _vigente_y_abierta(solicitud)
    if not solicitud.consolidada and str(solicitud.creada_por) != g.claims['sub']:
        raise ErrorApi(409, 'no_consolidada', 'La solicitud no acepta necesidades de otros comercios.')
    if comercio.zona_id != solicitud.zona_id:
        raise ErrorApi(409, 'otra_zona', 'Tu comercio está en otra zona.')
    if solicitud.cotizaciones:
        raise ErrorApi(409, 'ya_cotizada', 'Ya hay cotizaciones; no se pueden cambiar las necesidades.')
    _agregar_necesidades(solicitud, comercio, datos.necesidades)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'SolicitudCotizacion', solicitud.id,
                     f'{comercio.nombre_comercio} se suma a {solicitud.folio_legible}',
                     datos_nuevos={'productos': len(datos.necesidades)})
    db.session.commit()
    db.session.refresh(solicitud)
    return solicitud_a_dict(solicitud)


@srv.ruta('/solicitudes', 'GET', resumen='Solicitudes que me corresponden', etiqueta='Solicitudes',
          permisos=['abastecimiento.solicitar', 'abastecimiento.cotizar', 'pedidos.ver_todos'],
          consulta=SolicitudesConsulta, raiz_xml='solicitudes')
def listar(q):
    """Comerciante: las suyas, aquellas en que participa y las consolidadas abiertas de su zona. Proveedor: las de
    las zonas donde entrega."""
    consulta = SolicitudCotizacion.query
    if tiene('pedidos.ver_todos'):
        pass
    elif tiene('abastecimiento.cotizar'):
        empresa = _mi_empresa()
        consulta = consulta.filter(SolicitudCotizacion.zona_id.in_(
            db.session.query(proveedor_zonas.c.zona_id).filter(proveedor_zonas.c.proveedor_id == empresa.id)))
    else:
        mios = mis_comercios_ids()
        zonas = {c.zona_id for c in Comercio.query.filter(Comercio.id.in_(mios)).all() if c.zona_id}
        consulta = consulta.filter(or_(
            SolicitudCotizacion.creada_por == UUID(g.claims['sub']),
            SolicitudCotizacion.id.in_(db.session.query(NecesidadSolicitud.solicitud_id)
                                       .filter(NecesidadSolicitud.comercio_id.in_(mios))),
            (SolicitudCotizacion.consolidada.is_(True)) & (SolicitudCotizacion.estado == 'ABIERTA')
            & SolicitudCotizacion.zona_id.in_(zonas)))
    if q.estado:
        consulta = consulta.filter(SolicitudCotizacion.estado == q.estado)
    resultado = paginar(consulta.order_by(SolicitudCotizacion.created_at.desc()), q.pagina, q.por_pagina,
                        lambda s: solicitud_a_dict(s, con_cotizaciones=False))
    resultado['solicitudes'] = resultado.pop('items')
    return resultado


@srv.ruta('/solicitudes/<uuid:id>', 'GET', resumen='Solicitud con necesidades consolidadas', etiqueta='Solicitudes',
          permisos=['abastecimiento.solicitar', 'abastecimiento.cotizar', 'pedidos.ver_todos'], raiz_xml='solicitud')
def detalle(id):
    return solicitud_a_dict(_solicitud(id))


@srv.ruta('/solicitudes/<uuid:id>/cancelacion', 'POST', resumen='Cancelar la solicitud', etiqueta='Solicitudes',
          permisos=['abastecimiento.solicitar'], raiz_xml='solicitud')
def cancelar(id):
    solicitud = _solicitud(id)
    if str(solicitud.creada_por) != g.claims['sub']:
        raise prohibido('Sólo quien creó la solicitud la cancela.')
    if solicitud.estado in ('ADJUDICADA', 'CANCELADA'):
        raise ErrorApi(409, 'solicitud_cerrada', f'La solicitud ya está {solicitud.estado}.')
    anterior, solicitud.estado = solicitud.estado, 'CANCELADA'
    registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'SolicitudCotizacion', solicitud.id, 'Solicitud cancelada',
                     datos_anteriores={'estado': anterior}, datos_nuevos={'estado': 'CANCELADA'})
    db.session.commit()
    return solicitud_a_dict(solicitud)


# ---------------------------------------------------------------- cotizaciones

@srv.ruta('/solicitudes/<uuid:id>/cotizaciones', 'POST', resumen='Cotizar (proveedor)', etiqueta='Cotizaciones',
          permisos=['abastecimiento.cotizar'], cuerpo=CotizacionEntrada, status=201, raiz_xml='cotizacion',
          entrada_xml='cotizacion_entrada',
          ejemplo_entrada={'tiempo_entrega_dias': 1, 'vigencia': '2026-11-30', 'notas': 'Precio por volumen',
                           'partidas': [{'producto_id': 1, 'precio_unitario': 24.5, 'cantidad_disponible': 100}]})
def cotizar(id, datos):
    """Una cotización por proveedor y solicitud; sólo de productos solicitados y si entrega en la zona."""
    solicitud = _solicitud(id)
    empresa = _mi_empresa()
    _vigente_y_abierta(solicitud)
    if empresa.estado_verificacion != 'VERIFICADO':
        raise ErrorApi(409, 'proveedor_no_verificado', 'Tu empresa aún no está verificada.')
    if not entrega_en_zona(empresa.id, solicitud.zona_id):
        raise ErrorApi(409, 'fuera_de_zona', 'No entregas en la zona de la solicitud.')
    if Cotizacion.query.filter_by(solicitud_id=solicitud.id, proveedor_id=empresa.id).first():
        raise ErrorApi(409, 'cotizacion_duplicada', 'Ya cotizaste esta solicitud.')
    if datos.vigencia < date.today():
        raise ErrorApi(422, 'vigencia_invalida', 'La vigencia no puede ser pasada.')
    pedidos = set(consolidado(solicitud))
    ajenos = [p.producto_id for p in datos.partidas if p.producto_id not in pedidos]
    if ajenos:
        raise ErrorApi(422, 'producto_no_solicitado', f'Productos que no están en la solicitud: {ajenos}.')
    cotizacion = Cotizacion(solicitud_id=solicitud.id, proveedor_id=empresa.id, tiempo_entrega_dias=datos.tiempo_entrega_dias,
                            vigencia=datos.vigencia, notas=datos.notas, usuario_id=UUID(g.claims['sub']))
    db.session.add(cotizacion)
    db.session.flush()
    for p in datos.partidas:
        db.session.add(PartidaCotizacion(cotizacion_id=cotizacion.id, **p.model_dump()))
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'Cotizacion', cotizacion.id,
                     f'{empresa.nombre_empresa} cotiza {solicitud.folio_legible}',
                     datos_nuevos={'partidas': len(datos.partidas), 'tiempo_entrega_dias': datos.tiempo_entrega_dias})
    db.session.commit()
    db.session.refresh(cotizacion)
    participantes = {solicitud.creada_por} | {n.comercio.usuario_id for n in solicitud.necesidades}
    notificar(participantes, 'cotizacion', f'Nueva cotización para {solicitud.titulo}',
              f'{empresa.nombre_empresa} cotizó {len(datos.partidas)} producto(s).',
              entidad={'tipo': 'solicitud', 'id': str(solicitud.id)}, origen='abastecimiento')
    return cotizacion_a_dict(cotizacion)


def comparar(solicitud):
    necesidades = consolidado(solicitud)
    renglones, mejores = [], {pid: None for pid in necesidades}
    for c in solicitud.cotizaciones:
        precios = {p.producto_id: p for p in c.partidas}
        cubiertos = [pid for pid, (_, cantidad, _) in necesidades.items()
                     if pid in precios and precios[pid].cantidad_disponible >= cantidad]
        total = sum((precios[pid].precio_unitario * necesidades[pid][1] for pid in cubiertos), Decimal(0))
        calificacion = db.session.execute(text('SELECT avg(calificacion) FROM evaluaciones_proveedor '
                                               'WHERE proveedor_id = :p'), {'p': c.proveedor_id}).scalar()
        renglones.append({'cotizacion_id': str(c.id), 'proveedor': c.proveedor.nombre_empresa,
                          'tiempo_entrega_dias': c.tiempo_entrega_dias, 'total': total.quantize(DOS),
                          'productos_cubiertos': len(cubiertos), 'productos_solicitados': len(necesidades),
                          'cobertura_pct': round(len(cubiertos) * 100 / len(necesidades), 1) if necesidades else 0,
                          'pedido_minimo': c.proveedor.pedido_minimo, 'cumple_minimo': total >= c.proveedor.pedido_minimo,
                          'vigente': c.vigencia >= date.today(),
                          'calificacion': round(float(calificacion), 2) if calificacion else None, 'recomendada': False})
        for pid, partida in precios.items():
            if pid in mejores and (mejores[pid] is None or partida.precio_unitario < mejores[pid][1].precio_unitario):
                mejores[pid] = (c, partida)
    elegibles = [r for r in renglones if r['vigente'] and r['cumple_minimo'] and r['productos_cubiertos']]
    if elegibles:
        min(elegibles, key=lambda r: (-r['productos_cubiertos'], r['total'], r['tiempo_entrega_dias']))['recomendada'] = True
    renglones.sort(key=lambda r: (not r['recomendada'], -r['productos_cubiertos'], r['total']))
    return renglones, [{'producto_id': pid, 'producto': necesidades[pid][0].nombre, 'cantidad': necesidades[pid][1],
                        'proveedor': m[0].proveedor.nombre_empresa if m else None,
                        'precio_unitario': m[1].precio_unitario if m else None,
                        'cotizaciones': sum(1 for c in solicitud.cotizaciones if any(p.producto_id == pid for p in c.partidas))}
                       for pid, m in mejores.items()]


@srv.ruta('/solicitudes/<uuid:id>/comparacion', 'GET', resumen='Comparar las cotizaciones', etiqueta='Cotizaciones',
          permisos=['abastecimiento.solicitar', 'pedidos.ver_todos'], raiz_xml='comparacion')
def comparacion(id):
    solicitud = _solicitud(id)
    if not (es_participante(solicitud) or tiene('pedidos.ver_todos')):
        raise prohibido('Sólo los participantes comparan las cotizaciones.')
    renglones, mejores = comparar(solicitud)
    return {'solicitud_id': str(solicitud.id),
            'criterio': 'Mayor número de productos cubiertos, luego menor total y menor tiempo de entrega; '
                        'sólo cotizaciones vigentes que cumplen el pedido mínimo del proveedor.',
            'cotizaciones': renglones, 'mejores_precios': mejores}


def orden_a_dict(o):
    return {'id': str(o.id), 'folio': o.folio_legible, 'solicitud_id': str(o.solicitud_id),
            'comercio_id': str(o.comercio_id), 'comercio': o.comercio.nombre_comercio,
            'proveedor_id': str(o.proveedor_id), 'proveedor': o.proveedor.nombre_empresa, 'total': o.total,
            'estado': o.estado, 'pedido_id': str(o.pedido_id) if o.pedido_id else None, 'fecha': o.created_at,
            'partidas': [{'producto_id': p.producto_id, 'producto': p.producto.nombre, 'cantidad': p.cantidad,
                          'precio_unitario': p.precio_unitario, 'subtotal': p.subtotal} for p in o.partidas]}


@srv.ruta('/solicitudes/<uuid:id>/adjudicacion', 'POST', resumen='Elegir proveedor y generar órdenes de compra',
          etiqueta='Órdenes de compra', permisos=['abastecimiento.solicitar'], cuerpo=AdjudicacionEntrada,
          status=201, raiz_xml='adjudicacion', entrada_xml='adjudicacion_entrada',
          ejemplo_entrada={'cotizacion_id': '7d2a...'})
def adjudicar(id, datos):
    """Sólo quien creó la solicitud. Genera una orden por comercio participante con los productos que la cotización
    cubre (a los precios cotizados) y descarta las demás cotizaciones."""
    with bloqueo(f'solicitud:{id}', ttl_segundos=30, mensaje='La solicitud se está adjudicando.'):
        solicitud = _solicitud(id)
        if str(solicitud.creada_por) != g.claims['sub']:
            raise prohibido('Sólo quien creó la solicitud la adjudica.')
        if solicitud.estado not in ('ABIERTA', 'CERRADA'):
            raise ErrorApi(409, 'solicitud_cerrada', f'La solicitud está {solicitud.estado}.')
        cotizacion = next((c for c in solicitud.cotizaciones if str(c.id) == datos.cotizacion_id), None)
        if not cotizacion:
            raise ErrorApi(422, 'cotizacion_ajena', 'Esa cotización no es de esta solicitud.')
        if cotizacion.vigencia < date.today():
            raise ErrorApi(409, 'cotizacion_vencida', 'La cotización ya no está vigente.')
        precios = {p.producto_id: p for p in cotizacion.partidas}
        por_comercio = {}
        for n in solicitud.necesidades:
            if n.producto_id in precios:
                por_comercio.setdefault(n.comercio_id, []).append(n)
        if not por_comercio:
            raise ErrorApi(409, 'sin_cobertura', 'La cotización no cubre ningún producto solicitado.')
        ordenes = []
        for comercio_id, necesidades in por_comercio.items():
            partidas = [(n.producto_id, n.cantidad, precios[n.producto_id].precio_unitario) for n in necesidades]
            orden = OrdenCompra(solicitud_id=solicitud.id, cotizacion_id=cotizacion.id, comercio_id=comercio_id,
                                proveedor_id=cotizacion.proveedor_id,
                                total=sum((c * p for _, c, p in partidas), Decimal(0)).quantize(DOS))
            db.session.add(orden)
            db.session.flush()
            for producto_id, cantidad, precio in partidas:
                db.session.add(PartidaOrden(orden_id=orden.id, producto_id=producto_id, cantidad=cantidad,
                                            precio_unitario=precio, subtotal=(cantidad * precio).quantize(DOS)))
            ordenes.append(orden)
        for c in solicitud.cotizaciones:
            c.estado = 'ADJUDICADA' if c.id == cotizacion.id else 'DESCARTADA'
        anterior, solicitud.estado = solicitud.estado, 'ADJUDICADA'
        registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'SolicitudCotizacion', solicitud.id,
                         f'{solicitud.folio_legible} adjudicada a {cotizacion.proveedor.nombre_empresa}',
                         datos_anteriores={'estado': anterior},
                         datos_nuevos={'estado': 'ADJUDICADA', 'cotizacion_id': str(cotizacion.id),
                                       'ordenes': len(ordenes)})
        db.session.commit()
    for orden in ordenes:
        db.session.refresh(orden)
        notificar(orden.comercio.usuario_id, 'cotizacion', f'Orden de compra {orden.folio_legible} generada',
                  f'{cotizacion.proveedor.nombre_empresa}: ${orden.total}. Conviértela en pedido para enviarla.',
                  entidad={'tipo': 'orden', 'id': str(orden.id)}, origen='abastecimiento')
    notificar(cotizacion.proveedor.usuario_id, 'cotizacion', f'Ganaste la cotización {solicitud.folio_legible}',
              f'{len(ordenes)} orden(es) de compra por ${sum(o.total for o in ordenes)}.',
              entidad={'tipo': 'solicitud', 'id': str(solicitud.id)}, origen='abastecimiento')
    return {'solicitud': solicitud_a_dict(solicitud), 'ordenes': [orden_a_dict(o) for o in ordenes]}


# ---------------------------------------------------------------- órdenes de compra

@srv.ruta('/ordenes', 'GET', resumen='Mis órdenes de compra', etiqueta='Órdenes de compra',
          permisos=['abastecimiento.solicitar', 'abastecimiento.cotizar', 'pedidos.ver_todos'],
          consulta=OrdenesConsulta, raiz_xml='ordenes')
def ordenes(q):
    consulta = OrdenCompra.query
    if tiene('pedidos.ver_todos'):
        pass
    elif tiene('abastecimiento.cotizar'):
        consulta = consulta.filter(OrdenCompra.proveedor_id == _mi_empresa().id)
    else:
        consulta = consulta.filter(OrdenCompra.comercio_id.in_(mis_comercios_ids()))
    if q.comercio_id:
        consulta = consulta.filter(OrdenCompra.comercio_id == _uuid(q.comercio_id, 'comercio_id'))
    if q.estado:
        consulta = consulta.filter(OrdenCompra.estado == q.estado)
    lista = consulta.order_by(OrdenCompra.created_at.desc()).limit(200).all()
    return {'total': len(lista), 'ordenes': [orden_a_dict(o) for o in lista]}


@srv.ruta('/ordenes/<uuid:id>', 'GET', resumen='Una orden de compra', etiqueta='Órdenes de compra',
          permisos=['abastecimiento.solicitar', 'abastecimiento.cotizar', 'pedidos.ver_todos'], raiz_xml='orden')
def orden(id):
    o = db.session.get(OrdenCompra, id)
    if not o:
        raise no_encontrado('La orden')
    if not (o.comercio_id in mis_comercios_ids() or str(o.proveedor_id) == g.claims.get('proveedor_id')
            or tiene('pedidos.ver_todos')):
        raise prohibido('La orden no es tuya.')
    return orden_a_dict(o)


@srv.ruta('/ordenes/<uuid:id>/pedido', 'POST', resumen='Convertir la orden en pedido (ms-pedidos)',
          etiqueta='Órdenes de compra', permisos=['abastecimiento.solicitar'], raiz_xml='orden')
def convertir(id):
    """Crea el pedido (borrador) en ms-pedidos con el token del comerciante; ms-pedidos aplica sus reglas (cobertura,
    venta mínima). El pedido usa el precio del catálogo del proveedor; el precio cotizado queda en las notas."""
    with bloqueo(f'orden:{id}', ttl_segundos=30, mensaje='La orden se está convirtiendo.'):
        o = db.session.get(OrdenCompra, id)
        if not o:
            raise no_encontrado('La orden')
        if o.comercio_id not in mis_comercios_ids():
            raise prohibido('Sólo el comercio de la orden la convierte en pedido.')
        if o.estado != 'GENERADA':
            raise ErrorApi(409, 'orden_convertida', f'La orden está {o.estado}' +
                           (f' (pedido {o.pedido_id}).' if o.pedido_id else '.'))
        cuerpo = {'comercio_id': str(o.comercio_id), 'proveedor_id': str(o.proveedor_id),
                  'partidas': [{'producto_id': p.producto_id, 'cantidad': str(p.cantidad)} for p in o.partidas],
                  'notas': (f'Orden {o.folio_legible} (cotización {o.solicitud.folio_legible}). Precios cotizados: ' +
                            ', '.join(f'{p.producto.nombre} ${p.precio_unitario}' for p in o.partidas))[:500]}
        db.session.rollback()
        respuesta = llamar('pedidos', 'POST', '/api/v1/pedidos', token=g.token, json=cuerpo)
        if respuesta.status_code != 201:
            try:
                error = respuesta.json().get('error', {})
            except ValueError:
                error = {}
            raise ErrorApi(409 if respuesta.status_code < 500 else 503, 'pedido_rechazado',
                           f"ms-pedidos: {error.get('mensaje') or respuesta.status_code}")
        pedido = respuesta.json()
        o = db.session.get(OrdenCompra, id)
        o.estado, o.pedido_id = 'CONVERTIDA', UUID(pedido['id'])
        registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'OrdenCompra', o.id,
                         f'Orden {o.folio_legible} convertida en el pedido {pedido.get("folio")}',
                         datos_anteriores={'estado': 'GENERADA'}, datos_nuevos={'estado': 'CONVERTIDA',
                                                                                 'pedido_id': pedido['id']})
        db.session.commit()
    return orden_a_dict(o)


# ---------------------------------------------------------------- sugerencia de reabastecimiento

@srv.ruta('/comercios/<uuid:comercio_id>/sugerencia-reabastecimiento', 'GET',
          resumen='Qué pedir y a quién (faltantes + mejores ofertas)', etiqueta='Reabastecimiento',
          permisos=['abastecimiento.solicitar'], raiz_xml='sugerencia')
def sugerencia(comercio_id):
    """Para cada producto en BAJO o AGOTADO: la cantidad para llegar al máximo (o al doble del mínimo) y el proveedor
    verificado más barato que entrega en la zona con existencia suficiente. Se agrupa por proveedor para ver si se
    alcanza su pedido mínimo."""
    comercio = _mi_comercio(comercio_id)
    renglones = (InventarioComercio.query.filter_by(comercio_id=comercio.id, activo=True)
                 .filter(InventarioComercio.estado.in_(('BAJO', 'AGOTADO'))).all())
    productos, grupos = [], {}
    for r in renglones:
        cantidad = r.cantidad_sugerida
        oferta = db.session.execute(text(
            'SELECT pr.id, pr.nombre_empresa, pr.pedido_minimo, pr.tiempo_entrega_dias, cp.precio_mayoreo '
            'FROM catalogo_proveedor cp JOIN proveedores pr ON pr.id = cp.proveedor_id '
            'JOIN proveedor_zonas pz ON pz.proveedor_id = pr.id AND pz.zona_id = :z '
            "WHERE cp.producto_id = :p AND cp.activo AND pr.activo AND pr.estado_verificacion = 'VERIFICADO' "
            'AND cp.existencia_disponible >= :c AND cp.cantidad_minima <= :c ORDER BY cp.precio_mayoreo LIMIT 1'),
            {'z': comercio.zona_id, 'p': r.producto_id, 'c': max(cantidad, Decimal(1))}).first()
        subtotal = (oferta.precio_mayoreo * cantidad).quantize(DOS) if oferta else None
        productos.append({'inventario_id': r.id, 'producto_id': r.producto_id, 'producto': r.producto.nombre,
                          'existencia': r.existencia, 'stock_minimo': r.stock_minimo, 'cantidad_sugerida': cantidad,
                          'proveedor_id': str(oferta.id) if oferta else None,
                          'proveedor': oferta.nombre_empresa if oferta else None,
                          'precio_mayoreo': oferta.precio_mayoreo if oferta else None, 'subtotal': subtotal})
        if oferta:
            grupo = grupos.setdefault(oferta.id, {'proveedor_id': str(oferta.id), 'proveedor': oferta.nombre_empresa,
                                                  'productos': 0, 'total': Decimal(0),
                                                  'pedido_minimo': oferta.pedido_minimo,
                                                  'tiempo_entrega_dias': oferta.tiempo_entrega_dias})
            grupo['productos'] += 1
            grupo['total'] += subtotal
    por_proveedor = [{**g_, 'cumple_minimo': g_['total'] >= g_['pedido_minimo']} for g_ in grupos.values()]
    por_proveedor.sort(key=lambda x: -x['total'])
    return {'comercio_id': str(comercio.id), 'productos': productos, 'por_proveedor': por_proveedor}

