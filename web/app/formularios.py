from flask_wtf import FlaskForm
from wtforms import (BooleanField, DecimalField, IntegerField, PasswordField, SelectField, SelectMultipleField,
                     StringField, TextAreaField, TimeField, widgets)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, ValidationError

from app.models.comercio import TIPOS_COMERCIO

UNIDADES = [('pieza', 'pieza'), ('kg', 'kg'), ('litro', 'litro'), ('paquete', 'paquete'), ('caja', 'caja')]

# Perfiles que una persona puede elegir al registrarse; los demás los asigna el administrador
PERFILES_REGISTRO = [
    ('Comerciante Informal', 'Comerciante informal (tianguis, mercado, puesto)'),
    ('Minorista Formal', 'Tienda establecida (abarrotes, minisúper, recaudería)'),
    ('Proveedor', 'Proveedor o mayorista'),
]


class CasillasMultiples(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class LoginForm(FlaskForm):
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])


class RegistroForm(FlaskForm):
    perfil = SelectField('¿Qué tipo de cuenta necesitas?', choices=PERFILES_REGISTRO)
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    apellido_paterno = StringField('Apellido', validators=[DataRequired(), Length(max=100)])
    telefono = StringField('Teléfono (opcional)', validators=[Optional(), Length(max=20)])
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=8, message='Mínimo 8 caracteres')])
    confirmar = PasswordField('Confirmar contraseña', validators=[EqualTo('password', message='No coinciden')])


class RecuperarForm(FlaskForm):
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])


class ComercioForm(FlaskForm):
    nombre_comercio = StringField('Nombre del comercio', validators=[DataRequired(), Length(max=255)])
    tipo_comercio = SelectField('Tipo', choices=[(k, v) for k, v in TIPOS_COMERCIO.items() if k != 'MAYORISTA'])
    descripcion = TextAreaField('Descripción', validators=[Optional()])
    direccion = StringField('Dirección o referencia', validators=[DataRequired(), Length(max=255)])
    colonia = StringField('Colonia', validators=[Optional(), Length(max=100)])
    municipio = StringField('Municipio', validators=[DataRequired(), Length(max=100)])
    estado = StringField('Estado', default='Nuevo León', validators=[DataRequired(), Length(max=100)])
    zona_id = SelectField('Zona', coerce=int, validators=[Optional()])
    latitud = DecimalField('Latitud', places=7, validators=[Optional(), NumberRange(-90, 90)])
    longitud = DecimalField('Longitud', places=7, validators=[Optional(), NumberRange(-180, 180)])
    telefono_comercio = StringField('Teléfono', validators=[Optional(), Length(max=20)])
    horario_apertura = TimeField('Abre', validators=[Optional()])
    horario_cierre = TimeField('Cierra', validators=[Optional()])


class ProductoForm(FlaskForm):
    nombre = StringField('Nombre y presentación', validators=[DataRequired(), Length(max=200)])
    descripcion = TextAreaField('Descripción', validators=[Optional()])
    categoria_id = SelectField('Categoría', coerce=int)
    unidad_medida = SelectField('Unidad de venta', choices=UNIDADES)
    codigo_barras = StringField('Código de barras', validators=[Optional(), Length(max=50)])
    es_canasta_basica = BooleanField('Forma parte de la canasta básica')


class CategoriaForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    descripcion = StringField('Descripción', validators=[Optional()])


class ZonaForm(FlaskForm):
    nombre = StringField('Nombre de la zona', validators=[DataRequired(), Length(max=100)])
    municipio = StringField('Municipio', validators=[DataRequired(), Length(max=100)])
    estado = StringField('Estado', default='Nuevo León', validators=[DataRequired()])
    latitud_centro = DecimalField('Latitud del centro', places=7, validators=[DataRequired(), NumberRange(-90, 90)])
    longitud_centro = DecimalField('Longitud del centro', places=7,
                                   validators=[DataRequired(), NumberRange(-180, 180)])
    radio_km = DecimalField('Radio (km)', places=2, validators=[DataRequired(), NumberRange(0.1, 50)])
    poblacion = IntegerField('Población estimada', validators=[DataRequired(), NumberRange(min=0)])
    activa = BooleanField('Activa', default=True)


class InventarioForm(FlaskForm):
    stock_minimo = DecimalField('Stock mínimo', places=2, validators=[DataRequired(), NumberRange(min=0)])
    stock_maximo = DecimalField('Stock máximo', places=2, validators=[Optional(), NumberRange(min=0)])
    precio_venta = DecimalField('Precio de venta', places=2, validators=[Optional(), NumberRange(min=0.01)])

    def validate_stock_maximo(self, campo):
        if campo.data is not None and self.stock_minimo.data is not None and campo.data < self.stock_minimo.data:
            raise ValidationError('Debe ser mayor o igual al mínimo.')


class MovimientoForm(FlaskForm):
    tipo = SelectField('Movimiento', choices=[
        ('ENTRADA', 'Entrada (compra o surtido)'),
        ('SALIDA', 'Salida (venta)'),
        ('AJUSTE', 'Ajuste por conteo físico'),
    ])
    cantidad = DecimalField('Cantidad', places=2, validators=[DataRequired(), NumberRange(min=0)])
    motivo = StringField('Motivo', validators=[Optional(), Length(max=255)])


class ProveedorForm(FlaskForm):
    nombre_empresa = StringField('Nombre comercial', validators=[DataRequired(), Length(max=255)])
    rfc = StringField('RFC', validators=[Optional(), Length(min=12, max=13)])
    descripcion = TextAreaField('¿Qué vendes?', validators=[Optional()])
    telefono_contacto = StringField('Teléfono', validators=[Optional(), Length(max=20)])
    email_contacto = StringField('Correo de contacto', validators=[Optional(), Email()])
    direccion = StringField('Dirección de bodega', validators=[Optional(), Length(max=255)])
    municipio = StringField('Municipio', validators=[Optional(), Length(max=100)])
    latitud = DecimalField('Latitud', places=7, validators=[Optional(), NumberRange(-90, 90)])
    longitud = DecimalField('Longitud', places=7, validators=[Optional(), NumberRange(-180, 180)])
    pedido_minimo = DecimalField('Pedido mínimo ($)', places=2, default=0, validators=[NumberRange(min=0)])
    tiempo_entrega_dias = IntegerField('Tiempo de entrega (días)', default=1, validators=[NumberRange(min=0, max=30)])
    condiciones_venta = TextAreaField('Condiciones de venta', validators=[Optional()])
    zonas = CasillasMultiples('Zonas donde entregas', coerce=int)


class OfertaForm(FlaskForm):
    producto_id = SelectField('Producto', coerce=int)
    precio_mayoreo = DecimalField('Precio de mayoreo (por unidad)', places=2,
                                  validators=[DataRequired(), NumberRange(min=0.01)])
    cantidad_minima = DecimalField('Venta mínima', places=2, default=1, validators=[DataRequired(), NumberRange(min=0.01)])
    existencia_disponible = DecimalField('Existencia disponible', places=2, default=0,
                                         validators=[Optional(), NumberRange(min=0)])


class UsuarioAdminForm(FlaskForm):
    rol_id = SelectField('Rol', coerce=int)
    activo = BooleanField('Cuenta activa')


class RestablecerForm(FlaskForm):
    password = PasswordField('Nueva contraseña', validators=[DataRequired(), Length(min=8, message='Mínimo 8 caracteres')])
    confirmar = PasswordField('Confirmar contraseña', validators=[EqualTo('password', message='No coinciden')])
