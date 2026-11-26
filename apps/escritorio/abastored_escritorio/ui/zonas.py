"""Configuración de zonas municipales (ms-geolocalizacion, en XML): alta, cambio de centro y radio, activar."""
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLineEdit, QSpinBox)

from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila_seleccionada, imprimir_tabla, tabla

COLUMNAS = [('nombre', 'Zona'), ('municipio', 'Municipio'), ('latitud_centro', 'Latitud'),
            ('longitud_centro', 'Longitud'), ('radio_km', 'Radio (km)'), ('poblacion', 'Población'), ('activa', 'Activa')]


class DialogoZona(QDialog):
    def __init__(self, padre, zona=None):
        super().__init__(padre)
        self.setWindowTitle('Editar zona' if zona else 'Nueva zona')
        formulario = QFormLayout(self)
        self.nombre, self.municipio, self.codigo_postal = QLineEdit(), QLineEdit(), QLineEdit()
        self.latitud, self.longitud, self.radio = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for control, minimo, maximo, decimales in ((self.latitud, -90, 90, 6), (self.longitud, -180, 180, 6),
                                                   (self.radio, 0.1, 20, 2)):
            control.setRange(minimo, maximo)
            control.setDecimals(decimales)
        self.latitud.setValue(25.6866)
        self.longitud.setValue(-100.3161)
        self.radio.setValue(2)
        self.poblacion = QSpinBox()
        self.poblacion.setRange(0, 5_000_000)
        self.activa = QCheckBox('Activa')
        self.activa.setChecked(True)
        formulario.addRow('Nombre:', self.nombre)
        formulario.addRow('Municipio:', self.municipio)
        formulario.addRow('Código postal:', self.codigo_postal)
        formulario.addRow('Latitud del centro:', self.latitud)
        formulario.addRow('Longitud del centro:', self.longitud)
        formulario.addRow('Radio (km, máx. 20):', self.radio)
        formulario.addRow('Población estimada:', self.poblacion)
        formulario.addRow('', self.activa)
        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        formulario.addRow(botones)
        self.zona = zona
        if zona:
            self.nombre.setText(zona['nombre'])
            self.municipio.setText(zona['municipio'])
            self.municipio.setEnabled(False)         # el municipio identifica los datos históricos de la zona
            self.codigo_postal.setText(zona.get('codigo_postal') or '')
            self.latitud.setValue(float(zona['latitud_centro']))
            self.longitud.setValue(float(zona['longitud_centro']))
            self.radio.setValue(float(zona['radio_km']))
            self.poblacion.setValue(int(zona.get('poblacion') or 0))
            self.activa.setChecked(bool(zona.get('activa', True)))
        else:
            self.activa.setVisible(False)

    def datos(self):
        datos = {'nombre': self.nombre.text().strip(), 'codigo_postal': self.codigo_postal.text().strip() or None,
                 'latitud_centro': round(self.latitud.value(), 6), 'longitud_centro': round(self.longitud.value(), 6),
                 'radio_km': round(self.radio.value(), 2), 'poblacion': self.poblacion.value()}
        if self.zona:
            return {**datos, 'activa': self.activa.isChecked()}
        return {**datos, 'municipio': self.municipio.text().strip(), 'estado': 'Nuevo León'}


class Zonas(Pantalla):
    titulo = 'Configuración de zonas'
    descripcion = ('Zonas municipales que se usan para asignar comercios, medir cobertura y brechas. Al cambiar el centro '
                   'o el radio, PostGIS recalcula el área de la zona.')
    permisos = ('catalogos.gestionar',)

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.barra(self.boton('Nueva zona…', self.nueva, principal=True), self.boton('Editar…', self.editar),
                   self.boton('Imprimir…', self.imprimir), None, self.estado)
        self.modelo = ModeloFilas(COLUMNAS)
        self.vista = tabla(self.modelo)
        self.vista.doubleClicked.connect(lambda _: self.editar())
        self.diseno.addWidget(self.vista, 1)

    def al_mostrar(self):
        self.cargar()

    def cargar(self):
        self.ejecutar(lambda: self.cliente.get('geolocalizacion', '/zonas', incluir_inactivas='true').datos['zonas'],
                      self.modelo.cambiar)

    def _guardar(self, metodo, ruta, raiz, dialogo, mensaje):
        def hecho(respuesta):
            self.bitacora.accion(mensaje, 'geolocalizacion', respuesta.correlation_id)
            self.cargar()
        self.ejecutar(lambda: self.cliente.peticion('geolocalizacion', metodo, ruta, raiz=raiz, datos=dialogo.datos()),
                      hecho, 'Guardando…')

    def nueva(self):
        dialogo = DialogoZona(self)
        if dialogo.exec() == QDialog.Accepted:
            self._guardar('POST', '/zonas', 'zona_entrada', dialogo, f'Alta de la zona «{dialogo.nombre.text()}»')

    def editar(self):
        zona = fila_seleccionada(self.vista)
        if not zona:
            return
        dialogo = DialogoZona(self, zona)
        if dialogo.exec() == QDialog.Accepted:
            self._guardar('PATCH', f"/zonas/{zona['id']}", 'zona_cambio', dialogo, f"Cambio de la zona «{zona['nombre']}»")

    def imprimir(self):
        imprimir_tabla(self, 'Zonas municipales', COLUMNAS, self.modelo.filas)
