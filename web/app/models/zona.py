from app.extensions import db
from datetime import datetime

class ZonaMunicipal(db.Model):
    __tablename__ = 'zonas_municipales'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(100), nullable=False)
    municipio = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(100), nullable=False)
    codigo_postal = db.Column(db.String(10))
    latitud_centro = db.Column(db.Numeric(10, 8))
    longitud_centro = db.Column(db.Numeric(11, 8))
    radio_km = db.Column(db.Numeric(5, 2))
    activa = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comercios = db.relationship('Comercio', back_populates='zona')
