from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


class PrecioComercio(db.Model):
    """Historial de precios al consumidor."""
    __tablename__ = 'precios_comercio'

    id = db.Column(db.BigInteger, primary_key=True)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    precio_anterior = db.Column(db.Numeric(10, 2))
    fecha_registro = db.Column(db.DateTime, server_default=db.func.now())
    metodo_captura = db.Column(db.String(20), default='MANUAL')
    estado_validacion = db.Column(db.String(30), default='VALIDADO')
    usuario_registro_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    notas = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)

    comercio = db.relationship('Comercio')
    producto = db.relationship('ProductoMaestro')


class PrecioMayoreo(db.Model):
    """Historial de precios de mayoreo publicados por los proveedores."""
    __tablename__ = 'precios_mayoreo'

    id = db.Column(db.BigInteger, primary_key=True)
    proveedor_id = db.Column(UUID(as_uuid=True), db.ForeignKey('proveedores.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    fecha_registro = db.Column(db.DateTime, server_default=db.func.now())
