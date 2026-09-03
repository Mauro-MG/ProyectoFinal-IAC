from flask import Blueprint, render_template
from app.models.comercio import Comercio

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def index():
    return render_template('public/index.html')

@public_bp.route('/comercios-publico')
def comercios_publico():
    comercios = Comercio.query.filter_by(activo=True, estado_registro='VERIFICADO').limit(20).all()
    return render_template('public/comercios_publico.html', comercios=comercios)

@public_bp.route('/disponibilidad')
def disponibilidad():
    return render_template('public/disponibilidad.html')

@public_bp.route('/acerca')
def acerca():
    return render_template('public/acerca.html')
