from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


class ConfiguracionSistema(db.Model):
    __tablename__ = 'configuracion_sistema'

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(100), unique=True, nullable=False)
    valor = db.Column(db.Text)
    descripcion = db.Column(db.Text)
    tipo_dato = db.Column(db.String(20))
    updated_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_by = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
