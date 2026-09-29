"""Cobertura territorial, brechas y recomendación de surtido."""
from collections import Counter

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import app
from app.models import Categoria, ProductoMaestro, ZonaMunicipal
from app.permisos import permiso_requerido
from app.rutas.inventario import comercios_del_usuario
from app.servicios import analisis
from app.servicios.parametros import parametro


@app.route('/analisis/cobertura')
@login_required
@permiso_requerido('analisis.ver')
def cobertura():
    producto_id = request.args.get('producto_id', type=int)
    return render_template(
        'analisis/cobertura.html',
        zonas=analisis.indicadores_zonas(),
        puntos=analisis.puntos_mapa(producto_id),
        producto_id=producto_id,
        productos=ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre).all())


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
    filas = analisis.brechas(**filtros)

    # Conteo por zona y nivel para la gráfica apilada
    conteo = Counter((f['zona'], f['nivel']) for f in filas)
    zonas_grafica = sorted({f['zona'] for f in filas})
    grafica = {
        'categorias': zonas_grafica,
        'series': [{'name': nivel.replace('_', ' ').capitalize(), 'data': [conteo[(z, nivel)] for z in zonas_grafica]}
                   for nivel in ('ALTA', 'MEDIA', 'BAJA', 'SIN_BRECHA')],
    }
    return render_template(
        'analisis/brechas.html', filas=filas, filtros=filtros, grafica=grafica,
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
