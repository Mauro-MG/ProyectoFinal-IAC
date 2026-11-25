"""
Aplicación de escritorio de AbastoRed.

    cd apps/escritorio
    python -m abastored_escritorio               # abre la aplicación
    python -m abastored_escritorio --diagnostico # revisa configuración, TLS y contratos sin abrir ventanas

Configuración: abastored.ini (lo pone el instalador) o variables ABASTORED_GATEWAY, ABASTORED_CA,
ABASTORED_CARPETA (ver configuracion.py).
"""
import sys


def diagnostico():
    """Comprobación para soporte y para probar el instalador en un equipo limpio. Regresa 0 si todo responde."""
    from abastored_escritorio import configuracion
    from abastored_escritorio.cliente import Cliente, ErrorServicio
    print(f'AbastoRed escritorio · ejecutable: {configuracion.CONGELADA}')
    print(f'Gateway: {configuracion.GATEWAY}')
    print(f'Certificado: {configuracion.certificado()}')
    print(f'Carpeta local: {configuracion.CARPETA_LOCAL}')
    cliente = Cliente()
    try:
        for servicio in ('seguridad', 'comercios', 'analisis'):
            contrato = cliente.contrato(servicio)
            print(f'  ms-{servicio}: contrato XSD válido con {len(contrato.raices)} elementos raíz')
        r = cliente.http.get(f'{cliente.gateway}/ms/monitoreo/api/v1/estado/publico',
                             headers={'Accept': 'application/xml'}, timeout=30)
        documento = __import__('lxml.etree', fromlist=['etree']).fromstring(r.content)
        cliente.contrato('monitoreo').validar(documento)
        datos = cliente.contrato('monitoreo').a_datos(documento)
        print(f"  Estado público (XML validado): {datos['ok']} de {datos['total']} servicios en línea")
    except (ErrorServicio, Exception) as error:  # noqa: BLE001 - se informa cualquier falla
        print(f'ERROR: {error}')
        return 1
    print('Diagnóstico correcto')
    return 0


def main():
    if '--diagnostico' in sys.argv:
        return diagnostico()
    from PySide6.QtWidgets import QApplication, QDialog

    from abastored_escritorio.bitacora import Bitacora
    from abastored_escritorio.cliente import Cliente
    from abastored_escritorio.ui.principal import ESTILO, Login, VentanaPrincipal

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
