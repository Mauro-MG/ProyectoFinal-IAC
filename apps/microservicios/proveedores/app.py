"""
ms-proveedores: registro, verificación y administración de proveedores mayoristas.

Es DUEÑO de: proveedores, proveedor_zonas, catalogo_proveedor, precios_mayoreo y
evaluaciones_proveedor (ningún otro servicio escribe en ellas).

- Registro de la empresa, verificación por el coordinador municipal o el administrador.
- Zonas de servicio, condiciones comerciales, tiempos de entrega y capacidad de surtido.
- Catálogo mayorista del proveedor (antes en ms-catalogo) y "¿quién me vende este producto?".
- Evaluación del proveedor por los comercios después de cada pedido entregado.

Redis: la caché del catálogo maestro vive en ms-catalogo; aquí se invalida la de análisis
(`analisis:version`) cuando cambia la oferta mayorista, porque cambia la cobertura.
Integración: avisa al proveedor (ms-notificaciones) cuando cambia su verificación.
"""
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from flask import g
from sqlalchemy import func, text

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene, usuario_actual
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import (CatalogoProveedor, Comercio, EvaluacionProveedor, PedidoAbasto, PrecioMayoreo,
                                    ProductoMaestro, Proveedor, ZonaMunicipal, proveedor_zonas)
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.notificaciones import notificar
from abasto_dominio.servicios.precios import ofertas_producto

from esquemas import (CONTRATOS_XML, CondicionesEntrada, EvaluacionEntrada, OfertaCambio, OfertaEntrada,
                      OfertasConsulta, PaginaConsulta, ProveedorEntrada, ProveedoresConsulta, SalidaEntrada,
                      VerificacionEntrada, ZonasEntrada)

srv = Servicio('proveedores', 'Proveedores',
               'Registro, verificación y administración de proveedores mayoristas: zonas de servicio, condiciones '
               'comerciales, tiempos de entrega, capacidad de surtido, catálogo mayorista y evaluación por los '
               'comercios.',
               xsd=Path(__file__).parent / 'xsd' / 'proveedores.xsd', contratos=CONTRATOS_XML)
app = srv.app

EN_PROCESO = ('ENVIADO', 'ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO')


def _uuid(valor, campo):
    try:
        return UUID(str(valor))
    except ValueError:
        raise ErrorApi(400, 'parametro_invalido', f'{campo} debe ser un UUID.')


def resumen_evaluacion(proveedor_id):
    fila = (db.session.query(func.avg(EvaluacionProveedor.calificacion), func.avg(EvaluacionProveedor.puntualidad),
                             func.avg(EvaluacionProveedor.calidad), func.count(EvaluacionProveedor.id))
            .filter(EvaluacionProveedor.proveedor_id == proveedor_id).one())
    redondear = lambda v: round(float(v), 2) if v is not None else None  # noqa: E731
    return {'promedio': redondear(fila[0]), 'puntualidad': redondear(fila[1]), 'calidad': redondear(fila[2]),
            'total': fila[3]}


def proveedor_a_dict(p, detalle=False):
    datos = {'id': str(p.id), 'nombre_empresa': p.nombre_empresa, 'municipio': p.municipio,
             'pedido_minimo': p.pedido_minimo, 'tiempo_entrega_dias': p.tiempo_entrega_dias,
             'condiciones_venta': p.condiciones_venta, 'plan': p.plan, 'estado_verificacion': p.estado_verificacion,
             'capacidad_pedidos_dia': p.capacidad_pedidos_dia, 'monto_maximo_pedido': p.monto_maximo_pedido,
             'dias_entrega': p.dias_entrega, 'zonas': [{'id': z.id, 'nombre': z.nombre} for z in p.zonas],
             'evaluacion': resumen_evaluacion(p.id)}
    if detalle:
        datos.update({'descripcion': p.descripcion, 'rfc': p.rfc, 'telefono_contacto': p.telefono_contacto,
                      'email_contacto': p.email_contacto, 'direccion': p.direccion,
                      'fecha_verificacion': p.fecha_verificacion})
    return datos


def oferta_a_dict(o):
    return {'id': o.id, 'proveedor_id': str(o.proveedor_id), 'proveedor': o.proveedor.nombre_empresa,
            'producto_id': o.producto_id, 'producto': o.producto.nombre, 'unidad_medida': o.producto.unidad_medida,
            'precio_mayoreo': o.precio_mayoreo, 'cantidad_minima': o.cantidad_minima,
            'existencia_disponible': o.existencia_disponible, 'actualizado': o.updated_at}


def _proveedor(id, editar=False):
    proveedor = db.session.get(Proveedor, id)
    if not proveedor or not proveedor.activo:
        raise no_encontrado('El proveedor')
    if editar and str(proveedor.id) != g.claims.get('proveedor_id') and not tiene('catalogos.gestionar'):
        raise prohibido('Sólo el propio proveedor o el administrador pueden cambiar estos datos.')
    return proveedor


def _mi_proveedor():
    empresa_id = g.claims.get('proveedor_id')
    proveedor = db.session.get(Proveedor, UUID(empresa_id)) if empresa_id else None
    if not proveedor:
        raise ErrorApi(409, 'sin_empresa', 'Tu cuenta aún no tiene datos de empresa proveedora.')
    return proveedor


# ---------------------------------------------------------------- proveedores

@srv.ruta('/proveedores', 'GET', resumen='Buscar y evaluar proveedores', etiqueta='Proveedores',
          permisos=['proveedores.consultar', 'proveedor.catalogo', 'proveedores.verificar'],
          consulta=ProveedoresConsulta, raiz_xml='proveedores')
def listar(q):
    """Filtra por zona de servicio, producto ofrecido, texto y estado de verificación. Los comercios sólo ven
    proveedores VERIFICADOS; el coordinador y el administrador ven todos. `orden=calificacion` ordena por la
    evaluación promedio que dejaron los comercios."""
    consulta = Proveedor.query.filter(Proveedor.activo.is_(True))
    if not (tiene('proveedores.verificar') or tiene('catalogos.gestionar')):
        consulta = consulta.filter(Proveedor.estado_verificacion == 'VERIFICADO')
    elif q.estado_verificacion:
        consulta = consulta.filter(Proveedor.estado_verificacion == q.estado_verificacion)
    if q.zona_id:
        consulta = consulta.join(proveedor_zonas).filter(proveedor_zonas.c.zona_id == q.zona_id)
    if q.producto_id:
        consulta = consulta.filter(Proveedor.id.in_(
            db.session.query(CatalogoProveedor.proveedor_id).filter_by(producto_id=q.producto_id, activo=True)))
    if q.texto:
        consulta = consulta.filter(Proveedor.nombre_empresa.ilike(f'%{q.texto}%'))
    if q.orden == 'calificacion':
        promedio = (db.session.query(EvaluacionProveedor.proveedor_id,
                                     func.avg(EvaluacionProveedor.calificacion).label('prom'))
                    .group_by(EvaluacionProveedor.proveedor_id).subquery())
        consulta = consulta.outerjoin(promedio, promedio.c.proveedor_id == Proveedor.id).order_by(
            promedio.c.prom.desc().nulls_last(), Proveedor.nombre_empresa)
    elif q.orden == 'tiempo_entrega':
        consulta = consulta.order_by(Proveedor.tiempo_entrega_dias, Proveedor.nombre_empresa)
    else:
        consulta = consulta.order_by(Proveedor.nombre_empresa)
    resultado = paginar(consulta, q.pagina, q.por_pagina, proveedor_a_dict)
    resultado['proveedores'] = resultado.pop('items')
    return resultado


@srv.ruta('/proveedores/<uuid:id>', 'GET', resumen='Proveedor con su catálogo mayorista', etiqueta='Proveedores',
          permisos=['proveedores.consultar', 'proveedor.catalogo', 'proveedores.verificar'], raiz_xml='proveedor')
def detalle(id):
    proveedor = _proveedor(id)
    ofertas = (CatalogoProveedor.query.filter_by(proveedor_id=id, activo=True)
               .join(ProductoMaestro).order_by(ProductoMaestro.nombre).all())
    return {**proveedor_a_dict(proveedor, detalle=True), 'ofertas': [oferta_a_dict(o) for o in ofertas]}


@srv.ruta('/proveedores', 'POST', resumen='Registrar mi empresa proveedora', etiqueta='Proveedores',
          permisos=['proveedor.catalogo'], cuerpo=ProveedorEntrada, status=201, raiz_xml='proveedor',
          entrada_xml='proveedor_entrada',
          ejemplo_entrada={'nombre_empresa': 'Abarrotes Mayoristas del Norte', 'rfc': 'AMN010101AB1',
                           'municipio': 'Apodaca', 'pedido_minimo': 1500, 'tiempo_entrega_dias': 2,
                           'condiciones_venta': 'Contado o crédito a 15 días'})
def registrar(datos):
    """El usuario con rol Proveedor registra su empresa; queda PENDIENTE de verificación y no aparece en las
    búsquedas de los comercios hasta que la verifique el coordinador municipal."""
    usuario = usuario_actual()
    if usuario.proveedor:
        raise ErrorApi(409, 'empresa_existente', 'Tu cuenta ya tiene una empresa registrada.')
    if datos.rfc and Proveedor.query.filter_by(rfc=datos.rfc).first():
        raise ErrorApi(409, 'rfc_duplicado', 'Ya hay un proveedor registrado con ese RFC.')
    proveedor = Proveedor(usuario_id=usuario.id, estado_verificacion='PENDIENTE', **datos.model_dump())
    db.session.add(proveedor)
    db.session.flush()
    registrar_evento(usuario.id, 'CREACION', 'Proveedor', proveedor.id,
                     f'Registro del proveedor {proveedor.nombre_empresa}', datos_nuevos=datos.model_dump())
    db.session.commit()
    return proveedor_a_dict(proveedor, detalle=True)


@srv.ruta('/proveedores/<uuid:id>', 'PATCH', resumen='Condiciones comerciales y capacidad de surtido',
          etiqueta='Proveedores', permisos=['proveedor.catalogo', 'catalogos.gestionar'], cuerpo=CondicionesEntrada,
          raiz_xml='proveedor', entrada_xml='condiciones_entrada',
          ejemplo_entrada={'pedido_minimo': 1200, 'tiempo_entrega_dias': 1, 'capacidad_pedidos_dia': 30,
                           'dias_entrega': ['LUN', 'MIE', 'VIE']})
def cambiar_condiciones(id, datos):
    proveedor = _proveedor(id, editar=True)
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise ErrorApi(422, 'sin_cambios', 'Indica al menos un campo a cambiar.')
    antes = {k: getattr(proveedor, k) for k in cambios}
    for campo, valor in cambios.items():
        setattr(proveedor, campo, valor)
    proveedor.updated_at = datetime.now()
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Proveedor', proveedor.id,
                     f'Condiciones de {proveedor.nombre_empresa}', datos_anteriores=antes, datos_nuevos=cambios)
    db.session.commit()
    invalidar_analisis()
    return proveedor_a_dict(proveedor, detalle=True)


@srv.ruta('/proveedores/<uuid:id>/zonas', 'PUT', resumen='Zonas de servicio', etiqueta='Proveedores',
          permisos=['proveedor.catalogo', 'catalogos.gestionar'], cuerpo=ZonasEntrada, raiz_xml='proveedor',
          entrada_xml='zonas_entrada', ejemplo_entrada={'zonas': [1, 2, 5]})
def cambiar_zonas(id, datos):
    """Reemplaza las zonas donde entrega. Afecta la validación de cobertura de los pedidos (RN-011)."""
    proveedor = _proveedor(id, editar=True)
    zonas = ZonaMunicipal.query.filter(ZonaMunicipal.id.in_(datos.zonas), ZonaMunicipal.activa.is_(True)).all()
    faltantes = sorted(set(datos.zonas) - {z.id for z in zonas})
    if faltantes:
        raise ErrorApi(422, 'zona_inexistente', f'Zonas inexistentes o inactivas: {faltantes}.')
    antes = sorted(z.id for z in proveedor.zonas)
    proveedor.zonas = zonas
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Proveedor', proveedor.id,
                     f'Zonas de servicio de {proveedor.nombre_empresa}', datos_anteriores={'zonas': antes},
                     datos_nuevos={'zonas': sorted(datos.zonas)})
    db.session.commit()
    invalidar_analisis()
    return proveedor_a_dict(proveedor, detalle=True)


@srv.ruta('/proveedores/<uuid:id>/verificacion', 'PATCH', resumen='Verificar, rechazar o suspender',
          etiqueta='Verificación', permisos=['proveedores.verificar'], cuerpo=VerificacionEntrada,
          raiz_xml='proveedor', entrada_xml='verificacion_entrada',
          ejemplo_entrada={'estado': 'VERIFICADO', 'observaciones': 'RFC y domicilio comprobados'})
def verificar(id, datos):
    proveedor = _proveedor(id)
    if proveedor.estado_verificacion == datos.estado:
        raise ErrorApi(409, 'sin_cambio', f'El proveedor ya está {datos.estado}.')
    anterior = proveedor.estado_verificacion
    proveedor.estado_verificacion = datos.estado
    proveedor.verificado_por = UUID(g.claims['sub'])
    proveedor.fecha_verificacion = datetime.now()
    registrar_evento(UUID(g.claims['sub']), 'CAMBIO_ESTADO', 'Proveedor', proveedor.id,
                     f'Verificación de {proveedor.nombre_empresa}: {anterior} -> {datos.estado}',
                     datos_anteriores={'estado_verificacion': anterior},
                     datos_nuevos={'estado_verificacion': datos.estado, 'observaciones': datos.observaciones})
    db.session.commit()
    notificar([proveedor.usuario_id], 'proveedor', f'Tu empresa quedó {datos.estado.lower()}',
              datos.observaciones or f'El estado de verificación de {proveedor.nombre_empresa} cambió a {datos.estado}.',
              entidad={'tipo': 'proveedor', 'id': str(proveedor.id)}, origen='proveedores')
    invalidar_analisis()
    return proveedor_a_dict(proveedor, detalle=True)


@srv.ruta('/proveedores/<uuid:id>/capacidad', 'GET', resumen='Capacidad de surtido de hoy', etiqueta='Proveedores',
          permisos=['proveedores.consultar', 'proveedor.catalogo', 'pedidos.atender'], raiz_xml='capacidad')
def capacidad(id):
    """Pedidos recibidos hoy contra la capacidad diaria declarada, y pedidos aún en proceso."""
    proveedor = _proveedor(id)
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    pedidos_hoy = PedidoAbasto.query.filter(PedidoAbasto.proveedor_id == id, PedidoAbasto.fecha_envio >= hoy).count()
    en_proceso = PedidoAbasto.query.filter(PedidoAbasto.proveedor_id == id,
                                           PedidoAbasto.estado.in_(EN_PROCESO)).count()
    tope = proveedor.capacidad_pedidos_dia
    return {'proveedor_id': str(id), 'capacidad_pedidos_dia': tope, 'pedidos_hoy': pedidos_hoy,
            'disponibles_hoy': max(tope - pedidos_hoy, 0) if tope else None, 'pedidos_en_proceso': en_proceso,
            'monto_maximo_pedido': proveedor.monto_maximo_pedido, 'dias_entrega': proveedor.dias_entrega,
            'tiempo_entrega_dias': proveedor.tiempo_entrega_dias}


# ---------------------------------------------------------------- evaluación

def evaluacion_a_dict(e):
    return {'id': e.id, 'pedido_id': str(e.pedido_id), 'comercio_id': str(e.comercio_id),
            'calificacion': e.calificacion, 'puntualidad': e.puntualidad, 'calidad': e.calidad,
            'comentario': e.comentario, 'fecha': e.created_at}


@srv.ruta('/proveedores/<uuid:id>/evaluaciones', 'POST', resumen='Evaluar al proveedor después de un pedido',
          etiqueta='Evaluación', permisos=['pedidos.crear'], cuerpo=EvaluacionEntrada, status=201,
          raiz_xml='evaluacion', entrada_xml='evaluacion_entrada',
          ejemplo_entrada={'pedido_id': '0b7c...', 'calificacion': 5, 'puntualidad': 4, 'calidad': 5,
                           'comentario': 'Llegó completo y a tiempo'})
def evaluar(id, datos):
    """Sólo el dueño del comercio, sólo pedidos ENTREGADOS de ese proveedor y una vez por pedido."""
    proveedor = _proveedor(id)
    usuario = usuario_actual()
    pedido = db.session.get(PedidoAbasto, _uuid(datos.pedido_id, 'pedido_id'))
    if not pedido or pedido.proveedor_id != proveedor.id:
        raise no_encontrado('El pedido de este proveedor')
    if pedido.comercio.usuario_id != usuario.id:
        raise prohibido('Sólo el comercio que hizo el pedido puede evaluarlo.')
    if pedido.estado != 'ENTREGADO':
        raise ErrorApi(409, 'pedido_no_entregado', 'Sólo se evalúan pedidos entregados.')
    if EvaluacionProveedor.query.filter_by(pedido_id=pedido.id).first():
        raise ErrorApi(409, 'evaluacion_duplicada', 'Ese pedido ya fue evaluado.')
    evaluacion = EvaluacionProveedor(proveedor_id=proveedor.id, pedido_id=pedido.id, comercio_id=pedido.comercio_id,
                                     usuario_id=usuario.id, **datos.model_dump(exclude={'pedido_id'}))
    db.session.add(evaluacion)
    db.session.flush()
    registrar_evento(usuario.id, 'CREACION', 'EvaluacionProveedor', evaluacion.id,
                     f'Evaluación de {proveedor.nombre_empresa} ({datos.calificacion}/5)', datos_nuevos=datos.model_dump())
    db.session.commit()
    return evaluacion_a_dict(evaluacion)


@srv.ruta('/proveedores/<uuid:id>/evaluaciones', 'GET', resumen='Evaluaciones del proveedor', etiqueta='Evaluación',
          permisos=['proveedores.consultar', 'proveedor.catalogo', 'proveedores.verificar'], consulta=PaginaConsulta,
          raiz_xml='evaluaciones')
def evaluaciones(id, q):
    _proveedor(id)
    consulta = EvaluacionProveedor.query.filter_by(proveedor_id=id).order_by(EvaluacionProveedor.created_at.desc())
    resultado = paginar(consulta, q.pagina, q.por_pagina, evaluacion_a_dict)
    return {'proveedor_id': str(id), 'resumen': resumen_evaluacion(id), 'paginacion': resultado['paginacion'],
            'evaluaciones': resultado['items']}


# ---------------------------------------------------------------- ofertas y catálogo mayorista

@srv.ruta('/ofertas', 'GET', resumen='¿Quién me vende este producto?', etiqueta='Catálogo mayorista',
          permisos=['proveedores.consultar'], consulta=OfertasConsulta, raiz_xml='ofertas')
def buscar_ofertas(q):
    """Ofertas de mayoreo del producto de proveedores verificados: primero quienes entregan en la zona y tienen
    existencia, luego por precio."""
    if not db.session.get(ProductoMaestro, q.producto_id):
        raise no_encontrado('El producto')
    ofertas = [o for o in ofertas_producto(q.producto_id, q.zona_id) if o.proveedor.estado_verificacion == 'VERIFICADO']
    return {'producto_id': q.producto_id, 'zona_id': q.zona_id, 'total': len(ofertas), 'ofertas': [
        {**oferta_a_dict(o), 'cubre_zona': o.cubre_zona, 'pedido_minimo': o.proveedor.pedido_minimo,
         'tiempo_entrega_dias': o.proveedor.tiempo_entrega_dias, 'condiciones_venta': o.proveedor.condiciones_venta,
         'plan': o.proveedor.plan} for o in ofertas]}


@srv.ruta('/mi-catalogo', 'GET', resumen='Mi catálogo mayorista', etiqueta='Catálogo mayorista',
          permisos=['proveedor.catalogo'], raiz_xml='ofertas')
def mi_catalogo():
    proveedor = _mi_proveedor()
    ofertas = (CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id, activo=True)
               .join(ProductoMaestro).order_by(ProductoMaestro.nombre).all())
    return {'proveedor_id': str(proveedor.id), 'total': len(ofertas), 'ofertas': [oferta_a_dict(o) for o in ofertas]}


@srv.ruta('/mi-catalogo', 'POST', resumen='Publicar producto a precio de mayoreo', etiqueta='Catálogo mayorista',
          permisos=['proveedor.catalogo'], cuerpo=OfertaEntrada, status=201, raiz_xml='oferta',
          entrada_xml='oferta_entrada',
          ejemplo_entrada={'producto_id': 19, 'precio_mayoreo': 21.5, 'cantidad_minima': 12, 'existencia_disponible': 300})
def publicar_oferta(datos):
    proveedor = _mi_proveedor()
    if not db.session.get(ProductoMaestro, datos.producto_id):
        raise ErrorApi(422, 'producto_inexistente', 'El producto no existe en el catálogo maestro.')
    oferta = CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id, producto_id=datos.producto_id).first()
    if oferta and oferta.activo:
        raise ErrorApi(409, 'oferta_duplicada', 'Ya ofreces ese producto; actualízalo con PATCH.')
    if not oferta:
        oferta = CatalogoProveedor(proveedor_id=proveedor.id, producto_id=datos.producto_id)
        db.session.add(oferta)
    oferta.activo = True
    oferta.precio_mayoreo, oferta.cantidad_minima = datos.precio_mayoreo, datos.cantidad_minima
    oferta.existencia_disponible = datos.existencia_disponible
    db.session.add(PrecioMayoreo(proveedor_id=proveedor.id, producto_id=datos.producto_id, precio=datos.precio_mayoreo))
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'CatalogoProveedor', oferta.id,
                     f'{proveedor.nombre_empresa} ofrece {oferta.producto.nombre}', datos_nuevos=datos.model_dump())
    db.session.commit()
    invalidar_analisis()
    return oferta_a_dict(oferta)


def _mi_oferta(id):
    oferta = db.session.get(CatalogoProveedor, id)
    if not oferta or not oferta.activo:
        raise no_encontrado('La oferta')
    if str(oferta.proveedor_id) != g.claims.get('proveedor_id') and not tiene('catalogos.gestionar'):
        raise prohibido('La oferta es de otro proveedor.')
    return oferta


@srv.ruta('/mi-catalogo/<int:id>', 'PATCH', resumen='Cambiar precio, mínimo o existencia',
          etiqueta='Catálogo mayorista', permisos=['proveedor.catalogo'], cuerpo=OfertaCambio, raiz_xml='oferta',
          entrada_xml='oferta_cambio', ejemplo_entrada={'precio_mayoreo': 20.9, 'existencia_disponible': 250})
def cambiar_oferta(id, datos):
    """Un cambio de precio se agrega al historial de precios de mayoreo."""
    oferta = _mi_oferta(id)
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise ErrorApi(422, 'sin_cambios', 'Indica al menos un campo a cambiar.')
    antes = {k: getattr(oferta, k) for k in cambios}
    if 'precio_mayoreo' in cambios and cambios['precio_mayoreo'] != oferta.precio_mayoreo:
        db.session.add(PrecioMayoreo(proveedor_id=oferta.proveedor_id, producto_id=oferta.producto_id,
                                     precio=cambios['precio_mayoreo']))
    for campo, valor in cambios.items():
        setattr(oferta, campo, valor)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'CatalogoProveedor', oferta.id,
                     f'Actualización de {oferta.producto.nombre}', datos_anteriores=antes, datos_nuevos=cambios)
    db.session.commit()
    invalidar_analisis()
    return oferta_a_dict(oferta)


@srv.ruta('/mi-catalogo/<int:id>', 'DELETE', resumen='Retirar producto de mi catálogo', etiqueta='Catálogo mayorista',
          permisos=['proveedor.catalogo'], raiz_xml='resultado')
def retirar_oferta(id):
    oferta = _mi_oferta(id)
    oferta.activo = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'CatalogoProveedor', oferta.id,
                     f'Se retiró {oferta.producto.nombre} del catálogo mayorista')
    db.session.commit()
    invalidar_analisis()
    return {'mensaje': 'Producto retirado del catálogo', 'id': str(oferta.id)}


@srv.ruta('/proveedores/<uuid:id>/salidas', 'POST', resumen='Descontar existencia del catálogo (uso de ms-pedidos)',
          etiqueta='Catálogo mayorista', permisos=['pedidos.atender', 'proveedor.catalogo'], cuerpo=SalidaEntrada,
          raiz_xml='salida', entrada_xml='salida_entrada',
          ejemplo_entrada={'referencia': 'pedido:0b7c...', 'partidas': [{'producto_id': 1, 'cantidad': 40}]})
def descontar(id, datos):
    """ms-pedidos la llama al despachar, con el token del proveedor u operador. Todas las partidas o ninguna (409 si no
    alcanza la existencia). Con la misma `referencia` responde lo que ya se había aplicado, sin descontar otra vez."""
    proveedor = _proveedor(id)
    if str(proveedor.id) != g.claims.get('proveedor_id'):
        raise prohibido('Sólo el proveedor o sus operadores descuentan existencia de su catálogo.')
    previa = db.session.execute(text('SELECT partidas FROM salidas_catalogo WHERE referencia = :r'),
                                {'r': datos.referencia}).first()
    if previa:
        return {'referencia': datos.referencia, 'proveedor_id': str(proveedor.id), 'ya_aplicada': True,
                'partidas': previa.partidas}
    ofertas = {o.producto_id: o for o in CatalogoProveedor.query.filter(
        CatalogoProveedor.proveedor_id == proveedor.id, CatalogoProveedor.activo.is_(True),
        CatalogoProveedor.producto_id.in_([p.producto_id for p in datos.partidas])).with_for_update().all()}
    renglones = []
    for p in datos.partidas:
        oferta = ofertas.get(p.producto_id)
        if not oferta or oferta.existencia_disponible < p.cantidad:
            db.session.rollback()
            raise ErrorApi(409, 'existencia_insuficiente',
                           f'No hay existencia suficiente del producto {p.producto_id} en el catálogo.')
        anterior = oferta.existencia_disponible
        oferta.existencia_disponible = anterior - p.cantidad
        renglones.append({'producto_id': p.producto_id, 'cantidad': float(p.cantidad),
                          'existencia_anterior': float(anterior), 'existencia_nueva': float(oferta.existencia_disponible)})
    db.session.execute(text('INSERT INTO salidas_catalogo (referencia, proveedor_id, partidas, usuario_id) '
                            'VALUES (:r, :p, CAST(:d AS jsonb), :u)'),
                       {'r': datos.referencia, 'p': proveedor.id, 'd': json.dumps(renglones), 'u': g.claims['sub']})
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'CatalogoProveedor', str(proveedor.id),
                     f'Salida de existencia ({datos.referencia})', datos_nuevos={'partidas': renglones})
    db.session.commit()
    invalidar_analisis()
    return {'referencia': datos.referencia, 'proveedor_id': str(proveedor.id), 'ya_aplicada': False,
            'partidas': renglones}


@srv.ruta('/comercios/<uuid:comercio_id>/proveedores-sugeridos', 'GET', resumen='Proveedores que surten a mi zona',
          etiqueta='Proveedores', permisos=['proveedores.consultar'], consulta=PaginaConsulta, raiz_xml='proveedores')
def sugeridos(comercio_id, q):
    """Proveedores verificados que entregan en la zona del comercio, ordenados por evaluación."""
    comercio = db.session.get(Comercio, comercio_id)
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    if not comercio.zona_id:
        raise ErrorApi(409, 'sin_zona', 'El comercio no tiene zona asignada.')
    return listar.__wrapped__(ProveedoresConsulta(zona_id=comercio.zona_id, orden='calificacion',
                                                  pagina=q.pagina, por_pagina=q.por_pagina))
