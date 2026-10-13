"""
API JSON del monolito.

Desde el segundo parcial los tokens los emite ms-seguridad (/api/v1/auth/login)
y las operaciones de la app móvil y de escritorio viven en los microservicios.
El web conserva sólo estas rutas de consulta, protegidas con el mismo mecanismo
común: firma JWT + sesión activa en Redis (abasto_dominio.sesiones).
"""
from functools import wraps
from uuid import UUID

from flask import jsonify, request

from app import app
from app.extensions import db
from abasto_dominio import sesiones
from abasto_dominio.modelos import Comercio, InventarioComercio, PrecioComercio, ProductoMaestro, Usuario, ZonaMunicipal
from abasto_dominio.servicios.precios import SECTOR


def jwt_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        encabezado = request.headers.get('Authorization', '')
        if not encabezado.startswith('Bearer '):
            return jsonify(error='Token JWT requerido'), 401
        try:
            claims = sesiones.validar_token(encabezado.removeprefix('Bearer ').strip())
            usuario = db.session.get(Usuario, UUID(claims['sub']))
        except sesiones.ErrorSesion as error:
            return jsonify(error=error.mensaje, codigo=error.codigo), error.codigo_http
        except ValueError:
            return jsonify(error='Token JWT inválido'), 401
        if not usuario or not usuario.activo:
            return jsonify(error='Usuario no autorizado'), 401
        request.usuario_api = usuario
        return vista(*args, **kwargs)
    return envoltura


@app.route('/api/me')
@jwt_requerido
def api_me():
    u = request.usuario_api
    return jsonify(id=str(u.id), email=u.email, nombre=u.nombre_completo, rol=u.rol.nombre, permisos=u.rol.permisos)


@app.route('/api/inventario')
@jwt_requerido
def api_inventario():
    """Inventario de los comercios del usuario (lo usará la app móvil)."""
    renglones = (InventarioComercio.query.join(Comercio)
                 .filter(Comercio.usuario_id == request.usuario_api.id, Comercio.activo.is_(True),
                         InventarioComercio.activo.is_(True)).all())
    return jsonify([{
        'id': r.id,
        'comercio_id': str(r.comercio_id),
        'comercio': r.comercio.nombre_comercio,
        'producto_id': r.producto_id,
        'producto': r.producto.nombre,
        'unidad': r.producto.unidad_medida,
        'existencia': float(r.existencia),
        'stock_minimo': float(r.stock_minimo),
        'precio_venta': float(r.precio_venta) if r.precio_venta else None,
        'estado': r.estado,
        'actualizado': r.updated_at.isoformat() if r.updated_at else None,
    } for r in renglones])


@app.route('/api/disponibilidad')
def api_disponibilidad():
    """Consulta pública: existencia por producto y comercio verificado (sin datos personales)."""
    producto_id = request.args.get('producto_id', type=int)
    consulta = (db.session.query(InventarioComercio, Comercio)
                .join(Comercio, InventarioComercio.comercio_id == Comercio.id)
                .filter(InventarioComercio.activo.is_(True), Comercio.activo.is_(True),
                        Comercio.estado_registro == 'VERIFICADO'))
    if producto_id:
        consulta = consulta.filter(InventarioComercio.producto_id == producto_id)
    return jsonify([{
        'producto': i.producto.nombre,
        'comercio': c.nombre_comercio,
        'sector': c.sector,
        'zona': c.zona.nombre if c.zona else None,
        'existencia': float(i.existencia),
        'precio': float(i.precio_venta) if i.precio_venta else None,
        'actualizado': i.updated_at.isoformat() if i.updated_at else None,
    } for i, c in consulta.limit(500)])


@app.route('/api/precios/resumen')
@jwt_requerido
def api_precios_resumen():
    filas = (db.session.query(ProductoMaestro.nombre, ZonaMunicipal.nombre, SECTOR,
                              db.func.avg(PrecioComercio.precio), db.func.count(PrecioComercio.id))
             .join(ProductoMaestro, PrecioComercio.producto_id == ProductoMaestro.id)
             .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
             .outerjoin(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
             .filter(PrecioComercio.activo.is_(True), PrecioComercio.estado_validacion == 'VALIDADO')
             .group_by(ProductoMaestro.nombre, ZonaMunicipal.nombre, SECTOR)
             .order_by(ProductoMaestro.nombre, ZonaMunicipal.nombre).all())
    return jsonify([{'producto': p, 'zona': z, 'sector': s, 'promedio': round(float(prom), 2), 'muestras': n}
                    for p, z, s, prom, n in filas])
