"""
ms-catalogo: catálogo maestro de productos, categorías, proveedores y catálogo mayorista.

PostgreSQL: productos_maestros, categorias, proveedores, proveedor_zonas,
catalogo_proveedor, precios_mayoreo.
Redis: caché de consultas del catálogo maestro (`catalogo:v{n}:productos:{filtros}`, 10 min);
cualquier alta o cambio incrementa `catalogo:version` y la caché vieja deja de usarse.
"""
from pathlib import Path
import hashlib
import json
from uuid import UUID

from flask import g
from redis.exceptions import RedisError
from sqlalchemy import func, or_

from abasto_api.formatos import compatible_json
from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, prohibido, tiene
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import (CatalogoProveedor, Categoria, PrecioMayoreo, ProductoMaestro, Proveedor,
                                    proveedor_zonas)
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.precios import ofertas_producto

from esquemas import (CONTRATOS_XML, OfertaCambio, OfertaEntrada, OfertasConsulta, ProductoEntrada,
                      ProductosConsulta, ProveedoresConsulta)

srv = Servicio('catalogo', 'Catálogo',
               'Catálogo maestro de productos y categorías, proveedores con sus zonas de entrega y condiciones, '
               'catálogo mayorista y la consulta "¿quién me vende este producto?".',
               xsd=Path(__file__).parent / 'xsd' / 'catalogo.xsd', contratos=CONTRATOS_XML)
app = srv.app


def producto_a_dict(p):
    return {'id': p.id, 'nombre': p.nombre, 'categoria_id': p.categoria_id, 'categoria': p.categoria.nombre,
            'unidad_medida': p.unidad_medida, 'codigo_barras': p.codigo_barras,
            'es_canasta_basica': p.es_canasta_basica, 'descripcion': p.descripcion}


def proveedor_a_dict(p, detalle=False):
    datos = {'id': str(p.id), 'nombre_empresa': p.nombre_empresa, 'municipio': p.municipio,
             'pedido_minimo': p.pedido_minimo, 'tiempo_entrega_dias': p.tiempo_entrega_dias,
             'condiciones_venta': p.condiciones_venta, 'plan': p.plan,
             'zonas': [{'id': z.id, 'nombre': z.nombre} for z in p.zonas]}
    if detalle:
        datos.update({'descripcion': p.descripcion, 'telefono_contacto': p.telefono_contacto,
                      'email_contacto': p.email_contacto, 'direccion': p.direccion})
    return datos


def oferta_a_dict(o):
    return {'id': o.id, 'proveedor_id': str(o.proveedor_id), 'proveedor': o.proveedor.nombre_empresa,
            'producto_id': o.producto_id, 'producto': o.producto.nombre, 'unidad_medida': o.producto.unidad_medida,
            'precio_mayoreo': o.precio_mayoreo, 'cantidad_minima': o.cantidad_minima,
            'existencia_disponible': o.existencia_disponible, 'actualizado': o.updated_at}


def _version_cache():
    try:
        return extensiones.redis_client.get('catalogo:version') or '0'
    except RedisError:
        return None


def _invalidar_cache():
    try:
        extensiones.redis_client.incr('catalogo:version')
    except RedisError:
        pass
    invalidar_analisis()


# ---------------------------------------------------------------- catálogo maestro

@srv.ruta('/productos', 'GET', resumen='Catálogo maestro', etiqueta='Productos', publico=True,
          consulta=ProductosConsulta, raiz_xml='productos')
def listar_productos(q):
    """Público (lo consulta la app sin sesión). La respuesta se guarda 10 minutos en Redis por combinación de filtros;
    el campo `origen` indica si vino de la caché."""
    version = _version_cache()
    clave = None
    if version is not None:
        filtros = hashlib.md5(json.dumps(q.model_dump(), sort_keys=True).encode()).hexdigest()[:12]
        clave = f'catalogo:v{version}:productos:{filtros}'
        try:
            guardado = extensiones.redis_client.get(clave)
            if guardado:
                return {**json.loads(guardado), 'origen': 'cache'}
        except RedisError:
            clave = None

    consulta = ProductoMaestro.query.filter_by(activo=True).join(Categoria)
    if q.texto:
        consulta = consulta.filter(or_(ProductoMaestro.nombre.ilike(f'%{q.texto}%'),
                                       ProductoMaestro.codigo_barras == q.texto))
    if q.categoria_id:
        consulta = consulta.filter(ProductoMaestro.categoria_id == q.categoria_id)
    if q.canasta_basica is not None:
        consulta = consulta.filter(ProductoMaestro.es_canasta_basica.is_(q.canasta_basica))
    resultado = paginar(consulta.order_by(ProductoMaestro.nombre), q.pagina, q.por_pagina, producto_a_dict)
    resultado['productos'] = resultado.pop('items')
    if clave:
        try:
            extensiones.redis_client.setex(clave, 600, json.dumps(compatible_json(resultado)))
        except RedisError:
            pass
    return {**resultado, 'origen': 'postgres'}


@srv.ruta('/productos/<int:id>', 'GET', resumen='Detalle de producto', etiqueta='Productos', publico=True,
          raiz_xml='producto', errores=(404,))
def obtener_producto(id):
    producto = db.session.get(ProductoMaestro, id)
    if not producto or not producto.activo:
        raise no_encontrado('El producto')
    return producto_a_dict(producto)


def _validar_producto(datos, actual=None):
    if not db.session.get(Categoria, datos.categoria_id):
        raise ErrorApi(422, 'categoria_inexistente', 'La categoría no existe.')
    repetido = ProductoMaestro.query.filter(func.lower(ProductoMaestro.nombre) == datos.nombre.lower(),
                                            ProductoMaestro.unidad_medida == datos.unidad_medida)
    if actual:
        repetido = repetido.filter(ProductoMaestro.id != actual.id)
    if repetido.first():
        raise ErrorApi(409, 'producto_duplicado', 'Ya existe un producto con ese nombre y unidad.')


EJEMPLO_PRODUCTO = {'nombre': 'Lenteja 500 g', 'categoria_id': 1, 'unidad_medida': 'pieza',
                    'codigo_barras': '7501000123456', 'es_canasta_basica': True}


@srv.ruta('/productos', 'POST', resumen='Alta en el catálogo maestro', etiqueta='Productos',
          permisos=['catalogos.gestionar'], cuerpo=ProductoEntrada, status=201, raiz_xml='producto',
          entrada_xml='producto_entrada', ejemplo_entrada=EJEMPLO_PRODUCTO)
def crear_producto(datos):
    _validar_producto(datos)
    producto = ProductoMaestro(**datos.model_dump())
    db.session.add(producto)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'ProductoMaestro', producto.id,
                     f'Alta de {producto.nombre} (ms-catalogo)', datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar_cache()
    return producto_a_dict(producto)


@srv.ruta('/productos/<int:id>', 'PUT', resumen='Actualizar producto', etiqueta='Productos',
          permisos=['catalogos.gestionar'], cuerpo=ProductoEntrada, raiz_xml='producto',
          entrada_xml='producto_entrada', ejemplo_entrada=EJEMPLO_PRODUCTO)
def actualizar_producto(id, datos):
    producto = db.session.get(ProductoMaestro, id)
    if not producto or not producto.activo:
        raise no_encontrado('El producto')
    _validar_producto(datos, producto)
    antes = producto_a_dict(producto)
    for campo, valor in datos.model_dump().items():
        setattr(producto, campo, valor)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'ProductoMaestro', producto.id,
                     f'Edición de {producto.nombre} (ms-catalogo)', datos_anteriores=antes, datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar_cache()
    return producto_a_dict(producto)


@srv.ruta('/productos/<int:id>', 'DELETE', resumen='Baja lógica de producto', etiqueta='Productos',
          permisos=['catalogos.gestionar'], raiz_xml='resultado')
def baja_producto(id):
    producto = db.session.get(ProductoMaestro, id)
    if not producto or not producto.activo:
        raise no_encontrado('El producto')
    producto.activo = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'ProductoMaestro', producto.id,
                     f'Baja lógica de {producto.nombre} (ms-catalogo)')
    db.session.commit()
    _invalidar_cache()
    return {'mensaje': 'Producto dado de baja', 'id': str(producto.id)}


@srv.ruta('/categorias', 'GET', resumen='Categorías', etiqueta='Productos', publico=True, raiz_xml='categorias')
def listar_categorias():
    conteo = dict(db.session.query(ProductoMaestro.categoria_id, func.count(ProductoMaestro.id))
                  .filter_by(activo=True).group_by(ProductoMaestro.categoria_id).all())
    return {'categorias': [{'id': c.id, 'nombre': c.nombre, 'descripcion': c.descripcion,
                            'productos': conteo.get(c.id, 0)}
                           for c in Categoria.query.filter_by(activa=True).order_by(Categoria.orden)]}


# ---------------------------------------------------------------- proveedores y mayoreo

@srv.ruta('/proveedores', 'GET', resumen='Proveedores', etiqueta='Proveedores',
          permisos=['proveedores.consultar', 'proveedor.catalogo'], consulta=ProveedoresConsulta,
          raiz_xml='proveedores')
def listar_proveedores(q):
    consulta = Proveedor.query.filter_by(activo=True)
    if q.zona_id:
        consulta = consulta.join(proveedor_zonas).filter(proveedor_zonas.c.zona_id == q.zona_id)
    if q.texto:
        consulta = consulta.filter(Proveedor.nombre_empresa.ilike(f'%{q.texto}%'))
    resultado = paginar(consulta.order_by(Proveedor.nombre_empresa), q.pagina, q.por_pagina, proveedor_a_dict)
    resultado['proveedores'] = resultado.pop('items')
    return resultado


@srv.ruta('/proveedores/<uuid:id>', 'GET', resumen='Proveedor con su catálogo mayorista', etiqueta='Proveedores',
          permisos=['proveedores.consultar', 'proveedor.catalogo'], raiz_xml='proveedor')
def obtener_proveedor(id):
    proveedor = db.session.get(Proveedor, id)
    if not proveedor or not proveedor.activo:
        raise no_encontrado('El proveedor')
    ofertas = (CatalogoProveedor.query.filter_by(proveedor_id=id, activo=True)
               .join(ProductoMaestro).order_by(ProductoMaestro.nombre).all())
    return {**proveedor_a_dict(proveedor, detalle=True), 'ofertas': [oferta_a_dict(o) for o in ofertas]}


@srv.ruta('/ofertas', 'GET', resumen='¿Quién me vende este producto?', etiqueta='Proveedores',
          permisos=['proveedores.consultar'], consulta=OfertasConsulta, raiz_xml='ofertas')
def buscar_ofertas(q):
    """Ofertas de mayoreo del producto: primero quienes entregan en la zona y tienen existencia, luego por precio."""
    if not db.session.get(ProductoMaestro, q.producto_id):
        raise no_encontrado('El producto')
    ofertas = ofertas_producto(q.producto_id, q.zona_id)
    return {'producto_id': q.producto_id, 'zona_id': q.zona_id, 'total': len(ofertas), 'ofertas': [
        {**oferta_a_dict(o), 'cubre_zona': o.cubre_zona, 'pedido_minimo': o.proveedor.pedido_minimo,
         'tiempo_entrega_dias': o.proveedor.tiempo_entrega_dias, 'condiciones_venta': o.proveedor.condiciones_venta,
         'plan': o.proveedor.plan} for o in ofertas]}


def _mi_proveedor():
    empresa_id = g.claims.get('proveedor_id')
    proveedor = db.session.get(Proveedor, UUID(empresa_id)) if empresa_id else None
    if not proveedor:
        raise ErrorApi(409, 'sin_empresa', 'Tu cuenta aún no tiene datos de empresa proveedora.')
    return proveedor


@srv.ruta('/mi-catalogo', 'GET', resumen='Mi catálogo mayorista', etiqueta='Mi catálogo',
          permisos=['proveedor.catalogo'], raiz_xml='ofertas')
def mi_catalogo():
    proveedor = _mi_proveedor()
    ofertas = (CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id, activo=True)
               .join(ProductoMaestro).order_by(ProductoMaestro.nombre).all())
    return {'proveedor_id': str(proveedor.id), 'total': len(ofertas), 'ofertas': [oferta_a_dict(o) for o in ofertas]}


@srv.ruta('/mi-catalogo', 'POST', resumen='Publicar producto a precio de mayoreo', etiqueta='Mi catálogo',
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
                     f'{proveedor.nombre_empresa} ofrece {oferta.producto.nombre} (ms-catalogo)',
                     datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar_cache()
    return oferta_a_dict(oferta)


def _mi_oferta(id):
    oferta = db.session.get(CatalogoProveedor, id)
    if not oferta or not oferta.activo:
        raise no_encontrado('La oferta')
    if str(oferta.proveedor_id) != g.claims.get('proveedor_id') and not tiene('catalogos.gestionar'):
        raise prohibido('La oferta es de otro proveedor.')
    return oferta


@srv.ruta('/mi-catalogo/<int:id>', 'PATCH', resumen='Cambiar precio, mínimo o existencia', etiqueta='Mi catálogo',
          permisos=['proveedor.catalogo'], cuerpo=OfertaCambio, raiz_xml='oferta', entrada_xml='oferta_cambio',
         ejemplo_entrada={'precio_mayoreo': 20.9, 'existencia_disponible': 250})
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
                     f'Actualización de {oferta.producto.nombre} (ms-catalogo)', datos_anteriores=antes, datos_nuevos=cambios)
    db.session.commit()
    _invalidar_cache()
    return oferta_a_dict(oferta)


@srv.ruta('/mi-catalogo/<int:id>', 'DELETE', resumen='Retirar producto de mi catálogo', etiqueta='Mi catálogo',
          permisos=['proveedor.catalogo'], raiz_xml='resultado')
def retirar_oferta(id):
    oferta = _mi_oferta(id)
    oferta.activo = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'CatalogoProveedor', oferta.id,
                     f'Se retiró {oferta.producto.nombre} del catálogo mayorista (ms-catalogo)')
    db.session.commit()
    _invalidar_cache()
    return {'mensaje': 'Producto retirado del catálogo', 'id': str(oferta.id)}
