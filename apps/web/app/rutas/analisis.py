"""
Cobertura territorial, brechas y recomendación de surtido.

Cobertura y brechas se piden a ms-analisis (que guarda los resultados en caché
de Redis). Si el servicio no responde, se calculan aquí con la misma
biblioteca de dominio y la pantalla indica la fuente.
"""
from collections import Counter

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required
from pymongo.errors import PyMongoError

from app import app
from app.microservicios import ServicioNoDisponible, llamar
from abasto_dominio.modelos import Categoria, ProductoMaestro, ZonaMunicipal
from app.permisos import permiso_requerido
from app.rutas.inventario import comercios_del_usuario
from abasto_dominio.servicios import analisis, historicos
from abasto_dominio.servicios.parametros import parametro

FUENTE_LOCAL = 'cálculo local (ms-analisis no disponible)'
POR_PAGINA = 50


def _desde_servicio(ruta, params=None):
    """Datos de ms-analisis; None si no responde o rechaza la petición (la vista calcula local)."""
    if not app.config['ANALISIS_VIA_SERVICIO']:
        return None
    try:
        respuesta = llamar('analisis', 'GET', ruta, params=params)
    except ServicioNoDisponible:
        return None
    if not respuesta.ok:
        app.logger.warning('ms-analisis %s respondió %s', ruta, respuesta.status)
        return None
    return respuesta.datos


@app.route('/analisis/cobertura')
@login_required
@permiso_requerido('analisis.ver')
def cobertura():
    producto_id = request.args.get('producto_id', type=int)
    zonas = _desde_servicio('/analisis/zonas')
    puntos = _desde_servicio('/analisis/mapa', {'producto_id': producto_id} if producto_id else None)
    fuente = 'ms-analisis'
    if zonas is None or puntos is None:
        fuente = FUENTE_LOCAL
        zonas, puntos = {'zonas': analisis.indicadores_zonas()}, analisis.puntos_mapa(producto_id)
    evolucion = _desde_servicio('/analisis/ejecuciones/evolucion', {'dias': 90})
    if evolucion is None:
        try:
            evolucion = {'datos': historicos.evolucion_indice(None, 90)}
        except PyMongoError:
            evolucion = {'datos': []}
    return render_template(
        'analisis/cobertura.html', zonas=zonas['zonas'], puntos=puntos, producto_id=producto_id, fuente=fuente,
        evolucion=evolucion['datos'],
        productos=ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre).all())


@app.route('/analisis/cobertura/corte', methods=['POST'])
@login_required
@permiso_requerido('analisis.ver')
def cobertura_corte():
    """Guarda el índice actual de cada zona en MongoDB para ver su evolución."""
    try:
        respuesta = llamar('analisis', 'POST', '/analisis/ejecuciones')
        if respuesta.ok:
            flash(f"Corte guardado: {respuesta.datos['zonas']} zonas, "
                  f"{respuesta.datos['criticas']} con acceso crítico.", 'ok')
        else:
            flash(respuesta.mensaje_error, 'error')
    except ServicioNoDisponible:
        flash('El servicio de análisis no está disponible; intenta más tarde.', 'error')
    return redirect(url_for('cobertura'))


@app.route('/analisis/brechas')
@login_required
@permiso_requerido('analisis.ver')
def brechas():
    filtros = {
        'zona_id': request.args.get('zona_id', type=int),
        'categoria_id': request.args.get('categoria_id', type=int),
        'producto_id': request.args.get('producto_id', type=int),
        'solo_canasta': request.args.get('canasta') == '1',
        'nivel': request.args.get('nivel') or None,
    }

    # La gráfica necesita todas las filas; la tabla se pagina aquí
    params = {clave: filtros[clave] for clave in ('zona_id', 'categoria_id', 'producto_id', 'nivel') if filtros[clave]}
    params.update(canasta_basica=str(filtros['solo_canasta']).lower(), por_pagina=500)
    filas, fuente = [], 'ms-analisis'
    while True:
        datos = _desde_servicio('/analisis/brechas', params | {'pagina': len(filas) // 500 + 1})
        if datos is None:
            filas, fuente = analisis.brechas(**filtros), FUENTE_LOCAL
            break
        filas += datos['brechas']
        if not datos['brechas'] or len(filas) >= datos['paginacion']['total']:
            break

    # Conteo por zona y nivel para la gráfica apilada
    conteo = Counter((f['zona'], f['nivel']) for f in filas)
    zonas_grafica = sorted({f['zona'] for f in filas})
    grafica = {
        'categorias': zonas_grafica,
        'series': [{'name': nivel.replace('_', ' ').capitalize(), 'data': [conteo[(z, nivel)] for z in zonas_grafica]}
                   for nivel in ('ALTA', 'MEDIA', 'BAJA', 'SIN_BRECHA')],
    }
    paginas = max((len(filas) + POR_PAGINA - 1) // POR_PAGINA, 1)
    pagina = min(max(request.args.get('page', 1, type=int), 1), paginas)
    return render_template(
        'analisis/brechas.html', filas=filas[(pagina - 1) * POR_PAGINA:pagina * POR_PAGINA], filtros=filtros,
        grafica=grafica, fuente=fuente, paginacion={'pagina': pagina, 'paginas': paginas, 'total': len(filas)},
        totales=Counter(f['nivel'] for f in filas),
        umbrales=analisis.umbrales(), habitantes_por_punto=parametro('HABITANTES_POR_PUNTO'),
        zonas=ZonaMunicipal.query.filter_by(activa=True).order_by(ZonaMunicipal.nombre).all(),
        categorias=Categoria.query.filter_by(activa=True).order_by(Categoria.orden).all(),
        productos=ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre).all())


@app.route('/recomendaciones')
@login_required
@permiso_requerido('recomendaciones.ver')
def recomendaciones():
    comercios = comercios_del_usuario()
    if not comercios:
        flash('Registra un comercio para recibir recomendaciones de surtido.', 'info')
        return redirect(url_for('comercio_nuevo'))
    comercio_id = request.args.get('comercio_id')
    comercio = next((c for c in comercios if str(c.id) == comercio_id), comercios[0])
    return render_template('analisis/recomendaciones.html', comercio=comercio, comercios=comercios,
                           recomendaciones=analisis.recomendaciones(comercio),
                           faltantes=analisis.faltantes(comercio),
                           umbral=parametro('UMBRAL_COBERTURA_RECOMENDACION'))
