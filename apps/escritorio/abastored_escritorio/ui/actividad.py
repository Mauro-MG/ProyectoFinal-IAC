"""Registro local de actividades y búsqueda de la traza de una operación en ms-auditoria."""
from PySide6.QtWidgets import QCheckBox, QLabel

from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila_seleccionada, tabla


class Actividad(Pantalla):
    titulo = 'Mi actividad'
    descripcion = ('Lo que has hecho desde esta computadora, guardado localmente (también sin conexión). Con el '
                   'folio de una operación, quien tenga el permiso de auditoría ve su traza completa en todos los '
                   'servicios.')
    permisos = ()    # todos

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.solo_acciones = QCheckBox('Solo mis acciones')
        self.solo_acciones.setChecked(True)
        self.solo_acciones.toggled.connect(lambda _: self.cargar())
        self.traza_boton = self.boton('Ver traza en ms-auditoria', self.traza)
        self.traza_boton.setVisible(cliente.puede('auditoria.ver'))
        self.barra(self.solo_acciones, self.boton('Actualizar', self.cargar), None, self.traza_boton)
        self.modelo = ModeloFilas([('fecha', 'Fecha'), ('servicio', 'Servicio'), ('descripcion', 'Actividad'),
                                   ('status', 'HTTP'), ('correlation_id', 'Folio (correlation id)')])
        self.vista = tabla(self.modelo)
        self.diseno.addWidget(self.vista, 1)
        self.pasos = ModeloFilas([('fecha', 'Hora'), ('servicio', 'Servicio'), ('tipo', 'Paso'), ('ruta', 'Ruta'),
                                  ('status', 'HTTP'), ('descripcion', 'Cambio')])
        self.titulo_traza = QLabel()
        self.diseno.addWidget(self.titulo_traza)
        self.vista_pasos = tabla(self.pasos)
        self.vista_pasos.setVisible(False)
        self.diseno.addWidget(self.vista_pasos, 1)
        self.diseno.addWidget(self.estado)

    def al_mostrar(self):
        self.cargar()

    def cargar(self):
        self.modelo.cambiar(self.bitacora.recientes(solo_acciones=self.solo_acciones.isChecked()))

    def traza(self):
        registro = fila_seleccionada(self.vista)
        if not registro or not registro.get('correlation_id'):
            self.estado.setText('Selecciona una actividad que tenga folio.')
            return
        folio = registro['correlation_id']

        def mostrar(datos):
            self.titulo_traza.setText(f'<b>Traza {folio}</b>: {len(datos["pasos"])} pasos')
            self.pasos.cambiar(datos['pasos'])
            self.vista_pasos.setVisible(True)
        self.ejecutar(lambda: self.cliente.get('auditoria', f'/trazas/{folio}').datos, mostrar)
