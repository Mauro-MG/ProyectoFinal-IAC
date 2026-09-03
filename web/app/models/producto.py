from app.extensions import db
from datetime import datetime

class ProductoMaestro(db.Model):
    __tablename__ = 'productos_maestros'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)
    unidad_medida = db.Column(db.String(50), nullable=False)
    codigo_barras = db.Column(db.String(100))
    imagen_url = db.Column(db.String(255))
    es_canasta_basica = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    categoria = db.relationship('Categoria', back_populates='productos')
    precios = db.relationship('PrecioComercio', back_populates='producto')
    detalles_pedido = db.relationship('DetallePedido', back_populates='producto')
