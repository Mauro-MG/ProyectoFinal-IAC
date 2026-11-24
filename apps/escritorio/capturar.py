"""
Abre la aplicación con un usuario, recorre todos sus módulos y guarda una captura de cada uno.
Sirve para revisar la interfaz sin hacer clic y para las evidencias del avance.

    python capturar.py coordinador@test.mx Password123! [carpeta]

Con QT_QPA_PLATFORM=offscreen corre sin mostrar ventanas.
"""
import sys
import time
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from abastored_escritorio.bitacora import Bitacora
from abastored_escritorio.cliente import Cliente
from abastored_escritorio.ui.principal import ESTILO, VentanaPrincipal


def esperar(app, segundos=20):
    limite = time.time() + segundos
    while time.time() < limite:
        app.processEvents()
        if QThreadPool.globalInstance().activeThreadCount() == 0:
            for _ in range(5):
                app.processEvents()
                time.sleep(0.05)
            if QThreadPool.globalInstance().activeThreadCount() == 0:
                return
        time.sleep(0.05)


def main(email, password, carpeta='capturas'):
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(ESTILO)
    bitacora = Bitacora()
    cliente = Cliente(al_registrar=bitacora.peticion)
    cliente.iniciar_sesion(email, password)
    bitacora.usuario = email
    ventana = VentanaPrincipal(cliente, bitacora)
    ventana.show()
    salida = Path(carpeta)
    salida.mkdir(parents=True, exist_ok=True)
    rol = cliente.usuario['rol'].split()[0].lower()
    for i in range(ventana.menu.count()):
        ventana.menu.setCurrentRow(i)
        esperar(app)
        nombre = ventana.menu.item(i).text().lower().replace(' ', '_')
        ventana.grab().save(str(salida / f'{rol}_{i:02d}_{nombre}.png'))
        print('captura', rol, ventana.menu.item(i).text())
    ventana.close()


if __name__ == '__main__':
    main(*sys.argv[1:])
