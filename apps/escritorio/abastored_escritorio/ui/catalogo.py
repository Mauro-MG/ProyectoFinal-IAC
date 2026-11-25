"""Administración del catálogo maestro: productos y categorías (ms-catalogo, en XML)."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QMessageBox, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila, fila_seleccionada, tabla

UNIDADES = ['pieza', 'kg', 'litro', 'paquete', 'caja']


class DialogoProducto(QDialog):
    def __init__(self, padre, categorias, producto=None):
        super().__init__(padre)
        self.setWindowTitle('Editar producto' if producto else 'Nuevo producto')
        formulario = QFormLayout(self)
        self.nombre, self.codigo, self.descripcion = QLineEdit(), QLineEdit(), QLineEdit()
        self.categoria, self.unidad = QComboBox(), QComboBox()
        for c in categorias:
            self.categoria.addItem(c['nombre'], c['id'])
        self.unidad.addItems(UNIDADES)
        self.canasta = QCheckBox('Forma parte de la canasta básica')
        self.codigo.setPlaceholderText('8 a 14 dígitos (opcional)')
        formulario.addRow('Nombre y presentación:', self.nombre)
        formulario.addRow('Categoría:', self.categoria)
        formulario.addRow('Unidad:', self.unidad)
        formulario.addRow('Código de barras:', self.codigo)
        formulario.addRow('Descripción:', self.descripcion)
        formulario.addRow('', self.canasta)
        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        formulario.addRow(botones)
        self.producto = producto or {}
        if producto:
            self.nombre.setText(producto['nombre'])
            self.categoria.setCurrentIndex(max(self.categoria.findData(producto['categoria_id']), 0))
            self.unidad.setCurrentText(producto.get('unidad_medida') or 'pieza')
            self.codigo.setText(producto.get('codigo_barras') or '')
            self.descripcion.setText(producto.get('descripcion') or '')
            self.canasta.setChecked(bool(producto.get('es_canasta_basica')))

    def datos(self):
        """Cuerpo de <producto_entrada>. El PUT reemplaza el producto: marca y clave estándar se conservan."""
        return {'nombre': self.nombre.text().strip(), 'categoria_id': self.categoria.currentData(),
                'unidad_medida': self.unidad.currentText(), 'codigo_barras': self.codigo.text().strip() or None,
                'es_canasta_basica': self.canasta.isChecked(), 'descripcion': self.descripcion.text().strip() or None,
                'marca_id': self.producto.get('marca_id'), 'clave_estandar': self.producto.get('clave_estandar')}


class Catalogo(Pantalla):
    titulo = 'Catálogo maestro'
    descripcion = ('Productos y categorías que usan todos los comercios. Los cambios los valida y audita ms-catalogo '
                   '(nombre y unidad no repetidos, código de barras único).')
    permisos = ('catalogos.gestionar',)

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.categorias = []
        pestanas = QTabWidget()
        pestanas.addTab(self._productos(), 'Productos')
        pestanas.addTab(self._categorias(), 'Categorías')
        self.diseno.addWidget(pestanas, 1)
        self.diseno.addWidget(self.estado)

    # ------------------------------------------------------------ productos
    def _productos(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText('Buscar producto…')
        self.buscar.returnPressed.connect(self.cargar_productos)
        diseno.addLayout(fila(self.buscar, self.boton('Buscar', self.cargar_productos), None,
                              self.boton('Nuevo…', self.nuevo, principal=True), self.boton('Editar…', self.editar),
                              self.boton('Dar de baja', self.baja)))
        self.productos = ModeloFilas([('nombre', 'Producto'), ('categoria', 'Categoría'), ('unidad_medida', 'Unidad'),
                                      ('codigo_barras', 'Código'), ('es_canasta_basica', 'Canasta')])
        self.vista_productos = tabla(self.productos)
        self.vista_productos.doubleClicked.connect(lambda _: self.editar())
        diseno.addWidget(self.vista_productos, 1)
        return hoja

    def al_mostrar(self):
        self.cargar_categorias()
        self.cargar_productos()

    def cargar_productos(self):
        texto = self.buscar.text().strip()
        self.ejecutar(lambda: self.cliente.get('catalogo', '/productos', texto=texto, por_pagina=200).datos['productos'],
                      self.productos.cambiar)

    def _guardar(self, metodo, ruta, dialogo, mensaje):
        def hecho(respuesta):
            self.bitacora.accion(mensaje, 'catalogo', respuesta.correlation_id)
            self.cargar_productos()
        self.ejecutar(lambda: self.cliente.peticion('catalogo', metodo, ruta, raiz='producto_entrada',
                                                    datos=dialogo.datos()), hecho, 'Guardando…')

    def nuevo(self):
        dialogo = DialogoProducto(self, self.categorias)
        if dialogo.exec() == QDialog.Accepted:
            self._guardar('POST', '/productos', dialogo, f'Alta del producto «{dialogo.nombre.text()}»')

    def editar(self):
        producto = fila_seleccionada(self.vista_productos)
        if not producto:
            return
        dialogo = DialogoProducto(self, self.categorias, producto)
        if dialogo.exec() == QDialog.Accepted:
            self._guardar('PUT', f"/productos/{producto['id']}", dialogo, f"Edición del producto «{producto['nombre']}»")

    def baja(self):
        producto = fila_seleccionada(self.vista_productos)
        if not producto or QMessageBox.question(
                self, 'Baja', f"¿Dar de baja «{producto['nombre']}»? Ya no aparecerá en el catálogo.") != QMessageBox.Yes:
            return

        def hecho(respuesta):
            self.bitacora.accion(f"Baja del producto «{producto['nombre']}»", 'catalogo', respuesta.correlation_id)
            self.cargar_productos()
        self.ejecutar(lambda: self.cliente.peticion('catalogo', 'DELETE', f"/productos/{producto['id']}"), hecho)

    # ------------------------------------------------------------ categorías
    def _categorias(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.nueva_categoria = QLineEdit()
        self.nueva_categoria.setPlaceholderText('Nombre de la nueva categoría')
        self.orden = QSpinBox()
        self.orden.setRange(0, 999)
        diseno.addLayout(fila(self.nueva_categoria, QLabel('Orden:'), self.orden,
                              self.boton('Agregar', self.agregar_categoria, principal=True), None,
                              self.boton('Activar / desactivar', self.alternar_categoria)))
        self.modelo_categorias = ModeloFilas([('nombre', 'Categoría'), ('descripcion', 'Descripción'),
                                              ('productos', 'Productos'), ('activa', 'Activa')])
        self.vista_categorias = tabla(self.modelo_categorias)
        diseno.addWidget(self.vista_categorias, 1)
        return hoja

    def cargar_categorias(self):
        def llenar(categorias):
            self.categorias = [c for c in categorias if c.get('activa', True)]
            self.modelo_categorias.cambiar(categorias)
        self.ejecutar(lambda: self.cliente.get('catalogo', '/categorias', incluir_inactivas='true').datos['categorias'],
                      llenar)

    def agregar_categoria(self):
        nombre = self.nueva_categoria.text().strip()
        if len(nombre) < 3:
            self.estado.setText('El nombre debe tener al menos 3 caracteres.')
            return

        def hecho(respuesta):
            self.bitacora.accion(f'Alta de la categoría «{nombre}»', 'catalogo', respuesta.correlation_id)
            self.nueva_categoria.clear()
            self.cargar_categorias()
        self.ejecutar(lambda: self.cliente.peticion('catalogo', 'POST', '/categorias', raiz='categoria_entrada',
                                                    datos={'nombre': nombre, 'orden': self.orden.value()}), hecho)

    def alternar_categoria(self):
        categoria = fila_seleccionada(self.vista_categorias)
        if not categoria:
            return
        activa = not categoria.get('activa', True)

        def hecho(respuesta):
            self.bitacora.accion(f"Categoría «{categoria['nombre']}» {'activada' if activa else 'desactivada'}",
                                 'catalogo', respuesta.correlation_id)
            self.cargar_categorias()
        self.ejecutar(lambda: self.cliente.peticion('catalogo', 'PATCH', f"/categorias/{categoria['id']}",
                                                    raiz='categoria_cambio', datos={'activa': activa}), hecho)
