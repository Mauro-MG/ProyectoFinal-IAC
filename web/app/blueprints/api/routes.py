from datetime import datetime
from functools import wraps
from hashlib import sha256
from uuid import UUID

import jwt
from flask import Blueprint, current_app, jsonify, request
from redis.exceptions import RedisError
from sqlalchemy import case, cast, func

from app.extensions import db
from app.models.comercio import Comercio
from app.models.precio import PrecioComercio
from app.models.producto import ProductoMaestro
from app.models.usuario import Usuario
from app.models.zona import ZonaMunicipal
from app.utils.audit import registrar_evento

api_bp = Blueprint('api', __name__)


def token_blacklist_key(token):
    return f"jwt:blacklist:{sha256(token.encode('utf-8')).hexdigest()}"


def jwt_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify(error='Token JWT requerido'), 401

        token = auth_header.removeprefix('Bearer ').strip()
        try:
            from app.extensions import redis_client
            if redis_client and redis_client.exists(token_blacklist_key(token)):
                return jsonify(error='Token JWT revocado'), 401
        except RedisError:
            current_app.logger.warning('No se pudo consultar Redis para validar el JWT.')

        try:
            payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify(error='Token JWT expirado'), 401
        except jwt.InvalidTokenError:
            return jsonify(error='Token JWT inválido'), 401

        try:
            usuario_id = UUID(payload.get('user_id'))
        except (TypeError, ValueError):
            return jsonify(error='Token JWT inválido'), 401

        usuario = db.session.get(Usuario, usuario_id)
        if not usuario or not usuario.activo:
            return jsonify(error='Usuario no autorizado'), 401

        request.api_user = usuario
        return view(*args, **kwargs)
    return wrapped


@api_bp.route('/auth/token', methods=['POST'])
def generar_token():
    data = request.get_json(silent=True) or {}
    usuario = Usuario.query.filter_by(email=data.get('email'), activo=True).first()

    if not usuario or not usuario.check_password(data.get('password', '')):
        return jsonify(error='Credenciales inválidas'), 401

    token = jwt.encode(
        {
            'user_id': str(usuario.id),
            'rol': usuario.rol.nombre,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES'],
        },
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256',
    )
    registrar_evento(usuario.id, 'LOGIN', 'Usuario', usuario.id, 'Token JWT emitido para API')
    return jsonify(access_token=token, token_type='Bearer')


@api_bp.route('/me')
@jwt_required
def me():
    usuario = request.api_user
    return jsonify(
        id=str(usuario.id),
        email=usuario.email,
        nombre=usuario.nombre,
        rol=usuario.rol.nombre,
    )


@api_bp.route('/precios/resumen')
@jwt_required
def resumen_precios():
    tipo_comercio_text = cast(Comercio.tipo_comercio, db.String)
    sector_expr = case(
        (tipo_comercio_text.like('FORMAL%'), 'Formal'),
        (tipo_comercio_text.like('INFORMAL%'), 'Informal'),
        else_='Mayorista',
    )
    filas = (
        db.session.query(
            ProductoMaestro.nombre.label('producto'),
            ZonaMunicipal.nombre.label('zona'),
            sector_expr.label('sector'),
            func.avg(PrecioComercio.precio).label('promedio'),
            func.count(PrecioComercio.id).label('muestras'),
        )
        .join(ProductoMaestro, PrecioComercio.producto_id == ProductoMaestro.id)
        .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
        .outerjoin(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
        .filter(
            PrecioComercio.activo.is_(True),
            PrecioComercio.estado_validacion == 'VALIDADO',
        )
        .group_by(ProductoMaestro.nombre, ZonaMunicipal.nombre, sector_expr)
        .order_by(ProductoMaestro.nombre, ZonaMunicipal.nombre, sector_expr)
        .all()
    )

    return jsonify([
        {
            'producto': fila.producto,
            'zona': fila.zona,
            'sector': fila.sector,
            'promedio': float(fila.promedio),
            'muestras': fila.muestras,
        }
        for fila in filas
    ])
