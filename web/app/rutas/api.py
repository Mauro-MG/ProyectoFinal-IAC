"""
API JSON mínima del monolito, protegida con JWT + lista de revocación en Redis.

Es la base de lo que en el segundo parcial se separará en microservicios
(que además responderán en XML para la aplicación de escritorio).
"""
from functools import wraps
from uuid import UUID

import jwt
from flask import current_app, jsonify, request
from redis.exceptions import RedisError

from app import app, extensions
from app.extensions import csrf, db
from app.models import Comercio, InventarioComercio, PrecioComercio, ProductoMaestro, Usuario, ZonaMunicipal
from app.rutas.auth import clave_token_revocado, emitir_jwt
from app.servicios.auditoria import registrar_evento
from app.servicios.precios import SECTOR


def jwt_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        encabezado = request.headers.get('Authorization', '')
        if not encabezado.startswith('Bearer '):
            return jsonify(error='Token JWT requerido'), 401
        token = encabezado.removeprefix('Bearer ').strip()

        try:
            if extensions.redis_client.exists(clave_token_revocado(token)):
                return jsonify(error='Token JWT revocado'), 401
        except RedisError:
            # Sin Redis no se puede confirmar la revocación: se rechaza por seguridad
            return jsonify(error='Servicio de sesiones no disponible'), 503

        try:
            datos = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            usuario = db.session.get(Usuario, UUID(datos.get('user_id')))
        except jwt.ExpiredSignatureError:
            return jsonify(error='Token JWT expirado'), 401
        except (jwt.InvalidTokenError, TypeError, ValueError):
            return jsonify(error='Token JWT inválido'), 401

        if not usuario or not usuario.activo:
            return jsonify(error='Usuario no autorizado'), 401
        request.usuario_api = usuario
        request.token_api = token
        return vista(*args, **kwargs)
    return envoltura


@app.route('/api/auth/token', methods=['POST'])
@csrf.exempt
def api_token():
    datos = request.get_json(silent=True) or {}
    usuario = Usuario.query.filter_by(email=(datos.get('email') or '').strip().lower(), activo=True).first()
    if not usuario or not usuario.check_password(datos.get('password') or ''):
        return jsonify(error='Credenciales inválidas'), 401
    registrar_evento(usuario.id, 'LOGIN', 'Usuario', usuario.id, 'Token JWT emitido para la API')
    db.session.commit()
    return jsonify(access_token=emitir_jwt(usuario), token_type='Bearer',
                   expires_in=int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds()))


@app.route('/api/auth/logout', methods=['POST'])
@csrf.exempt
@jwt_requerido
def api_logout():
    try:
        extensions.redis_client.setex(clave_token_revocado(request.token_api),
                                      int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds()), '1')
    except RedisError:
        return jsonify(error='No se pudo revocar el token'), 503
    return jsonify(mensaje='Token revocado')


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
