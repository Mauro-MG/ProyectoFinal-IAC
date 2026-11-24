"""Tablas propias de ms-ventas (ver db/postgres/04_servicios.sql). Ningún otro servicio escribe en ellas."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from abasto_dominio.extensiones import db


class Venta(db.Model):
    __tablename__ = 'ventas'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folio = db.Column(db.BigInteger, server_default=db.FetchedValue(), unique=True)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    total = db.Column(db.Numeric(12, 2), nullable=False)
    metodo_pago = db.Column(db.String(15), nullable=False, default='EFECTIVO')
    estado = db.Column(db.String(18), nullable=False, default='REGISTRADA')
    origen = db.Column(db.String(12), nullable=False, default='web')
    id_cliente = db.Column(db.String(64), unique=True)
    fecha_venta = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    comercio = db.relationship('Comercio')
    partidas = db.relationship('DetalleVenta', back_populates='venta', order_by='DetalleVenta.id')
    devoluciones = db.relationship('Devolucion', back_populates='venta', order_by='Devolucion.id')

    @property
    def folio_legible(self):
        return f'V-{self.folio:06d}' if self.folio else None


class DetalleVenta(db.Model):
    __tablename__ = 'detalle_ventas'

    id = db.Column(db.BigInteger, primary_key=True)
    venta_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ventas.id'), nullable=False)
    inventario_id = db.Column(db.BigInteger, db.ForeignKey('inventario_comercio.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    cantidad_devuelta = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    venta = db.relationship('Venta', back_populates='partidas')
    producto = db.relationship('ProductoMaestro')


class Devolucion(db.Model):
    __tablename__ = 'devoluciones'

    id = db.Column(db.BigInteger, primary_key=True)
    venta_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ventas.id'), nullable=False)
    motivo = db.Column(db.String(255), nullable=False)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    venta = db.relationship('Venta', back_populates='devoluciones')
    partidas = db.relationship('DetalleDevolucion', back_populates='devolucion')


class DetalleDevolucion(db.Model):
    __tablename__ = 'detalle_devoluciones'

    id = db.Column(db.BigInteger, primary_key=True)
    devolucion_id = db.Column(db.BigInteger, db.ForeignKey('devoluciones.id'), nullable=False)
    detalle_venta_id = db.Column(db.BigInteger, db.ForeignKey('detalle_ventas.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)

    devolucion = db.relationship('Devolucion', back_populates='partidas')
    detalle = db.relationship('DetalleVenta')
