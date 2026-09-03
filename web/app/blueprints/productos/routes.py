from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.producto import ProductoMaestro
from app.models.categoria import Categoria
from app.blueprints.productos.forms import ProductoForm
from app.utils.audit import registrar_evento
from app.utils.decorators import role_required

productos_bp = Blueprint('productos', __name__)

@productos_bp.route('/')
@login_required
def lista():
    page = request.args.get('page', 1, type=int)
    productos_pag = ProductoMaestro.query.filter_by(activo=True).paginate(page=page, per_page=20)
    return render_template('productos/lista.html', productos=productos_pag)

@productos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@role_required('Administrador General')
def nuevo():
    form = ProductoForm()
    form.categoria_id.choices = [(c.id, c.nombre) for c in Categoria.query.filter_by(activa=True).all()]
    if form.validate_on_submit():
        producto = ProductoMaestro(
            nombre=form.nombre.data,
            descripcion=form.descripcion.data,
            categoria_id=form.categoria_id.data,
            unidad_medida=form.unidad_medida.data,
            es_canasta_basica=form.es_canasta_basica.data
        )
        db.session.add(producto)
        db.session.commit()
        
        registrar_evento(current_user.id, 'CREACION', 'ProductoMaestro', producto.id, f'Creado producto {producto.nombre}')
        flash('Producto creado exitosamente', 'success')
        return redirect(url_for('productos.lista'))
        
    return render_template('productos/formulario.html', form=form, title="Nuevo Producto")

@productos_bp.route('/<int:id>')
@login_required
def detalle(id):
    producto = ProductoMaestro.query.get_or_404(id)
    return render_template('productos/detalle.html', producto=producto)


@productos_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('Administrador General')
def editar(id):
    producto = ProductoMaestro.query.get_or_404(id)
    form = ProductoForm(obj=producto)
    form.categoria_id.choices = [(c.id, c.nombre) for c in Categoria.query.filter_by(activa=True).all()]

    if form.validate_on_submit():
        datos_anteriores = {
            'nombre': producto.nombre,
            'categoria_id': producto.categoria_id,
            'unidad_medida': producto.unidad_medida,
            'es_canasta_basica': producto.es_canasta_basica,
        }
        producto.nombre = form.nombre.data
        producto.descripcion = form.descripcion.data
        producto.categoria_id = form.categoria_id.data
        producto.unidad_medida = form.unidad_medida.data
        producto.es_canasta_basica = form.es_canasta_basica.data
        db.session.commit()

        registrar_evento(
            current_user.id,
            'ACTUALIZACION',
            'ProductoMaestro',
            producto.id,
            f'Actualizado producto {producto.nombre}',
            datos_anteriores=datos_anteriores,
            datos_nuevos={
                'nombre': producto.nombre,
                'categoria_id': producto.categoria_id,
                'unidad_medida': producto.unidad_medida,
                'es_canasta_basica': producto.es_canasta_basica,
            },
        )
        flash('Producto actualizado exitosamente', 'success')
        return redirect(url_for('productos.detalle', id=producto.id))

    return render_template('productos/formulario.html', form=form, title="Editar Producto")


@productos_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
@role_required('Administrador General')
def eliminar(id):
    producto = ProductoMaestro.query.get_or_404(id)
    producto.activo = False
    db.session.commit()
    registrar_evento(current_user.id, 'ELIMINACION', 'ProductoMaestro', producto.id, f'Desactivado producto {producto.nombre}')
    flash('Producto desactivado exitosamente', 'success')
    return redirect(url_for('productos.lista'))
