from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired

class ComercioForm(FlaskForm):
    nombre_comercio = StringField('Nombre del Comercio', validators=[DataRequired()])
    tipo_comercio = SelectField(
        'Tipo de Comercio',
        choices=[
            ('FORMAL_ABARROTES', 'Formal - Abarrotes'),
            ('FORMAL_MINISUPER', 'Formal - Minisúper'),
            ('FORMAL_RECAUDERIA', 'Formal - Recaudería'),
            ('INFORMAL_TIANGUIS', 'Informal - Tianguis'),
            ('INFORMAL_FIJO', 'Informal - Puesto fijo'),
            ('INFORMAL_AMBULANTE', 'Informal - Ambulante'),
            ('MAYORISTA', 'Proveedor mayorista'),
        ],
        validators=[DataRequired()],
    )
    direccion = StringField('Dirección', validators=[DataRequired()])
    municipio = StringField('Municipio', validators=[DataRequired()])
    estado = StringField('Estado', validators=[DataRequired()])
    submit = SubmitField('Guardar')
