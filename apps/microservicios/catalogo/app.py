"""
ms-catalogo: catálogo maestro de productos.

Es DUEÑO de: productos_maestros, categorias, marcas, unidades_medida, variantes_producto y
equivalencias_producto. Los proveedores y su catálogo mayorista pasaron a ms-proveedores.

- CRUD de productos y categorías; marcas, unidades de medida y variantes (presentaciones con su
  propio código de barras).
- Búsqueda, filtrado (texto, categoría, marca, canasta básica), orden y paginación.
- Búsqueda por código de barras (del producto o de una de sus variantes).
- Productos equivalentes (sustitutos o el mismo producto con otro nombre) y clave estandarizada.
- Imagen del producto: se sube a ms-documentos (entidad producto, visibilidad pública) y aquí se
  guarda la ruta de su contenido.
Redis: caché de consultas (`catalogo:v{n}:productos:{filtros}`, 10 min); cualquier alta o cambio
incrementa `catalogo:version` y la caché vieja deja de usarse.
"""
import hashlib
import json
from pathlib import Path
from uuid import UUID

from flask import g
from redis.exceptions import RedisError
from sqlalchemy import func, or_

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar
from abasto_api.formatos import compatible_json
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import (Categoria, Marca, ProductoMaestro, UnidadMedida, VarianteProducto,
                                    equivalencias_producto)
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis

from esquemas import (CONTRATOS_XML, CategoriaCambio, CategoriaEntrada, EquivalenciaEntrada, MarcaEntrada, ProductoEntrada,
                      ProductosConsulta, VarianteEntrada)

srv = Servicio('catalogo', 'Catálogo',
               'CRUD de productos, categorías, marcas, unidades de medida y variantes; búsqueda, filtrado y '
               'paginación; códigos de barras; imágenes; productos equivalentes y clasificación estandarizada.',
               xsd=Path(__file__).parent / 'xsd' / 'catalogo.xsd', contratos=CONTRATOS_XML)
app = srv.app

GESTION = ['catalogos.gestionar']


def variante_a_dict(v):
    return {'id': v.id, 'producto_id': v.producto_id, 'nombre': v.nombre, 'codigo_barras': v.codigo_barras,
            'factor': v.factor}


def equivalentes(producto_id):
    filas = (db.session.query(ProductoMaestro, equivalencias_producto.c.tipo)
             .join(equivalencias_producto, equivalencias_producto.c.equivalente_id == ProductoMaestro.id)
             .filter(equivalencias_producto.c.producto_id == producto_id, ProductoMaestro.activo.is_(True)).all())
    return [{'producto_id': p.id, 'nombre': p.nombre, 'tipo': tipo} for p, tipo in filas]


def producto_a_dict(p, detalle=False):
    datos = {'id': p.id, 'nombre': p.nombre, 'categoria_id': p.categoria_id, 'categoria': p.categoria.nombre,
             'unidad_medida': p.unidad_medida, 'codigo_barras': p.codigo_barras,
             'es_canasta_basica': p.es_canasta_basica, 'descripcion': p.descripcion, 'marca_id': p.marca_id,
             'marca': p.marca.nombre if p.marca else None, 'clave_estandar': p.clave_estandar,
             'imagen_url': p.imagen_url}
    if detalle:
        datos['variantes'] = [variante_a_dict(v) for v in p.variantes if v.activo]
        datos['equivalentes'] = equivalentes(p.id)
    return datos


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


def _producto(id):
    producto = db.session.get(ProductoMaestro, id)
    if not producto or not producto.activo:
        raise no_encontrado('El producto')
    return producto


def _codigo_libre(codigo, producto_id=None, variante_id=None):
    if not codigo:
        return
    otro = ProductoMaestro.query.filter(ProductoMaestro.codigo_barras == codigo,
                                        ProductoMaestro.id != (producto_id or 0)).first()
    variante = VarianteProducto.query.filter(VarianteProducto.codigo_barras == codigo,
                                             VarianteProducto.id != (variante_id or 0)).first()
    if otro or variante:
        raise ErrorApi(409, 'codigo_duplicado', f'El código de barras {codigo} ya pertenece a otro producto o variante.')


# ---------------------------------------------------------------- catálogo maestro

@srv.ruta('/productos', 'GET', resumen='Catálogo maestro', etiqueta='Productos', publico=True,
          consulta=ProductosConsulta, raiz_xml='productos')
def listar_productos(q):
    """Público (lo consultan las apps sin sesión). El texto busca en nombre, descripción, marca y código de barras.
    La respuesta se guarda 10 minutos en Redis por combinación de filtros; `origen` indica si vino de la caché."""
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

    consulta = ProductoMaestro.query.filter_by(activo=True).join(Categoria).outerjoin(Marca)
    if q.texto:
        consulta = consulta.filter(or_(ProductoMaestro.nombre.ilike(f'%{q.texto}%'),
                                       ProductoMaestro.descripcion.ilike(f'%{q.texto}%'),
                                       Marca.nombre.ilike(f'%{q.texto}%'),
                                       ProductoMaestro.codigo_barras == q.texto))
    if q.categoria_id:
        consulta = consulta.filter(ProductoMaestro.categoria_id == q.categoria_id)
    if q.marca_id:
        consulta = consulta.filter(ProductoMaestro.marca_id == q.marca_id)
    if q.canasta_basica is not None:
        consulta = consulta.filter(ProductoMaestro.es_canasta_basica.is_(q.canasta_basica))
    orden = {'nombre': [ProductoMaestro.nombre], 'categoria': [Categoria.orden, ProductoMaestro.nombre],
             'recientes': [ProductoMaestro.created_at.desc()]}[q.orden]
    resultado = paginar(consulta.order_by(*orden), q.pagina, q.por_pagina, producto_a_dict)
    resultado['productos'] = resultado.pop('items')
    if clave:
        try:
            extensiones.redis_client.setex(clave, 600, json.dumps(compatible_json(resultado)))
        except RedisError:
            pass
    return {**resultado, 'origen': 'postgres'}


@srv.ruta('/productos/<int:id>', 'GET', resumen='Detalle de producto (variantes y equivalentes)', etiqueta='Productos',
          publico=True, raiz_xml='producto', errores=(404,))
def obtener_producto(id):
    return producto_a_dict(_producto(id), detalle=True)


@srv.ruta('/productos/codigo/<codigo>', 'GET', resumen='Buscar por código de barras', etiqueta='Productos',
          publico=True, raiz_xml='producto', errores=(404,))
def por_codigo(codigo):
    """Busca el código en los productos y en sus variantes; lo usan los lectores de código de las apps."""
    producto = ProductoMaestro.query.filter_by(codigo_barras=codigo, activo=True).first()
    if producto:
        return {**producto_a_dict(producto, detalle=True), 'coincidencia': 'producto'}
    variante = VarianteProducto.query.filter_by(codigo_barras=codigo, activo=True).first()
    if variante and variante.producto.activo:
        return {**producto_a_dict(variante.producto, detalle=True), 'coincidencia': f'variante: {variante.nombre}'}
    raise no_encontrado(f'El código {codigo}')


def _validar_producto(datos, actual=None):
    if not db.session.get(Categoria, datos.categoria_id):
        raise ErrorApi(422, 'categoria_inexistente', 'La categoría no existe.')
    if not db.session.get(UnidadMedida, datos.unidad_medida):
        raise ErrorApi(422, 'unidad_inexistente', f'La unidad {datos.unidad_medida} no existe; consulta GET /unidades.')
    if datos.marca_id and not db.session.get(Marca, datos.marca_id):
        raise ErrorApi(422, 'marca_inexistente', 'La marca no existe.')
    repetido = ProductoMaestro.query.filter(func.lower(ProductoMaestro.nombre) == datos.nombre.lower(),
                                            ProductoMaestro.unidad_medida == datos.unidad_medida)
    if actual:
        repetido = repetido.filter(ProductoMaestro.id != actual.id)
    if repetido.first():
        raise ErrorApi(409, 'producto_duplicado', 'Ya existe un producto con ese nombre y unidad.')
    _codigo_libre(datos.codigo_barras, actual.id if actual else None)


def _campos(datos):
    campos = datos.model_dump(exclude={'imagen_documento_id'})
    if datos.imagen_documento_id:
        campos['imagen_url'] = f'/ms/documentos/api/v1/documentos/{datos.imagen_documento_id}/contenido'
    return campos


EJEMPLO_PRODUCTO = {'nombre': 'Lenteja 500 g', 'categoria_id': 1, 'unidad_medida': 'pieza',
                    'codigo_barras': '7501000123456', 'es_canasta_basica': True, 'marca_id': 1}


@srv.ruta('/productos', 'POST', resumen='Alta en el catálogo maestro', etiqueta='Productos', permisos=GESTION,
          cuerpo=ProductoEntrada, status=201, raiz_xml='producto', entrada_xml='producto_entrada',
          ejemplo_entrada=EJEMPLO_PRODUCTO)
def crear_producto(datos):
    _validar_producto(datos)
    producto = ProductoMaestro(**_campos(datos))
    db.session.add(producto)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'ProductoMaestro', producto.id, f'Alta de {producto.nombre}',
                     datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar_cache()
    return producto_a_dict(producto, detalle=True)


@srv.ruta('/productos/<int:id>', 'PUT', resumen='Actualizar producto', etiqueta='Productos', permisos=GESTION,
          cuerpo=ProductoEntrada, raiz_xml='producto', entrada_xml='producto_entrada', ejemplo_entrada=EJEMPLO_PRODUCTO)
def actualizar_producto(id, datos):
    producto = _producto(id)
    _validar_producto(datos, producto)
    antes = producto_a_dict(producto)
    for campo, valor in _campos(datos).items():
        setattr(producto, campo, valor)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'ProductoMaestro', producto.id,
                     f'Edición de {producto.nombre}', datos_anteriores=antes, datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar_cache()
    return producto_a_dict(producto, detalle=True)


@srv.ruta('/productos/<int:id>', 'DELETE', resumen='Baja lógica de producto', etiqueta='Productos', permisos=GESTION,
          raiz_xml='resultado')
def baja_producto(id):
    producto = _producto(id)
    producto.activo = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'ProductoMaestro', producto.id,
                     f'Baja lógica de {producto.nombre}')
    db.session.commit()
    _invalidar_cache()
    return {'mensaje': 'Producto dado de baja', 'id': str(producto.id)}


# ---------------------------------------------------------------- variantes y equivalencias

@srv.ruta('/productos/<int:id>/variantes', 'POST', resumen='Agregar una presentación (variante)', etiqueta='Variantes',
          permisos=GESTION, cuerpo=VarianteEntrada, status=201, raiz_xml='variante', entrada_xml='variante_entrada',
          ejemplo_entrada={'nombre': 'Caja con 12', 'codigo_barras': '17501000123453', 'factor': 12})
def agregar_variante(id, datos):
    producto = _producto(id)
    if VarianteProducto.query.filter_by(producto_id=id, nombre=datos.nombre).first():
        raise ErrorApi(409, 'variante_duplicada', 'El producto ya tiene una variante con ese nombre.')
    _codigo_libre(datos.codigo_barras)
    variante = VarianteProducto(producto_id=producto.id, **datos.model_dump())
    db.session.add(variante)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'VarianteProducto', variante.id,
                     f'Variante {datos.nombre} de {producto.nombre}', datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar_cache()
    return variante_a_dict(variante)


@srv.ruta('/variantes/<int:id>', 'DELETE', resumen='Retirar una variante', etiqueta='Variantes', permisos=GESTION,
          raiz_xml='resultado')
def retirar_variante(id):
    variante = db.session.get(VarianteProducto, id)
    if not variante or not variante.activo:
        raise no_encontrado('La variante')
    variante.activo = False
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'VarianteProducto', variante.id, f'Baja de {variante.nombre}')
    db.session.commit()
    _invalidar_cache()
    return {'mensaje': 'Variante retirada', 'id': str(id)}


@srv.ruta('/productos/<int:id>/equivalentes', 'POST', resumen='Asociar un producto equivalente', etiqueta='Variantes',
          permisos=GESTION, cuerpo=EquivalenciaEntrada, status=201, raiz_xml='producto',
          entrada_xml='equivalencia_entrada', ejemplo_entrada={'equivalente_id': 4, 'tipo': 'SUSTITUTO'})
def asociar_equivalente(id, datos):
    """La relación se guarda en ambos sentidos (si A sustituye a B, B sustituye a A)."""
    producto, otro = _producto(id), _producto(datos.equivalente_id)
    if producto.id == otro.id:
        raise ErrorApi(422, 'mismo_producto', 'Un producto no puede ser equivalente de sí mismo.')
    existe = db.session.query(equivalencias_producto).filter_by(producto_id=id, equivalente_id=otro.id).first()
    if existe:
        raise ErrorApi(409, 'equivalencia_existente', 'Ya están asociados.')
    db.session.execute(equivalencias_producto.insert(), [
        {'producto_id': producto.id, 'equivalente_id': otro.id, 'tipo': datos.tipo},
        {'producto_id': otro.id, 'equivalente_id': producto.id, 'tipo': datos.tipo}])
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'EquivalenciaProducto', f'{producto.id}-{otro.id}',
                     f'{producto.nombre} ≈ {otro.nombre} ({datos.tipo})')
    db.session.commit()
    _invalidar_cache()
    return producto_a_dict(producto, detalle=True)


@srv.ruta('/productos/<int:id>/equivalentes/<int:equivalente_id>', 'DELETE', resumen='Quitar una equivalencia',
          etiqueta='Variantes', permisos=GESTION, raiz_xml='resultado')
def quitar_equivalente(id, equivalente_id):
    borradas = db.session.execute(equivalencias_producto.delete().where(or_(
        (equivalencias_producto.c.producto_id == id) & (equivalencias_producto.c.equivalente_id == equivalente_id),
        (equivalencias_producto.c.producto_id == equivalente_id) & (equivalencias_producto.c.equivalente_id == id)))).rowcount
    if not borradas:
        raise no_encontrado('La equivalencia')
    registrar_evento(UUID(g.claims['sub']), 'ELIMINACION', 'EquivalenciaProducto', f'{id}-{equivalente_id}',
                     'Equivalencia retirada')
    db.session.commit()
    _invalidar_cache()
    return {'mensaje': 'Equivalencia retirada', 'id': f'{id}-{equivalente_id}'}


# ---------------------------------------------------------------- categorías, marcas y unidades

def categoria_a_dict(c, productos=0):
    return {'id': c.id, 'nombre': c.nombre, 'descripcion': c.descripcion, 'productos': productos, 'activa': c.activa}


@srv.ruta('/categorias', 'GET', resumen='Categorías', etiqueta='Clasificación', publico=True, raiz_xml='categorias')
def listar_categorias():
    conteo = dict(db.session.query(ProductoMaestro.categoria_id, func.count(ProductoMaestro.id))
                  .filter_by(activo=True).group_by(ProductoMaestro.categoria_id).all())
    return {'categorias': [categoria_a_dict(c, conteo.get(c.id, 0))
                           for c in Categoria.query.filter_by(activa=True).order_by(Categoria.orden)]}


@srv.ruta('/categorias', 'POST', resumen='Alta de categoría', etiqueta='Clasificación', permisos=GESTION,
          cuerpo=CategoriaEntrada, status=201, raiz_xml='categoria', entrada_xml='categoria_entrada',
          ejemplo_entrada={'nombre': 'Limpieza', 'descripcion': 'Artículos de limpieza del hogar', 'orden': 9})
def crear_categoria(datos):
    if Categoria.query.filter(func.lower(Categoria.nombre) == datos.nombre.lower()).first():
        raise ErrorApi(409, 'categoria_duplicada', 'Ya existe esa categoría.')
    categoria = Categoria(**datos.model_dump())
    db.session.add(categoria)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'Categoria', categoria.id, f'Alta de la categoría {datos.nombre}')
    db.session.commit()
    _invalidar_cache()
    return categoria_a_dict(categoria)


@srv.ruta('/categorias/<int:id>', 'PATCH', resumen='Cambiar, activar o desactivar una categoría',
          etiqueta='Clasificación', permisos=GESTION, cuerpo=CategoriaCambio, raiz_xml='categoria',
          entrada_xml='categoria_cambio', ejemplo_entrada={'activa': False})
def cambiar_categoria(id, datos):
    categoria = db.session.get(Categoria, id)
    if not categoria:
        raise no_encontrado('La categoría')
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise ErrorApi(422, 'sin_cambios', 'Indica al menos un campo a cambiar.')
    if 'nombre' in cambios and Categoria.query.filter(func.lower(Categoria.nombre) == cambios['nombre'].lower(),
                                                      Categoria.id != id).first():
        raise ErrorApi(409, 'categoria_duplicada', 'Ya existe esa categoría.')
    antes = {k: getattr(categoria, k) for k in cambios}
    for campo, valor in cambios.items():
        setattr(categoria, campo, valor)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Categoria', categoria.id,
                     f'Categoría {categoria.nombre}', datos_anteriores=antes, datos_nuevos=cambios)
    db.session.commit()
    _invalidar_cache()
    conteo = ProductoMaestro.query.filter_by(categoria_id=id, activo=True).count()
    return categoria_a_dict(categoria, conteo)


@srv.ruta('/marcas', 'GET', resumen='Marcas', etiqueta='Clasificación', publico=True, raiz_xml='marcas')
def listar_marcas():
    conteo = dict(db.session.query(ProductoMaestro.marca_id, func.count(ProductoMaestro.id))
                  .filter_by(activo=True).group_by(ProductoMaestro.marca_id).all())
    return {'marcas': [{'id': m.id, 'nombre': m.nombre, 'productos': conteo.get(m.id, 0)}
                       for m in Marca.query.filter_by(activo=True).order_by(Marca.nombre)]}


@srv.ruta('/marcas', 'POST', resumen='Alta de marca', etiqueta='Clasificación', permisos=GESTION, cuerpo=MarcaEntrada,
          status=201, raiz_xml='marca', entrada_xml='marca_entrada', ejemplo_entrada={'nombre': 'Sierra Madre'})
def crear_marca(datos):
    if Marca.query.filter(func.lower(Marca.nombre) == datos.nombre.lower()).first():
        raise ErrorApi(409, 'marca_duplicada', 'Ya existe esa marca.')
    marca = Marca(nombre=datos.nombre)
    db.session.add(marca)
    db.session.flush()
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'Marca', marca.id, f'Alta de la marca {datos.nombre}')
    db.session.commit()
    return {'id': marca.id, 'nombre': marca.nombre, 'productos': 0}


@srv.ruta('/unidades', 'GET', resumen='Unidades de medida', etiqueta='Clasificación', publico=True,
          raiz_xml='unidades')
def listar_unidades():
    return {'unidades': [{'clave': u.clave, 'nombre': u.nombre, 'tipo': u.tipo}
                         for u in UnidadMedida.query.order_by(UnidadMedida.tipo, UnidadMedida.nombre)]}
