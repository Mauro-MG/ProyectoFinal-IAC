"""Bitácora de auditoría (sólo lectura)."""
from datetime import datetime, timedelta

from flask import render_template, request
from flask_login import login_required

from app import app
from app.extensions import db
from app.models import AuditoriaEvento, Usuario
from app.models.auditoria import TIPOS_EVENTO
from app.permisos import permiso_requerido


@app.route('/auditoria')
@login_required
@permiso_requerido('auditoria.ver')
def auditoria_lista():
    consulta = AuditoriaEvento.query
    filtros = {
        'entidad': request.args.get('entidad') or None,
        'tipo': request.args.get('tipo') or None,
        'usuario': request.args.get('usuario', '').strip(),
        'desde': request.args.get('desde') or None,
        'hasta': request.args.get('hasta') or None,
    }
    if filtros['entidad']:
        consulta = consulta.filter(AuditoriaEvento.entidad == filtros['entidad'])
    if filtros['tipo']:
        consulta = consulta.filter(AuditoriaEvento.tipo_evento == filtros['tipo'])
    if filtros['usuario']:
        consulta = consulta.join(Usuario, AuditoriaEvento.usuario_id == Usuario.id) \
                           .filter(Usuario.email.ilike(f"%{filtros['usuario']}%"))
    try:
        if filtros['desde']:
            consulta = consulta.filter(AuditoriaEvento.created_at >= datetime.strptime(filtros['desde'], '%Y-%m-%d'))
        if filtros['hasta']:
            consulta = consulta.filter(AuditoriaEvento.created_at <
                                       datetime.strptime(filtros['hasta'], '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        pass

    entidades = [e for (e,) in db.session.query(AuditoriaEvento.entidad).distinct().order_by(AuditoriaEvento.entidad)]
    pagina = consulta.order_by(AuditoriaEvento.created_at.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=40, error_out=False)
    return render_template('auditoria/lista.html', pagina=pagina, filtros=filtros, entidades=entidades,
                           tipos=TIPOS_EVENTO)


@app.route('/auditoria/<int:id>')
@login_required
@permiso_requerido('auditoria.ver')
def auditoria_detalle(id):
    evento = db.get_or_404(AuditoriaEvento, id)
    relacionados = (AuditoriaEvento.query
                    .filter_by(entidad=evento.entidad, entidad_id=evento.entidad_id)
                    .order_by(AuditoriaEvento.created_at).all()) if evento.entidad_id else []
    return render_template('auditoria/detalle.html', evento=evento, relacionados=relacionados)
