from app.extensions import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID

class PrecioComercio(db.Model):
    __tablename__ = 'precios_comercio'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    precio_anterior = db.Column(db.Numeric(10, 2))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    metodo_captura = db.Column(db.String(50))
    estado_validacion = db.Column(db.String(30), default='VALIDADO')
    usuario_registro_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'), nullable=False)
    notas = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)

    comercio = db.relationship('Comercio', back_populates='precios')
    producto = db.relationship('ProductoMaestro', back_populates='precios')
