from sqlalchemy.dialects.postgresql import UUID

from abasto_dominio.extensiones import db


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


class Promocion(db.Model):
    """Precio promocional de un producto de un comercio durante un periodo."""
    __tablename__ = 'promociones'

    id = db.Column(db.BigInteger, primary_key=True)
    inventario_id = db.Column(db.BigInteger, db.ForeignKey('inventario_comercio.id'), nullable=False)
    precio_promocional = db.Column(db.Numeric(10, 2), nullable=False)
    descripcion = db.Column(db.String(255))
    inicio = db.Column(db.Date, nullable=False)
    fin = db.Column(db.Date, nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    inventario = db.relationship('InventarioComercio')
