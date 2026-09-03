import uuid
from app.extensions import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum

estado_pedido_enum = Enum(
    'BORRADOR',
    'SOLICITADO',
    'CONFIRMADO',
    'EN_TRANSITO',
    'ENTREGADO',
    'CANCELADO',
    name='estado_pedido',
)

class PedidoAbasto(db.Model):
    __tablename__ = 'pedidos_abasto'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    proveedor_id = db.Column(UUID(as_uuid=True), db.ForeignKey('proveedores.id'), nullable=False)
    estado = db.Column(estado_pedido_enum, default='BORRADOR')
    fecha_solicitud = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_confirmacion = db.Column(db.DateTime)
    fecha_entrega_estimada = db.Column(db.DateTime)
    fecha_entrega_real = db.Column(db.DateTime)
    subtotal = db.Column(db.Numeric(12, 2))
    iva = db.Column(db.Numeric(12, 2))
    total = db.Column(db.Numeric(12, 2))
    notas = db.Column(db.Text)
    usuario_creacion_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    comercio = db.relationship('Comercio', back_populates='pedidos')
    proveedor = db.relationship('Proveedor', back_populates='pedidos')
    detalles = db.relationship('DetallePedido', back_populates='pedido', cascade="all, delete-orphan")

class DetallePedido(db.Model):
    __tablename__ = 'detalle_pedidos'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    pedido_id = db.Column(UUID(as_uuid=True), db.ForeignKey('pedidos_abasto.id', ondelete='CASCADE'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    unidad_medida = db.Column(db.String(50))
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    notas = db.Column(db.Text)

    pedido = db.relationship('PedidoAbasto', back_populates='detalles')
    producto = db.relationship('ProductoMaestro', back_populates='detalles_pedido')
