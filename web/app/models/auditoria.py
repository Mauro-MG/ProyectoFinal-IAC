from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from app.extensions import db

TIPOS_EVENTO = ('CREACION', 'LECTURA', 'ACTUALIZACION', 'ELIMINACION',
                'CAMBIO_ESTADO', 'LOGIN', 'LOGOUT', 'ERROR')

tipo_evento_enum = Enum(*TIPOS_EVENTO, name='tipo_evento_auditoria', create_type=False)


class AuditoriaEvento(db.Model):
    __tablename__ = 'auditoria_eventos'

    id = db.Column(db.BigInteger, primary_key=True)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    tipo_evento = db.Column(tipo_evento_enum, nullable=False)
    entidad = db.Column(db.String(100), nullable=False)
    entidad_id = db.Column(db.String(100))
    descripcion = db.Column(db.Text)
    datos_anteriores = db.Column(JSONB)
    datos_nuevos = db.Column(JSONB)
    ip_address = db.Column(INET)
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    usuario = db.relationship('Usuario')
