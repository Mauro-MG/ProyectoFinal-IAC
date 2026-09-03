from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.usuario import Usuario
from app.models.comercio import Comercio
from app.models.producto import ProductoMaestro
from app.models.precio import PrecioComercio

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/panel')
@login_required
def panel():
    stats = {}
    rol = current_user.rol.nombre
    
    if rol == 'Administrador General':
        stats['usuarios'] = Usuario.query.count()
        stats['comercios'] = Comercio.query.count()
        stats['productos'] = ProductoMaestro.query.count()
    elif rol in ['Comerciante Informal', 'Minorista Formal']:
        stats['mis_comercios'] = Comercio.query.filter_by(usuario_id=current_user.id).count()
    elif rol == 'Analista de Mercado':
        stats['comercios'] = Comercio.query.count()
        stats['productos'] = ProductoMaestro.query.count()
        stats['precios'] = PrecioComercio.query.count()
        
    return render_template('dashboard/panel.html', stats=stats)
