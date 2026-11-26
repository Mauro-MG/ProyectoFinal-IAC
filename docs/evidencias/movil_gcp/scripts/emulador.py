"""Maneja la app en el emulador con adb: buscar textos en la pantalla, tocar, escribir y capturar."""
import os
import re
import subprocess
import time

ADB = os.path.expandvars(r'%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe')
SALIDA = os.path.dirname(os.path.abspath(__file__))


def adb(*args, binario=False):
    r = subprocess.run([ADB, *args], capture_output=True)
    return r.stdout if binario else r.stdout.decode('utf-8', 'replace')


def nodos():
    adb('shell', 'uiautomator', 'dump', '/sdcard/ui.xml')
    xml = adb('shell', 'cat', '/sdcard/ui.xml')
    resultado = []
    for m in re.finditer(r'<node [^>]*>', xml):
        n = m.group(0)
        texto = re.search(r' text="([^"]*)"', n).group(1)
        desc = re.search(r'content-desc="([^"]*)"', n).group(1)
        x1, y1, x2, y2 = map(int, re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n).groups())
        resultado.append((texto or desc, (x1 + x2) // 2, (y1 + y2) // 2))
    return resultado


def esperar(texto, segundos=40):
    limite = time.time() + segundos
    while time.time() < limite:
        actuales = nodos()
        for t, x, y in actuales:                # primero la coincidencia exacta (botón «Agregar» vs título)
            if texto.lower() == t.lower():
                return x, y
        for t, x, y in actuales:
            if texto.lower() in t.lower():
                return x, y
        time.sleep(1.5)
    raise SystemExit(f'No apareció «{texto}». En pantalla: {[t for t, _, _ in nodos() if t][:30]}')


def tocar(texto, segundos=40):
    x, y = esperar(texto, segundos)
    adb('shell', 'input', 'tap', str(x), str(y))
    time.sleep(0.8)


def escribir(campo, valor):
    tocar(campo)
    adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
    for _ in range(20):
        adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    adb('shell', 'input', 'text', valor.replace(' ', '%s'))
    time.sleep(0.4)
    ocultar_teclado()


def ocultar_teclado():
    """Cierra el teclado en pantalla solo si está abierto (BACK sin teclado saldría de la pantalla)."""
    time.sleep(0.4)
    if re.search(r'mInputShown=true', adb('shell', 'dumpsys', 'input_method')):
        adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
        time.sleep(0.8)


def captura(nombre):
    with open(os.path.join(SALIDA, f'movil_{nombre}.png'), 'wb') as f:
        f.write(adb('exec-out', 'screencap', '-p', binario=True))


def textos():
    return [t for t, _, _ in nodos() if t]


def campos():
    """Centros de los campos de texto en pantalla, en orden."""
    adb('shell', 'uiautomator', 'dump', '/sdcard/ui.xml')
    xml = adb('shell', 'cat', '/sdcard/ui.xml')
    res = []
    for n in re.findall(r'<node [^>]*>', xml):
        if 'EditText' in n:
            x1, y1, x2, y2 = map(int, re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n).groups())
            res.append(((x1 + x2) // 2, (y1 + y2) // 2, re.search(r' text="([^"]*)"', n).group(1)))
    return res


def escribir_en(indice, valor):
    x, y, _ = campos()[indice]
    adb('shell', 'input', 'tap', str(x), str(y))
    time.sleep(0.8)
    adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
    for _ in range(40):
        adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    for parte in re.split(r'(@)', valor):      # el @ se manda como tecla para que el teclado no lo trate como atajo
        if parte == '@':
            adb('shell', 'input', 'keyevent', 'KEYCODE_AT')
        elif parte:
            adb('shell', 'input', 'text', parte.replace(' ', '%s'))
    ocultar_teclado()
    escrito = campos()[indice][2]
    if escrito != valor and '•' not in escrito and escrito:
        print(f'  aviso: campo {indice} quedó «{escrito}» en lugar de «{valor}»')
