from abasto_dominio.extensiones import db


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
    marca_id = db.Column(db.Integer, db.ForeignKey('marcas.id'))
    clave_estandar = db.Column(db.String(20))   # clasificación estandarizada
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now())

    categoria = db.relationship('Categoria', back_populates='productos')
    marca = db.relationship('Marca')
    variantes = db.relationship('VarianteProducto', back_populates='producto', order_by='VarianteProducto.nombre')


class UnidadMedida(db.Model):
    __tablename__ = 'unidades_medida'

    clave = db.Column(db.String(20), primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)


class Marca(db.Model):
    __tablename__ = 'marcas'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class VarianteProducto(db.Model):
    """Presentación de un producto (bolsa de 500 g, caja con 12) con su propio código de barras."""
    __tablename__ = 'variantes_producto'

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos_maestros.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    codigo_barras = db.Column(db.String(50), unique=True)
    factor = db.Column(db.Numeric(10, 3), nullable=False, default=1)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    producto = db.relationship('ProductoMaestro', back_populates='variantes')


equivalencias_producto = db.Table(
    'equivalencias_producto',
    db.Column('producto_id', db.Integer, db.ForeignKey('productos_maestros.id'), primary_key=True),
    db.Column('equivalente_id', db.Integer, db.ForeignKey('productos_maestros.id'), primary_key=True),
    db.Column('tipo', db.String(12), nullable=False, default='SUSTITUTO'),
    db.Column('created_at', db.DateTime, server_default=db.func.now()),
)
