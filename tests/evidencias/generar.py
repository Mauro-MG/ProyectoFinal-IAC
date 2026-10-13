"""
Generador de evidencias del avance 2.

Ejecuta, contra el sistema levantado con docker compose, los cinco casos que
pide la rúbrica para cada una de las 87 operaciones de los microservicios:

    exito          petición correcta
    invalido       parámetros o cuerpo con valores no válidos      (422 / 400)
    inexistente    registro que no existe                           (404)
    no_autorizado  sin token (401) y con un rol sin permiso (403)
    negocio        regla de negocio que impide la operación         (409 / 423 / 403 de plan)

El caso de éxito y los de negocio están escritos a mano (abajo, en orden de
ejecución: cada paso crea lo que usa el siguiente y al final se limpia). Los
de parámetros inválidos, inexistente y no autorizado se derivan del OpenAPI
de cada servicio (tipos, restricciones y permisos declarados).

Después consulta PostgreSQL, MongoDB y Redis dentro de los contenedores para
mostrar lo que quedó guardado.

    python tests/evidencias/generar.py

Salida:
    docs/evidencias/evidencias_avance2.html     reporte navegable e imprimible
    docs/evidencias/resultados.json             mismos datos, para el documento técnico
    docs/postman/AbastoRed_Avance2.postman_collection.json
"""
import copy
import html
import json
import random
import re
import struct
import subprocess
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integracion'))
from apoyo import PUERTOS, RAIZ, USUARIOS, base, iniciar_sesion, url  # noqa: E402

SALIDA = RAIZ / 'docs' / 'evidencias'
POSTMAN = RAIZ / 'docs' / 'postman'
TIPOS = ('exito', 'invalido', 'inexistente', 'no_autorizado', 'negocio')
NOMBRE_TIPO = {'exito': 'Éxito', 'invalido': 'Parámetros inválidos', 'inexistente': 'Registro inexistente',
               'no_autorizado': 'Acceso no autorizado', 'negocio': 'Error de negocio'}

USUARIOS.update({
    'jorge': ('jorge.trevino@test.mx', 'Password123!'),
    'lucia': ('lucia.rodriguez@test.mx', 'Password123!'),
    'rosa': ('rosa.hernandez@test.mx', 'Password123!'),
})
ROL_DE_USUARIO = {
    'Administrador General': 'admin', 'Comerciante Informal': 'comerciante', 'Minorista Formal': 'minorista',
    'Proveedor': 'dueno_regia', 'Operador de Proveedor': 'operador', 'Analista de Mercado': 'analista',
    'Coordinador Municipal': 'coordinador', 'Auditor': 'auditor',
}
# Orden en que se busca un rol sin permiso para el caso 403
CANDIDATOS_403 = ('auditor', 'comerciante', 'operador', 'analista', 'coordinador', 'minorista', 'dueno_regia', 'admin')

ctx = {}       # ids y valores que van dejando los pasos
tokens = {}    # rol -> respuesta de login
casos = []     # resultados
OPENAPI = {}   # servicio -> documento


# ====================================================================== utilidades

def token(rol):
    if rol not in tokens:
        tokens[rol] = iniciar_sesion(rol)
    return tokens[rol]['access_token']


def png():
    fila = b'\x00' + bytes((35, 122, 75)) * 32

    def trozo(tipo, datos):
        return struct.pack('>I', len(datos)) + tipo + datos + struct.pack('>I', zlib.crc32(tipo + datos))
    return (b'\x89PNG\r\n\x1a\n' + trozo(b'IHDR', struct.pack('>IIBBBBB', 32, 24, 8, 2, 0, 0, 0))
            + trozo(b'IDAT', zlib.compress(fila * 24)) + trozo(b'IEND', b''))


def valor(v):
    """Los campos de una especificación pueden ser funciones del contexto."""
    if callable(v):
        return v(ctx)
    if isinstance(v, str):
        return v.format(**ctx)
    if isinstance(v, dict):
        return {k: valor(x) for k, x in v.items()}
    if isinstance(v, list):
        return [valor(x) for x in v]
    return v


def enviar(servicio, metodo, ruta, rol=None, params=None, cuerpo=None, xml=None, archivos=None, datos=None,
           cabeceras=None):
    h = {'Accept': 'application/json', 'X-Correlation-ID': f'evidencia-{random.getrandbits(48):012x}'}
    if rol:
        h['Authorization'] = f'Bearer {token(rol)}' if rol != 'servicio' else f"Bearer {ctx['token_servicio']}"
    if xml is not None:
        h['Content-Type'] = 'application/xml'
    h.update(cabeceras or {})
    for _ in range(4):
        r = requests.request(metodo, url(servicio, ruta), params=params, json=cuerpo,
                             data=xml.encode() if isinstance(xml, str) else (datos if datos is not None else xml),
                             files=archivos, headers=h, timeout=30)
        if r.status_code != 429 or '/auth/login' not in ruta:
            break
        time.sleep(int(r.headers.get('Retry-After', 20)) + 1)  # límite de 10 logins por minuto por IP
    return r


def mostrar_cuerpo(r):
    tipo = r.headers.get('Content-Type', '')
    if 'json' in tipo:
        try:
            return json.dumps(r.json(), ensure_ascii=False, indent=2)[:3500]
        except ValueError:
            pass
    if 'xml' in tipo:
        return r.text[:3500]
    if r.content:
        return f'[contenido binario {tipo}, {len(r.content)} bytes]'
    return ''


def registrar(op, tipo, titulo, esperado, peticion, r, nota=None):
    esperado = esperado if isinstance(esperado, (list, tuple)) else (esperado,)
    caso = {
        'servicio': op['servicio'], 'operacion': f"{op['metodo']} {op['plantilla']}", 'resumen': op.get('resumen', ''),
        'tipo': tipo, 'titulo': titulo, 'esperado': list(esperado), 'obtenido': r.status_code if r is not None else None,
        'ok': r is not None and r.status_code in esperado, 'nota': nota,
        'peticion': peticion,
        'respuesta': None if r is None else {
            'status': r.status_code,
            'cabeceras': {k: r.headers[k] for k in ('Content-Type', 'X-Correlation-ID', 'X-Servicio', 'X-Tiempo-ms',
                                                    'X-RateLimit-Remaining', 'Retry-After') if k in r.headers},
            'cuerpo': mostrar_cuerpo(r)},
    }
    casos.append(caso)
    marca = 'ok ' if caso['ok'] else 'XX '
    print(f"  {marca}{tipo:13} {r.status_code if r is not None else '-':>4} (esperado {esperado}) {titulo}")
    return caso


def ejecutar(op, tipo, titulo, esperado, rol=None, ruta=None, params=None, cuerpo=None, xml=None, archivos=None,
             datos=None, nota=None, cabeceras=None):
    ruta = ruta if ruta is not None else op['ruta_real']
    peticion = {
        'metodo': op['metodo'], 'url': url(op['servicio'], ruta), 'rol': rol, 'params': params,
        'cuerpo': json.dumps(cuerpo, ensure_ascii=False, indent=2) if cuerpo is not None else xml,
        'formato_cuerpo': 'json' if cuerpo is not None else ('xml' if xml is not None else None),
        'archivos': {k: v[0] for k, v in archivos.items()} if archivos else None, 'datos': datos,
        'cabeceras': cabeceras,
    }
    r = enviar(op['servicio'], op['metodo'], ruta, rol, params, cuerpo, xml, archivos, datos, cabeceras)
    return r, registrar(op, tipo, titulo, esperado, peticion, r, nota)


# ====================================================================== derivación desde OpenAPI

def operacion_openapi(op):
    return OPENAPI[op['servicio']]['paths'][f"/api/v1{op['plantilla']}"][op['metodo'].lower()]


def permisos_de(op_api):
    m = re.search(r'\*\*Permisos:\*\* ([^\n]+)', op_api.get('description', ''))
    return [p.strip() for p in m.group(1).split(',')] if m else []


def esquema_cuerpo(op):
    op_api = operacion_openapi(op)
    contenido = op_api.get('requestBody', {}).get('content', {}).get('application/json', {})
    ref = contenido.get('schema', {}).get('$ref')
    return OPENAPI[op['servicio']]['components']['schemas'][ref.split('/')[-1]] if ref else None


def _tipo(prop):
    opciones = prop.get('anyOf') or [prop]
    no_nulo = next((o for o in opciones if o.get('type') != 'null'), prop)
    return no_nulo


def cuerpo_invalido(cuerpo, esquema):
    """Rompe un campo según su tipo declarado; regresa (cuerpo, explicación)."""
    cuerpo = copy.deepcopy(cuerpo)
    for nombre, prop in (esquema or {}).get('properties', {}).items():
        if nombre not in cuerpo:
            continue
        p = _tipo(prop)
        if p.get('type') in ('integer', 'number'):
            cuerpo[nombre] = 'no-es-numero'
            return cuerpo, f'«{nombre}» debe ser numérico; se envía texto'
        if 'enum' in p or 'const' in p:
            cuerpo[nombre] = 'VALOR_INEXISTENTE'
            return cuerpo, f'«{nombre}» fuera de los valores permitidos'
        if p.get('format') == 'email':
            cuerpo[nombre] = 'no-es-un-correo'
            return cuerpo, f'«{nombre}» no es un correo válido'
        if p.get('type') == 'string' and p.get('minLength'):
            cuerpo[nombre] = ''
            return cuerpo, f'«{nombre}» vacío (mínimo {p["minLength"]} caracteres)'
        if p.get('type') == 'boolean':
            cuerpo[nombre] = 'tal vez'
            return cuerpo, f'«{nombre}» debe ser booleano'
        if p.get('type') == 'array':
            cuerpo[nombre] = 'no-es-lista'
            return cuerpo, f'«{nombre}» debe ser una lista'
    cuerpo['campo_no_permitido'] = True
    return cuerpo, 'campo que el contrato no define (los modelos rechazan campos extra)'


def consulta_invalida(op_api, params):
    for p in op_api.get('parameters', []):
        if p['in'] != 'query' or p['name'] == 'formato':
            continue
        s = _tipo(p.get('schema', {}))
        if 'minimum' in s:
            return {**(params or {}), p['name']: s['minimum'] - 1}, f"«{p['name']}» menor al mínimo ({s['minimum']})"
        if 'enum' in s:
            return {**(params or {}), p['name']: 'VALOR_INEXISTENTE'}, f"«{p['name']}» fuera de los valores permitidos"
        if s.get('type') in ('integer', 'number'):
            return {**(params or {}), p['name']: 'abc'}, f"«{p['name']}» debe ser numérico"
    return None, None


def ruta_inexistente(op):
    """Sustituye el primer parámetro de la ruta por un id que no existe, del tipo correcto."""
    nombres = re.findall(r'\{(\w+)\}', op['plantilla'])
    if not nombres:
        return None
    nombre = nombres[0]
    tipo = next((_tipo(p.get('schema', {})) for p in operacion_openapi(op).get('parameters', [])
                 if p['name'] == nombre), {})
    if tipo.get('type') == 'integer':
        falso = '999999'
    elif nombre == 'jti':
        falso = '0' * 32
    elif nombre == 'correlation_id':
        falso = 'no-existe-0000'
    elif nombre == 'archivo_id' or op['servicio'] == 'notificaciones':
        falso = '0' * 24  # ObjectId de MongoDB
    else:
        falso = '00000000-0000-0000-0000-000000000000'
    return sustituir_parametro(op, nombre, falso)


def sustituir_parametro(op, nombre, nuevo):
    partes = op['ruta_real'].strip('/').split('/')
    plantilla = op['plantilla'].strip('/').split('/')
    partes[plantilla.index('{' + nombre + '}')] = nuevo
    return '/' + '/'.join(partes)


def rol_sin_permiso(permisos):
    for rol in CANDIDATOS_403:
        if not set(permisos) & set(ctx['permisos_rol'][rol]):
            return rol
    return None


# ====================================================================== catálogo de operaciones

OPS = []


def op(servicio, metodo, plantilla, rol, ruta=None, *, params=None, cuerpo=None, xml=None, archivos=None,
       datos=None, esperado=200, despues=None, antes=None, negocio=(), invalido=None, inexistente=None,
       no_autorizado=None, nota=None):
    OPS.append(dict(servicio=servicio, metodo=metodo, plantilla=plantilla, rol=rol, ruta=ruta or plantilla,
                    params=params, cuerpo=cuerpo, xml=xml, archivos=archivos, datos=datos, esperado=esperado,
                    despues=despues, antes=antes, negocio=negocio, invalido=invalido, inexistente=inexistente,
                    no_autorizado=no_autorizado, nota=nota))


def guardar(clave, extraer):
    def hacer(c, r):
        c[clave] = extraer(r.json())
    return hacer


def sesion_desechable(rol):
    """Login aparte (no el compartido) para casos que cierran o revocan la sesión."""
    def hacer(c):
        c[f'tok_{rol}'] = iniciar_sesion(rol)
        info = requests.get(url('seguridad', '/auth/sesion'),
                            headers={'Authorization': f"Bearer {c[f'tok_{rol}']['access_token']}"}, timeout=10).json()
        c[f'jti_{rol}'], c[f'id_{rol}'] = info['jti'], info['usuario_id']
    return hacer


def bloquear_cuenta(c):
    for _ in range(5):
        enviar('seguridad', 'POST', '/auth/login', cuerpo={'email': 'beto.garza@test.mx', 'password': 'Incorrecta-1'})


# ---------------------------------------------------------------- ms-seguridad
op('seguridad', 'POST', '/auth/login', None, cuerpo={'email': 'comerciante@test.mx', 'password': 'Password123!',
                                                     'origen': 'api'},
   despues=lambda c, r: c.update(cid=r.headers['X-Correlation-ID']),
   inexistente=dict(titulo='Correo que no está registrado', cuerpo={'email': 'no.existe@test.mx', 'password': 'Algo1234'},
                    esperado=401),
   no_autorizado=dict(titulo='Contraseña incorrecta', cuerpo={'email': 'comerciante@test.mx', 'password': 'NoEsLaClave'},
                      esperado=401),
   negocio=[dict(titulo='Cuenta bloqueada tras 5 intentos fallidos (Redis login_fallidos, 15 min)', antes=bloquear_cuenta,
                 cuerpo={'email': 'beto.garza@test.mx', 'password': 'Password123!'}, esperado=423)])
op('seguridad', 'POST', '/auth/renovar', None, antes=sesion_desechable('jorge'),
   cuerpo=lambda c: {'refresh_token': c['tok_jorge']['refresh_token']},
   despues=lambda c, r: c.update(tok_jorge_renovado=r.json(), refresh_usado=c['tok_jorge']['refresh_token']),
   inexistente=dict(titulo='Refresh token que no existe', cuerpo={'refresh_token': 'no-existe-' + 'x' * 40}, esperado=401),
   no_autorizado=dict(titulo='Refresh token ya usado (se rota en cada uso)',
                      cuerpo=lambda c: {'refresh_token': c['refresh_usado']}, esperado=401))
op('seguridad', 'POST', '/auth/logout', 'jorge',
   antes=lambda c: tokens.__setitem__('jorge', c['tok_jorge_renovado']),
   despues=lambda c, r: c.update(token_cerrado=c['tok_jorge_renovado']['access_token']),
   nota='Después del logout el mismo token responde 401 token_revocado en cualquier servicio.')
op('seguridad', 'GET', '/auth/sesion', 'minorista')
op('seguridad', 'POST', '/auth/validar', None, cuerpo=lambda c: {'token': token('minorista')},
   inexistente=dict(titulo='Token cuya sesión ya se cerró (responde valido=false)',
                    cuerpo=lambda c: {'token': c['token_cerrado']}, esperado=200))
op('seguridad', 'GET', '/usuarios/me', 'minorista')
op('seguridad', 'GET', '/sesiones', 'admin', params={'usuario_id': lambda c: c.get('id_minorista', '')})
op('seguridad', 'DELETE', '/sesiones/{jti}', 'admin', '/sesiones/{jti_lucia}', antes=sesion_desechable('lucia'))
op('seguridad', 'DELETE', '/usuarios/{id}/sesiones', 'admin', '/usuarios/{id_rosa}/sesiones',
   antes=sesion_desechable('rosa'))
op('seguridad', 'GET', '/usuarios', 'admin', params={'texto': 'test.mx', 'pagina': 1, 'por_pagina': 5})
op('seguridad', 'GET', '/usuarios/{id}', 'admin', '/usuarios/{id_rosa}')
op('seguridad', 'PATCH', '/usuarios/{id}', 'admin', '/usuarios/{id_rosa}', cuerpo={'activo': True},
   negocio=[dict(titulo='El administrador intenta desactivarse a sí mismo', ruta='/usuarios/{id_admin}',
                 cuerpo={'activo': False}, esperado=409)])
op('seguridad', 'GET', '/roles', 'admin')
op('seguridad', 'PUT', '/roles/{id}/permisos', 'admin', '/roles/{rol_operador_id}/permisos',
   cuerpo=lambda c: {'permisos': c['permisos_rol']['operador']},
   invalido=dict(titulo='Permiso que no existe en el catálogo', cuerpo={'permisos': ['permiso.inventado']},
                 esperado=422))
op('seguridad', 'GET', '/auditoria', 'admin', params={'entidad': 'PedidoAbasto', 'por_pagina': 5})
op('seguridad', 'GET', '/actividad', 'admin', params={'horas': 24})
op('seguridad', 'GET', '/actividad/peticiones/{correlation_id}', 'admin', '/actividad/peticiones/{cid}')

# ---------------------------------------------------------------- ms-comercios
COMERCIO = {'nombre_comercio': 'Puesto de evidencias {sufijo}', 'tipo_comercio': 'INFORMAL_TIANGUIS',
            'direccion': 'Tianguis Los Nogales, pasillo F', 'municipio': 'García', 'estado': 'Nuevo León',
            'latitud': 25.821, 'longitud': -100.589, 'horario_apertura': '07:00:00', 'horario_cierre': '15:00:00'}
op('comercios', 'GET', '/comercios', 'coordinador', params={'zona_id': '{zona_id}', 'por_pagina': 5})
op('comercios', 'POST', '/comercios', 'comerciante', cuerpo=COMERCIO, esperado=201,
   despues=guardar('comercio_nuevo', lambda d: d['id']))
op('comercios', 'GET', '/comercios/{id}', 'comerciante', '/comercios/{comercio_nuevo}',
   negocio=[dict(titulo='Comerciante consulta el comercio de otra persona', ruta='/comercios/{comercio_min}',
                 esperado=403)])
op('comercios', 'PUT', '/comercios/{id}', 'comerciante', '/comercios/{comercio_nuevo}',
   cuerpo={**COMERCIO, 'nombre_comercio': 'Puesto de evidencias {sufijo} (editado)'})
op('comercios', 'PATCH', '/comercios/{id}/validacion', 'coordinador', '/comercios/{comercio_nuevo}/validacion',
   cuerpo={'estado': 'VERIFICADO', 'observaciones': 'Visita en sitio (evidencias)'},
   negocio=[dict(titulo='Validar un comercio que ya está verificado', cuerpo={'estado': 'VERIFICADO'}, esperado=409)])
op('comercios', 'GET', '/zonas', None)
op('comercios', 'GET', '/zonas/localizar', None, params={'latitud': 25.6694, 'longitud': -100.3097},
   inexistente=dict(titulo='Punto fuera de todas las zonas', params={'latitud': 26.9, 'longitud': -99.0}, esperado=404))
op('comercios', 'POST', '/comercios/{id}/archivos', 'comerciante', '/comercios/{comercio_nuevo}/archivos',
   archivos=lambda c: {'archivo': ('fachada.png', png(), 'image/png')},
   datos={'categoria': 'foto_comercio', 'descripcion': 'Fachada del puesto'}, esperado=201,
   despues=guardar('archivo_id', lambda d: d['id']),
   invalido=dict(titulo='Petición sin el archivo (multipart sin campo «archivo»)',
                 datos={'categoria': 'foto_comercio'}, esperado=400),
   negocio=[dict(titulo='Tipo de archivo no permitido (.exe)',
                 archivos=lambda c: {'archivo': ('programa.exe', b'MZ\x90\x00', 'application/octet-stream')},
                 datos={'categoria': 'documento'}, esperado=409)])
op('comercios', 'GET', '/comercios/{id}/archivos', 'comerciante', '/comercios/{comercio_nuevo}/archivos')
op('comercios', 'GET', '/archivos/{archivo_id}', 'comerciante', '/archivos/{archivo_id}',
   negocio=[dict(titulo='Un proveedor intenta ver la foto de un comercio ajeno', rol='dueno_regia', esperado=403)])
op('comercios', 'DELETE', '/archivos/{archivo_id}', 'comerciante', '/archivos/{archivo_id}')

# ---------------------------------------------------------------- ms-catalogo
PRODUCTO = {'nombre': 'Producto de evidencias {sufijo}', 'categoria_id': 1, 'unidad_medida': 'pieza',
            'codigo_barras': '{codigo_barras}', 'es_canasta_basica': False}
op('catalogo', 'GET', '/productos', None, params={'texto': 'leche', 'pagina': 1, 'por_pagina': 5})
op('catalogo', 'POST', '/productos', 'admin', cuerpo=PRODUCTO, esperado=201,
   despues=guardar('producto_nuevo', lambda d: d['id']),
   negocio=[dict(titulo='Producto duplicado (mismo nombre y unidad)', esperado=409)])
op('catalogo', 'GET', '/productos/{id}', None, '/productos/{producto_nuevo}')
op('catalogo', 'PUT', '/productos/{id}', 'admin', '/productos/{producto_nuevo}',
   cuerpo={**PRODUCTO, 'nombre': 'Producto de evidencias {sufijo} (editado)'})
op('catalogo', 'DELETE', '/productos/{id}', 'admin', '/productos/{producto_nuevo}')
op('catalogo', 'GET', '/categorias', None)
op('catalogo', 'GET', '/proveedores', 'minorista', params={'zona_id': '{zona_id}'})
op('catalogo', 'GET', '/proveedores/{id}', 'minorista', '/proveedores/{regia_id}')
op('catalogo', 'GET', '/ofertas', 'minorista', params={'producto_id': '{producto_id}', 'zona_id': '{zona_id}'})
op('catalogo', 'GET', '/mi-catalogo', 'dueno_regia')
op('catalogo', 'POST', '/mi-catalogo', 'dueno_regia', cuerpo=lambda c: {
    'producto_id': c['producto_sin_oferta'], 'precio_mayoreo': 20.5, 'cantidad_minima': 12, 'existencia_disponible': 300},
   esperado=201, despues=guardar('oferta_nueva', lambda d: d['id']),
   negocio=[dict(titulo='Ofrecer otra vez un producto que ya está en el catálogo', esperado=409)])
op('catalogo', 'PATCH', '/mi-catalogo/{id}', 'dueno_regia', '/mi-catalogo/{oferta_nueva}',
   cuerpo={'precio_mayoreo': 19.9, 'existencia_disponible': 250})
op('catalogo', 'DELETE', '/mi-catalogo/{id}', 'dueno_regia', '/mi-catalogo/{oferta_nueva}')

# ---------------------------------------------------------------- ms-inventario
op('inventario', 'GET', '/comercios/{comercio_id}/inventario', 'minorista', '/comercios/{comercio_min}/inventario',
   params={'por_pagina': 5})
op('inventario', 'POST', '/comercios/{comercio_id}/inventario', 'comerciante', '/comercios/{comercio_nuevo}/inventario',
   cuerpo=lambda c: {'producto_id': c['producto_id'], 'existencia': 12, 'stock_minimo': 6, 'stock_maximo': 36,
                     'precio_venta': 28.5}, esperado=201, despues=guardar('renglon_nuevo', lambda d: d['id']),
   negocio=[dict(titulo='Agregar un producto que el comercio ya vende', esperado=409)])
op('inventario', 'GET', '/inventario/{id}', 'comerciante', '/inventario/{renglon_nuevo}')
op('inventario', 'PATCH', '/inventario/{id}', 'comerciante', '/inventario/{renglon_nuevo}',
   cuerpo={'stock_minimo': 8, 'stock_maximo': 40})
op('inventario', 'POST', '/inventario/{id}/movimientos', 'comerciante', '/inventario/{renglon_nuevo}/movimientos',
   cuerpo={'tipo': 'SALIDA', 'cantidad': 2, 'motivo': 'Venta de mostrador'}, esperado=201,
   negocio=[dict(titulo='Vender más de lo que hay en existencia', cuerpo={'tipo': 'SALIDA', 'cantidad': 9999},
                 esperado=409)])
op('inventario', 'GET', '/inventario/{id}/movimientos', 'comerciante', '/inventario/{renglon_nuevo}/movimientos')
op('inventario', 'DELETE', '/inventario/{id}', 'comerciante', '/inventario/{renglon_nuevo}')
op('inventario', 'GET', '/comercios/{comercio_id}/faltantes', 'minorista', '/comercios/{comercio_min}/faltantes')
op('inventario', 'POST', '/comercios/{comercio_id}/importaciones', 'minorista', '/comercios/{comercio_min}/importaciones',
   archivos=lambda c: {'archivo': ('inventario.csv', c['csv_importacion'].encode('utf-8'), 'text/csv')}, esperado=201,
   invalido=dict(titulo='Petición sin el archivo CSV', archivos=None, datos={'x': '1'}, esperado=400),
   negocio=[dict(titulo='CSV sin las columnas obligatorias (producto, existencia)',
                 archivos=lambda c: {'archivo': ('malo.csv', b'nombre;cantidad\nArroz;3\n', 'text/csv')}, esperado=409)])
op('inventario', 'GET', '/comercios/{comercio_id}/importaciones', 'minorista', '/comercios/{comercio_min}/importaciones')
op('inventario', 'GET', '/disponibilidad', None, params={'producto_id': '{producto_id}', 'por_pagina': 5})
op('comercios', 'DELETE', '/comercios/{id}', 'comerciante', '/comercios/{comercio_nuevo}',
   nota='Baja lógica: el comercio queda inactivo y deja de aparecer; su historial se conserva.')

# ---------------------------------------------------------------- ms-precios
op('precios', 'PUT', '/inventario/{id}/precio', 'minorista', '/inventario/{renglon_min_id}/precio',
   cuerpo=lambda c: {'precio': c['precio_nuevo'], 'metodo_captura': 'MOVIL'},
   negocio=[dict(titulo='Capturar el mismo precio que ya tiene', esperado=409)])
op('precios', 'GET', '/precios', 'analista', params={'producto_id': '{producto_id}', 'por_pagina': 5})
op('precios', 'GET', '/precios/pendientes', 'coordinador', antes=lambda c: crear_precio_pendiente(c))
op('precios', 'PATCH', '/precios/{id}/validacion', 'coordinador', '/precios/{precio_pendiente}/validacion',
   cuerpo={'decision': 'DESCARTAR', 'comentario': 'Error de captura confirmado con el comerciante'},
   negocio=[dict(titulo='Revisar un precio que ya se revisó', esperado=409)])
op('precios', 'GET', '/precios/comparacion', 'analista', params={'producto_id': '{producto_id}'})
op('precios', 'GET', '/precios/tendencia', 'analista', params={'producto_id': '{producto_id}', 'semanas': 8})
op('precios', 'POST', '/precios/snapshots', 'analista', esperado=201,
   nota='Upsert por (fecha, comercio, producto): correrlo dos veces el mismo día no duplica documentos.')
op('precios', 'GET', '/precios/snapshots', 'analista', params={'producto_id': '{producto_id}', 'por_pagina': 5})
op('precios', 'GET', '/precios/snapshots/tendencia', 'analista', params={'producto_id': '{producto_id}'})

# ---------------------------------------------------------------- ms-pedidos
op('pedidos', 'GET', '/pedidos', 'minorista', params={'por_pagina': 5})
op('pedidos', 'POST', '/pedidos', 'minorista', cuerpo=lambda c: {
    'comercio_id': c['comercio_min'], 'proveedor_id': c['regia_id'],
    'partidas': [{'producto_id': c['oferta']['producto_id'], 'cantidad': c['cantidad_pedido']}],
    'notas': 'Pedido de evidencias'}, esperado=201, despues=guardar('pedido_ev', lambda d: d['id']),
   negocio=[dict(titulo='Proveedor que no entrega en la zona del comercio (RN-011)', cuerpo=lambda c: {
       'comercio_id': c['comercio_min'], 'proveedor_id': c['proveedor_fuera']['proveedor_id'],
       'partidas': [{'producto_id': c['proveedor_fuera']['producto_id'], 'cantidad': c['proveedor_fuera']['cantidad_minima']}]},
       esperado=409, si=lambda c: c.get('proveedor_fuera'))])
op('pedidos', 'GET', '/pedidos/{id}', 'minorista', '/pedidos/{pedido_ev}',
   negocio=[dict(titulo='Otro proveedor intenta ver el pedido', rol='proveedor', esperado=403)])
op('pedidos', 'POST', '/pedidos/{id}/partidas', 'minorista', '/pedidos/{pedido_ev}/partidas',
   cuerpo=lambda c: {'producto_id': c['oferta2']['producto_id'], 'cantidad': c['oferta2']['cantidad_minima']},
   esperado=201, despues=lambda c, r: c.update(partida_id=next(
       p['id'] for p in r.json()['partidas'] if p['producto_id'] == c['oferta2']['producto_id'])),
   negocio=[dict(titulo='Producto que el proveedor no ofrece',
                 cuerpo=lambda c: {'producto_id': c['producto_no_ofrecido'], 'cantidad': 10}, esperado=409)])
op('pedidos', 'DELETE', '/pedidos/{id}/partidas/{partida_id}', 'minorista', '/pedidos/{pedido_ev}/partidas/{partida_id}')
op('pedidos', 'POST', '/pedidos/{id}/acciones/{accion}', 'minorista', '/pedidos/{pedido_ev}/acciones/enviar', cuerpo={},
   invalido=dict(titulo='Acción que no existe («volar»)', ruta='/pedidos/{pedido_ev}/acciones/volar', esperado=404),
   negocio=[dict(titulo='El proveedor intenta marcarlo como recibido (transición no permitida)', rol='operador',
                 ruta='/pedidos/{pedido_ev}/acciones/recibir', esperado=409),
            dict(titulo='Rechazar sin indicar el motivo', rol='operador',
                 ruta='/pedidos/{pedido_ev}/acciones/rechazar', cuerpo={}, esperado=409)])
op('pedidos', 'GET', '/pedidos/{id}/historial', 'minorista', '/pedidos/{pedido_ev}/historial')
op('pedidos', 'GET', '/estadisticas/proveedores', 'analista', params={'dias': 30})
op('pedidos', 'GET', '/estadisticas/productos', 'analista', params={'dias': 30})

# ---------------------------------------------------------------- ms-analisis
op('analisis', 'GET', '/analisis/zonas', 'analista')
op('analisis', 'GET', '/analisis/brechas', 'analista',
   params={'zona_id': '{zona_id}', 'canasta_basica': 'true', 'por_pagina': 5})
op('analisis', 'GET', '/analisis/recomendaciones/{comercio_id}', 'minorista', '/analisis/recomendaciones/{comercio_min}',
   negocio=[dict(titulo='Comercio sin zona asignada (ubicación fuera del área)', rol='comerciante',
                 antes=lambda c: crear_comercio_sin_zona(c), ruta='/analisis/recomendaciones/{comercio_sin_zona}',
                 esperado=409)])
op('analisis', 'GET', '/analisis/mapa', 'analista', params={'producto_id': '{producto_id}'})
op('analisis', 'GET', '/analisis/oportunidades', 'analista', params={'limite': 10},
   negocio=[dict(titulo='Proveedor con plan Básico (el reporte es del plan Destacado)', rol='proveedor', esperado=403)])
op('analisis', 'POST', '/analisis/ejecuciones', 'analista', esperado=201)
op('analisis', 'GET', '/analisis/ejecuciones/evolucion', 'analista', params={'dias': 30})

# ---------------------------------------------------------------- ms-notificaciones
op('notificaciones', 'GET', '/notificaciones', 'minorista', params={'por_pagina': 5})
op('notificaciones', 'POST', '/notificaciones', 'admin', cuerpo=lambda c: {
    'usuario_id': c['id_minorista'], 'tipo': 'sistema', 'titulo': 'Aviso de prueba',
    'mensaje': 'Mensaje generado para las evidencias del avance 2.'}, esperado=201,
   despues=guardar('notificacion_id', lambda d: d['id']),
   invalido=dict(titulo='usuario_id que no es UUID', cuerpo={'usuario_id': 'juan', 'titulo': 'x', 'mensaje': 'y'},
                 esperado=422))
op('notificaciones', 'GET', '/notificaciones/contador', 'minorista')
op('notificaciones', 'GET', '/notificaciones/{id}', 'minorista', '/notificaciones/{notificacion_id}',
   negocio=[dict(titulo='Otro usuario intenta leer la notificación (se responde como inexistente)', rol='comerciante',
                 esperado=404)])
op('notificaciones', 'PATCH', '/notificaciones/{id}', 'minorista', '/notificaciones/{notificacion_id}',
   cuerpo={'leida': True})
op('notificaciones', 'DELETE', '/notificaciones/{id}', 'minorista', '/notificaciones/{notificacion_id}')
op('notificaciones', 'POST', '/notificaciones/marcar-todas', 'minorista')
op('notificaciones', 'POST', '/notificaciones/lote', 'servicio', cuerpo=lambda c: {
    'usuarios': [c['id_minorista']], 'tipo': 'sistema', 'titulo': 'Aviso enviado por un servicio',
    'mensaje': 'Así llaman ms-pedidos, ms-inventario y ms-precios a este servicio.', 'origen': 'evidencias'},
   esperado=201, nota='Sólo con token de servicio (permiso notificaciones.crear); lo usan los demás microservicios.')
op('notificaciones', 'GET', '/notificaciones/resumen', 'minorista', params={'dias': 30},
   negocio=[dict(titulo='Un usuario normal pide el resumen de todas las cuentas', params={'todos': 'true'},
                 esperado=403)])


# ====================================================================== preparación

def crear_precio_pendiente(c):
    """Precio 4 veces arriba del actual: queda PENDIENTE_VALIDACION para el coordinador."""
    renglon = c['renglon_min2']
    enviar('precios', 'PUT', f"/inventario/{renglon['id']}/precio", 'minorista',
           cuerpo={'precio': round(float(renglon['precio_venta'] or 20) * 4, 2)})
    pendientes = enviar('precios', 'GET', '/precios/pendientes', 'coordinador').json()['precios']
    c['precio_pendiente'] = next(p['id'] for p in pendientes if p['comercio_id'] == c['comercio_min']
                                 and p['producto_id'] == renglon['producto_id'])


def crear_comercio_sin_zona(c):
    r = enviar('comercios', 'POST', '/comercios', 'comerciante', cuerpo={
        **valor(COMERCIO), 'nombre_comercio': f"Puesto fuera de zona {c['sufijo']}", 'latitud': 26.9, 'longitud': -99.0})
    c['comercio_sin_zona'] = r.json()['id']


def token_de_servicio():
    """Los tokens de servicio sólo se emiten dentro de la red de los servicios."""
    codigo = ("from app import app; from abasto_dominio.sesiones import token_servicio\n"
              "with app.app_context(): print(token_servicio('evidencias', ['notificaciones.crear'], minutos=10))")
    r = subprocess.run(['docker', 'exec', 'ms-pedidos', 'python', '-c', codigo],
                       capture_output=True, text=True, timeout=60)
    return r.stdout.strip().splitlines()[-1] if r.returncode == 0 else ''


def preparar():
    for servicio in PUERTOS:
        OPENAPI[servicio] = requests.get(f'{base(servicio)}/openapi.json', timeout=10).json()
    ctx['sufijo'] = datetime.now().strftime('%m%d-%H%M%S')
    ctx['codigo_barras'] = '750' + str(random.randint(10 ** 9, 10 ** 10 - 1))

    roles = enviar('seguridad', 'GET', '/roles', 'admin').json()['roles']
    ctx['permisos_rol'] = {ROL_DE_USUARIO[r['nombre']]: r['permisos'] for r in roles if r['nombre'] in ROL_DE_USUARIO}
    ctx['rol_operador_id'] = next(r['id'] for r in roles if r['nombre'] == 'Operador de Proveedor')
    ctx['id_admin'] = enviar('seguridad', 'GET', '/auth/sesion', 'admin').json()['usuario_id']
    sesion_minorista = enviar('seguridad', 'GET', '/auth/sesion', 'minorista').json()
    ctx['id_minorista'], ctx['jti_minorista'] = sesion_minorista['usuario_id'], sesion_minorista['jti']

    comercio = next(x for x in enviar('comercios', 'GET', '/comercios', 'minorista').json()['items'] if x['zona_id'])
    ctx.update(comercio_min=comercio['id'], zona_id=comercio['zona_id'])
    renglones = enviar('inventario', 'GET', f"/comercios/{comercio['id']}/inventario", 'minorista',
                       params={'por_pagina': 200}).json()['renglones']
    con_precio = [r for r in renglones if r['precio_venta']]
    ctx['renglon_min'], ctx['renglon_min2'] = con_precio[0], con_precio[1]
    ctx['renglon_min_id'] = con_precio[0]['id']
    ctx['precio_nuevo'] = round(float(con_precio[0]['precio_venta']) + 0.5, 2)
    ctx['csv_importacion'] = 'producto,existencia,stock_minimo,stock_maximo,precio\n' + ''.join(
        f"{r['producto']},{r['existencia']},{r['stock_minimo']},{r['stock_maximo'] or ''},\n" for r in renglones[:3])

    # Ofertas de la Distribuidora Regia que cubren la zona; un proveedor que no la cubre; un producto que Regia no ofrece
    ofertas_regia, fuera = [], None
    for r in renglones:
        datos = enviar('catalogo', 'GET', '/ofertas', 'minorista',
                       params={'producto_id': r['producto_id'], 'zona_id': comercio['zona_id']}).json()['ofertas']
        ofertas_regia += [o for o in datos if o['cubre_zona'] and o['proveedor'].startswith('Distribuidora Regia')]
        fuera = fuera or next((o for o in datos if not o['cubre_zona']), None)
        if len(ofertas_regia) >= 2 and fuera:
            break
    ctx['oferta'], ctx['oferta2'], ctx['proveedor_fuera'] = ofertas_regia[0], ofertas_regia[1], fuera
    ctx['regia_id'] = ofertas_regia[0]['proveedor_id']
    ctx['producto_id'] = ofertas_regia[0]['producto_id']
    o = ofertas_regia[0]
    ctx['cantidad_pedido'] = max(o['cantidad_minima'], int((o['pedido_minimo'] or 0) / o['precio_mayoreo']) + 1)

    mi_catalogo = {x['producto_id'] for x in enviar('catalogo', 'GET', '/mi-catalogo', 'dueno_regia').json()['ofertas']}
    productos = enviar('catalogo', 'GET', '/productos', None, params={'por_pagina': 200}).json()['productos']
    sin_oferta = [p['id'] for p in productos if p['id'] not in mi_catalogo]
    ctx['producto_sin_oferta'] = ctx['producto_no_ofrecido'] = sin_oferta[0]
    ctx['token_servicio'] = token_de_servicio()


# ====================================================================== ejecución

def correr(op_spec):
    o = dict(op_spec)
    o['resumen'] = operacion_openapi(o).get('summary', '')
    print(f"\n{o['servicio']:15} {o['metodo']:6} {o['plantilla']}  — {o['resumen']}")
    if o['antes']:
        o['antes'](ctx)
    o['ruta_real'] = valor(o['ruta'])
    params, cuerpo = valor(o['params']), valor(o['cuerpo'])
    archivos, datos = valor(o['archivos']), o['datos'] and valor(o['datos'])
    op_api = operacion_openapi(o)
    permisos = permisos_de(op_api)
    publico = not op_api.get('security')

    # 1. Éxito
    r, _ = ejecutar(o, 'exito', 'Petición correcta', o['esperado'], o['rol'], params=params, cuerpo=cuerpo,
                    xml=o['xml'], archivos=archivos, datos=datos, nota=o['nota'])
    if o['despues'] and r.ok:
        o['despues'](ctx, r)

    # 2. Parámetros inválidos
    inv = o['invalido']
    if inv:
        ejecutar(o, 'invalido', inv['titulo'], inv['esperado'], inv.get('rol', o['rol']),
                 ruta=valor(inv['ruta']) if 'ruta' in inv else None, params=valor(inv.get('params', params)),
                 cuerpo=valor(inv.get('cuerpo')) if 'cuerpo' in inv else (cuerpo if 'archivos' not in inv else None),
                 archivos=valor(inv['archivos']) if inv.get('archivos') else None, datos=valor(inv.get('datos')))
    elif cuerpo is not None:
        malo, porque = cuerpo_invalido(cuerpo, esquema_cuerpo(o))
        ejecutar(o, 'invalido', porque, 422, o['rol'], params=params, cuerpo=malo)
    else:
        malos, porque = consulta_invalida(op_api, params)
        if malos is not None:
            ejecutar(o, 'invalido', porque, 422, o['rol'], params=malos, archivos=archivos, datos=datos)
        elif re.search(r'\{(\w+)\}', o['plantilla']):
            primero = re.search(r'\{(\w+)\}', o['plantilla']).group(1)
            ruta_mala = sustituir_parametro(o, primero, 'valor-no-valido')
            ejecutar(o, 'invalido', 'Identificador con formato no válido en la ruta', (400, 404), o['rol'],
                     ruta=ruta_mala, params=params)
        else:
            casos.append({'servicio': o['servicio'], 'operacion': f"{o['metodo']} {o['plantilla']}", 'resumen': o['resumen'],
                          'tipo': 'invalido', 'titulo': 'No aplica: la operación no recibe parámetros', 'ok': None})

    # 3. Registro inexistente
    ine = o['inexistente']
    if ine:
        ejecutar(o, 'inexistente', ine['titulo'], ine['esperado'], ine.get('rol', o['rol']),
                 params=valor(ine.get('params', params)), cuerpo=valor(ine.get('cuerpo', cuerpo)))
    elif ruta_inexistente(o):
        ejecutar(o, 'inexistente', 'Identificador que no existe', 404, o['rol'], ruta=ruta_inexistente(o),
                 params=params, cuerpo=cuerpo, archivos=archivos, datos=datos)
    else:
        casos.append({'servicio': o['servicio'], 'operacion': f"{o['metodo']} {o['plantilla']}", 'resumen': o['resumen'],
                      'tipo': 'inexistente', 'titulo': 'No aplica: no se consulta un registro por identificador',
                      'ok': None})

    # 4. No autorizado: sin token y con un rol sin el permiso
    na = o['no_autorizado']
    if na:
        ejecutar(o, 'no_autorizado', na['titulo'], na['esperado'], None, cuerpo=valor(na.get('cuerpo')))
    elif publico:
        casos.append({'servicio': o['servicio'], 'operacion': f"{o['metodo']} {o['plantilla']}", 'resumen': o['resumen'],
                      'tipo': 'no_autorizado', 'titulo': 'No aplica: operación pública por diseño', 'ok': None})
    else:
        ejecutar(o, 'no_autorizado', 'Sin token (Authorization ausente)', 401, None, params=params, cuerpo=cuerpo)
        sin_permiso = rol_sin_permiso(permisos) if permisos else None
        if sin_permiso:
            ejecutar(o, 'no_autorizado', f'Rol sin permiso ({sin_permiso}; se requiere {" o ".join(permisos)})', 403,
                     sin_permiso, params=params, cuerpo=cuerpo, archivos=archivos, datos=datos)

    # 5. Reglas de negocio
    for neg in o['negocio']:
        if neg.get('si') and not neg['si'](ctx):
            casos.append({'servicio': o['servicio'], 'operacion': f"{o['metodo']} {o['plantilla']}",
                          'resumen': o['resumen'], 'tipo': 'negocio', 'ok': None,
                          'titulo': f"No se pudo preparar: {neg['titulo']}"})
            continue
        if neg.get('antes'):
            neg['antes'](ctx)
        ejecutar(o, 'negocio', neg['titulo'], neg['esperado'], neg.get('rol', o['rol']),
                 ruta=valor(neg['ruta']) if 'ruta' in neg else None, params=valor(neg.get('params', params)),
                 cuerpo=valor(neg['cuerpo']) if 'cuerpo' in neg else cuerpo,
                 archivos=valor(neg['archivos']) if 'archivos' in neg else archivos, datos=valor(neg.get('datos', datos)))
    if not o['negocio']:
        casos.append({'servicio': o['servicio'], 'operacion': f"{o['metodo']} {o['plantilla']}", 'resumen': o['resumen'],
                      'tipo': 'negocio', 'titulo': 'No aplica: la operación no tiene una regla de negocio que la impida',
                      'ok': None})


def limpiar():
    if ctx.get('comercio_sin_zona'):
        enviar('comercios', 'DELETE', f"/comercios/{ctx['comercio_sin_zona']}", 'comerciante')
    if ctx.get('pedido_ev'):
        enviar('pedidos', 'POST', f"/pedidos/{ctx['pedido_ev']}/acciones/rechazar", 'operador',
               cuerpo={'comentario': 'Pedido de evidencias: se rechaza para no afectar el inventario de prueba'})
    renglon = ctx['renglon_min']
    enviar('precios', 'PUT', f"/inventario/{renglon['id']}/precio", 'minorista', cuerpo={'precio': renglon['precio_venta']})


# ====================================================================== evidencia en las bases de datos

def _env():
    texto = (RAIZ / '.env').read_text(encoding='utf-8') if (RAIZ / '.env').exists() else ''
    return dict(re.findall(r'^(\w+)=(.*)$', texto, re.M))


def en_contenedor(contenedor, comando, extra_env=None):
    args = ['docker', 'exec']
    for k, v in (extra_env or {}).items():
        args += ['-e', f'{k}={v}']
    r = subprocess.run(args + [contenedor, 'sh', '-c', comando], capture_output=True, text=True, timeout=60,
                       encoding='utf-8', errors='replace')
    return (r.stdout or r.stderr).strip()


def evidencias_bd():
    pg = lambda sql: en_contenedor('abastored-postgres', f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "{sql}"')  # noqa: E731
    mongo = lambda js: en_contenedor('abastored-mongo', (  # noqa: E731
        'mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin '
        f'"$MONGO_INITDB_DATABASE" --quiet --eval \'{js}\''))
    redis = lambda cmd: en_contenedor('abastored-redis', f'redis-cli --no-auth-warning {cmd}',  # noqa: E731
                                      {'REDISCLI_AUTH': _env().get('REDIS_PASSWORD', '')})
    pedido, minorista, renglon = ctx.get('pedido_ev', ''), ctx['id_minorista'], ctx['renglon_min_id']
    dia = datetime.now().strftime('%Y%m%d')
    return [
        ('PostgreSQL', 'Pedido creado por la API y su historial de estados',
         pg(f"SELECT p.folio, p.estado, p.subtotal, h.estado_anterior, h.estado_nuevo, h.created_at "
            f"FROM pedidos_abasto p JOIN historial_pedido h ON h.pedido_id = p.id WHERE p.id = '{pedido}' "
            f"ORDER BY h.created_at;")),
        ('PostgreSQL', 'Movimientos de inventario del renglón usado en las pruebas',
         pg(f"SELECT tipo, cantidad, existencia_anterior, existencia_nueva, motivo, created_at FROM movimientos_inventario "
            f"WHERE inventario_id = {renglon} ORDER BY created_at DESC LIMIT 5;")),
        ('PostgreSQL', 'Bitácora de auditoría (operaciones críticas de esta corrida)',
         pg("SELECT tipo_evento, entidad, descripcion, created_at FROM auditoria_eventos ORDER BY created_at DESC LIMIT 10;")),
        ('PostgreSQL', 'Comercio dado de alta, validado y dado de baja (baja lógica)',
         pg(f"SELECT nombre_comercio, estado_registro, activo, zona_id FROM comercios WHERE id = '{ctx.get('comercio_nuevo', '')}';")),
        ('MongoDB', 'eventos_pedido: eventos del mismo pedido (ligados por pedido_id de PostgreSQL)',
         mongo(f'db.eventos_pedido.find({{pedido_id: "{pedido}"}}, {{_id: 0, folio: 1, accion: 1, estado_nuevo: 1, "actor.rol": 1, fecha: 1}}).toArray()')),
        ('MongoDB', 'notificaciones de la minorista (usuario_id de PostgreSQL)',
         mongo(f'db.notificaciones.find({{usuario_id: "{minorista}"}}, {{_id: 0, tipo: 1, titulo: 1, leida: 1, origen: 1, creada_en: 1}}).sort({{creada_en: -1}}).limit(5).toArray()')),
        ('MongoDB', 'importaciones: resultado de la última carga CSV',
         mongo('db.importaciones.find({}, {_id: 0, nombre_archivo: 1, filas_total: 1, agregados: 1, actualizados: 1, con_error: 1, fecha: 1}).sort({fecha: -1}).limit(1).toArray()')),
        ('MongoDB', 'GridFS (bucket archivos): archivos guardados por categoría',
         mongo('db.getCollection("archivos.files").aggregate([{$group: {_id: "$metadata.categoria", archivos: {$sum: 1}, bytes: {$sum: "$length"}}}]).toArray()')),
        ('MongoDB', 'bitacora_peticiones: peticiones por servicio en la última hora (agregación)',
         mongo('db.bitacora_peticiones.aggregate([{$match: {fecha: {$gte: new Date(Date.now() - 3600000)}}}, {$group: {_id: "$servicio", peticiones: {$sum: 1}, errores: {$sum: {$cond: [{$gte: ["$status", 400]}, 1, 0]}}}}, {$sort: {_id: 1}}]).toArray()')),
        ('MongoDB', 'Índices de cada colección',
         mongo('db.getCollectionNames().sort().map(c => ({coleccion: c, indices: db.getCollection(c).getIndexes().map(i => i.name)}))')),
        ('Redis', 'Sesiones vivas (sesion:{jti}) y jti revocados (jwt:revocado:{jti})',
         redis('--scan --pattern "sesion:*" | wc -l') + ' sesiones vivas\n'
         + redis('--scan --pattern "jwt:revocado:*" | wc -l') + ' tokens revocados vigentes'),
        ('Redis', 'TTL de una sesión (segundos que le quedan) y de su refresh token',
         redis(f"TTL sesion:{ctx['jti_minorista']}") + ' s (sesión de la minorista)\n'
         + redis(f"TTL refresh_de:{ctx['jti_minorista']}") + ' s (su refresh token)'),
        ('Redis', 'Versión de la caché de análisis/inventario y claves de caché vigentes',
         'analisis:version = ' + redis('GET analisis:version') + '\n' + redis('--scan --pattern "inventario:v*" | head -5')),
        ('Redis', 'Contadores diarios por servicio (contador:{servicio}:peticiones:{día})',
         '\n'.join(f'{s}: ' + redis(f'GET contador:{s}:peticiones:{dia}') for s in PUERTOS)),
        ('Redis', 'Límite de peticiones (rate:{servicio}:{sujeto}:{minuto}) y contador de no leídas',
         redis('--scan --pattern "rate:*" | head -5') + '\n' + f'notif:no_leidas:{minorista} = '
         + redis(f'GET notif:no_leidas:{minorista}')),
    ]


# ====================================================================== reporte HTML

CSS = """
:root { --tinta:#1d2420; --tenue:#5f6b64; --borde:#dedcd4; --fondo:#f7f6f2; --ok:#237a4b; --mal:#b3322a; --na:#8a8f8c;
        --codigo:#f1efe8; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 system-ui, -apple-system, 'Segoe UI', sans-serif; color: var(--tinta); background: #fff; }
main { max-width: 1200px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; } h2 { margin: 40px 0 8px; border-bottom: 2px solid var(--tinta); padding-bottom: 4px; }
h3 { margin: 28px 0 6px; font-size: 1.05rem; } .tenue { color: var(--tenue); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid var(--borde); padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: var(--fondo); }
.ok { color: var(--ok); font-weight: 600; } .mal { color: var(--mal); font-weight: 700; } .na { color: var(--na); }
.cifras { display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }
.cifra { border: 1px solid var(--borde); border-radius: 8px; padding: 10px 14px; min-width: 140px; }
.cifra b { display: block; font-size: 1.5rem; }
details { border: 1px solid var(--borde); border-radius: 6px; margin: 6px 0; }
summary { cursor: pointer; padding: 6px 10px; background: var(--fondo); }
.caso { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 10px; }
pre { background: var(--codigo); padding: 8px; overflow-x: auto; white-space: pre-wrap; word-break: break-word;
      font-size: 12px; margin: 4px 0; max-height: 420px; overflow-y: auto; }
.etiqueta { display: inline-block; padding: 0 6px; border-radius: 4px; font-size: 12px; background: var(--codigo); }
@media (max-width: 760px) { .caso { grid-template-columns: 1fr; } }
@media print { details { break-inside: avoid; } details:not([open]) .caso { display: block; } pre { max-height: none; } }
"""


def e(texto):
    return html.escape(str(texto if texto is not None else ''))


def html_caso(c):
    if c.get('ok') is None:
        return f'<p class="na">— {e(NOMBRE_TIPO[c["tipo"]])}: {e(c["titulo"])}</p>'
    p, r = c['peticion'], c['respuesta']
    linea = p['url'] + (('?' + '&'.join(f'{k}={v}' for k, v in p['params'].items())) if p.get('params') else '')
    cab = [f"Authorization: Bearer eyJ… (sesión de {p['rol']})" if p['rol'] else '(sin Authorization)']
    if p['formato_cuerpo'] == 'json':
        cab.append('Content-Type: application/json')
    if p['formato_cuerpo'] == 'xml':
        cab.append('Content-Type: application/xml')
    if p.get('archivos'):
        cab.append('Content-Type: multipart/form-data')
    cuerpo = p['cuerpo'] or ''
    if p.get('archivos'):
        cuerpo = 'archivos: ' + json.dumps(p['archivos'], ensure_ascii=False) + (
            '\ncampos: ' + json.dumps(p['datos'], ensure_ascii=False) if p.get('datos') else '')
    marca = '<span class="ok">✔</span>' if c['ok'] else '<span class="mal">✘</span>'
    return (f'<details><summary>{marca} <b>{e(NOMBRE_TIPO[c["tipo"]])}</b> · {e(c["titulo"])} · '
            f'<span class="etiqueta">HTTP {r["status"]}</span> <span class="tenue">(esperado {e("/".join(map(str, c["esperado"])))})</span></summary>'
            f'<div class="caso"><div><b>Solicitud</b><pre>{e(p["metodo"])} {e(linea)}\n{e(chr(10).join(cab))}</pre>'
            + (f'<pre>{e(cuerpo)}</pre>' if cuerpo else '')
            + f'</div><div><b>Respuesta</b><pre>HTTP {r["status"]}\n'
            + e('\n'.join(f'{k}: {v}' for k, v in r['cabeceras'].items())) + '</pre>'
            + (f'<pre>{e(r["cuerpo"])}</pre>' if r['cuerpo'] else '')
            + (f'<p class="tenue">{e(c["nota"])}</p>' if c.get('nota') else '') + '</div></div></details>')


def reporte(bd):
    operaciones = {}
    for c in casos:
        operaciones.setdefault((c['servicio'], c['operacion']), []).append(c)
    total = [c for c in casos if c.get('ok') is not None]
    fallas = [c for c in total if not c['ok']]
    filas = []
    for (servicio, operacion), lista in operaciones.items():
        celdas = []
        for tipo in TIPOS:
            del_tipo = [c for c in lista if c['tipo'] == tipo]
            if all(c.get('ok') is None for c in del_tipo):
                celdas.append('<td class="na">n/a</td>')
            else:
                celdas.append('<td>' + ' '.join(
                    f'<span class="{"ok" if c["ok"] else "mal"}">{c["obtenido"]}</span>' for c in del_tipo
                    if c.get('ok') is not None) + '</td>')
        ancla = re.sub(r'\W+', '-', f'{servicio}-{operacion}').strip('-')
        filas.append(f'<tr><td>ms-{e(servicio)}</td><td><a href="#{ancla}"><code>{e(operacion)}</code></a></td>{"".join(celdas)}</tr>')

    detalle = []
    servicio_actual = None
    for (servicio, operacion), lista in operaciones.items():
        if servicio != servicio_actual:
            detalle.append(f'<h2>ms-{e(servicio)} <span class="tenue">· puerto {PUERTOS[servicio]} · '
                           f'<a href="{base(servicio)}/docs">Swagger</a></span></h2>')
            servicio_actual = servicio
        ancla = re.sub(r'\W+', '-', f'{servicio}-{operacion}').strip('-')
        detalle.append(f'<h3 id="{ancla}"><code>{e(operacion)}</code> <span class="tenue">— {e(lista[0]["resumen"])}</span></h3>')
        detalle += [html_caso(c) for c in lista]

    bloques_bd = ''.join(f'<h3>{e(motor)} · {e(titulo)}</h3><pre>{e(salida)}</pre>' for motor, titulo, salida in bd)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Evidencias Avance 2</title><style>{CSS}</style></head>
<body><main>
<h1>AbastoRed · Evidencias de los microservicios (Avance 2)</h1>
<p class="tenue">Equipo 01 · Integración de Aplicaciones · generado el {datetime.now():%d/%m/%Y %H:%M} con
<code>python tests/evidencias/generar.py</code> contra el sistema levantado con Docker Compose.</p>
<div class="cifras">
  <div class="cifra"><b>{len(operaciones)}</b>operaciones</div>
  <div class="cifra"><b>{len(total)}</b>casos ejecutados</div>
  <div class="cifra"><b class="{'ok' if not fallas else 'mal'}">{len(total) - len(fallas)}</b>con el resultado esperado</div>
  <div class="cifra"><b>{sum(1 for c in total if c['tipo'] == 'negocio')}</b>reglas de negocio probadas</div>
</div>
<p>Cada operación se prueba con los cinco casos de la rúbrica. Los de parámetros inválidos, registro inexistente y
acceso no autorizado se derivan del contrato OpenAPI del servicio (tipos, restricciones y permisos declarados).
«n/a» indica que el caso no aplica (operación pública, sin parámetros o sin regla de negocio que la impida).
Cada caso muestra la solicitud y la respuesta completas; al final, lo que quedó guardado en las bases de datos.</p>
<h2>Resumen por operación</h2>
<table><thead><tr><th>Servicio</th><th>Operación</th><th>Éxito</th><th>Inválidos</th><th>Inexistente</th>
<th>No autorizado</th><th>Negocio</th></tr></thead><tbody>{''.join(filas)}</tbody></table>
{''.join(detalle)}
<h2>Evidencia en las bases de datos</h2>
<p class="tenue">Consultas ejecutadas dentro de los contenedores al terminar la corrida (psql, mongosh y redis-cli).</p>
{bloques_bd}
</main></body></html>"""


# ====================================================================== colección de Postman

def postman():
    variables = [{'key': f'ms_{s}', 'value': f'{base(s)}/api/v1'} for s in PUERTOS]
    variables += [{'key': f'token_{r}', 'value': ''} for r in USUARIOS]
    variables.append({'key': 'token_servicio', 'value': '', 'description':
                      'docker exec ms-pedidos python -c "from app import app; from abasto_dominio.sesiones import '
                      "token_servicio; app.app_context().push(); print(token_servicio('postman', ['notificaciones.crear']))\""})
    reemplazos = {str(v): k for k, v in ctx.items() if isinstance(v, (str, int)) and len(str(v)) >= 6
                  and k not in ('sufijo', 'csv_importacion', 'token_servicio', 'cid')}

    def con_variables(texto):
        for valor_real, clave in sorted(reemplazos.items(), key=lambda x: -len(x[0])):
            texto = texto.replace(valor_real, '{{' + clave + '}}')
        return texto

    for clave, v in ctx.items():
        if isinstance(v, (str, int)) and str(v) in reemplazos:
            variables.append({'key': clave, 'value': str(v)})

    sesiones = []
    for rol, (email, clave) in USUARIOS.items():
        sesiones.append({
            'name': f'Iniciar sesión · {rol}',
            'event': [{'listen': 'test', 'script': {'type': 'text/javascript', 'exec': [
                'pm.test("HTTP 200", () => pm.response.to.have.status(200));',
                f'pm.collectionVariables.set("token_{rol}", pm.response.json().access_token);']}}],
            'request': {'method': 'POST', 'header': [{'key': 'Content-Type', 'value': 'application/json'}],
                        'url': '{{ms_seguridad}}/auth/login',
                        'body': {'mode': 'raw', 'raw': json.dumps({'email': email, 'password': clave}),
                                 'options': {'raw': {'language': 'json'}}}}})

    carpetas = {}
    for c in casos:
        if c.get('ok') is None:
            continue
        p = c['peticion']
        cab = [{'key': 'Accept', 'value': 'application/json'}]
        if p['rol']:
            cab.append({'key': 'Authorization', 'value': 'Bearer {{token_%s}}' % p['rol']})
        ruta = con_variables(p['url'].replace(f"{base(c['servicio'])}/api/v1", '{{ms_%s}}' % c['servicio']))
        consulta = [{'key': k, 'value': con_variables(str(v))} for k, v in (p.get('params') or {}).items()]
        peticion = {'method': p['metodo'], 'header': cab,
                    'url': {'raw': ruta + ('?' + '&'.join(f"{q['key']}={q['value']}" for q in consulta) if consulta else ''),
                            'host': [ruta.split('/')[0]], 'path': ruta.split('/')[1:], 'query': consulta}}
        if p['formato_cuerpo']:
            cab.append({'key': 'Content-Type', 'value': f"application/{p['formato_cuerpo']}"})
            peticion['body'] = {'mode': 'raw', 'raw': con_variables(p['cuerpo']),
                                'options': {'raw': {'language': p['formato_cuerpo']}}}
        if p.get('archivos'):
            peticion['body'] = {'mode': 'formdata', 'formdata': [
                {'key': k, 'type': 'file', 'src': f'docs/postman/archivos/{v}'} for k, v in p['archivos'].items()]
                + [{'key': k, 'value': str(v), 'type': 'text'} for k, v in (p.get('datos') or {}).items()]}
        esperado = c['esperado']
        item = {'name': f"[{'/'.join(map(str, esperado))}] {NOMBRE_TIPO[c['tipo']]} · {c['titulo']}",
                'event': [{'listen': 'test', 'script': {'type': 'text/javascript', 'exec': [
                    f'pm.test("HTTP {"/".join(map(str, esperado))}", () => pm.expect(pm.response.code).to.be.oneOf({esperado}));']}}],
                'request': peticion}
        if c.get('nota'):
            item['request']['description'] = c['nota']
        carpetas.setdefault(c['servicio'], {}).setdefault(f"{c['operacion']} — {c['resumen']}", []).append(item)

    coleccion = {
        'info': {'name': 'AbastoRed · Avance 2 (Equipo 01)', '_postman_id': 'b6c1f7e0-abas-4c2d-9e3a-avance2equipo1',
                 'description': 'Cinco casos por operación (éxito, parámetros inválidos, inexistente, no autorizado y '
                                'regla de negocio) para los ocho microservicios. Ejecuta primero la carpeta '
                                '«00 · Sesiones» para obtener los tokens. Generada por tests/evidencias/generar.py.',
                 'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'},
        'variable': variables,
        'item': [{'name': '00 · Sesiones', 'item': sesiones}] + [
            {'name': f'{i:02d} · ms-{servicio}', 'item': [{'name': nombre, 'item': items} for nombre, items in ops.items()]}
            for i, (servicio, ops) in enumerate(carpetas.items(), start=1)],
    }
    POSTMAN.mkdir(parents=True, exist_ok=True)
    (POSTMAN / 'archivos').mkdir(exist_ok=True)
    (POSTMAN / 'archivos' / 'fachada.png').write_bytes(png())
    (POSTMAN / 'archivos' / 'inventario.csv').write_text(ctx['csv_importacion'], encoding='utf-8')
    (POSTMAN / 'archivos' / 'malo.csv').write_text('nombre;cantidad\nArroz;3\n', encoding='utf-8')
    (POSTMAN / 'archivos' / 'programa.exe').write_bytes(b'MZ\x90\x00')
    (POSTMAN / 'AbastoRed_Avance2.postman_collection.json').write_text(
        json.dumps(coleccion, ensure_ascii=False, indent=2), encoding='utf-8')


# ====================================================================== principal

def main():
    print('Preparando datos de prueba...')
    preparar()
    for especificacion in OPS:
        try:
            correr(especificacion)
        except KeyError as falta:  # un paso anterior no dejó el id que esta operación necesita
            print(f'  XX no se pudo ejecutar: falta {falta}')
            casos.append({'servicio': especificacion['servicio'], 'resumen': '', 'tipo': 'exito', 'ok': False,
                          'operacion': f"{especificacion['metodo']} {especificacion['plantilla']}",
                          'titulo': f'No se ejecutó: falta {falta} (falló un paso anterior)', 'obtenido': None,
                          'esperado': [especificacion['esperado']], 'peticion': None, 'respuesta': None})
    limpiar()
    print('\nConsultando las bases de datos...')
    bd = evidencias_bd()

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / 'evidencias_avance2.html').write_text(reporte(bd), encoding='utf-8')
    (SALIDA / 'resultados.json').write_text(json.dumps(
        {'generado': datetime.now().isoformat(timespec='seconds'), 'casos': casos,
         'bases_de_datos': [{'motor': m, 'titulo': t, 'salida': s} for m, t, s in bd]},
        ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    postman()

    ejecutados = [c for c in casos if c.get('ok') is not None]
    fallas = [c for c in ejecutados if not c['ok']]
    print(f"\n{len({(c['servicio'], c['operacion']) for c in casos})} operaciones, {len(ejecutados)} casos, "
          f"{len(fallas)} con resultado distinto al esperado.")
    for c in fallas:
        print(f"  XX {c['operacion']} [{c['tipo']}] {c['titulo']}: obtuvo {c['obtenido']}, esperaba {c['esperado']}")
    print(f'Reporte: {SALIDA / "evidencias_avance2.html"}')
    return 1 if fallas else 0


if __name__ == '__main__':
    sys.exit(main())
