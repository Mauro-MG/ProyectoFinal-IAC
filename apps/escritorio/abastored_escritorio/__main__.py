"""
Aplicación de escritorio de AbastoRed.

    cd apps/escritorio
    python -m abastored_escritorio

Variables opcionales: ABASTORED_GATEWAY (por omisión https://localhost),
ABASTORED_CA (certificado del gateway), ABASTORED_CARPETA (bitácora y reportes).
"""
import sys

from PySide6.QtWidgets import QApplication, QDialog

from abastored_escritorio.bitacora import Bitacora
from abastored_escritorio.cliente import Cliente
from abastored_escritorio.ui.principal import ESTILO, Login, VentanaPrincipal


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('AbastoRed')
    app.setStyleSheet(ESTILO)
    bitacora = Bitacora()
    cliente = Cliente(al_registrar=bitacora.peticion)
    if Login(cliente, bitacora).exec() != QDialog.Accepted:
        return 0
    ventana = VentanaPrincipal(cliente, bitacora)
    ventana.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
