"""Catálogos maestros: productos, categorías y zonas."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import app
from app.extensions import db
from app.formularios import CategoriaForm, ProductoForm, ZonaForm
from app.models import Categoria, ProductoMaestro, ZonaMunicipal
from app.permisos import permiso_requerido
from app.servicios.auditoria import registrar_evento
from app.servicios.cache import invalidar_analisis


def _campos(objeto, nombres):
    return {n: getattr(objeto, n) for n in nombres}


# ---------------------------------------------------------------- productos

CAMPOS_PRODUCTO = ('nombre', 'categoria_id', 'unidad_medida', 'codigo_barras', 'es_canasta_basica')


def _categorias(form):
    form.categoria_id.choices = [(c.id, c.nombre) for c in
                                 Categoria.query.filter_by(activa=True).order_by(Categoria.orden)]


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
        if ProductoMaestro.query.filter_by(nombre=form.nombre.data, unidad_medida=form.unidad_medida.data).first():
            flash('Ya existe un producto con ese nombre y unidad.', 'error')
        else:
            producto = ProductoMaestro()
            form.populate_obj(producto)
            db.session.add(producto)
            db.session.flush()
            registrar_evento(current_user.id, 'CREACION', 'ProductoMaestro', producto.id,
                             f'Alta de {producto.nombre} en el catálogo maestro',
                             datos_nuevos=_campos(producto, CAMPOS_PRODUCTO))
            db.session.commit()
            flash('Producto agregado al catálogo maestro.', 'ok')
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
        antes = _campos(producto, CAMPOS_PRODUCTO)
        form.populate_obj(producto)
        registrar_evento(current_user.id, 'ACTUALIZACION', 'ProductoMaestro', producto.id,
                         f'Edición de {producto.nombre}', datos_anteriores=antes,
                         datos_nuevos=_campos(producto, CAMPOS_PRODUCTO))
        db.session.commit()
        invalidar_analisis()
        flash('Producto actualizado.', 'ok')
        return redirect(url_for('productos_lista'))
    return render_template('catalogo/producto_form.html', form=form, titulo=f'Editar {producto.nombre}')


@app.route('/catalogo/productos/<int:id>/desactivar', methods=['POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def producto_desactivar(id):
    producto = db.get_or_404(ProductoMaestro, id)
    producto.activo = False
    registrar_evento(current_user.id, 'ELIMINACION', 'ProductoMaestro', producto.id,
                     f'Baja lógica de {producto.nombre}')
    db.session.commit()
    invalidar_analisis()
    flash(f'{producto.nombre} ya no aparecerá en el catálogo.', 'ok')
    return redirect(url_for('productos_lista'))


# ---------------------------------------------------------------- categorías

@app.route('/catalogo/categorias', methods=['GET', 'POST'])
@login_required
@permiso_requerido('catalogos.gestionar')
def categorias():
    form = CategoriaForm()
    if form.validate_on_submit():
        if Categoria.query.filter(db.func.lower(Categoria.nombre) == form.nombre.data.strip().lower()).first():
            flash('Esa categoría ya existe.', 'error')
        else:
            categoria = Categoria(nombre=form.nombre.data.strip(), descripcion=form.descripcion.data,
                                  orden=(db.session.query(db.func.max(Categoria.orden)).scalar() or 0) + 1)
            db.session.add(categoria)
            db.session.flush()
            registrar_evento(current_user.id, 'CREACION', 'Categoria', categoria.id, f'Alta de categoría {categoria.nombre}')
            db.session.commit()
            flash('Categoría agregada.', 'ok')
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
    categoria.activa = not categoria.activa
    registrar_evento(current_user.id, 'ACTUALIZACION', 'Categoria', categoria.id,
                     f'Categoría {categoria.nombre} {"activada" if categoria.activa else "desactivada"}')
    db.session.commit()
    return redirect(url_for('categorias'))


# ---------------------------------------------------------------- zonas

CAMPOS_ZONA = ('nombre', 'municipio', 'latitud_centro', 'longitud_centro', 'radio_km', 'poblacion', 'activa')


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
        antes = _campos(zona, CAMPOS_ZONA) if zona else None
        if not zona:
            zona = ZonaMunicipal()
            db.session.add(zona)
        form.populate_obj(zona)
        db.session.flush()
        registrar_evento(current_user.id, 'ACTUALIZACION' if antes else 'CREACION', 'ZonaMunicipal', zona.id,
                         f'Zona {zona.nombre} ({zona.municipio})', datos_anteriores=antes,
                         datos_nuevos=_campos(zona, CAMPOS_ZONA))
        db.session.commit()
        invalidar_analisis()
        flash('Zona guardada.', 'ok')
        return redirect(url_for('zonas_lista'))
    return render_template('catalogo/zona_form.html', form=form, zona=zona)
