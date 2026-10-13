"""
Administración técnica: sesiones abiertas (Redis, vía ms-seguridad) y estado
de los microservicios (health checks y actividad registrada en MongoDB).
"""
from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import login_required

from app import app
from app.microservicios import SERVICIOS, ServicioNoDisponible, llamar, salud_todos
from app.permisos import permiso_requerido
from abasto_dominio.modelos import Usuario


@app.route('/admin/sesiones')
@login_required
@permiso_requerido('sesiones.gestionar')
def sesiones_lista():
    usuario_id = request.args.get('usuario_id') or None
    lista, disponible = [], True
    try:
        respuesta = llamar('seguridad', 'GET', '/sesiones', params={'usuario_id': usuario_id} if usuario_id else None)
        lista = respuesta.datos.get('sesiones', []) if respuesta.ok else []
    except ServicioNoDisponible:
        disponible = False
    # Los tokens de servicio (llamadas entre microservicios) también son sesiones: usuario_id = "servicio:x"
    ids = {s['usuario_id'] for s in lista if not s['usuario_id'].startswith('servicio:')}
    correos = {str(u.id): u for u in Usuario.query.filter(Usuario.id.in_(ids))} if ids else {}
    resumen = {}
    for s in lista:
        resumen[s.get('origen') or 'otro'] = resumen.get(s.get('origen') or 'otro', 0) + 1
    return render_template('admin/sesiones.html', sesiones=lista, usuarios=correos, disponible=disponible,
                           usuario_id=usuario_id, propia=session.get('jwt_jti'), resumen=resumen)


@app.route('/admin/sesiones/<jti>/revocar', methods=['POST'])
@login_required
@permiso_requerido('sesiones.gestionar')
def sesion_revocar(jti):
    if jti == session.get('jwt_jti'):
        flash('Ésa es tu sesión actual; usa «Salir» para cerrarla.', 'alerta')
        return redirect(url_for('sesiones_lista'))
    try:
        respuesta = llamar('seguridad', 'DELETE', f'/sesiones/{jti}')
        flash('Sesión cerrada. El usuario deberá iniciar sesión de nuevo.' if respuesta.ok else respuesta.mensaje_error,
              'ok' if respuesta.ok else 'error')
    except ServicioNoDisponible:
        flash('El servicio de seguridad no está disponible.', 'error')
    return redirect(request.referrer or url_for('sesiones_lista'))


@app.route('/admin/usuarios/<uuid:id>/cerrar-sesiones', methods=['POST'])
@login_required
@permiso_requerido('sesiones.gestionar')
def usuario_cerrar_sesiones(id):
    try:
        respuesta = llamar('seguridad', 'DELETE', f'/usuarios/{id}/sesiones')
        flash(respuesta.datos.get('mensaje') if respuesta.ok else respuesta.mensaje_error,
              'ok' if respuesta.ok else 'error')
    except ServicioNoDisponible:
        flash('El servicio de seguridad no está disponible.', 'error')
    return redirect(request.referrer or url_for('sesiones_lista'))


@app.route('/admin/servicios')
@login_required
@permiso_requerido('servicios.monitorear')
def servicios_estado():
    horas = request.args.get('horas', 24, type=int)
    if horas not in (1, 24, 168):
        horas = 24
    estados = salud_todos()
    actividad = []
    try:
        respuesta = llamar('seguridad', 'GET', '/actividad', params={'horas': horas})
        actividad = respuesta.datos.get('servicios', []) if respuesta.ok else []
    except ServicioNoDisponible:
        pass

    rastreo, correlation_id = None, (request.args.get('correlation_id') or '').strip()
    if correlation_id:
        try:
            respuesta = llamar('seguridad', 'GET', f'/actividad/peticiones/{correlation_id}')
            if respuesta.ok:
                rastreo = respuesta.datos['pasos']
            else:
                flash(respuesta.mensaje_error, 'alerta')
        except ServicioNoDisponible:
            flash('El servicio de seguridad no está disponible.', 'error')
    # Swagger de cada servicio en el puerto que publica docker-compose (8101 a 8108, mismo orden que SERVICIOS)
    base = current_app.config['MS_DOCS_HOST']
    docs = {s: f'{base}:{8101 + i}/docs' for i, s in enumerate(SERVICIOS)}
    return render_template('admin/servicios.html', estados=estados, actividad=actividad, horas=horas,
                           rastreo=rastreo, correlation_id=correlation_id, docs=docs,
                           arriba=sum(1 for e in estados.values() if e.get('estado') == 'ok'))
