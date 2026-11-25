"""Recorrido de la app Android (APK de release firmado) contra el sistema desplegado en Google Cloud."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uuid

import requests

from emulador import adb, captura, escribir, escribir_en, esperar, textos, tocar

GATEWAY = 'https://34.135.84.31'
CA = r'C:\Integracion\ProyectoFinal-IAC\apps\infra\gcp\certificado_gateway_gcp.crt'
PAQUETE = 'mx.abastored.movil'
email = f'movil{uuid.uuid4().hex[:6]}@prueba.mx'
clave = 'MovilPrueba2026'

adb('shell', 'pm', 'clear', PAQUETE)
for permiso in ('ACCESS_FINE_LOCATION', 'ACCESS_COARSE_LOCATION', 'CAMERA', 'POST_NOTIFICATIONS'):
    adb('shell', 'pm', 'grant', PAQUETE, f'android.permission.{permiso}')
adb('shell', 'am', 'start', '-n', f'{PAQUETE}/.ui.MainActivity')

# 1. Registro simplificado
tocar('Crear una cuenta nueva')
captura('10_registro')
escribir_en(0, 'Lucia')
escribir_en(1, 'Trevino')
escribir_en(3, email)
escribir_en(4, clave)
tocar('Crear cuenta')
esperar('Inventario', 60)
print('1 REGISTRO OK', email)

# 2. Comercio con la ubicación del teléfono (Perfil)
tocar('Perfil')
esperar('Registra tu comercio')
escribir('Nombre del comercio', 'Puesto Lucia movil')
escribir('Dirección o referencia', 'Mercado Juarez pasillo 3')
escribir('Municipio', 'Monterrey')
tocar('Usar mi ubicación')
esperar('Ubicación: 25.68', 30)
captura('11_comercio_ubicacion')
tocar('Registrar comercio')
esperar('Comercio registrado', 40)
print('2 COMERCIO OK', [t for t in textos() if 'zona' in t.lower()][:2])
time.sleep(3)

# 3. Alta de producto desde el catálogo maestro
tocar('Inventario')
time.sleep(2)
tocar('Agregar producto')
escribir('Buscar en el catálogo', 'arroz')
esperar('Arroz blanco 1 kg', 30)
tocar('Arroz blanco 1 kg')
escribir('Existencia inicial', '12')
escribir('Precio de venta (opcional)', '30')
tocar('Agregar')
esperar('agregado a tu inventario', 40)
captura('12_inventario')
print('3 PRODUCTO OK')
time.sleep(3)

# 4. Abasto: recomendaciones y solicitud a un proveedor
tocar('Abasto')
esperar('Recomendado para tu comercio', 40)
time.sleep(6)
captura('13_abasto')
tocar('Ver proveedores', 40)
time.sleep(4)
captura('14_ofertas')
nombres = [t for t in textos() if ': $' in t]
print('4 OFERTAS', nombres[:3])
if nombres:
    tocar(nombres[0])
    time.sleep(1)
    escribir_en(0, '20')
    tocar('Enviar pedido')
    esperar('enviado a', 40)
    print('4 PEDIDO ENVIADO')
time.sleep(3)

# 5. Avisos y perfil
tocar('Avisos')
time.sleep(5)
captura('15_avisos')
print('5 AVISOS', textos()[:4])
tocar('Perfil')
time.sleep(4)
captura('16_perfil')

# 5b. Sin revocar, al reabrir la app la sesión sigue (el dispositivo sigue vigente en el servidor)
adb('shell', 'am', 'force-stop', PAQUETE)
adb('shell', 'am', 'start', '-n', f'{PAQUETE}/.ui.MainActivity')
time.sleep(8)
esperar('Inventario', 60)
assert 'Entrar' not in textos(), 'la app cerró la sesión sin que se revocara el dispositivo'
print('5b REAPERTURA: la sesión se mantiene')

# 6. El dispositivo quedó registrado; se revoca desde el servidor y la app cierra la sesión al abrirse
s = requests.Session()
s.verify = CA
t = s.post(f'{GATEWAY}/ms/seguridad/api/v1/auth/login', json={'email': email, 'password': clave}).json()
s.headers['Authorization'] = 'Bearer ' + t['access_token']
dispositivos = s.get(f'{GATEWAY}/ms/notificaciones/api/v1/dispositivos').json()['dispositivos']
print('6 DISPOSITIVOS EN EL SERVIDOR', [(d.get('plataforma'), d.get('nombre'), d.get('token_final')) for d in dispositivos])
for d in dispositivos:
    print('  revocado', s.delete(f"{GATEWAY}/ms/notificaciones/api/v1/dispositivos/{d['token_final']}").status_code)
adb('shell', 'am', 'force-stop', PAQUETE)
adb('shell', 'am', 'start', '-n', f'{PAQUETE}/.ui.MainActivity')
esperar('Entrar', 60)
captura('17_revocado')
print('6 REVOCACION: la app volvió al inicio de sesión')
