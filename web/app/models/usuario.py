import uuid

import bcrypt
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    apellido_paterno = db.Column(db.String(100), nullable=False)
    apellido_materno = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    rol_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    email_verificado = db.Column(db.Boolean, default=False)
    ultimo_acceso = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now())

    rol = db.relationship('Rol', back_populates='usuarios')
    comercios = db.relationship('Comercio', foreign_keys='Comercio.usuario_id', back_populates='usuario')
    proveedor = db.relationship('Proveedor', back_populates='usuario', uselist=False)

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido_paterno}'

    @property
    def is_active(self):
        # Flask-Login no deja iniciar sesión a usuarios desactivados
        return bool(self.activo)

    def tiene_permiso(self, codigo):
        return bool(self.rol) and codigo in (self.rol.permisos or [])

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
