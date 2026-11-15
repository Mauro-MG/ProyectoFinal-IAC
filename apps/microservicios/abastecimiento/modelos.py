"""Tablas propias de ms-abastecimiento (ver db/postgres/04_servicios.sql)."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from abasto_dominio.extensiones import db


class SolicitudCotizacion(db.Model):
    __tablename__ = 'solicitudes_cotizacion'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folio = db.Column(db.BigInteger, server_default=db.FetchedValue(), unique=True)
    zona_id = db.Column(db.Integer, db.ForeignKey('zonas_municipales.id'), nullable=False)
    creada_por = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False)
    titulo = db.Column(db.String(150), nullable=False)
    consolidada = db.Column(db.Boolean, nullable=False, default=False)
    estado = db.Column(db.String(12), nullable=False, default='ABIERTA')
    fecha_limite = db.Column(db.DateTime, nullable=False)
    notas = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    zona = db.relationship('ZonaMunicipal')
    necesidades = db.relationship('NecesidadSolicitud', back_populates='solicitud', order_by='NecesidadSolicitud.id')
    cotizaciones = db.relationship('Cotizacion', back_populates='solicitud', order_by='Cotizacion.created_at')

    @property
    def folio_legible(self):
        return f'COT-{self.folio:05d}' if self.folio else None


class NecesidadSolicitud(db.Model):
    __tablename__ = 'necesidades_solicitud'

    id = db.Column(db.BigInteger, primary_key=True)
    solicitud_id = db.Column(UUID(as_uuid=True), db.ForeignKey('solicitudes_cotizacion.id'), nullable=False)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    solicitud = db.relationship('SolicitudCotizacion', back_populates='necesidades')
    comercio = db.relationship('Comercio')
    producto = db.relationship('ProductoMaestro')


class Cotizacion(db.Model):
    __tablename__ = 'cotizaciones'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    solicitud_id = db.Column(UUID(as_uuid=True), db.ForeignKey('solicitudes_cotizacion.id'), nullable=False)
    proveedor_id = db.Column(UUID(as_uuid=True), db.ForeignKey('proveedores.id'), nullable=False)
    tiempo_entrega_dias = db.Column(db.Integer, nullable=False)
    vigencia = db.Column(db.Date, nullable=False)
    notas = db.Column(db.String(500))
    estado = db.Column(db.String(12), nullable=False, default='ENVIADA')
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    solicitud = db.relationship('SolicitudCotizacion', back_populates='cotizaciones')
    proveedor = db.relationship('Proveedor')
    partidas = db.relationship('PartidaCotizacion', back_populates='cotizacion', order_by='PartidaCotizacion.id')


class PartidaCotizacion(db.Model):
    __tablename__ = 'partidas_cotizacion'

    id = db.Column(db.BigInteger, primary_key=True)
    cotizacion_id = db.Column(UUID(as_uuid=True), db.ForeignKey('cotizaciones.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    cantidad_disponible = db.Column(db.Numeric(12, 2), nullable=False)

    cotizacion = db.relationship('Cotizacion', back_populates='partidas')
    producto = db.relationship('ProductoMaestro')


class OrdenCompra(db.Model):
    __tablename__ = 'ordenes_compra'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folio = db.Column(db.BigInteger, server_default=db.FetchedValue(), unique=True)
    solicitud_id = db.Column(UUID(as_uuid=True), db.ForeignKey('solicitudes_cotizacion.id'), nullable=False)
    cotizacion_id = db.Column(UUID(as_uuid=True), db.ForeignKey('cotizaciones.id'), nullable=False)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    proveedor_id = db.Column(UUID(as_uuid=True), db.ForeignKey('proveedores.id'), nullable=False)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    estado = db.Column(db.String(12), nullable=False, default='GENERADA')
    pedido_id = db.Column(UUID(as_uuid=True))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    comercio = db.relationship('Comercio')
    proveedor = db.relationship('Proveedor')
    solicitud = db.relationship('SolicitudCotizacion')
    partidas = db.relationship('PartidaOrden', back_populates='orden', order_by='PartidaOrden.id')

    @property
    def folio_legible(self):
        return f'OC-{self.folio:05d}' if self.folio else None


class PartidaOrden(db.Model):
    __tablename__ = 'partidas_orden'

    id = db.Column(db.BigInteger, primary_key=True)
    orden_id = db.Column(UUID(as_uuid=True), db.ForeignKey('ordenes_compra.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    orden = db.relationship('OrdenCompra', back_populates='partidas')
    producto = db.relationship('ProductoMaestro')
