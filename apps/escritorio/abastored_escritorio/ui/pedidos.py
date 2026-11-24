"""Pedidos de abasto recibidos por el proveedor: revisar partidas y avanzar el pedido (ms-pedidos)."""
from PySide6.QtWidgets import QComboBox, QGroupBox, QInputDialog, QLabel, QSplitter, QVBoxLayout

from abastored_escritorio.ui.comun import ModeloFilas, Pantalla, fila, fila_seleccionada, formato, tabla

ESTADOS = [('Por atender', 'ENVIADO'), ('Aceptados', 'ACEPTADO'), ('En preparación', 'EN_PREPARACION'),
           ('En camino', 'ENVIADO_A_COMERCIO'), ('Entregados', 'ENTREGADO'), ('Todos', None)]
ETIQUETAS = {'aceptar': 'Aceptar', 'rechazar': 'Rechazar', 'preparar': 'Empezar a preparar',
             'despachar': 'Despachar', 'cancelar': 'Cancelar', 'enviar': 'Enviar', 'recibir': 'Confirmar recepción'}


class Pedidos(Pantalla):
    titulo = 'Pedidos recibidos'
    descripcion = ('Pedidos que los comercios le hicieron a tu empresa. Al despachar, ms-pedidos descuenta la '
                   'existencia de tu catálogo en ms-proveedores; si no alcanza, el pedido no avanza.')
    permisos = ('pedidos.atender',)

    def __init__(self, cliente, bitacora):
        super().__init__(cliente, bitacora)
        self.filtro = QComboBox()
        for nombre, estado in ESTADOS:
            self.filtro.addItem(nombre, estado)
        self.filtro.currentIndexChanged.connect(lambda _: self.cargar())
        self.barra(QLabel('Mostrar:'), self.filtro, self.boton('Actualizar', self.cargar), None, self.estado)

        self.modelo = ModeloFilas([('folio', 'Folio'), ('comercio', 'Comercio'), ('estado_legible', 'Estado'),
                                   ('subtotal', 'Subtotal'), ('fecha_envio', 'Enviado'),
                                   ('fecha_entrega_estimada', 'Entrega estimada')])
        self.vista = tabla(self.modelo)
        self.vista.selectionModel().selectionChanged.connect(self.detalle)

        panel = QGroupBox('Detalle')
        diseno = QVBoxLayout(panel)
        self.encabezado = QLabel()
        self.encabezado.setWordWrap(True)
        self.partidas = ModeloFilas([('producto', 'Producto'), ('cantidad', 'Cantidad'),
                                     ('precio_unitario', 'Precio'), ('subtotal', 'Subtotal')])
        self.acciones = fila()
        diseno.addWidget(self.encabezado)
        diseno.addWidget(tabla(self.partidas), 1)
        diseno.addLayout(self.acciones)

        division = QSplitter()
        division.addWidget(self.vista)
        division.addWidget(panel)
        division.setSizes([620, 460])
        self.diseno.addWidget(division, 1)

    def al_mostrar(self):
        self.cargar()

    def cargar(self):
        estado = self.filtro.currentData()
        self.ejecutar(lambda: self.cliente.get('pedidos', '/pedidos', estado=estado, por_pagina=100).datos['pedidos'],
                      lambda pedidos: (self.modelo.cambiar(pedidos), self._pintar(None)))

    def detalle(self, *_):
        pedido = fila_seleccionada(self.vista)
        if pedido:
            self.ejecutar(lambda: self.cliente.get('pedidos', f"/pedidos/{pedido['id']}").datos, self._pintar)
        else:
            self._pintar(None)

    def _pintar(self, pedido):
        while self.acciones.count():
            self.acciones.takeAt(0).widget().deleteLater()
        if not pedido:
            self.encabezado.setText('Selecciona un pedido.')
            self.partidas.cambiar([])
            return
        self.encabezado.setText(f"<b>{pedido['folio']}</b> · {pedido['comercio']} · {pedido['estado_legible']}<br>"
                                f"Subtotal ${formato(pedido['subtotal'])} (mínimo ${formato(pedido['pedido_minimo'])})"
                                + (f"<br>Notas: {pedido['notas']}" if pedido.get('notas') else ''))
        self.partidas.cambiar(pedido.get('partidas') or [])
        for accion in pedido.get('acciones') or []:
            self.acciones.addWidget(self.boton(ETIQUETAS.get(accion, accion),
                                               lambda _=False, a=accion, p=pedido: self.ejecutar_accion(p, a),
                                               principal=accion in ('aceptar', 'despachar')))

    def ejecutar_accion(self, pedido, accion):
        comentario = None
        if accion == 'rechazar':
            comentario, ok = QInputDialog.getText(self, 'Rechazar', 'Motivo (lo verá el comercio):')
            if not ok or not comentario.strip():
                return

        def hecho(respuesta):
            t = respuesta.datos['transicion']
            self.bitacora.accion(f"Pedido {pedido['folio']}: {t['de']} → {t['a']}", 'pedidos', respuesta.correlation_id)
            self._pintar(respuesta.datos)
            self.cargar()
        self.ejecutar(lambda: self.cliente.peticion('pedidos', 'POST', f"/pedidos/{pedido['id']}/acciones/{accion}",
                                                    raiz='accion_entrada', datos={'comentario': comentario}),
                      hecho, 'Enviando…')
