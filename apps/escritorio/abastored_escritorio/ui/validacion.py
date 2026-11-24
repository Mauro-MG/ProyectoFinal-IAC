"""Validación de comercios y verificación de proveedores (coordinación municipal)."""
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QSplitter, QTextEdit, QWidget)

from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila_seleccionada, formato, tabla

ESTADOS = ['PENDIENTE', 'VERIFICADO', 'SUSPENDIDO', 'RECHAZADO']


class _Revision(Pantalla):
    """Lista filtrada por estado, detalle del registro y botones para cambiar su estado."""
    servicio = ruta = parametro_estado = raiz_entrada = clave_lista = entidad = campo_estado = ''
    columnas = ()
    campos_detalle = ()

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.filtro = QComboBox()
        self.filtro.addItems(ESTADOS)
        self.filtro.currentTextChanged.connect(lambda _: self.cargar())
        self.texto = QLineEdit()
        self.texto.setPlaceholderText('Buscar por nombre…')
        self.texto.returnPressed.connect(self.cargar)
        self.barra(QLabel('Estado:'), self.filtro, self.texto, self.boton('Actualizar', self.cargar), None, self.estado)

        self.modelo = ModeloFilas(list(self.columnas))
        self.vista = tabla(self.modelo)
        self.vista.selectionModel().selectionChanged.connect(self.mostrar_detalle)

        panel = QGroupBox('Detalle y revisión')
        formulario = QFormLayout(panel)
        self.etiquetas = {}
        for clave, titulo in self.campos_detalle:
            self.etiquetas[clave] = QLabel()
            self.etiquetas[clave].setWordWrap(True)
            formulario.addRow(f'{titulo}:', self.etiquetas[clave])
        self.observaciones = QTextEdit()
        self.observaciones.setPlaceholderText('Observaciones (se envían al dueño junto con el resultado)')
        self.observaciones.setMaximumHeight(90)
        formulario.addRow('Observaciones:', self.observaciones)
        self.botones = {'VERIFICADO': self.boton('Verificar', lambda: self.revisar('VERIFICADO'), principal=True),
                        'SUSPENDIDO': self.boton('Suspender', lambda: self.revisar('SUSPENDIDO')),
                        'RECHAZADO': self.boton('Rechazar', lambda: self.revisar('RECHAZADO'))}
        formulario.addRow(self._fila(self.botones.values()))

        division = QSplitter()
        division.addWidget(self.vista)
        division.addWidget(panel)
        division.setSizes([700, 380])
        self.diseno.addWidget(division, 1)
        self.mostrar_detalle()

    def _fila(self, widgets):
        contenedor = QWidget()
        diseno = QHBoxLayout(contenedor)
        diseno.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            diseno.addWidget(w)
        return contenedor

    def al_mostrar(self):
        self.cargar()

    def cargar(self):
        params = {self.parametro_estado: self.filtro.currentText(), 'texto': self.texto.text().strip(),
                  'por_pagina': 100}
        self.ejecutar(lambda: self.cliente.get(self.servicio, self.ruta, **params).datos,
                      lambda datos: (self.modelo.cambiar(datos[self.clave_lista]), self.mostrar_detalle()))

    def mostrar_detalle(self, *_):
        registro = fila_seleccionada(self.vista)
        for clave, etiqueta in self.etiquetas.items():
            etiqueta.setText(formato(registro.get(clave)) if registro else '')
        for estado, boton in self.botones.items():
            boton.setEnabled(registro is not None and registro.get(self.campo_estado) != estado)

    def revisar(self, estado):
        registro = fila_seleccionada(self.vista)
        if not registro:
            return
        nombre = registro.get(self.columnas[0][0])
        if QMessageBox.question(self, 'Confirmar', f'¿Marcar «{nombre}» como {estado.lower()}?') != QMessageBox.Yes:
            return
        observaciones = self.observaciones.toPlainText().strip() or None

        def hecho(respuesta):
            self.bitacora.accion(f'{self.entidad} «{nombre}» → {estado}', self.servicio, respuesta.correlation_id)
            self.observaciones.clear()
            self.cargar()
        self.ejecutar(lambda: self.cliente.peticion(self.servicio, 'PATCH', self.ruta_revision(registro),
                                                    raiz=self.raiz_entrada,
                                                    datos={'estado': estado, 'observaciones': observaciones}),
                      hecho, 'Enviando…')


class ValidacionComercios(_Revision):
    titulo = 'Validación de comercios'
    descripcion = ('Comercios registrados en tu municipio. Solo los verificados aparecen en el portal público y en '
                   'los análisis (RN-015). El dueño recibe una notificación con el resultado.')
    permisos = ('comercios.validar',)
    servicio, ruta, parametro_estado, clave_lista = 'comercios', '/comercios', 'estado_registro', 'items'
    raiz_entrada, entidad, campo_estado = 'validacion_entrada', 'Comercio', 'estado_registro'
    columnas = (('nombre_comercio', 'Comercio'), ('sector', 'Sector'), ('municipio', 'Municipio'), ('zona', 'Zona'),
                ('estado_registro', 'Estado'))
    campos_detalle = (('nombre_comercio', 'Nombre'), ('tipo_comercio', 'Tipo'), ('direccion', 'Dirección'),
                      ('colonia', 'Colonia'), ('municipio', 'Municipio'), ('zona', 'Zona'),
                      ('telefono_comercio', 'Teléfono'), ('estado_registro', 'Estado'))

    def ruta_revision(self, registro):
        return f"/comercios/{registro['id']}/validacion"


class VerificacionProveedores(_Revision):
    titulo = 'Verificación de proveedores'
    descripcion = ('Proveedores que se registraron en la plataforma. Mientras no estén verificados no aparecen en '
                   'las búsquedas de los comercios.')
    permisos = ('proveedores.verificar',)
    servicio, ruta, parametro_estado, clave_lista = 'proveedores', '/proveedores', 'estado_verificacion', 'proveedores'
    raiz_entrada, entidad, campo_estado = 'verificacion_entrada', 'Proveedor', 'estado_verificacion'
    columnas = (('nombre_empresa', 'Empresa'), ('municipio', 'Municipio'), ('pedido_minimo', 'Pedido mínimo'),
                ('tiempo_entrega_dias', 'Días de entrega'), ('estado_verificacion', 'Estado'))
    campos_detalle = (('nombre_empresa', 'Empresa'), ('municipio', 'Municipio'), ('condiciones_venta', 'Condiciones'),
                      ('pedido_minimo', 'Pedido mínimo'), ('estado_verificacion', 'Estado'))

    def ruta_revision(self, registro):
        return f"/proveedores/{registro['id']}/verificacion"
