"""Reportes, tendencias y exportación a CSV."""
import csv
import io
from datetime import date

from flask import Response, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from app import app
from app.extensions import db
from app.models.pedido import ESTADOS_PEDIDO
from app.models import Comercio, InventarioComercio, PedidoAbasto, ProductoMaestro, ZonaMunicipal
from app.servicios import analisis
from app.servicios.auditoria import registrar_evento
from app.servicios.precios import tendencia_semanal


def puede_ver_oportunidades(usuario):
    """Analistas y coordinadores siempre; proveedores sólo con plan Destacado."""
    if usuario.tiene_permiso('reportes.ver'):
        return True
    return usuario.tiene_permiso('pedidos.atender') and usuario.proveedor and usuario.proveedor.plan == 'DESTACADO'


def oportunidades_abasto(zona_ids=None):
    """Zona-producto con brecha ALTA o MEDIA y demanda: dónde conviene surtir."""
    filas = [f for f in analisis.brechas() if f['nivel'] in ('ALTA', 'MEDIA')
             and (f['canasta_basica'] or f['ventas'] > 0)]
    if zona_ids is not None:
        filas = [f for f in filas if f['zona_id'] in zona_ids]
    return sorted(filas, key=lambda f: (f['cobertura'], -f['ventas']))


@app.route('/reportes')
@login_required
def reportes():
    if not (current_user.tiene_permiso('reportes.ver') or puede_ver_oportunidades(current_user)
            or current_user.tiene_permiso('pedidos.atender')):
        abort(403)

    producto_id = request.args.get('producto_id', type=int)
    if not producto_id:
        leche = ProductoMaestro.query.filter(ProductoMaestro.nombre.ilike('Leche%')).first()
        producto_id = leche.id if leche else None

    datos = {'producto_id': producto_id}
    if current_user.tiene_permiso('reportes.ver'):
        datos['tendencia'] = tendencia_semanal(producto_id) if producto_id else None
        datos['zonas'] = analisis.indicadores_zonas()
        datos['pedidos'] = [{'name': ESTADOS_PEDIDO[estado], 'y': total} for estado, total in
                            db.session.query(PedidoAbasto.estado, func.count(PedidoAbasto.id))
                            .group_by(PedidoAbasto.estado).all()]
    if puede_ver_oportunidades(current_user):
        zona_ids = None
        if not current_user.tiene_permiso('reportes.ver'):
            zona_ids = {z.id for z in current_user.proveedor.zonas}
        datos['oportunidades'] = oportunidades_abasto(zona_ids)[:15]

    return render_template('reportes/index.html', datos=datos, puede_oportunidades=puede_ver_oportunidades(current_user),
                           productos=ProductoMaestro.query.filter_by(activo=True).order_by(ProductoMaestro.nombre).all())


def _csv(nombre, encabezados, filas):
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(encabezados)
    escritor.writerows(filas)
    # BOM para que Excel abra bien los acentos
    return Response('﻿' + salida.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={nombre}_{date.today():%Y%m%d}.csv'})


@app.route('/reportes/exportar/<tipo>')
@login_required
def exportar(tipo):
    if tipo == 'oportunidades':
        if not puede_ver_oportunidades(current_user):
            abort(403)
        zona_ids = None if current_user.tiene_permiso('reportes.ver') else {z.id for z in current_user.proveedor.zonas}
        filas = oportunidades_abasto(zona_ids)
        respuesta = _csv('oportunidades_abasto',
                         ['Zona', 'Municipio', 'Producto', 'Canasta básica', 'Comercios', 'Con existencia',
                          'Cobertura %', 'Brecha', 'Ventas 30 días', 'Proveedores en zona', 'Mayoreo mín.',
                          'Precio consumidor prom.'],
                         [[f['zona'], f['municipio'], f['producto'], 'Sí' if f['canasta_basica'] else 'No',
                           f['comercios_analizados'], f['con_disponibilidad'], f['cobertura'], f['nivel'],
                           f['ventas'], f['proveedores'], f['precio_mayoreo_min'] or '',
                           round(f['precio_promedio'], 2) if f['precio_promedio'] else ''] for f in filas])
    elif tipo == 'brechas':
        if not current_user.tiene_permiso('analisis.ver'):
            abort(403)
        filas = analisis.brechas()
        respuesta = _csv('brechas',
                         ['Zona', 'Municipio', 'Producto', 'Comercios', 'Con existencia', 'Sin existencia',
                          'Cobertura %', 'Puntos requeridos', 'Déficit', 'Ventas 30 días', 'Proveedores', 'Brecha'],
                         [[f['zona'], f['municipio'], f['producto'], f['comercios_analizados'],
                           f['con_disponibilidad'], f['sin_disponibilidad'], f['cobertura'],
                           f['puntos_requeridos'], f['deficit_puntos'], f['ventas'], f['proveedores'], f['nivel']]
                          for f in filas])
    elif tipo == 'disponibilidad':
        if not current_user.tiene_permiso('reportes.ver'):
            abort(403)
        filas = (db.session.query(ProductoMaestro.nombre, Comercio.nombre_comercio, ZonaMunicipal.nombre,
                                  InventarioComercio.existencia, InventarioComercio.precio_venta,
                                  InventarioComercio.estado, InventarioComercio.updated_at)
                 .join(Comercio, InventarioComercio.comercio_id == Comercio.id)
                 .join(ProductoMaestro, InventarioComercio.producto_id == ProductoMaestro.id)
                 .outerjoin(ZonaMunicipal, Comercio.zona_id == ZonaMunicipal.id)
                 .filter(InventarioComercio.activo.is_(True), Comercio.activo.is_(True))
                 .order_by(ProductoMaestro.nombre, ZonaMunicipal.nombre).all())
        respuesta = _csv('disponibilidad',
                         ['Producto', 'Comercio', 'Zona', 'Existencia', 'Precio', 'Estado', 'Actualizado'],
                         [[p, c, z, e, pr, es, a.strftime('%Y-%m-%d %H:%M') if a else ''] for p, c, z, e, pr, es, a in filas])
    else:
        abort(404)

    registrar_evento(current_user.id, 'LECTURA', 'Reporte', tipo, f'Exportación CSV: {tipo}')
    db.session.commit()
    return respuesta
