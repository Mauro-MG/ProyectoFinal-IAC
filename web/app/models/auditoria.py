from app.extensions import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import INET

tipo_evento_enum = Enum(
    'CREACION',
    'LECTURA',
    'ACTUALIZACION',
    'ELIMINACION',
    'LOGIN',
    'LOGOUT',
    'ERROR',
    name='tipo_evento_auditoria',
)

class AuditoriaEvento(db.Model):
    __tablename__ = 'auditoria_eventos'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    tipo_evento = db.Column(tipo_evento_enum, nullable=False)
    entidad = db.Column(db.String(100), nullable=False)
    entidad_id = db.Column(db.String(255))
    descripcion = db.Column(db.Text)
    datos_anteriores = db.Column(JSONB)
    datos_nuevos = db.Column(JSONB)
    ip_address = db.Column(INET)
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
