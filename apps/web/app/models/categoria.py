from app.extensions import db


class Categoria(db.Model):
    __tablename__ = 'categorias'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    icono = db.Column(db.String(100))
    orden = db.Column(db.Integer, default=0)
    activa = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    productos = db.relationship('ProductoMaestro', back_populates='categoria')
