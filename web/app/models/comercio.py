import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy import Enum

tipo_comercio_enum = Enum(
    'FORMAL_ABARROTES',
    'FORMAL_MINISUPER',
    'FORMAL_RECAUDERIA',
    'INFORMAL_TIANGUIS',
    'INFORMAL_FIJO',
    'INFORMAL_AMBULANTE',
    'MAYORISTA',
    name='tipo_comercio',
)
estado_comercio_enum = Enum('PENDIENTE', 'VERIFICADO', 'SUSPENDIDO', 'RECHAZADO', name='estado_comercio')

class Comercio(db.Model):
    __tablename__ = 'comercios'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False)
    nombre_comercio = db.Column(db.String(150), nullable=False)
    tipo_comercio = db.Column(tipo_comercio_enum, nullable=False)
    descripcion = db.Column(db.Text)
    direccion = db.Column(db.String(255), nullable=False)
    colonia = db.Column(db.String(100))
    municipio = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(100), nullable=False)
    codigo_postal = db.Column(db.String(10))
    latitud = db.Column(db.Numeric(10, 8))
    longitud = db.Column(db.Numeric(11, 8))
    telefono_comercio = db.Column(db.String(20))
    horario_apertura = db.Column(db.Time)
    horario_cierre = db.Column(db.Time)
    dias_operacion = db.Column(ARRAY(db.String))
    zona_id = db.Column(db.Integer, db.ForeignKey('zonas_municipales.id'))
    estado_registro = db.Column(estado_comercio_enum, default='PENDIENTE')
    verificado_por = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    fecha_verificacion = db.Column(db.DateTime)
    foto_url = db.Column(db.String(255))
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario = db.relationship('Usuario', foreign_keys=[usuario_id], back_populates='comercios')
    zona = db.relationship('ZonaMunicipal', back_populates='comercios')
    precios = db.relationship('PrecioComercio', back_populates='comercio')
    pedidos = db.relationship('PedidoAbasto', back_populates='comercio')
