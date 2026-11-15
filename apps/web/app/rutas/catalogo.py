"""
Catálogos maestros: productos y categorías (ms-catalogo) y zonas (ms-geolocalizacion).

Las listas se leen de la base; las altas y cambios los hace el servicio dueño.
"""
from flask import redirect, render_template, request, url_for
from flask_login import login_required

from app import app
from abasto_dominio.extensiones import db
from app.formularios import CategoriaForm, ProductoForm, ZonaForm
from app.microservicios import escribir
from abasto_dominio.modelos import Categoria, ProductoMaestro, ZonaMunicipal
from app.permisos import permiso_requerido


# ---------------------------------------------------------------- productos

def _categorias(form):
    form.categoria_id.choices = [(c.id, c.nombre) for c in
                                 Categoria.query.filter_by(activa=True).order_by(Categoria.orden)]


def _producto_json(form, actual=None):
    """Cuerpo para ms-catalogo. El PUT reemplaza el producto completo: los campos que esta pantalla no
    maneja (marca, clave estándar) se mandan con su valor actual para no borrarlos."""
    return {'nombre': form.nombre.data.strip(), 'categoria_id': form.categoria_id.data,
            'unidad_medida': form.unidad_medida.data, 'codigo_barras': (form.codigo_barras.data or '').strip() or None,
            'es_canasta_basica': form.es_canasta_basica.data, 'descripcion': form.descripcion.data or None,
            'marca_id': actual.marca_id if actual else None,
            'clave_estandar': actual.clave_estandar if actual else None}


@app.route('/catalogo/productos')
@login_required
def productos_lista():
    categoria_id = request.args.get('categoria_id', type=int)
    texto = request.args.get('q', '').strip()
    consulta = ProductoMaestro.query.filter_by(activo=True)
    if categoria_id:
        consulta = consulta.filter_by(categoria_id=categoria_id)
    if texto:
        consulta = consulta.filter(ProductoMaestro.nombre.ilike(f'%{texto}%'))
    return render_template('catalogo/productos.html',
                           productos=consulta.order_by(ProductoMaestro.nombre).all(),
                           categorias=Categoria.query.order_by(Categoria.orden).all(),
                           categoria_id=categoria_id, texto=texto)


@app.route('/catalogo/productos/nuevo', methods=['GET', 'POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def producto_nuevo():
    form = ProductoForm()
    _categorias(form)
    if form.validate_on_submit():
        if escribir('catalogo', 'POST', '/productos', json=_producto_json(form),
                    exito='Producto agregado al catálogo maestro.') is not None:
            return redirect(url_for('productos_lista'))
    return render_template('catalogo/producto_form.html', form=form, titulo='Nuevo producto')


@app.route('/catalogo/productos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def producto_editar(id):
    producto = db.get_or_404(ProductoMaestro, id)
    form = ProductoForm(obj=producto)
    _categorias(form)
    if form.validate_on_submit():
        if escribir('catalogo', 'PUT', f'/productos/{id}', json=_producto_json(form, producto),
                    exito='Producto actualizado.') is not None:
            return redirect(url_for('productos_lista'))
    return render_template('catalogo/producto_form.html', form=form, titulo=f'Editar {producto.nombre}')


@app.route('/catalogo/productos/<int:id>/desactivar', methods=['POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def producto_desactivar(id):
    producto = db.get_or_404(ProductoMaestro, id)
    escribir('catalogo', 'DELETE', f'/productos/{id}', exito=f'{producto.nombre} ya no aparecerá en el catálogo.')
    return redirect(url_for('productos_lista'))


# ---------------------------------------------------------------- categorías

@app.route('/catalogo/categorias', methods=['GET', 'POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def categorias():
    form = CategoriaForm()
    if form.validate_on_submit():
        orden = (db.session.query(db.func.max(Categoria.orden)).scalar() or 0) + 1
        if escribir('catalogo', 'POST', '/categorias', exito='Categoría agregada.',
                    json={'nombre': form.nombre.data.strip(), 'descripcion': form.descripcion.data or None,
                          'orden': min(orden, 999)}) is not None:
            return redirect(url_for('categorias'))

    conteo = dict(db.session.query(ProductoMaestro.categoria_id, db.func.count(ProductoMaestro.id))
                  .filter_by(activo=True).group_by(ProductoMaestro.categoria_id).all())
    return render_template('catalogo/categorias.html', form=form, conteo=conteo,
                           categorias=Categoria.query.order_by(Categoria.orden).all())


@app.route('/catalogo/categorias/<int:id>/estado', methods=['POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def categoria_estado(id):
    categoria = db.get_or_404(Categoria, id)
    escribir('catalogo', 'PATCH', f'/categorias/{id}', json={'activa': not categoria.activa})
    return redirect(url_for('categorias'))


# ---------------------------------------------------------------- zonas (ms-geolocalizacion)

@app.route('/catalogo/zonas')
@login_required
@permiso_requerido('catalogos.gestionar', 'analisis.ver')
def zonas_lista():
    return render_template('catalogo/zonas.html',
                           zonas=ZonaMunicipal.query.order_by(ZonaMunicipal.municipio, ZonaMunicipal.nombre).all())


@app.route('/catalogo/zonas/nueva', methods=['GET', 'POST'])
@app.route('/catalogo/zonas/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def zona_form(id=None):
    zona = db.get_or_404(ZonaMunicipal, id) if id else None
    form = ZonaForm(obj=zona)
    if form.validate_on_submit():
        datos = {'nombre': form.nombre.data.strip(), 'latitud_centro': form.latitud_centro.data,
                 'longitud_centro': form.longitud_centro.data, 'radio_km': form.radio_km.data,
                 'poblacion': form.poblacion.data}
        if zona:
            # El municipio y el estado no cambian en una zona existente (identifican sus datos históricos)
            guardado = escribir('geolocalizacion', 'PATCH', f'/zonas/{id}', json={**datos, 'activa': form.activa.data},
                                exito='Zona guardada.')
        else:
            guardado = escribir('geolocalizacion', 'POST', '/zonas', exito='Zona guardada.',
                                json={**datos, 'municipio': form.municipio.data.strip(),
                                      'estado': form.estado.data.strip()})
        if guardado is not None:
            return redirect(url_for('zonas_lista'))
    return render_template('catalogo/zona_form.html', form=form, zona=zona)
