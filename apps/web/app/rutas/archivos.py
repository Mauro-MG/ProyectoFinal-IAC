"""
Fotos y evidencias de comercios. Se guardan en MongoDB GridFS a través de
ms-comercios; el web sólo reenvía el archivo con el JWT del usuario.

Subir y eliminar requieren el servicio. Ver y descargar tienen respaldo: si el
servicio no responde se leen directo de GridFS con la misma regla de acceso.
"""
from flask import Response, abort, flash, redirect, request, url_for
from flask_login import current_user, login_required
from pymongo.errors import PyMongoError

from app import app
from app.microservicios import ServicioNoDisponible, llamar
from app.permisos import permiso_requerido
from app.rutas.comercios import puede_ver_comercio
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio
from abasto_dominio.servicios import archivos as gridfs

CATEGORIAS_COMERCIO = {k: gridfs.CATEGORIAS[k] for k in ('foto_comercio', 'evidencia_validacion', 'documento')}


def archivos_de_comercio(comercio):
    """(lista, fuente) para la ficha del comercio."""
    try:
        respuesta = llamar('comercios', 'GET', f'/comercios/{comercio.id}/archivos', params={'por_pagina': 50})
        if respuesta.ok:
            return respuesta.datos['archivos'], 'ms-comercios'
    except ServicioNoDisponible:
        pass
    try:
        return gridfs.listar('comercio', comercio.id, por_pagina=50)[0], 'GridFS (directo)'
    except PyMongoError:
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
    try:
        respuesta = llamar(
            'comercios', 'POST', f'/comercios/{id}/archivos',
            files={'archivo': (archivo.filename, archivo.stream, archivo.mimetype)},
            data={'categoria': request.form.get('categoria', 'foto_comercio'),
                  'descripcion': request.form.get('descripcion', '').strip()})
    except ServicioNoDisponible:
        flash('El servicio de archivos no está disponible; intenta más tarde.', 'error')
        return redirect(url_for('comercio_detalle', id=id))
    if respuesta.ok:
        flash(f"Archivo «{respuesta.datos['nombre']}» guardado.", 'ok')
    else:
        flash(respuesta.mensaje_error, 'error')
    return redirect(url_for('comercio_detalle', id=id))


@app.route('/archivos/<archivo_id>')
@login_required
def archivo_ver(archivo_id):
    try:
        respuesta = llamar('comercios', 'GET', f'/archivos/{archivo_id}')
        if respuesta.status in (403, 404):
            abort(respuesta.status)
        if respuesta.ok:
            return Response(respuesta.contenido, mimetype=respuesta.headers.get('Content-Type'),
                            headers={'Content-Disposition': respuesta.headers.get('Content-Disposition', 'inline')})
    except ServicioNoDisponible:
        pass
    meta, contenido = gridfs.abrir(archivo_id)
    if not meta:
        abort(404)
    if meta['entidad'] == 'comercio':
        comercio = db.session.get(Comercio, meta['entidad_id'])
        if not comercio or not puede_ver_comercio(comercio):
            abort(403)
    elif meta['usuario_id'] != str(current_user.id):
        abort(403)
    return Response(contenido.read(), mimetype=meta['tipo_mime'],
                    headers={'Content-Disposition': f'inline; filename="{meta["nombre"]}"'})


@app.route('/archivos/<archivo_id>/eliminar', methods=['POST'])
@login_required
@permiso_requerido('archivos.gestionar')
def archivo_eliminar(archivo_id):
    try:
        respuesta = llamar('comercios', 'DELETE', f'/archivos/{archivo_id}')
        flash('Archivo eliminado.' if respuesta.ok else respuesta.mensaje_error, 'ok' if respuesta.ok else 'error')
    except ServicioNoDisponible:
        flash('El servicio de archivos no está disponible; intenta más tarde.', 'error')
    return redirect(request.referrer or url_for('panel'))
