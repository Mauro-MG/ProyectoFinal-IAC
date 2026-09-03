import uuid
from app.extensions import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID

class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False)
    nombre_empresa = db.Column(db.String(150), nullable=False)
    rfc = db.Column(db.String(20))
    tipo_productos = db.Column(db.String(255))
    zona_cobertura = db.Column(db.Text)
    telefono_contacto = db.Column(db.String(20))
    email_contacto = db.Column(db.String(120))
    direccion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario = db.relationship('Usuario', back_populates='proveedores')
    pedidos = db.relationship('PedidoAbasto', back_populates='proveedor')
