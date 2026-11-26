"""Ejecución de recomendaciones de surtido por zona y del análisis de cobertura (ms-recomendaciones, ms-analisis)."""
from PySide6.QtWidgets import QComboBox, QLabel, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila, imprimir_tabla, tabla

COLUMNAS = [('producto', 'Producto'), ('canasta_basica', 'Canasta'), ('brecha', 'Brecha'), ('cobertura', 'Cobertura %'),
            ('ventas', 'Ventas 30 días'), ('proveedores', 'Proveedores'), ('puntaje', 'Puntaje')]


class Recomendaciones(Pantalla):
    titulo = 'Recomendaciones de surtido'
    descripcion = ('Qué productos conviene surtir en cada zona: brecha de cobertura, canasta básica, ventas, proveedores '
                   'que entregan y búsquedas sin resultado (ms-demanda). Y la ejecución del análisis de cobertura, que '
                   'guarda un corte del índice de acceso de cada zona para seguir su evolución.')
    permisos = ('analisis.ver',)

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        pestanas = QTabWidget()
        pestanas.addTab(self._por_zona(), 'Por zona')
        pestanas.addTab(self._efectividad(), 'Efectividad')
        self.diseno.addWidget(pestanas, 1)
        self.diseno.addWidget(self.estado)

    def _por_zona(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.zona = QComboBox()
        self.zona.setMinimumWidth(240)
        diseno.addLayout(fila(QLabel('Zona:'), self.zona, self.boton('Calcular recomendaciones', self.calcular,
                                                                      principal=True),
                              self.boton('Imprimir…', self.imprimir), None,
                              self.boton('Ejecutar análisis de cobertura', self.ejecutar_analisis)))
        self.modelo = ModeloFilas(COLUMNAS)
        diseno.addWidget(tabla(self.modelo), 1)
        return hoja

    def _efectividad(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.resumen_efectividad = QLabel()
        self.resumen_efectividad.setWordWrap(True)
        self.motivos = ModeloFilas([('motivo', 'Motivo'), ('emitidas', 'Emitidas'), ('adoptadas', 'Adoptadas'),
                                    ('tasa_adopcion_pct', 'Adopción %')])
        diseno.addLayout(fila(self.boton('Actualizar', self.efectividad), None))
        diseno.addWidget(self.resumen_efectividad)
        diseno.addWidget(tabla(self.motivos), 1)
        return hoja

    def al_mostrar(self):
        def llenar(zonas):
            for z in zonas:
                self.zona.addItem(f"{z['nombre']} ({z['municipio']})", z['id'])
            self.calcular()
            self.efectividad()
        self.ejecutar(lambda: self.cliente.get('geolocalizacion', '/zonas').datos['zonas'], llenar)

    def calcular(self):
        zona_id = self.zona.currentData()
        if zona_id is None:
            return

        def mostrar(datos):
            self.modelo.cambiar(datos['productos'])
            self.estado.setText(f"{len(datos['productos'])} productos recomendados para {self.zona.currentText()}")
        self.ejecutar(lambda: self.cliente.get('recomendaciones', f'/recomendaciones/zonas/{zona_id}').datos, mostrar)

    def ejecutar_analisis(self):
        def hecho(respuesta):
            d = respuesta.datos
            self.bitacora.accion(f"Ejecutó el análisis de cobertura: {d['zonas']} zonas, {d['criticas']} críticas",
                                 'analisis', respuesta.correlation_id)
            QMessageBox.information(self, 'Análisis de cobertura',
                                    f"Corte guardado: {d['zonas']} zonas analizadas, {d['criticas']} en nivel crítico.")
        self.ejecutar(lambda: self.cliente.peticion('analisis', 'POST', '/analisis/ejecuciones'), hecho, 'Analizando…')

    def efectividad(self):
        def mostrar(d):
            self.resumen_efectividad.setText(
                f"Últimos {d['dias']} días: {d['emitidas']} recomendaciones emitidas a {d['comercios']} comercios, "
                f"{d['adoptadas']} adoptadas (<b>{d['tasa_adopcion_pct']} %</b>).")
            self.motivos.cambiar(d.get('motivos') or [])
        self.ejecutar(lambda: self.cliente.get('recomendaciones', '/recomendaciones/efectividad').datos, mostrar)

    def imprimir(self):
        imprimir_tabla(self, 'Recomendaciones de surtido', COLUMNAS, self.modelo.filas, self.zona.currentText())
