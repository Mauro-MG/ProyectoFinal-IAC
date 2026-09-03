from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from redis.exceptions import RedisError
from sqlalchemy import case, cast, func
from app.extensions import db
from app.models.precio import PrecioComercio
from app.models.producto import ProductoMaestro
from app.models.comercio import Comercio
from app.models.zona import ZonaMunicipal
from app.blueprints.precios.forms import PrecioForm
from app.utils.audit import registrar_evento
from app.utils.decorators import role_required

precios_bp = Blueprint('precios', __name__)

@precios_bp.route('/')
@login_required
def comparacion():
    producto_id = request.args.get('producto_id', type=int)
    tipo_comercio_text = cast(Comercio.tipo_comercio, db.String)
    sector_expr = case(
        (tipo_comercio_text.like('FORMAL%'), 'Formal'),
        (tipo_comercio_text.like('INFORMAL%'), 'Informal'),
        else_='Mayorista',
    )

    query = (
        db.session.query(
            ProductoMaestro.id.label('producto_id'),
            ProductoMaestro.nombre.label('producto'),
            ZonaMunicipal.nombre.label('zona'),
            sector_expr.label('sector'),
            func.avg(PrecioComercio.precio).label('promedio'),
            func.min(PrecioComercio.precio).label('minimo'),
            func.max(PrecioComercio.precio).label('maximo'),
            func.count(PrecioComercio.id).label('muestras'),
        )
        .join(ProductoMaestro, PrecioComercio.producto_id == ProductoMaestro.id)
        .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
        .outerjoin(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
        .filter(
            PrecioComercio.activo.is_(True),
            PrecioComercio.estado_validacion == 'VALIDADO',
        )
        .group_by(ProductoMaestro.id, ProductoMaestro.nombre, ZonaMunicipal.nombre, sector_expr)
        .order_by(ProductoMaestro.nombre, ZonaMunicipal.nombre, sector_expr)
    )

    if producto_id:
        query = query.filter(ProductoMaestro.id == producto_id)

    resumen = query.all()
    productos = ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre).all()
    return render_template(
        'precios/comparacion.html',
        resumen=resumen,
        productos=productos,
        producto_id=producto_id,
    )

@precios_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
@role_required('Administrador General', 'Comerciante Informal', 'Minorista Formal')
def registrar():
    form = PrecioForm()
    
    if current_user.rol.nombre in ['Administrador General']:
        comercios = Comercio.query.filter_by(activo=True).all()
    else:
        comercios = Comercio.query.filter_by(usuario_id=current_user.id, activo=True).all()
        
    form.comercio_id.choices = [(str(c.id), c.nombre_comercio) for c in comercios]
    form.producto_id.choices = [(p.id, p.nombre) for p in ProductoMaestro.query.filter_by(activo=True).all()]
    if not comercios:
        flash('Primero debes registrar un comercio activo para capturar precios.', 'warning')
    
    if form.validate_on_submit():
        comercio_id = UUID(form.comercio_id.data)
        precio_nuevo = Decimal(form.precio.data)
        fecha_limite = datetime.utcnow() - timedelta(days=7)

        ultimo_precio = PrecioComercio.query.filter_by(
            comercio_id=comercio_id,
            producto_id=form.producto_id.data
        ).order_by(PrecioComercio.fecha_registro.desc()).first()

        precio_ant = ultimo_precio.precio if ultimo_precio else None
        comercio = db.session.get(Comercio, comercio_id)
        promedio_regional = None

        if comercio and comercio.zona_id:
            promedio_regional = (
                db.session.query(func.avg(PrecioComercio.precio))
                .join(Comercio, PrecioComercio.comercio_id == Comercio.id)
                .filter(
                    Comercio.zona_id == comercio.zona_id,
                    PrecioComercio.producto_id == form.producto_id.data,
                    PrecioComercio.fecha_registro >= fecha_limite,
                    PrecioComercio.activo.is_(True),
                    PrecioComercio.estado_validacion == 'VALIDADO',
                )
                .scalar()
            )

        estado_validacion = 'VALIDADO'
        notas = None
        if promedio_regional:
            promedio_decimal = Decimal(promedio_regional)
            limite_superior = promedio_decimal * Decimal('1.50')
            limite_inferior = promedio_decimal * Decimal('0.10')
            if precio_nuevo > limite_superior or precio_nuevo < limite_inferior:
                estado_validacion = 'PENDIENTE_VALIDACION'
                notas = 'Precio fuera del umbral regional de 7 días; requiere revisión.'
        
        precio = PrecioComercio(
            comercio_id=comercio_id,
            producto_id=form.producto_id.data,
            precio=precio_nuevo,
            precio_anterior=precio_ant,
            estado_validacion=estado_validacion,
            usuario_registro_id=current_user.id,
            notas=notas,
        )
        db.session.add(precio)
        db.session.commit()

        if comercio and comercio.zona_id:
            try:
                from app.extensions import redis_client
                redis_client.setex(
                    f"precio_promedio:zona:{comercio.zona_id}:producto:{form.producto_id.data}",
                    int(current_app.config.get('PRECIO_PROMEDIO_TTL_SEGUNDOS', 14400)),
                    str(promedio_regional or precio_nuevo),
                )
            except (AttributeError, RedisError):
                current_app.logger.warning('No se pudo actualizar la caché de precios en Redis.')
        
        registrar_evento(
            current_user.id,
            'CREACION',
            'PrecioComercio',
            precio.id,
            'Precio registrado',
            datos_nuevos={
                'precio': str(precio_nuevo),
                'producto_id': form.producto_id.data,
                'comercio_id': str(comercio_id),
                'estado_validacion': estado_validacion,
            },
        )
        if estado_validacion == 'PENDIENTE_VALIDACION':
            flash('Precio registrado como pendiente de validación por salir del umbral regional.', 'warning')
        else:
            flash('Precio registrado exitosamente', 'success')
        return redirect(url_for('precios.comparacion'))
        
    return render_template('precios/registrar.html', form=form)
