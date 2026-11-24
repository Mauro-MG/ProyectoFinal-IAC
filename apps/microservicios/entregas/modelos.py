"""Tablas propias de ms-entregas (ver db/postgres/04_servicios.sql)."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from abasto_dominio.extensiones import db


class Entrega(db.Model):
    __tablename__ = 'entregas'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pedido_id = db.Column(UUID(as_uuid=True), nullable=False, unique=True)   # de ms-pedidos
    proveedor_id = db.Column(UUID(as_uuid=True), db.ForeignKey('proveedores.id'), nullable=False)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    estado = db.Column(db.String(16), nullable=False, default='PROGRAMADA')
    responsable_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    responsable_nombre = db.Column(db.String(150))
    vehiculo = db.Column(db.String(100))
    fecha_estimada = db.Column(db.Date)
    fecha_salida = db.Column(db.DateTime)
    fecha_entrega = db.Column(db.DateTime)
    codigo_confirmacion = db.Column(db.String(12), nullable=False)
    recibido_por = db.Column(db.String(150))
    evidencia_archivo_id = db.Column(db.String(24))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    proveedor = db.relationship('Proveedor')
    comercio = db.relationship('Comercio')
    eventos = db.relationship('EventoEntrega', order_by='EventoEntrega.id')
    incidencias = db.relationship('IncidenciaEntrega', order_by='IncidenciaEntrega.id', back_populates='entrega')


class EventoEntrega(db.Model):
    __tablename__ = 'eventos_entrega'

    id = db.Column(db.BigInteger, primary_key=True)
    entrega_id = db.Column(UUID(as_uuid=True), db.ForeignKey('entregas.id'), nullable=False)
    estado = db.Column(db.String(16), nullable=False)
    comentario = db.Column(db.String(500))
    latitud = db.Column(db.Numeric(10, 7))
    longitud = db.Column(db.Numeric(10, 7))
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class IncidenciaEntrega(db.Model):
    __tablename__ = 'incidencias_entrega'

    id = db.Column(db.BigInteger, primary_key=True)
    entrega_id = db.Column(UUID(as_uuid=True), db.ForeignKey('entregas.id'), nullable=False)
    tipo = db.Column(db.String(16), nullable=False)
    descripcion = db.Column(db.String(500), nullable=False)
    estado = db.Column(db.String(10), nullable=False, default='ABIERTA')
    resolucion = db.Column(db.String(500))
    reportada_por = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    resuelta_at = db.Column(db.DateTime)

    entrega = db.relationship('Entrega', back_populates='incidencias')
