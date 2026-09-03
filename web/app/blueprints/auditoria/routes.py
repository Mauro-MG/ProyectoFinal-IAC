from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models.auditoria import AuditoriaEvento
from app.utils.decorators import role_required

auditoria_bp = Blueprint('auditoria', __name__)

@auditoria_bp.route('/')
@login_required
@role_required('Administrador General', 'Auditor')
def lista():
    page = request.args.get('page', 1, type=int)
    eventos = AuditoriaEvento.query.order_by(AuditoriaEvento.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('auditoria/lista.html', eventos=eventos)

@auditoria_bp.route('/<int:id>')
@login_required
@role_required('Administrador General', 'Auditor')
def detalle(id):
    evento = AuditoriaEvento.query.get_or_404(id)
    return render_template('auditoria/detalle.html', evento=evento)
