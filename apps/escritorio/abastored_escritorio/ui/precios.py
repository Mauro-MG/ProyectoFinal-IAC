"""Comparación de precios (consumidor formal/informal y mayoreo) y revisión de precios atípicos."""
from PySide6.QtWidgets import QComboBox, QInputDialog, QLabel, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila, fila_seleccionada, formato, tabla


def catalogos(cliente):
    """Productos (ms-catalogo) y zonas (ms-geolocalizacion) para los filtros."""
    productos = cliente.get('catalogo', '/productos', por_pagina=200).datos['productos']
    zonas = cliente.get('geolocalizacion', '/zonas').datos['zonas']
    return productos, zonas


class ComparacionPrecios(Pantalla):
    titulo = 'Precios'
    descripcion = ('Compara el precio al consumidor entre comercios formales e informales y contra el precio de '
                   'mayoreo de los proveedores (últimos 30 días, ms-precios).')
    permisos = ('precios.consultar', 'comercios.validar')

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        pestanas = QTabWidget()
        self.diseno.addWidget(pestanas, 1)
        pestanas.addTab(self._comparacion(), 'Comparación')
        if cliente.puede('comercios.validar'):
            pestanas.addTab(self._atipicos(), 'Precios atípicos por revisar')
        self.diseno.addWidget(self.estado)

    # ------------------------------------------------------------ comparación
    def _comparacion(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.producto, self.zona = QComboBox(), QComboBox()
        self.producto.setMinimumWidth(260)
        self.zona.addItem('Todas las zonas', None)
        diseno.addLayout(fila(QLabel('Producto:'), self.producto, QLabel('Zona:'), self.zona,
                              self.boton('Comparar', self.comparar, principal=True), None))
        self.resumen = QLabel()
        self.resumen.setWordWrap(True)
        diseno.addWidget(self.resumen)
        self.consumidor = ModeloFilas([('zona', 'Zona'), ('municipio', 'Municipio'), ('sector', 'Sector'),
                                       ('minimo', 'Mínimo'), ('promedio', 'Promedio'), ('maximo', 'Máximo'),
                                       ('comercios', 'Comercios'), ('muestras', 'Muestras')])
        self.mayoreo = ModeloFilas([('proveedor', 'Proveedor'), ('minimo', 'Mínimo'), ('promedio', 'Promedio'),
                                    ('maximo', 'Máximo'), ('muestras', 'Muestras')])
        diseno.addWidget(QLabel('<b>Precio al consumidor</b>'))
        diseno.addWidget(tabla(self.consumidor), 2)
        diseno.addWidget(QLabel('<b>Precio de mayoreo</b>'))
        diseno.addWidget(tabla(self.mayoreo), 1)
        return hoja

    def al_mostrar(self):
        def llenar(resultado):
            productos, zonas = resultado
            for p in productos:
                self.producto.addItem(p['nombre'], p['id'])
            for z in zonas:
                self.zona.addItem(f"{z['nombre']} ({z['municipio']})", z['id'])
            self.comparar()
        self.ejecutar(lambda: catalogos(self.cliente), llenar, 'Cargando catálogos…')
        if self.cliente.puede('comercios.validar'):
            self.cargar_atipicos()

    def comparar(self):
        producto_id, zona_id = self.producto.currentData(), self.zona.currentData()
        if producto_id is None:
            return

        def mostrar(datos):
            self.consumidor.cambiar(datos['consumidor'])
            self.mayoreo.cambiar(datos['mayoreo'])
            r = (datos['resumen'] or [{}])[0]
            self.resumen.setText(
                f"Del {formato(datos['desde'])} al {formato(datos['hasta'])} · promedio formal "
                f"<b>${formato(r.get('formal'))}</b> · informal <b>${formato(r.get('informal'))}</b> · diferencia "
                f"<b>{formato(r.get('diferencia_pct'))} %</b> · mayoreo mínimo <b>${formato(r.get('mayoreo_min'))}</b>"
                f" · margen <b>{formato(r.get('margen_pct'))} %</b>" if r else 'Sin precios registrados en el periodo.')
        self.ejecutar(lambda: self.cliente.get('precios', '/precios/comparacion', producto_id=producto_id,
                                               zona_id=zona_id).datos, mostrar)

    # ------------------------------------------------------------ atípicos
    def _atipicos(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        diseno.addWidget(QLabel('Precios que salieron del rango normal de su zona (10 %–150 % del promedio, RN-001). '
                                'No entran a la comparación hasta que se validen.'))
        self.pendientes = ModeloFilas([('comercio', 'Comercio'), ('producto', 'Producto'), ('precio_anterior', 'Antes'),
                                       ('precio', 'Precio'), ('metodo_captura', 'Captura'), ('fecha', 'Fecha')])
        self.vista_pendientes = tabla(self.pendientes)
        diseno.addWidget(self.vista_pendientes, 1)
        diseno.addLayout(fila(self.boton('Validar', lambda: self.revisar('VALIDAR'), principal=True),
                              self.boton('Descartar', lambda: self.revisar('DESCARTAR')),
                              self.boton('Actualizar', self.cargar_atipicos), None))
        return hoja

    def cargar_atipicos(self):
        self.ejecutar(lambda: self.cliente.get('precios', '/precios/pendientes').datos['precios'],
                      self.pendientes.cambiar)

    def revisar(self, decision):
        precio = fila_seleccionada(self.vista_pendientes)
        if not precio:
            QMessageBox.information(self, 'Precios', 'Selecciona un precio.')
            return
        comentario, ok = QInputDialog.getText(self, 'Comentario', 'Comentario para el comerciante (opcional):')
        if not ok:
            return

        def hecho(respuesta):
            self.bitacora.accion(f"Precio de {precio['producto']} en {precio['comercio']}: {decision}", 'precios',
                                 respuesta.correlation_id)
            self.cargar_atipicos()
        self.ejecutar(lambda: self.cliente.peticion('precios', 'PATCH', f"/precios/{precio['id']}/validacion",
                                                    raiz='validacion_precio',
                                                    datos={'decision': decision, 'comentario': comentario or None}),
                      hecho, 'Enviando…')
