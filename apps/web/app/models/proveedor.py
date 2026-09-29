import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db

proveedor_zonas = db.Table(
    'proveedor_zonas',
    db.Column('proveedor_id', UUID(as_uuid=True), db.ForeignKey('proveedores.id'), primary_key=True),
    db.Column('zona_id', db.Integer, db.ForeignKey('zonas_municipales.id'), primary_key=True),
)


class Proveedor(db.Model):
    __tablename__ = 'proveedores'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False, unique=True)
    nombre_empresa = db.Column(db.String(255), nullable=False)
    rfc = db.Column(db.String(13))
    descripcion = db.Column(db.Text)
    telefono_contacto = db.Column(db.String(20))
    email_contacto = db.Column(db.String(255))
    direccion = db.Column(db.String(255))
    municipio = db.Column(db.String(100))
    latitud = db.Column(db.Numeric(10, 7))
    longitud = db.Column(db.Numeric(10, 7))
    pedido_minimo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tiempo_entrega_dias = db.Column(db.Integer, nullable=False, default=1)
    condiciones_venta = db.Column(db.Text)
    plan = db.Column(db.String(20), nullable=False, default='BASICO')
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now())

    usuario = db.relationship('Usuario', back_populates='proveedor')
    zonas = db.relationship('ZonaMunicipal', secondary=proveedor_zonas, order_by='ZonaMunicipal.nombre')
    catalogo = db.relationship('CatalogoProveedor', back_populates='proveedor')
    pedidos = db.relationship('PedidoAbasto', back_populates='proveedor')

    def cubre_zona(self, zona_id):
        return any(z.id == zona_id for z in self.zonas)


class CatalogoProveedor(db.Model):
    """Producto que ofrece un proveedor a precio de mayoreo."""
    __tablename__ = 'catalogo_proveedor'

    id = db.Column(db.BigInteger, primary_key=True)
    proveedor_id = db.Column(UUID(as_uuid=True), db.ForeignKey('proveedores.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    precio_mayoreo = db.Column(db.Numeric(10, 2), nullable=False)
    cantidad_minima = db.Column(db.Numeric(10, 2), nullable=False, default=1)
    existencia_disponible = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.FetchedValue())

    proveedor = db.relationship('Proveedor', back_populates='catalogo')
    producto = db.relationship('ProductoMaestro')
