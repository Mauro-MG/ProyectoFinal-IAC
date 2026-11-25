"""
Cobertura, brechas, oportunidades de abasto y concentraciones comerciales (ms-analisis, en XML).

Cada tabla se puede exportar a CSV o PDF e imprimir. Exportar datos es una operación sensible:
queda en la bitácora local y en ms-auditoria (POST /eventos, origen escritorio).
"""
import csv

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QLabel, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from abastored_escritorio import configuracion
from abastored_escritorio.ui.comun import (ModeloFilas, Pantalla, exportar_pdf, fila, formato, imprimir_tabla, tabla)

BRECHAS = [('zona', 'Zona'), ('municipio', 'Municipio'), ('producto', 'Producto'), ('canasta_basica', 'Canasta'),
           ('comercios_analizados', 'Comercios'), ('con_disponibilidad', 'Con existencia'),
           ('cobertura', 'Cobertura %'), ('puntos_requeridos', 'Puntos requeridos'), ('deficit_puntos', 'Déficit'),
           ('proveedores', 'Proveedores'), ('precio_mayoreo_min', 'Mayoreo mín.'), ('nivel', 'Brecha')]
OPORTUNIDADES = [('zona', 'Zona'), ('producto', 'Producto'), ('nivel', 'Brecha'), ('cobertura', 'Cobertura %'),
                 ('sin_disponibilidad', 'Comercios sin existencia'), ('comercios_analizados', 'Comercios'),
                 ('ventas', 'Ventas 30 días'), ('proveedores', 'Proveedores'), ('precio_mayoreo_min', 'Mayoreo mín.'),
                 ('precio_promedio', 'Precio consumidor')]
CONCENTRACIONES = [('municipio_principal', 'Municipio'), ('tamano', 'Comercios'), ('formales', 'Formales'),
                   ('informales', 'Informales'), ('radio_m', 'Radio (m)'), ('cobertura_producto_pct', 'Con producto %'),
                   ('lectura', 'Lectura')]
COLUMNAS = BRECHAS   # compatibilidad con pruebas y otros módulos


class Cobertura(Pantalla):
    titulo = 'Cobertura y brechas'
    descripcion = ('Dónde falta un producto (cobertura contra los puntos de venta que requiere la población), las '
                   'oportunidades de abasto para proveedores y las concentraciones comerciales (DBSCAN).')
    permisos = ('analisis.ver',)

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.pestanas = QTabWidget()
        self.pestanas.addTab(self._brechas(), 'Brechas')
        self.pestanas.addTab(self._oportunidades(), 'Oportunidades de abasto')
        self.pestanas.addTab(self._concentraciones(), 'Concentraciones')
        self.diseno.addWidget(self.pestanas, 1)
        self.diseno.addWidget(self.estado)

    # ------------------------------------------------------------ pestañas
    def _botones_salida(self, nombre, columnas, modelo):
        return (self.boton('CSV…', lambda: self.exportar(nombre, columnas, modelo, 'csv')),
                self.boton('PDF…', lambda: self.exportar(nombre, columnas, modelo, 'pdf')),
                self.boton('Imprimir…', lambda: self.imprimir(nombre, columnas, modelo)))

    def _brechas(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.zona, self.nivel = QComboBox(), QComboBox()
        self.zona.addItem('Todas las zonas', None)
        self.nivel.addItem('Todos los niveles', None)
        for nivel in ('ALTA', 'MEDIA', 'BAJA', 'SIN_BRECHA'):
            self.nivel.addItem(nivel.replace('_', ' ').capitalize(), nivel)
        self.canasta = QCheckBox('Solo canasta básica')
        self.modelo = ModeloFilas(BRECHAS)
        diseno.addLayout(fila(QLabel('Zona:'), self.zona, QLabel('Brecha:'), self.nivel, self.canasta,
                              self.boton('Consultar', self.cargar, principal=True), None,
                              *self._botones_salida('Brechas de surtido', BRECHAS, self.modelo)))
        self.totales = QLabel()
        diseno.addWidget(self.totales)
        diseno.addWidget(tabla(self.modelo), 1)
        return hoja

    def _oportunidades(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.limite = QSpinBox()
        self.limite.setRange(1, 500)
        self.limite.setValue(100)
        self.oportunidades = ModeloFilas(OPORTUNIDADES)
        diseno.addWidget(QLabel('Productos con brecha alta o media en zonas donde hay ventas y proveedores que entregan: '
                                'dónde conviene ofrecer surtido.'))
        diseno.addLayout(fila(QLabel('Máximo:'), self.limite,
                              self.boton('Consultar', self.cargar_oportunidades, principal=True), None,
                              *self._botones_salida('Oportunidades de abasto', OPORTUNIDADES, self.oportunidades)))
        diseno.addWidget(tabla(self.oportunidades), 1)
        return hoja

    def _concentraciones(self):
        hoja = QWidget()
        diseno = QVBoxLayout(hoja)
        self.radio, self.minimo, self.producto = QSpinBox(), QSpinBox(), QComboBox()
        self.radio.setRange(25, 5000)
        self.radio.setSingleStep(50)
        self.radio.setValue(400)
        self.minimo.setRange(1, 100)
        self.minimo.setValue(4)
        self.producto.addItem('(sin producto)', None)
        self.concentraciones = ModeloFilas(CONCENTRACIONES)
        self.resumen_grupos = QLabel()
        diseno.addLayout(fila(QLabel('Distancia (m):'), self.radio, QLabel('Mínimo:'), self.minimo,
                              QLabel('Producto:'), self.producto,
                              self.boton('Agrupar', self.cargar_concentraciones, principal=True), None,
                              *self._botones_salida('Concentraciones comerciales', CONCENTRACIONES,
                                                    self.concentraciones)))
        diseno.addWidget(self.resumen_grupos)
        diseno.addWidget(tabla(self.concentraciones), 1)
        return hoja

    # ------------------------------------------------------------ datos
    def al_mostrar(self):
        def cargar_listas():
            return (self.cliente.get('geolocalizacion', '/zonas').datos['zonas'],
                    self.cliente.get('catalogo', '/productos', por_pagina=200).datos['productos'])

        def llenar(resultado):
            zonas, productos = resultado
            for z in zonas:
                self.zona.addItem(f"{z['nombre']} ({z['municipio']})", z['id'])
            for p in productos:
                self.producto.addItem(p['nombre'], p['id'])
            self.cargar()
        self.ejecutar(cargar_listas, llenar)

    def cargar(self):
        params = {'zona_id': self.zona.currentData(), 'nivel': self.nivel.currentData(), 'por_pagina': 500,
                  'canasta_basica': 'true' if self.canasta.isChecked() else None}

        def mostrar(datos):
            self.modelo.cambiar(datos['brechas'])
            t = datos.get('totales') or {}
            self.totales.setText(f"Brecha alta: <b>{t.get('ALTA', 0)}</b> · media: <b>{t.get('MEDIA', 0)}</b> · "
                                 f"baja: <b>{t.get('BAJA', 0)}</b> · sin brecha: <b>{t.get('SIN_BRECHA', 0)}</b> · "
                                 f"mostrando {len(datos['brechas'])} de {datos['paginacion']['total']}")
        self.ejecutar(lambda: self.cliente.get('analisis', '/analisis/brechas', **params).datos, mostrar)

    def cargar_oportunidades(self):
        limite = self.limite.value()
        self.ejecutar(lambda: self.cliente.get('analisis', '/analisis/oportunidades', limite=limite).datos['oportunidades'],
                      self.oportunidades.cambiar)

    def cargar_concentraciones(self):
        params = {'radio_m': self.radio.value(), 'minimo': self.minimo.value(), 'producto_id': self.producto.currentData()}

        def mostrar(d):
            self.concentraciones.cambiar(d['grupos'])
            self.resumen_grupos.setText(f"{d['algoritmo']}: {d['grupos_encontrados']} concentraciones entre "
                                        f"{d['validos']} comercios; {d['porcentaje_ruido']} % aislados "
                                        f"({d['tiempo_ms']} ms).")
        self.ejecutar(lambda: self.cliente.get('analisis', '/analisis/agrupamientos', **params).datos, mostrar)

    # ------------------------------------------------------------ salida
    def _auditar(self, descripcion, entidad):
        self.bitacora.accion(descripcion, 'analisis')
        self.ejecutar(lambda: self.cliente.peticion('auditoria', 'POST', '/eventos', raiz='evento_entrada', datos={
            'tipo_evento': 'LECTURA', 'entidad': entidad, 'descripcion': descripcion, 'origen': 'escritorio'}),
            lambda _: None, 'Registrando…')

    def exportar(self, nombre, columnas, modelo, tipo):
        if not modelo.filas:
            self.estado.setText('No hay datos para exportar; consulta primero.')
            return
        configuracion.CARPETA_LOCAL.mkdir(parents=True, exist_ok=True)
        sugerido = configuracion.CARPETA_LOCAL / f"{nombre.lower().replace(' ', '_')}.{tipo}"
        ruta, _ = QFileDialog.getSaveFileName(self, f'Exportar {nombre}', str(sugerido),
                                              'CSV (*.csv)' if tipo == 'csv' else 'PDF (*.pdf)')
        if not ruta:
            return
        self.guardar(ruta, nombre, columnas, modelo, tipo)

    def guardar(self, ruta, nombre, columnas, modelo, tipo):
        if tipo == 'csv':
            with open(ruta, 'w', newline='', encoding='utf-8-sig') as archivo:   # con BOM: Excel respeta los acentos
                escritor = csv.writer(archivo)
                escritor.writerow([titulo for _, titulo in columnas])
                for f in modelo.filas:
                    escritor.writerow([formato(f.get(clave)) for clave, _ in columnas])
        else:
            exportar_pdf(ruta, nombre, columnas, modelo.filas, 'Exportado desde la app de escritorio')
        self.estado.setText(f'Exportado a {ruta}')
        self._auditar(f'Exportó {len(modelo.filas)} renglones de «{nombre}» a {tipo.upper()} desde la app de escritorio',
                      nombre.replace(' ', ''))
        return ruta

    def imprimir(self, nombre, columnas, modelo):
        if modelo.filas:
            imprimir_tabla(self, nombre, columnas, modelo.filas)
            self._auditar(f'Imprimió {len(modelo.filas)} renglones de «{nombre}» desde la app de escritorio',
                          nombre.replace(' ', ''))
