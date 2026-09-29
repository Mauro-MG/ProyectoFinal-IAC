import uuid

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db

ESTADOS_PEDIDO = {
    'BORRADOR': 'Borrador',
    'ENVIADO': 'Enviado al proveedor',
    'ACEPTADO': 'Aceptado',
    'EN_PREPARACION': 'En preparación',
    'ENVIADO_A_COMERCIO': 'En camino',
    'ENTREGADO': 'Entregado',
    'CANCELADO': 'Cancelado',
    'RECHAZADO': 'Rechazado',
}

estado_pedido_enum = Enum(*ESTADOS_PEDIDO, name='estado_pedido', create_type=False)


class PedidoAbasto(db.Model):
    __tablename__ = 'pedidos_abasto'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # BIGSERIAL en la base de datos; se usa como número de pedido legible
    folio = db.Column(db.BigInteger, unique=True, server_default=db.FetchedValue())
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    proveedor_id = db.Column(UUID(as_uuid=True), db.ForeignKey('proveedores.id'), nullable=False)
    estado = db.Column(estado_pedido_enum, nullable=False, default='BORRADOR')
    fecha_envio = db.Column(db.DateTime)
    fecha_respuesta = db.Column(db.DateTime)
    fecha_entrega_estimada = db.Column(db.Date)
    fecha_entrega_real = db.Column(db.DateTime)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    comision_plataforma = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    motivo_rechazo = db.Column(db.Text)
    notas = db.Column(db.Text)
    usuario_creacion_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now())

    comercio = db.relationship('Comercio', back_populates='pedidos')
    proveedor = db.relationship('Proveedor', back_populates='pedidos')
    detalles = db.relationship('DetallePedido', back_populates='pedido', cascade='all, delete-orphan',
                               order_by='DetallePedido.id')
    historial = db.relationship('HistorialPedido', back_populates='pedido', cascade='all, delete-orphan',
                                order_by='HistorialPedido.created_at')

    @property
    def folio_legible(self):
        return f'PED-{self.folio:05d}' if self.folio else 'PED-nuevo'

    @property
    def estado_legible(self):
        return ESTADOS_PEDIDO.get(self.estado, self.estado)

    def recalcular_subtotal(self):
        self.subtotal = sum((d.subtotal for d in self.detalles), 0)


class DetallePedido(db.Model):
    __tablename__ = 'detalle_pedidos'

    id = db.Column(db.BigInteger, primary_key=True)
    pedido_id = db.Column(UUID(as_uuid=True), db.ForeignKey('pedidos_abasto.id', ondelete='CASCADE'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    pedido = db.relationship('PedidoAbasto', back_populates='detalles')
    producto = db.relationship('ProductoMaestro')


class HistorialPedido(db.Model):
    __tablename__ = 'historial_pedido'

    id = db.Column(db.BigInteger, primary_key=True)
    pedido_id = db.Column(UUID(as_uuid=True), db.ForeignKey('pedidos_abasto.id', ondelete='CASCADE'), nullable=False)
    estado_anterior = db.Column(estado_pedido_enum)
    estado_nuevo = db.Column(estado_pedido_enum, nullable=False)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    comentario = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    pedido = db.relationship('PedidoAbasto', back_populates='historial')
    usuario = db.relationship('Usuario')
