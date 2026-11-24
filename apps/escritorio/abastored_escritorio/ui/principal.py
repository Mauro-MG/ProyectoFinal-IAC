"""Ventana de inicio de sesión y ventana principal con los módulos que permite el rol."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QPushButton, QSplitter, QStackedWidget, QVBoxLayout)

from abastored_escritorio.ui.actividad import Actividad
from abastored_escritorio.ui.cobertura import Cobertura
from abastored_escritorio.ui.comun import en_segundo_plano, mostrar_error
from abastored_escritorio.ui.importacion import Importacion
from abastored_escritorio.ui.pedidos import Pedidos
from abastored_escritorio.ui.precios import ComparacionPrecios
from abastored_escritorio.ui.reportes import Reportes
from abastored_escritorio.ui.validacion import ValidacionComercios, VerificacionProveedores

MODULOS = [ValidacionComercios, VerificacionProveedores, Pedidos, ComparacionPrecios, Cobertura, Importacion,
           Reportes, Actividad]

ESTILO = """
QWidget { font-size: 10pt; }
QListWidget#menu { background: #1f3b2d; color: #e8f0eb; border: none; padding-top: 8px; }
QListWidget#menu::item { padding: 10px 14px; }
QListWidget#menu::item:selected { background: #2f6b4f; color: white; }
QPushButton#principal { background: #2f6b4f; color: white; padding: 5px 14px; border-radius: 3px; }
QPushButton#principal:disabled { background: #9db5a8; }
QLabel#estado { color: #5f6b64; }
"""


class Login(QDialog):
    def __init__(self, cliente, bitacora):
        super().__init__()
        self.cliente, self.bitacora = cliente, bitacora
        self.setWindowTitle('AbastoRed · Iniciar sesión')
        self.setMinimumWidth(380)
        diseno = QVBoxLayout(self)
        diseno.addWidget(QLabel('<h2>AbastoRed</h2><p>Aplicación de escritorio para coordinación municipal, '
                                'análisis de mercado y proveedores.</p>'))
        formulario = QFormLayout()
        self.email, self.password = QLineEdit(), QLineEdit()
        self.email.setPlaceholderText('correo@ejemplo.mx')
        self.password.setEchoMode(QLineEdit.Password)
        formulario.addRow('Correo:', self.email)
        formulario.addRow('Contraseña:', self.password)
        diseno.addLayout(formulario)
        self.mensaje = QLabel()
        self.mensaje.setWordWrap(True)
        self.mensaje.setStyleSheet('color: #a33;')
        diseno.addWidget(self.mensaje)
        self.entrar = QPushButton('Entrar')
        self.entrar.setObjectName('principal')
        self.entrar.setDefault(True)
        self.entrar.clicked.connect(self.iniciar)
        diseno.addWidget(self.entrar)
        diseno.addWidget(QLabel(f'<small>Servidor: {cliente.gateway}</small>'))

    def iniciar(self):
        email, password = self.email.text().strip(), self.password.text()
        if not email or not password:
            self.mensaje.setText('Escribe tu correo y tu contraseña.')
            return
        self.entrar.setEnabled(False)
        self.mensaje.setText('Validando…')

        def listo(usuario):
            self.bitacora.usuario = usuario['email']
            self.bitacora.accion(f"Inicio de sesión ({usuario['rol']})", 'seguridad')
            self.accept()

        def fallo(error):
            self.entrar.setEnabled(True)
            self.mensaje.setText(str(error))
        en_segundo_plano(lambda: self.cliente.iniciar_sesion(email, password), listo, fallo, self)


class VentanaPrincipal(QMainWindow):
    def __init__(self, cliente, bitacora):
        super().__init__()
        self.cliente, self.bitacora = cliente, bitacora
        usuario = cliente.usuario
        self.setWindowTitle(f"AbastoRed · {usuario['nombre']} {usuario.get('apellido') or ''} ({usuario['rol']})")
        self.resize(1200, 760)

        self.menu = QListWidget()
        self.menu.setObjectName('menu')
        self.menu.setFixedWidth(220)
        self.paginas = QStackedWidget()
        self.mostradas = set()
        for modulo in MODULOS:
            if modulo.permisos and not cliente.puede(*modulo.permisos):
                continue
            pagina = modulo(cliente, bitacora)
            self.paginas.addWidget(pagina)
            QListWidgetItem(modulo.titulo, self.menu)
        self.menu.currentRowChanged.connect(self.abrir)

        division = QSplitter()
        division.addWidget(self.menu)
        division.addWidget(self.paginas)
        division.setStretchFactor(1, 1)
        self.setCentralWidget(division)

        salir = QPushButton('Cerrar sesión')
        salir.clicked.connect(self.cerrar_sesion)
        self.sesion = QLabel()
        self.statusBar().addPermanentWidget(self.sesion)
        self.statusBar().addPermanentWidget(salir)
        self._reloj = QTimer(self)
        self._reloj.timeout.connect(self._estado_sesion)
        self._reloj.start(30_000)
        self._estado_sesion()
        self.menu.setCurrentRow(0)

    def abrir(self, indice):
        self.paginas.setCurrentIndex(indice)
        pagina = self.paginas.widget(indice)
        if pagina is not None and indice not in self.mostradas:
            self.mostradas.add(indice)
            pagina.al_mostrar()

    def _estado_sesion(self):
        minutos = max(self.cliente.segundos_restantes(), 0) // 60
        self.sesion.setText(f"{self.cliente.usuario['email']} · sesión vigente {minutos // 60} h {minutos % 60} min "
                            f"(se renueva sola)")

    def cerrar_sesion(self):
        self.bitacora.accion('Cierre de sesión', 'seguridad')
        en_segundo_plano(self.cliente.cerrar_sesion, lambda _: self.close(), lambda e: mostrar_error(self, e), self)

    def closeEvent(self, evento):
        self._reloj.stop()
        super().closeEvent(evento)


__all__ = ['Login', 'VentanaPrincipal', 'ESTILO', 'MODULOS', 'Qt']
