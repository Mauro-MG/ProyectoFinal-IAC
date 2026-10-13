"""Notificaciones internas en el web, servidas por ms-notificaciones."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from pymongo.errors import PyMongoError

from app import app
from app.microservicios import ServicioNoDisponible, llamar
from abasto_dominio.servicios import notificaciones as directo

TIPOS = {'pedido': 'Pedidos', 'stock_bajo': 'Stock bajo', 'precio_atipico': 'Precios en revisión',
         'comercio': 'Comercio', 'importacion': 'Importaciones', 'sistema': 'Sistema'}


@app.context_processor
def contador_notificaciones():
    """
    Número de la campana. Se lee en cada página, así que va directo al contador
    de Redis (notif:no_leidas:{usuario}) en lugar de hacer una llamada HTTP; el
    contador lo mantiene ms-notificaciones al crear o marcar avisos.
    """
    if not current_user.is_authenticated:
        return {}
    try:
        return {'avisos_sin_leer': directo.contar_no_leidas(current_user.id)}
    except PyMongoError:
        return {'avisos_sin_leer': None}


@app.route('/notificaciones')
@login_required
def notificaciones():
    pagina = request.args.get('page', 1, type=int)
    tipo = request.args.get('tipo') or None
    solo = request.args.get('solo_no_leidas') == '1'
    params = {'pagina': pagina, 'por_pagina': 20, 'solo_no_leidas': str(solo).lower()}
    if tipo:
        params['tipo'] = tipo
    fuente = 'ms-notificaciones'
    try:
        respuesta = llamar('notificaciones', 'GET', '/notificaciones', params=params)
        datos = respuesta.datos
        items, paginacion = datos.get('notificaciones', []), datos.get('paginacion', {})
    except ServicioNoDisponible:
        fuente = 'MongoDB (directo: el servicio no respondió)'
        try:
            items, total = directo.listar(current_user.id, solo, tipo, pagina, 20)
        except PyMongoError:
            items, total = [], 0
            flash('No se pudieron cargar las notificaciones en este momento.', 'error')
        paginacion = {'pagina': pagina, 'paginas': (total + 19) // 20, 'total': total}
    return render_template('notificaciones/lista.html', items=items, paginacion=paginacion, tipo=tipo,
                           solo=solo, tipos=TIPOS, fuente=fuente)


@app.route('/notificaciones/<id>/abrir')
@login_required
def notificacion_abrir(id):
    """Marca como leída y lleva a la pantalla relacionada."""
    destino = request.args.get('url') or url_for('notificaciones')
    try:
        llamar('notificaciones', 'PATCH', f'/notificaciones/{id}', json={'leida': True})
    except ServicioNoDisponible:
        directo.marcar_leida(id, current_user.id)
    if not destino.startswith('/') or destino.startswith('//'):
        destino = url_for('notificaciones')
    return redirect(destino)


@app.route('/notificaciones/marcar-todas', methods=['POST'])
@login_required
def notificaciones_marcar_todas():
    try:
        respuesta = llamar('notificaciones', 'POST', '/notificaciones/marcar-todas')
        flash(respuesta.datos.get('mensaje', 'Listo.'), 'ok')
    except ServicioNoDisponible:
        flash(f'{directo.marcar_todas(current_user.id)} notificaciones marcadas como leídas.', 'ok')
    return redirect(url_for('notificaciones'))


@app.route('/notificaciones/<id>/eliminar', methods=['POST'])
@login_required
def notificacion_eliminar(id):
    try:
        respuesta = llamar('notificaciones', 'DELETE', f'/notificaciones/{id}')
        if not respuesta.ok:
            flash(respuesta.mensaje_error, 'error')
    except ServicioNoDisponible:
        directo.eliminar(id, current_user.id)
    return redirect(request.referrer or url_for('notificaciones'))
