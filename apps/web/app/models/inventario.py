from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db

tipo_movimiento_enum = Enum('ENTRADA', 'SALIDA', 'AJUSTE', name='tipo_movimiento', create_type=False)


class InventarioComercio(db.Model):
    """Producto del catálogo maestro que vende un comercio, con su existencia y precio."""
    __tablename__ = 'inventario_comercio'

    id = db.Column(db.BigInteger, primary_key=True)
    comercio_id = db.Column(UUID(as_uuid=True), db.ForeignKey('comercios.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    existencia = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stock_minimo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stock_maximo = db.Column(db.Numeric(10, 2))
    precio_venta = db.Column(db.Numeric(10, 2))
    # Columna generada en PostgreSQL: DISPONIBLE, BAJO o AGOTADO
    estado = db.Column(db.String(12), db.Computed(
        "CASE WHEN existencia <= 0 THEN 'AGOTADO' "
        "WHEN existencia <= stock_minimo THEN 'BAJO' ELSE 'DISPONIBLE' END"
    ))
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.FetchedValue())

    comercio = db.relationship('Comercio', back_populates='inventario')
    producto = db.relationship('ProductoMaestro')
    movimientos = db.relationship('MovimientoInventario', back_populates='inventario',
                                  order_by='MovimientoInventario.created_at.desc()', lazy='dynamic')

    @property
    def cantidad_sugerida(self):
        """Lo que falta para llegar al stock máximo (o al doble del mínimo si no hay máximo)."""
        objetivo = self.stock_maximo if self.stock_maximo else self.stock_minimo * 2
        return max(objetivo - self.existencia, 0)


class MovimientoInventario(db.Model):
    __tablename__ = 'movimientos_inventario'

    id = db.Column(db.BigInteger, primary_key=True)
    inventario_id = db.Column(db.BigInteger, db.ForeignKey('inventario_comercio.id'), nullable=False)
    tipo = db.Column(tipo_movimiento_enum, nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    existencia_anterior = db.Column(db.Numeric(10, 2), nullable=False)
    existencia_nueva = db.Column(db.Numeric(10, 2), nullable=False)
    motivo = db.Column(db.String(255))
    pedido_id = db.Column(UUID(as_uuid=True), db.ForeignKey('pedidos_abasto.id'))
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey('usuarios.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    inventario = db.relationship('InventarioComercio', back_populates='movimientos')
    usuario = db.relationship('Usuario')
