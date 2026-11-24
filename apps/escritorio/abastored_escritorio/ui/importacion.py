"""Importación de catálogo mayorista, inventario o precios desde CSV, JSON o XML (ms-integraciones)."""
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QLabel, QLineEdit

from abastored_escritorio import configuracion
from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila, tabla

DESTINOS = {'catalogo_proveedor': 'Catálogo mayorista (proveedor)', 'inventario': 'Inventario de un comercio',
            'precios': 'Precios de un comercio'}


class Importacion(Pantalla):
    titulo = 'Importar archivos'
    descripcion = ('Carga masiva validada por ms-integraciones: cada fila se revisa contra el contrato del destino y '
                   'se aplica en el servicio dueño (ms-proveedores, ms-inventario o ms-precios). Con «simulación» '
                   'solo se valida y no se cambia nada.')
    permisos = ('integraciones.ejecutar', 'importaciones.ejecutar', 'proveedor.catalogo')

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        caja = QGroupBox('Archivo')
        formulario = QFormLayout(caja)
        self.destino, self.comercio = QComboBox(), QComboBox()
        for clave, nombre in DESTINOS.items():
            if clave != 'catalogo_proveedor' or cliente.puede('proveedor.catalogo'):
                self.destino.addItem(nombre, clave)
        self.destino.currentIndexChanged.connect(self._destino_cambio)
        self.ruta = QLineEdit()
        self.ruta.setReadOnly(True)
        self.simulacion = QCheckBox('Simulación (solo validar)')
        self.simulacion.setChecked(True)
        formulario.addRow('Destino:', self.destino)
        formulario.addRow('Comercio:', self.comercio)
        formulario.addRow('Archivo:', fila(self.ruta, self.boton('Elegir…', self.elegir),
                                           self.boton('Descargar plantilla', self.plantilla)))
        formulario.addRow('', self.simulacion)
        formulario.addRow(self.boton('Importar', self.importar, principal=True))
        self.formulario = formulario
        self.diseno.addWidget(caja)
        self.resultado = QLabel()
        self.resultado.setWordWrap(True)
        self.diseno.addWidget(self.resultado)
        self.errores = ModeloFilas([('fila', 'Fila'), ('campo', 'Campo'), ('mensaje', 'Error')])
        self.diseno.addWidget(tabla(self.errores), 1)
        self.diseno.addWidget(self.estado)

    def al_mostrar(self):
        self._destino_cambio()
        if self.cliente.puede('inventario.gestionar'):
            self.ejecutar(lambda: self.cliente.get('comercios', '/comercios', por_pagina=100).datos['items'],
                          lambda comercios: [self.comercio.addItem(c['nombre_comercio'], c['id']) for c in comercios])

    def _destino_cambio(self):
        self.formulario.setRowVisible(self.comercio, self.destino.currentData() in ('inventario', 'precios'))

    def elegir(self):
        ruta, _ = QFileDialog.getOpenFileName(self, 'Archivo a importar', str(Path.home()),
                                              'Datos (*.csv *.json *.xml)')
        if ruta:
            self.ruta.setText(ruta)

    def plantilla(self):
        destino = self.destino.currentData()

        def bajar():
            r = self.cliente.peticion('integraciones', 'GET', f'/plantillas/{destino}', params={'archivo': 'csv'},
                                      binario=True)
            configuracion.CARPETA_LOCAL.mkdir(parents=True, exist_ok=True)
            archivo = configuracion.CARPETA_LOCAL / f'plantilla_{destino}.csv'
            archivo.write_bytes(r.contenido)
            return archivo
        self.ejecutar(bajar, lambda archivo: (self.ruta.setText(str(archivo)),
                                              self.estado.setText(f'Plantilla guardada en {archivo}')))

    def importar(self):
        if not self.ruta.text():
            self.estado.setText('Elige un archivo.')
            return
        ruta, destino = Path(self.ruta.text()), self.destino.currentData()
        formulario = {'destino': destino, 'simulacion': 'true' if self.simulacion.isChecked() else 'false'}
        if destino in ('inventario', 'precios'):
            formulario['comercio_id'] = self.comercio.currentData()

        def enviar():
            with ruta.open('rb') as archivo:
                return self.cliente.peticion('integraciones', 'POST', '/importaciones', form=formulario,
                                             files={'archivo': (ruta.name, archivo.read())})

        def mostrar(respuesta):
            lote = respuesta.datos
            modo = 'Simulación' if lote['simulacion'] else 'Importación'
            self.resultado.setText(
                f"<b>{modo} de {lote['filas']} filas</b>: {lote['validas']} válidas, {lote.get('aplicadas') or 0} "
                f"aplicadas ({lote.get('creadas') or 0} nuevas, {lote.get('actualizadas') or 0} actualizadas), "
                f"<b>{lote['con_error']} con error</b>.")
            self.errores.cambiar(lote.get('errores') or [])
            if not lote['simulacion']:
                self.bitacora.accion(f"Importó {ruta.name} a {DESTINOS[destino]}: {lote.get('aplicadas') or 0} filas "
                                     f"aplicadas, {lote['con_error']} con error", 'integraciones',
                                     respuesta.correlation_id)
        self.ejecutar(enviar, mostrar, 'Enviando archivo…')
