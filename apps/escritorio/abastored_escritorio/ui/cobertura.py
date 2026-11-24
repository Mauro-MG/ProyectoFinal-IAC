"""Cobertura y brechas de surtido por zona y producto (ms-analisis), con exportación a CSV."""
import csv

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QLabel

from abastored_escritorio import configuracion
from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, formato, tabla

COLUMNAS = [('zona', 'Zona'), ('municipio', 'Municipio'), ('producto', 'Producto'), ('canasta_basica', 'Canasta'),
            ('comercios_analizados', 'Comercios'), ('con_disponibilidad', 'Con existencia'),
            ('cobertura', 'Cobertura %'), ('puntos_requeridos', 'Puntos requeridos'), ('deficit_puntos', 'Déficit'),
            ('proveedores', 'Proveedores'), ('precio_mayoreo_min', 'Mayoreo mín.'), ('nivel', 'Brecha')]


class Cobertura(Pantalla):
    titulo = 'Cobertura y brechas'
    descripcion = ('Dónde falta un producto: cobertura de comercios con existencia contra los puntos de venta '
                   'necesarios para la población de cada zona. Los umbrales los define ms-configuracion.')
    permisos = ('analisis.ver',)

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.zona, self.nivel = QComboBox(), QComboBox()
        self.zona.addItem('Todas las zonas', None)
        self.nivel.addItem('Todos los niveles', None)
        for nivel in ('ALTA', 'MEDIA', 'BAJA', 'SIN_BRECHA'):
            self.nivel.addItem(nivel.replace('_', ' ').capitalize(), nivel)
        self.canasta = QCheckBox('Solo canasta básica')
        self.barra(QLabel('Zona:'), self.zona, QLabel('Brecha:'), self.nivel, self.canasta,
                   self.boton('Consultar', self.cargar, principal=True), None,
                   self.boton('Exportar CSV…', self.exportar))
        self.totales = QLabel()
        self.diseno.addWidget(self.totales)
        self.modelo = ModeloFilas(COLUMNAS)
        self.diseno.addWidget(tabla(self.modelo), 1)
        self.diseno.addWidget(self.estado)

    def al_mostrar(self):
        def llenar(zonas):
            for z in zonas:
                self.zona.addItem(f"{z['nombre']} ({z['municipio']})", z['id'])
            self.cargar()
        self.ejecutar(lambda: self.cliente.get('geolocalizacion', '/zonas').datos['zonas'], llenar)

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

    def exportar(self):
        if not self.modelo.filas:
            return
        configuracion.CARPETA_LOCAL.mkdir(parents=True, exist_ok=True)
        ruta, _ = QFileDialog.getSaveFileName(self, 'Exportar brechas', str(configuracion.CARPETA_LOCAL / 'brechas.csv'),
                                              'CSV (*.csv)')
        if not ruta:
            return
        with open(ruta, 'w', newline='', encoding='utf-8-sig') as archivo:   # con BOM: Excel respeta los acentos
            escritor = csv.writer(archivo)
            escritor.writerow([titulo for _, titulo in COLUMNAS])
            for f in self.modelo.filas:
                escritor.writerow([formato(f.get(clave)) for clave, _ in COLUMNAS])
        # Exportar datos es una operación sensible: queda en la bitácora local y en ms-auditoria
        descripcion = f'Exportó {len(self.modelo.filas)} brechas a CSV desde la app de escritorio'
        self.bitacora.accion(descripcion, 'analisis')
        self.ejecutar(lambda: self.cliente.peticion('auditoria', 'POST', '/eventos', raiz='evento_entrada', datos={
            'tipo_evento': 'LECTURA', 'entidad': 'ReporteBrechas', 'descripcion': descripcion, 'origen': 'escritorio',
            'datos': None}), lambda _: self.estado.setText(f'Exportado a {ruta}'), 'Registrando…')
