from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db


class Rol(db.Model):
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    permisos = db.Column(JSONB, nullable=False, default=list)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now())

    usuarios = db.relationship('Usuario', back_populates='rol')
