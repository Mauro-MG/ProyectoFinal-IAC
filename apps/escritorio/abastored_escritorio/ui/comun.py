"""Piezas comunes de la interfaz: tareas en segundo plano, tablas y mensajes."""
from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QTableView, QVBoxLayout, QWidget)

from abastored_escritorio.cliente import ContratoInvalido, ErrorServicio


# ---------------------------------------------------------------- segundo plano

class _Senales(QObject):
    exito = Signal(object)
    fallo = Signal(object)


class _Tarea(QRunnable):
    def __init__(self, funcion):
        super().__init__()
        self.funcion = funcion
        self.senales = _Senales()

    def run(self):
        try:
            resultado = self.funcion()
        except Exception as error:  # noqa: BLE001 - se muestra al usuario en el hilo de la interfaz
            self.senales.fallo.emit(error)
        else:
            self.senales.exito.emit(resultado)


_TAREAS = set()   # referencias vivas mientras corren (si no, Python puede liberar las señales antes de tiempo)


def en_segundo_plano(funcion, al_terminar, al_fallar=None, padre=None):
    """Ejecuta `funcion` sin congelar la ventana; el resultado llega a `al_terminar` en el hilo de la interfaz."""
    tarea = _Tarea(funcion)
    _TAREAS.add(tarea)

    def terminar(resultado):
        _TAREAS.discard(tarea)
        al_terminar(resultado)

    def fallar(error):
        _TAREAS.discard(tarea)
        (al_fallar or (lambda e: mostrar_error(padre, e)))(error)

    tarea.senales.exito.connect(terminar)
    tarea.senales.fallo.connect(fallar)
    QThreadPool.globalInstance().start(tarea)


def mostrar_error(padre, error):
    if isinstance(error, ErrorServicio):
        titulo = {401: 'Sesión', 403: 'Sin permiso', 409: 'No se pudo aplicar', 422: 'Datos inválidos',
                  503: 'Sin conexión'}.get(error.status, 'Error del servicio')
        texto = str(error)
        if error.correlation_id:
            texto += f'\n\nFolio para soporte: {error.correlation_id}'
    elif isinstance(error, ContratoInvalido):
        titulo, texto = 'Contrato XML', str(error)
    else:
        titulo, texto = 'Error inesperado', f'{error.__class__.__name__}: {error}'
    QMessageBox.warning(padre, titulo, texto)


# ---------------------------------------------------------------- tablas

def formato(valor):
    if valor is None:
        return ''
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if isinstance(valor, Decimal):
        return f'{valor:,.2f}'
    if isinstance(valor, datetime):
        return valor.strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    if isinstance(valor, list):
        return ', '.join(formato(v) for v in valor)
    return str(valor)


class ModeloFilas(QAbstractTableModel):
    """Tabla de diccionarios: columnas = [(clave, título), ...]."""

    def __init__(self, columnas, filas=None):
        super().__init__()
        self.columnas = columnas
        self.filas = filas or []

    def cambiar(self, filas):
        self.beginResetModel()
        self.filas = list(filas)
        self.endResetModel()

    def rowCount(self, padre=QModelIndex()):
        return 0 if padre.isValid() else len(self.filas)

    def columnCount(self, padre=QModelIndex()):
        return len(self.columnas)

    def data(self, indice, rol=Qt.DisplayRole):
        valor = self.filas[indice.row()].get(self.columnas[indice.column()][0])
        if rol == Qt.DisplayRole:
            return formato(valor)
        if rol == Qt.TextAlignmentRole and isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rol == Qt.UserRole:
            return valor
        return None

    def headerData(self, seccion, orientacion, rol=Qt.DisplayRole):
        if rol == Qt.DisplayRole and orientacion == Qt.Horizontal:
            return self.columnas[seccion][1]
        return None

    def fila(self, indice):
        return self.filas[indice] if 0 <= indice < len(self.filas) else None


def tabla(modelo):
    vista = QTableView()
    vista.setModel(modelo)
    vista.setSelectionBehavior(QAbstractItemView.SelectRows)
    vista.setSelectionMode(QAbstractItemView.SingleSelection)
    vista.setEditTriggers(QAbstractItemView.NoEditTriggers)
    vista.setAlternatingRowColors(True)
    vista.verticalHeader().hide()
    vista.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    vista.horizontalHeader().setStretchLastSection(True)
    return vista


def fila_seleccionada(vista):
    seleccion = vista.selectionModel().selectedRows()
    return vista.model().fila(seleccion[0].row()) if seleccion else None


def fila(*widgets):
    """Fila horizontal de controles; None deja un espacio flexible."""
    diseno = QHBoxLayout()
    for w in widgets:
        diseno.addWidget(w) if w is not None else diseno.addStretch()
    return diseno


class Pantalla(QWidget):
    """Base de cada módulo: título, descripción, barra de botones y estado."""
    titulo = ''
    descripcion = ''
    permisos = ()          # basta con uno para ver el módulo

    def __init__(self, cliente, bitacora):
        super().__init__()
        self.cliente, self.bitacora = cliente, bitacora
        self.diseno = QVBoxLayout(self)
        encabezado = QLabel(f'<h2>{self.titulo}</h2><p>{self.descripcion}</p>')
        encabezado.setWordWrap(True)
        self.diseno.addWidget(encabezado)
        self.estado = QLabel()
        self.estado.setObjectName('estado')

    def barra(self, *widgets):
        diseno = fila(*widgets)
        self.diseno.addLayout(diseno)
        return diseno

    def boton(self, texto, accion, principal=False):
        b = QPushButton(texto)
        b.clicked.connect(accion)
        if principal:
            b.setDefault(True)
            b.setObjectName('principal')
        return b

    def ejecutar(self, funcion, al_terminar, mensaje='Consultando…'):
        self.estado.setText(mensaje)
        self.setCursor(Qt.BusyCursor)

        def terminar(resultado):
            self.unsetCursor()
            self.estado.setText('')
            al_terminar(resultado)

        def fallar(error):
            self.unsetCursor()
            self.estado.setText('')
            mostrar_error(self, error)
        en_segundo_plano(funcion, terminar, fallar, self)

    def al_mostrar(self):
        """Se llama la primera vez que el usuario abre el módulo."""
