from app.extensions import db


class ProductoMaestro(db.Model):
    __tablename__ = 'productos_maestros'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)
    unidad_medida = db.Column(db.String(20), nullable=False)
    codigo_barras = db.Column(db.String(50))
    imagen_url = db.Column(db.String(255))
    es_canasta_basica = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now())

    categoria = db.relationship('Categoria', back_populates='productos')
