from app.extensions import db


class ZonaMunicipal(db.Model):
    __tablename__ = 'zonas_municipales'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    municipio = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(100), nullable=False)
    codigo_postal = db.Column(db.String(10))
    latitud_centro = db.Column(db.Numeric(10, 7), nullable=False)
    longitud_centro = db.Column(db.Numeric(10, 7), nullable=False)
    radio_km = db.Column(db.Numeric(5, 2), nullable=False, default=2)
    poblacion = db.Column(db.Integer, nullable=False, default=0)
    activa = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    comercios = db.relationship('Comercio', back_populates='zona')

    def __str__(self):
        return f'{self.nombre} ({self.municipio})'
