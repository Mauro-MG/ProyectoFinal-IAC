"""
Fotos y evidencias de comercios. El contenido vive en el bucket privado de
Google Cloud Storage y lo administra ms-documentos; el web solo reenvía el
archivo con el JWT del usuario y nunca tiene credenciales del bucket.

Para ver un archivo el web pide a ms-documentos una URL firmada (que revisa el
permiso sobre ESE documento) y redirige el navegador al bucket. Si ms-documentos
no responde no hay respaldo: el web no puede leer el bucket por su cuenta.
"""
from flask import Response, abort, flash, redirect, request, url_for
from flask_login import login_required

from app import app
from app.microservicios import ServicioNoDisponible, llamar
from app.permisos import permiso_requerido
from app.rutas.comercios import puede_ver_comercio
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio
from abasto_dominio.servicios.archivos import CATEGORIAS

CATEGORIAS_COMERCIO = {k: CATEGORIAS[k] for k in ('foto_comercio', 'evidencia_validacion', 'documento')}


def archivos_de_comercio(comercio):
    """(lista, fuente) para la ficha del comercio."""
    try:
        respuesta = llamar('documentos', 'GET', '/documentos',
                           params={'entidad': 'comercio', 'entidad_id': str(comercio.id), 'por_pagina': 50})
        if respuesta.ok:
            return respuesta.datos['documentos'], 'ms-documentos'
    except ServicioNoDisponible:
        pass
    return [], 'no disponible'


@app.route('/comercios/<uuid:id>/archivos', methods=['POST'])
@login_required
@permiso_requerido('archivos.gestionar')
def comercio_subir_archivo(id):
    comercio = db.get_or_404(Comercio, id)
    if not puede_ver_comercio(comercio):
        abort(403)
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        flash('Selecciona un archivo.', 'error')
        return redirect(url_for('comercio_detalle', id=id))
    categoria = request.form.get('categoria', 'foto_comercio')
    try:
        # ms-documentos guarda el archivo; si es la foto principal, ms-comercios (dueño de la tabla) la fija
        respuesta = llamar(
            'documentos', 'POST', '/documentos',
            files={'archivo': (archivo.filename, archivo.stream, archivo.mimetype)},
            data={'categoria': categoria, 'entidad': 'comercio', 'entidad_id': str(id),
                  'descripcion': request.form.get('descripcion', '').strip()}, timeout=15)
        if respuesta.ok and categoria == 'foto_comercio':
            foto = llamar('comercios', 'PUT', f'/comercios/{id}/foto', json={'documento_id': respuesta.datos['id']})
            if not foto.ok:
                flash(f'El archivo se guardó pero no se pudo fijar como foto: {foto.mensaje_error}', 'alerta')
    except ServicioNoDisponible:
        flash('El servicio de documentos no está disponible; intenta más tarde.', 'error')
        return redirect(url_for('comercio_detalle', id=id))
    if respuesta.ok:
        flash(f"Archivo «{respuesta.datos['nombre']}» guardado.", 'ok')
    else:
        flash(respuesta.mensaje_error, 'error')
    return redirect(url_for('comercio_detalle', id=id))


@app.route('/archivos/<archivo_id>')
@login_required
def archivo_ver(archivo_id):
    """Redirige a una URL firmada de 5 minutos. Los archivos que aún no se migran desde GridFS se sirven a
    través del servicio (/contenido)."""
    try:
        respuesta = llamar('documentos', 'GET', f'/documentos/{archivo_id}/url', params={'minutos': 5})
        if respuesta.status in (403, 404):
            abort(respuesta.status)
        if respuesta.ok:
            return redirect(respuesta.datos['url'])
        if respuesta.status == 409:   # sin URL directa: archivo anterior en GridFS
            contenido = llamar('documentos', 'GET', f'/documentos/{archivo_id}/contenido')
            if contenido.ok:
                return Response(contenido.contenido, mimetype=contenido.headers.get('Content-Type'),
                                headers={'Content-Disposition': contenido.headers.get('Content-Disposition', 'inline')})
        flash(respuesta.mensaje_error, 'error')
    except ServicioNoDisponible:
        flash('El servicio de documentos no está disponible; intenta en un momento.', 'error')
    return redirect(request.referrer or url_for('panel'))


@app.route('/archivos/<archivo_id>/eliminar', methods=['POST'])
@login_required
@permiso_requerido('archivos.gestionar')
def archivo_eliminar(archivo_id):
    try:
        respuesta = llamar('documentos', 'DELETE', f'/documentos/{archivo_id}')
        flash('Archivo eliminado.' if respuesta.ok else respuesta.mensaje_error, 'ok' if respuesta.ok else 'error')
    except ServicioNoDisponible:
        flash('El servicio de archivos no está disponible; intenta más tarde.', 'error')
    return redirect(request.referrer or url_for('panel'))
