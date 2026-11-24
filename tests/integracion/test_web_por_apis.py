"""
El sistema web solo escribe por las APIs de los servicios dueños (retroalimentación del avance 2).

Se recorre el web como un usuario real (formularios con su token CSRF, por el gateway) y se comprueba
en la bitácora de ms-auditoria que cada cambio lo registró el servicio dueño del dato y no el web:

    registro de cuenta        -> ms-seguridad
    alta del comercio         -> ms-comercios
    producto en el inventario -> ms-inventario (y el precio inicial -> ms-precios)
    movimiento de inventario  -> ms-inventario
    cambio de precio          -> ms-precios

La base de datos misma lo impide: el web entra a PostgreSQL con un usuario de solo lectura
(ver test_propiedad_datos.py).
"""
import re
import time
import uuid
from decimal import Decimal

import pytest
import requests

from apoyo import WEB, Api, sesion_de, url

CSRF = re.compile(r'name="csrf_token"[^>]*?value="([^"]+)"')
LIMITE = re.compile(r'Superaste \d+ peticiones por minuto en este servicio\. Intenta en (\d+) s')


class Navegador:
    """Sesión del web con cookies; cada POST lleva el token CSRF del formulario que se acaba de abrir."""

    def __init__(self):
        self.sesion = requests.Session()

    def abrir(self, ruta):
        r = self.sesion.get(f'{WEB}{ruta}', timeout=20)
        assert r.status_code == 200, f'GET {ruta}: {r.status_code}'
        return r

    def enviar(self, ruta_formulario, datos, ruta_post=None):
        for _ in range(3):
            token = CSRF.search(self.abrir(ruta_formulario).text).group(1)
            # Por HTTPS, Flask-WTF exige que el Referer sea del mismo sitio (como lo manda el navegador)
            r = self.sesion.post(f'{WEB}{ruta_post or ruta_formulario}', data={'csrf_token': token, **datos},
                                 headers={'Referer': f'{WEB}{ruta_formulario}'}, allow_redirects=False, timeout=30)
            # Login y registro tienen límite por minuto e IP en ms-seguridad; el web muestra cuánto esperar
            espera = LIMITE.search(r.text) if r.status_code in (200, 429) else None
            if not espera:
                return r
            time.sleep(int(espera.group(1)) + 1)
        return r


def _eventos(entidad, entidad_id):
    r = sesion_de('auditor').get('auditoria', f'/entidades/{entidad}/{entidad_id}/historial')
    assert r.status_code == 200, r.text[:200]
    return r.json()['eventos']


def _servicios(entidad, entidad_id):
    return {e['servicio'] for e in _eventos(entidad, entidad_id)}


def test_login_del_web_lo_valida_ms_seguridad():
    web = Navegador()
    r = web.enviar('/login', {'email': 'comerciante@test.mx', 'password': 'equivocada'})
    assert r.status_code == 200 and 'incorrectos' in r.text   # mensaje de ms-seguridad con intentos restantes
    r = web.enviar('/login', {'email': 'comerciante@test.mx', 'password': 'Password123!'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/panel')
    assert web.abrir('/panel').status_code == 200


def test_registro_comercio_inventario_y_precio_los_escriben_los_servicios_duenos():
    web = Navegador()
    email = f'web-{uuid.uuid4().hex[:8]}@prueba.mx'

    # 1. Registro de la cuenta: ms-seguridad crea el usuario y regresa el JWT que el web guarda en su sesión
    r = web.enviar('/registro', {'perfil': 'Comerciante Informal', 'nombre': 'Prueba', 'apellido_paterno': 'Web',
                                 'telefono': '', 'email': email, 'password': 'PruebaWeb2026',
                                 'confirmar': 'PruebaWeb2026'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/comercios/nuevo'), r.text[:300]
    usuario = Api('comerciante', tokens=_login(email, 'PruebaWeb2026'))
    usuario_id = usuario.tokens['usuario']['id']
    assert 'ms-seguridad' in _servicios('Usuario', usuario_id)

    # 2. Alta del comercio: ms-comercios lo guarda y le asigna la zona por ubicación (ms-geolocalizacion)
    r = web.enviar('/comercios/nuevo', {
        'nombre_comercio': 'Puesto de prueba del web', 'tipo_comercio': 'INFORMAL_TIANGUIS',
        'direccion': 'Tianguis Los Nogales, pasillo B', 'municipio': 'García', 'estado': 'Nuevo León',
        'zona_id': '0', 'latitud': '25.8150000', 'longitud': '-100.5900000'})
    assert r.status_code == 302 and '/inventario/' in r.headers['Location'], r.text[:300]
    comercio_id = r.headers['Location'].split('/inventario/')[1].split('/')[0]
    assert _servicios('Comercio', comercio_id) == {'ms-comercios'}

    # 3. Producto con existencia y precio iniciales: el renglón lo escribe ms-inventario y el precio ms-precios
    producto = requests.get(url('catalogo', '/productos'), params={'texto': 'arroz', 'por_pagina': 1},
                            timeout=10).json()['productos'][0]
    pid = producto['id']
    r = web.enviar(f'/inventario/{comercio_id}/agregar', {
        'producto_id': str(pid), f'existencia_{pid}': '10', f'minimo_{pid}': '2', f'maximo_{pid}': '',
        f'precio_{pid}': '25.50'})
    assert r.status_code == 302, r.text[:300]
    renglon = usuario.get('inventario', f'/comercios/{comercio_id}/inventario').json()['renglones'][0]
    assert renglon['producto_id'] == pid
    assert Decimal(str(renglon['existencia'])) == 10 and Decimal(str(renglon['precio_venta'])) == Decimal('25.50')
    servicios = _servicios('InventarioComercio', str(renglon['id']))
    assert 'ms-inventario' in servicios and 'web' not in servicios
    assert 'ms-precios' in _servicios('PrecioComercio', str(renglon['id']))

    # 4. Venta registrada como salida desde la pantalla del renglón
    item = f"/inventario/item/{renglon['id']}"
    r = web.enviar(item, {'tipo': 'SALIDA', 'cantidad': '3', 'motivo': 'Venta de prueba'},
                   ruta_post=f'{item}/movimiento')
    assert r.status_code == 302
    detalle = usuario.get('inventario', f"/inventario/{renglon['id']}").json()
    assert Decimal(str(detalle['existencia'])) == 7
    assert detalle['movimientos'][0]['tipo'] == 'SALIDA'

    # 5. Cambio de precio y de stock mínimo en el mismo formulario: cada parte va a su dueño
    r = web.enviar(item, {'stock_minimo': '4', 'stock_maximo': '', 'precio_venta': '26.00'},
                   ruta_post=f'{item}/editar')
    assert r.status_code == 302
    detalle = usuario.get('inventario', f"/inventario/{renglon['id']}").json()
    assert Decimal(str(detalle['stock_minimo'])) == 4 and Decimal(str(detalle['precio_venta'])) == 26
    eventos = _eventos('PrecioComercio', str(renglon['id']))
    assert eventos[-1]['servicio'] == 'ms-precios'
    assert {e['servicio'] for e in _eventos('InventarioComercio', str(renglon['id']))} <= {'ms-inventario'}


def _entrar(email, clave):
    web = Navegador()
    r = web.enviar('/login', {'email': email, 'password': clave})
    assert r.status_code == 302, f'login web de {email}: {r.status_code}'
    return web


def test_pedido_completo_desde_el_web_lo_coordina_ms_pedidos():
    """Comerciante, operador y dueño del proveedor usan el web; ms-pedidos aplica cada transición y, al despachar
    y recibir, pide el cambio de existencias a ms-proveedores y a ms-inventario."""
    minorista = sesion_de('minorista')
    comercio = next(c for c in minorista.get('comercios', '/comercios').json()['items'] if c['zona_id'])
    renglones = minorista.get('inventario', f"/comercios/{comercio['id']}/inventario",
                              params={'por_pagina': 200}).json()['renglones']
    oferta = renglon = None
    for r in renglones:
        ofertas = minorista.get('proveedores', '/ofertas', params={'producto_id': r['producto_id'],
                                                                   'zona_id': comercio['zona_id']}).json()['ofertas']
        oferta = next((o for o in ofertas if o['cubre_zona'] and o['proveedor'].startswith('Distribuidora Regia')
                       and o['existencia_disponible'] >= max(o['cantidad_minima'],
                                                             o['pedido_minimo'] / o['precio_mayoreo'] + 1)), None)
        if oferta:
            renglon = r
            break
    if not oferta:
        pytest.skip('Omitida: la Distribuidora Regia no tiene existencia suficiente para un pedido de prueba')
    cantidad = max(oferta['cantidad_minima'], int(oferta['pedido_minimo'] / oferta['precio_mayoreo']) + 1)
    for b in minorista.get('pedidos', '/pedidos', params={'estado': 'BORRADOR', 'comercio_id': comercio['id'],
                                                          'por_pagina': 100}).json()['pedidos']:
        if b['proveedor_id'] == oferta['proveedor_id']:
            minorista.post('pedidos', f"/pedidos/{b['id']}/acciones/cancelar", json={'comentario': 'Limpieza de prueba'})

    # Comerciante: abre el pedido desde la búsqueda de proveedores y lo envía
    comerciante = _entrar('minorista@test.mx', 'Password123!')
    r = comerciante.enviar(f"/proveedores/buscar?producto_id={oferta['producto_id']}&comercio_id={comercio['id']}",
                           {'comercio_id': comercio['id'], 'proveedor_id': oferta['proveedor_id'],
                            'producto_id': str(oferta['producto_id']), 'cantidad': str(cantidad)},
                           ruta_post='/pedidos/nuevo')
    assert r.status_code == 302 and '/pedidos/' in r.headers['Location'], r.text[:300]
    pedido = r.headers['Location'].rstrip('/').split('/')[-1]

    def accion(web, nombre):
        r = web.enviar(f'/pedidos/{pedido}', {'comentario': ''}, ruta_post=f'/pedidos/{pedido}/accion/{nombre}')
        assert r.status_code == 302

    accion(comerciante, 'enviar')
    operador = _entrar('operador@test.mx', 'Password123!')
    accion(operador, 'aceptar')
    accion(operador, 'preparar')
    accion(_entrar('proveedor@test.mx', 'Password123!'), 'despachar')
    accion(comerciante, 'recibir')

    detalle = minorista.get('pedidos', f'/pedidos/{pedido}').json()
    assert detalle['estado'] == 'ENTREGADO', detalle['estado']
    despues = minorista.get('inventario', f"/inventario/{renglon['id']}").json()
    assert Decimal(str(despues['existencia'])) == Decimal(str(renglon['existencia'])) + Decimal(str(cantidad))
    assert despues['movimientos'][0]['pedido_id'] == pedido
    assert _servicios('PedidoAbasto', pedido) == {'ms-pedidos'}


def test_equipo_del_proveedor_lo_administra_ms_seguridad():
    dueno = _entrar('proveedor@test.mx', 'Password123!')
    email = f'operador-{uuid.uuid4().hex[:8]}@prueba.mx'
    r = dueno.enviar('/mi-empresa/equipo', {'nombre': 'Operador', 'apellido_paterno': 'Web', 'email': email,
                                            'telefono': '', 'password': 'Temporal2026'})
    assert r.status_code == 302, r.text[:300]
    equipo = sesion_de('dueno_regia').get('seguridad', '/operadores').json()['items']
    operador = next(u for u in equipo if u['email'] == email)
    assert operador['activo'] and operador['rol'] == 'Operador de Proveedor'
    assert _login(email, 'Temporal2026')['usuario']['proveedor_id'] == sesion_de('dueno_regia').tokens['usuario']['proveedor_id']

    r = dueno.enviar('/mi-empresa/equipo', {}, ruta_post=f"/mi-empresa/equipo/{operador['id']}/estado")
    assert r.status_code == 302
    r = requests.post(url('seguridad', '/auth/login'), json={'email': email, 'password': 'Temporal2026'}, timeout=10)
    assert r.status_code == 401   # ya no puede entrar
    assert _servicios('Usuario', operador['id']) == {'ms-seguridad'}


def test_parametro_del_sistema_lo_cambia_ms_configuracion():
    admin = sesion_de('admin')
    parametros = admin.get('configuracion', '/parametros').json()['parametros']
    p = next(p for p in parametros if p['tipo_dato'] == 'int' and p['valor_maximo']
             and float(p['valor']) + 1 <= p['valor_maximo'])
    nuevo = str(int(float(p['valor'])) + 1)
    web = _entrar('admin@abastored.mx', 'Admin123!')
    try:
        r = web.enviar('/admin/configuracion', {q['clave']: (nuevo if q['clave'] == p['clave'] else q['valor'] or '')
                                                for q in parametros})
        assert r.status_code == 302
        assert admin.get('configuracion', f"/parametros/{p['clave']}").json()['valor'] == nuevo
        assert _eventos('ConfiguracionSistema', p['clave'])[-1]['servicio'] == 'ms-configuracion'
    finally:
        admin.put('configuracion', f"/parametros/{p['clave']}", json={'valor': p['valor'], 'motivo': 'Prueba'})


def test_si_el_servicio_rechaza_el_cambio_el_web_muestra_el_motivo():
    """La regla de negocio vive en el servicio: el web solo muestra su respuesta."""
    web = Navegador()
    web.enviar('/login', {'email': 'admin@abastored.mx', 'password': 'Admin123!'})
    r = web.enviar('/catalogo/categorias', {'nombre': 'Abarrotes', 'descripcion': ''})   # ya existe
    assert r.status_code == 200 and 'Ya existe esa categoría' in r.text


def _login(email, clave):
    for _ in range(3):
        r = requests.post(url('seguridad', '/auth/login'), json={'email': email, 'password': clave}, timeout=10)
        if r.status_code != 429:
            break
        time.sleep(int(r.headers.get('Retry-After', 30)) + 1)
    assert r.status_code == 200, r.text[:200]
    return r.json()

