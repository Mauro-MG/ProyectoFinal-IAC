import uuid

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from abasto_dominio.extensiones import db

TIPOS_COMERCIO = {
    'FORMAL_ABARROTES': 'Abarrotes',
    'FORMAL_MINISUPER': 'Minisúper',
    'FORMAL_RECAUDERIA': 'Recaudería',
    'INFORMAL_TIANGUIS': 'Puesto de tianguis',
    'INFORMAL_FIJO': 'Puesto fijo',
    'INFORMAL_AMBULANTE': 'Ambulante',
    'MAYORISTA': 'Mayorista',
}

tipo_comercio_enum = Enum(*TIPOS_COMERCIO, name='tipo_comercio', create_type=False)
estado_comercio_enum = Enum('PENDIENTE', 'VERIFICADO', 'SUSPENDIDO', 'RECHAZADO',
                            name='estado_comercio', create_type=False)


class Comercio(db.Model):
    __tablename__ = 'comercios'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False)
    nombre_comercio = db.Column(db.String(255), nullable=False)
    tipo_comercio = db.Column(tipo_comercio_enum, nullable=False)
    descripcion = db.Column(db.Text)
    direccion = db.Column(db.String(255), nullable=False)
    colonia = db.Column(db.String(100))
    municipio = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(100), nullable=False)
    codigo_postal = db.Column(db.String(10))
    latitud = db.Column(db.Numeric(10, 7))
    longitud = db.Column(db.Numeric(10, 7))
    telefono_comercio = db.Column(db.String(20))
    horario_apertura = db.Column(db.Time)
    horario_cierre = db.Column(db.Time)
    dias_operacion = db.Column(ARRAY(db.String))
    zona_id = db.Column(db.Integer, db.ForeignKey('zonas_municipales.id'))
    estado_registro = db.Column(estado_comercio_enum, default='PENDIENTE')
    verificado_por = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    fecha_verificacion = db.Column(db.DateTime)
    foto_url = db.Column(db.String(255))
    giro = db.Column(db.String(100))
    # Datos fiscales opcionales (los comercios informales normalmente no los tienen)
    rfc = db.Column(db.String(13))
    razon_social = db.Column(db.String(255))
    regimen_fiscal = db.Column(db.String(100))
    email_contacto = db.Column(db.String(255))
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now())

    usuario = db.relationship('Usuario', foreign_keys=[usuario_id], back_populates='comercios')
    zona = db.relationship('ZonaMunicipal', back_populates='comercios')
    inventario = db.relationship('InventarioComercio', back_populates='comercio')
    pedidos = db.relationship('PedidoAbasto', back_populates='comercio')
    responsables = db.relationship('ResponsableComercio', viewonly=True, order_by='ResponsableComercio.id',
                                   primaryjoin='and_(Comercio.id == ResponsableComercio.comercio_id, '
                                               'ResponsableComercio.activo.is_(True))')

    @property
    def sector(self):
        if self.tipo_comercio.startswith('FORMAL'):
            return 'Formal'
        if self.tipo_comercio.startswith('INFORMAL'):
            return 'Informal'
        return 'Mayorista'

    @property
    def tipo_legible(self):
        return TIPOS_COMERCIO.get(self.tipo_comercio, self.tipo_comercio)


class ResponsableComercio(db.Model):
    """Persona a cargo del comercio (dueño, encargado o empleado); puede o no tener cuenta."""
    __tablename__ = 'responsables_comercio'

    id = db.Column(db.BigInteger, primary_key=True)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    puesto = db.Column(db.String(20), nullable=False, default='ENCARGADO')
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(255))
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    comercio = db.relationship('Comercio')
