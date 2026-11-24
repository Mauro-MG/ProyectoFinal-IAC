"""Reportes en PDF, Excel, CSV o JSON generados por ms-reportes y guardados en la computadora."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QSpinBox

from abastored_escritorio import configuracion
from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila_seleccionada, tabla


class Reportes(Pantalla):
    titulo = 'Reportes'
    descripcion = ('ms-reportes arma el archivo con los datos vigentes y lo conserva 30 días. La aplicación lo '
                   'descarga a tu carpeta AbastoRed/reportes y lo abre.')
    permisos = ('reportes.ver', 'pedidos.atender', 'inventario.gestionar')

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.tipos = {}
        caja = QGroupBox('Nuevo reporte')
        formulario = QFormLayout(caja)
        self.tipo, self.formato_archivo = QComboBox(), QComboBox()
        self.tipo.currentIndexChanged.connect(self._filtros_del_tipo)
        self.zona, self.comercio = QComboBox(), QComboBox()
        self.zona.addItem('Todas', None)
        self.dias = QSpinBox()
        self.dias.setRange(1, 366)
        self.dias.setValue(30)
        self.canasta = QCheckBox('Solo canasta básica')
        self.descripcion_tipo = QLabel()
        formulario.addRow('Tipo:', self.tipo)
        formulario.addRow('', self.descripcion_tipo)
        formulario.addRow('Formato:', self.formato_archivo)
        self.filas_filtro = {'zona_id': ('Zona:', self.zona), 'comercio_id': ('Comercio:', self.comercio),
                             'dias': ('Días:', self.dias), 'solo_canasta': ('', self.canasta)}
        for titulo, control in self.filas_filtro.values():
            formulario.addRow(titulo, control)
        formulario.addRow(self.boton('Generar y abrir', self.generar, principal=True))
        self.formulario = formulario
        self.diseno.addWidget(caja)

        self.modelo = ModeloFilas([('titulo', 'Reporte'), ('formato', 'Formato'), ('renglones', 'Renglones'),
                                   ('generado', 'Generado'), ('expira', 'Disponible hasta'),
                                   ('nombre_archivo', 'Archivo')])
        self.vista = tabla(self.modelo)
        self.vista.doubleClicked.connect(lambda _: self.descargar(fila_seleccionada(self.vista)))
        self.diseno.addWidget(QLabel('<b>Mis reportes recientes</b> (doble clic para abrir)'))
        self.diseno.addWidget(self.vista, 1)
        self.diseno.addWidget(self.estado)

    def al_mostrar(self):
        def cargar():
            tipos = self.cliente.get('reportes', '/reportes/tipos').datos['tipos']
            zonas = self.cliente.get('geolocalizacion', '/zonas').datos['zonas']
            comercios = []
            if self.cliente.puede('inventario.gestionar', 'comercios.ver_todos'):
                comercios = self.cliente.get('comercios', '/comercios', por_pagina=100).datos['items']
            return tipos, zonas, comercios

        def llenar(resultado):
            tipos, zonas, comercios = resultado
            for z in zonas:
                self.zona.addItem(f"{z['nombre']} ({z['municipio']})", z['id'])
            for c in comercios:
                self.comercio.addItem(c['nombre_comercio'], c['id'])
            for t in tipos:
                self.tipos[t['tipo']] = t
                self.tipo.addItem(t['descripcion'], t['tipo'])
            self.recientes()
        self.ejecutar(cargar, llenar, 'Cargando tipos de reporte…')

    def _filtros_del_tipo(self):
        tipo = self.tipos.get(self.tipo.currentData())
        if not tipo:
            return
        self.descripcion_tipo.setText(f"<small>Filtros: {', '.join(tipo['filtros']) or 'ninguno'}</small>")
        self.formato_archivo.clear()
        self.formato_archivo.addItems(tipo['formatos'])
        for clave, (_, control) in self.filas_filtro.items():
            self.formulario.setRowVisible(control, clave in tipo['filtros'])

    def recientes(self):
        self.ejecutar(lambda: self.cliente.get('reportes', '/reportes').datos['reportes'], self.modelo.cambiar)

    def generar(self):
        tipo = self.tipos.get(self.tipo.currentData())
        if not tipo:
            return
        valores = {'zona_id': self.zona.currentData(), 'comercio_id': self.comercio.currentData(),
                   'dias': self.dias.value(), 'solo_canasta': self.canasta.isChecked() or None}
        filtros = {k: v for k, v in valores.items() if k in tipo['filtros'] and v is not None}
        if 'comercio_id' in tipo['filtros'] and not filtros.get('comercio_id'):
            self.estado.setText('Este reporte necesita un comercio.')
            return

        def hecho(respuesta):
            reporte = respuesta.datos
            self.bitacora.accion(f"Generó el reporte «{reporte['titulo']}» ({reporte['formato']}, "
                                 f"{reporte['renglones']} renglones)", 'reportes', respuesta.correlation_id)
            self.descargar(reporte)
            self.recientes()
        self.ejecutar(lambda: self.cliente.peticion('reportes', 'POST', '/reportes', raiz='reporte_entrada', datos={
            'tipo': tipo['tipo'], 'formato': self.formato_archivo.currentText(), 'filtros': filtros}), hecho,
            'Generando…')

    def descargar(self, reporte):
        if not reporte:
            return
        carpeta = configuracion.CARPETA_LOCAL / 'reportes'

        def bajar():
            archivo = self.cliente.peticion('reportes', 'GET', f"/reportes/{reporte['id']}/archivo", binario=True)
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / reporte['nombre_archivo']
            destino.write_bytes(archivo.contenido)
            return destino

        def abrir(destino):
            self.estado.setText(f'Guardado en {destino}')
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(destino)))
        self.ejecutar(bajar, abrir, 'Descargando…')
