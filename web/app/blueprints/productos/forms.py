from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired

class ProductoForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired()])
    descripcion = TextAreaField('Descripción')
    categoria_id = SelectField('Categoría', coerce=int, validators=[DataRequired()])
    unidad_medida = StringField('Unidad de Medida', validators=[DataRequired()])
    es_canasta_basica = BooleanField('Es de Canasta Básica')
    submit = SubmitField('Guardar')
