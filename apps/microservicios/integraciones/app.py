"""
ms-integraciones: importación y exportación de información externa por lotes.

Es DUEÑO de las colecciones `integraciones_lotes` y `integraciones_conectores` (MongoDB). No
escribe en tablas de negocio: cada fila válida se aplica con la API del servicio dueño y el
token del usuario (ms-proveedores para el catálogo mayorista, ms-inventario para existencias y
límites, ms-precios para precios).

Proceso de un lote:
1. Lectura del archivo: CSV (UTF-8 o Latin-1, separador configurable), JSON (lista de objetos o
   {"filas": [...]}) o XML validado contra el XSD de este servicio (raíz importacion_<destino>).
2. Mapeo: un CONECTOR guarda, por proveedor o sistema externo, qué columna de su archivo
   corresponde a cada campo (p. ej. "PRECIO" -> precio_mayoreo) y valores fijos.
3. Validación fila por fila con el contrato del destino (Pydantic) y resolución del producto por
   id, código de barras o nombre exacto.
4. Aplicación (o simulación con `simulacion=true`): cada fila se aplica por separado; un error en
   una fila no detiene a las demás y queda registrado con su número de fila y el motivo.
5. El resultado del lote (filas, válidas, aplicadas, creadas, actualizadas y errores) queda en
   MongoDB y en la auditoría.
"""
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from bson import ObjectId
from flask import Response, g, request
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado
from abasto_api.clientes import llamar
from abasto_api.formatos import a_xml, compatible_json, leer_xml
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.servicios.auditoria import registrar_evento

from esquemas import (CONTRATOS_XML, ConectorEntrada, ExportacionConsulta, FilaCatalogo, FilaInventario, FilaPrecio,
                      ImportacionesConsulta)

srv = Servicio('integraciones', 'Integraciones',
               'Importación y exportación de información externa: conectores con proveedores, procesamiento de '
               'archivos CSV, JSON y XML, validación de esquemas, transformación y mapeo de datos y control de errores '
               'por lote.',
               xsd=Path(__file__).parent / 'xsd' / 'integraciones.xsd', contratos=CONTRATOS_XML)
app = srv.app

MODELOS = {'catalogo_proveedor': FilaCatalogo, 'inventario': FilaInventario, 'precios': FilaPrecio}
RAICES_XML = {'catalogo_proveedor': 'importacion_catalogo', 'inventario': 'importacion_inventario',
              'precios': 'importacion_precios'}
MAX_FILAS = 1000
UUID_RE = r'^[0-9a-fA-F-]{36}$'


def _lotes():
    return extensiones.mongo_db()['integraciones_lotes']


def _conectores():
    return extensiones.mongo_db()['integraciones_conectores']


def _api(servicio, metodo, ruta, **kwargs):
    respuesta = llamar(servicio, metodo, f'/api/v1{ruta}', token=g.token, timeout=10, **kwargs)
    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}
    if respuesta.status_code >= 500:
        raise ErrorApi(503, 'servicio_no_disponible', f'ms-{servicio} respondió {respuesta.status_code}.')
    return respuesta.status_code, cuerpo


def _mensaje(cuerpo):
    return (cuerpo.get('error') or {}).get('mensaje') or 'rechazada'


# ---------------------------------------------------------------- lectura y transformación

def leer_archivo(contenido, formato, destino, separador):
    if formato == 'csv':
        try:
            texto = contenido.decode('utf-8-sig')
        except UnicodeDecodeError:
            texto = contenido.decode('latin-1')
        lector = csv.DictReader(io.StringIO(texto), delimiter=separador)
        if not lector.fieldnames:
            raise ErrorApi(422, 'archivo_vacio', 'El CSV no tiene encabezados.')
        return [{(k or '').strip(): (v or '').strip() for k, v in fila.items()} for fila in lector]
    if formato == 'json':
        try:
            datos = json.loads(contenido.decode('utf-8-sig'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ErrorApi(400, 'json_invalido', f'El archivo no es JSON válido: {error}')
        filas = datos.get('filas') if isinstance(datos, dict) else datos
        if not isinstance(filas, list) or not all(isinstance(f, dict) for f in filas):
            raise ErrorApi(422, 'json_invalido', 'Se espera una lista de objetos o {"filas": [...]}')
        return filas
    try:
        documento = leer_xml(contenido, srv.xsd, RAICES_XML[destino], {'filas'})
    except ValueError as error:
        raise ErrorApi(400, 'xml_invalido', f'El XML no cumple el XSD ({RAICES_XML[destino]}): {error}')
    return documento.get('filas') or []


def transformar(fila, modelo, mapeo, fijos):
    """Aplica el mapeo del conector: campo destino <- columna del archivo; los vacíos se omiten."""
    salida = {}
    for campo in modelo.model_fields:
        origen = mapeo.get(campo, campo)
        valor = fila.get(origen)
        if valor not in (None, ''):
            salida[campo] = valor
    salida.update({k: v for k, v in fijos.items() if k in modelo.model_fields})
    return salida


def resolver_producto(fila):
    if fila.producto_id:
        consulta, parametros = 'SELECT id FROM productos_maestros WHERE id = :v AND activo', {'v': fila.producto_id}
    elif fila.codigo_barras:
        consulta, parametros = ('SELECT producto_id AS id FROM variantes_producto WHERE codigo_barras = :v AND activo '
                                'UNION SELECT id FROM productos_maestros WHERE codigo_barras = :v AND activo',
                                {'v': fila.codigo_barras})
    else:
        consulta, parametros = ('SELECT id FROM productos_maestros WHERE lower(nombre) = lower(:v) AND activo',
                                {'v': fila.producto})
    ids = [r.id for r in db.session.execute(text(consulta), parametros)]
    return ids[0] if len(ids) == 1 else None


# ---------------------------------------------------------------- aplicación por destino

def _mapa_inventario(comercio_id):
    renglones, pagina = {}, 1
    while True:
        status, cuerpo = _api('inventario', 'GET', f'/comercios/{comercio_id}/inventario',
                              params={'pagina': pagina, 'por_pagina': 200})
        if status != 200:
            raise ErrorApi(403 if status in (401, 403) else 404, 'comercio_inaccesible',
                           f'ms-inventario: {_mensaje(cuerpo)}')
        renglones.update({r['producto_id']: r for r in cuerpo['renglones']})
        if pagina >= cuerpo['paginacion']['paginas']:
            return renglones
        pagina += 1


def aplicar_catalogo(filas):
    status, cuerpo = _api('proveedores', 'GET', '/mi-catalogo')
    if status != 200:
        raise ErrorApi(403 if status in (401, 403) else 409, 'catalogo_inaccesible', f'ms-proveedores: {_mensaje(cuerpo)}')
    existentes = {o['producto_id']: o['id'] for o in cuerpo['ofertas']}
    for numero, producto_id, fila in filas:
        datos = {'precio_mayoreo': str(fila.precio_mayoreo), 'cantidad_minima': str(fila.cantidad_minima),
                 'existencia_disponible': str(fila.existencia_disponible)}
        if producto_id in existentes:
            status, cuerpo = _api('proveedores', 'PATCH', f'/mi-catalogo/{existentes[producto_id]}', json=datos)
            yield numero, status == 200, 'actualizada', _mensaje(cuerpo)
        else:
            status, cuerpo = _api('proveedores', 'POST', '/mi-catalogo', json={'producto_id': producto_id, **datos})
            yield numero, status == 201, 'creada', _mensaje(cuerpo)


def aplicar_inventario(filas, comercio_id):
    renglones = _mapa_inventario(comercio_id)
    for numero, producto_id, fila in filas:
        actual = renglones.get(producto_id)
        if not actual:
            cuerpo = {'producto_id': producto_id, 'existencia': str(fila.existencia),
                      'stock_minimo': str(fila.stock_minimo or 0)}
            if fila.stock_maximo is not None:
                cuerpo['stock_maximo'] = str(fila.stock_maximo)
            if fila.precio_venta:
                cuerpo['precio_venta'] = str(fila.precio_venta)
            status, respuesta = _api('inventario', 'POST', f'/comercios/{comercio_id}/inventario', json=cuerpo)
            yield numero, status == 201, 'creada', _mensaje(respuesta)
            continue
        errores = []
        if float(actual['existencia']) != float(fila.existencia):
            status, respuesta = _api('inventario', 'POST', f"/inventario/{actual['id']}/movimientos", json={
                'tipo': 'AJUSTE', 'cantidad': str(fila.existencia), 'motivo': 'Importación de inventario (ms-integraciones)'})
            if status != 201:
                errores.append(_mensaje(respuesta))
        limites = {k: str(getattr(fila, k)) for k in ('stock_minimo', 'stock_maximo') if getattr(fila, k) is not None}
        if limites:
            status, respuesta = _api('inventario', 'PATCH', f"/inventario/{actual['id']}", json=limites)
            if status != 200:
                errores.append(_mensaje(respuesta))
        if fila.precio_venta and float(actual.get('precio_venta') or 0) != float(fila.precio_venta):
            status, respuesta = _api('precios', 'PUT', f"/inventario/{actual['id']}/precio",
                                     json={'precio': str(fila.precio_venta)})
            if status not in (200, 201):
                errores.append(_mensaje(respuesta))
        yield numero, not errores, 'actualizada', '; '.join(errores)


def aplicar_precios(filas, comercio_id):
    renglones = _mapa_inventario(comercio_id)
    for numero, producto_id, fila in filas:
        actual = renglones.get(producto_id)
        if not actual:
            yield numero, False, None, 'El comercio no vende ese producto; impórtalo primero al inventario.'
            continue
        status, cuerpo = _api('precios', 'PUT', f"/inventario/{actual['id']}/precio", json={'precio': str(fila.precio)})
        yield numero, status in (200, 201), 'actualizada', _mensaje(cuerpo)


# ---------------------------------------------------------------- importación

def conector_a_dict(c):
    return {'id': str(c['_id']), 'nombre': c['nombre'], 'destino': c['destino'], 'formato': c['formato'],
            'separador': c['separador'], 'mapeo': c['mapeo'], 'valores_fijos': c['valores_fijos'],
            'descripcion': c.get('descripcion'), 'creado': c['creado']}


def lote_a_dict(lote):
    return {'id': str(lote['_id']), **{k: lote[k] for k in (
        'destino', 'formato', 'archivo', 'conector', 'simulacion', 'fecha', 'filas', 'validas', 'aplicadas', 'creadas',
        'actualizadas', 'con_error', 'errores')}}


@srv.ruta('/importaciones', 'POST', resumen='Importar un archivo CSV, JSON o XML', etiqueta='Importación',
          permisos=['integraciones.ejecutar', 'importaciones.ejecutar', 'proveedor.catalogo'], status=201,
          raiz_xml='lote', errores=(400, 401, 403, 404, 413, 422),
          multipart={'type': 'object', 'required': ['archivo', 'destino'], 'properties': {
              'archivo': {'type': 'string', 'format': 'binary'},
              'destino': {'type': 'string', 'enum': list(MODELOS)},
              'formato': {'type': 'string', 'enum': ['csv', 'json', 'xml'],
                          'description': 'Por omisión, según la extensión del archivo'},
              'comercio_id': {'type': 'string', 'description': 'Obligatorio para inventario y precios'},
              'conector_id': {'type': 'string', 'description': 'Conector con el mapeo de columnas'},
              'separador': {'type': 'string', 'enum': [',', ';', '|']},
              'simulacion': {'type': 'boolean', 'description': 'true: sólo valida, no aplica nada'}}})
def importar():
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        raise ErrorApi(400, 'archivo_requerido', 'Envía el archivo en el campo "archivo" (multipart/form-data).')
    destino = request.form.get('destino')
    if destino not in MODELOS:
        raise ErrorApi(422, 'destino_invalido', f'destino debe ser: {", ".join(MODELOS)}.')
    conector = None
    if request.form.get('conector_id'):
        try:
            conector = _conectores().find_one({'_id': ObjectId(request.form['conector_id']),
                                               'propietario_id': g.claims['sub']})
        except Exception:  # noqa: BLE001 - id inválido
            conector = None
        if not conector:
            raise no_encontrado('El conector')
        if conector['destino'] != destino:
            raise ErrorApi(422, 'conector_otro_destino', f"El conector es para {conector['destino']}.")
    formato = request.form.get('formato') or (conector or {}).get('formato') or archivo.filename.rsplit('.', 1)[-1].lower()
    if formato not in ('csv', 'json', 'xml'):
        raise ErrorApi(422, 'formato_invalido', 'formato debe ser csv, json o xml.')
    comercio_id = request.form.get('comercio_id')
    if destino in ('inventario', 'precios') and not comercio_id:
        raise ErrorApi(422, 'comercio_requerido', 'Para inventario y precios indica comercio_id.')
    simulacion = request.form.get('simulacion', 'false').lower() == 'true'
    separador = request.form.get('separador') or (conector or {}).get('separador') or ','

    crudas = leer_archivo(archivo.read(), formato, destino, separador)
    if not crudas:
        raise ErrorApi(422, 'archivo_vacio', 'El archivo no tiene filas.')
    if len(crudas) > MAX_FILAS:
        raise ErrorApi(413, 'demasiadas_filas', f'Máximo {MAX_FILAS} filas por lote.')

    modelo = MODELOS[destino]
    errores, validas = [], []
    for numero, cruda in enumerate(crudas, start=2 if formato == 'csv' else 1):   # en CSV la fila 1 son encabezados
        try:
            fila = modelo.model_validate(transformar(cruda, modelo, (conector or {}).get('mapeo', {}),
                                                     (conector or {}).get('valores_fijos', {})))
        except ValidationError as error:
            for e in error.errors():
                errores.append({'fila': numero, 'campo': '.'.join(str(x) for x in e['loc']) or None, 'error': e['msg']})
            continue
        producto_id = resolver_producto(fila)
        if not producto_id:
            errores.append({'fila': numero, 'campo': 'producto', 'error': 'Producto no encontrado (o ambiguo).'})
            continue
        validas.append((numero, producto_id, fila))

    creadas = actualizadas = 0
    if validas and not simulacion:
        if destino == 'catalogo_proveedor':
            resultados = aplicar_catalogo(validas)
        elif destino == 'inventario':
            resultados = aplicar_inventario(validas, comercio_id)
        else:
            resultados = aplicar_precios(validas, comercio_id)
        for numero, ok, tipo, mensaje in resultados:
            if ok:
                creadas += tipo == 'creada'
                actualizadas += tipo == 'actualizada'
            else:
                errores.append({'fila': numero, 'campo': None, 'error': mensaje})
    errores.sort(key=lambda e: e['fila'])
    lote = {'usuario_id': g.claims['sub'], 'destino': destino, 'formato': formato, 'archivo': archivo.filename,
            'conector': conector['nombre'] if conector else None, 'comercio_id': comercio_id, 'simulacion': simulacion,
            'fecha': datetime.now(timezone.utc), 'filas': len(crudas), 'validas': len(validas),
            'aplicadas': 0 if simulacion else creadas + actualizadas, 'creadas': creadas, 'actualizadas': actualizadas,
            'con_error': len({e['fila'] for e in errores}), 'errores': errores[:500],
            'correlation_id': g.correlation_id}
    lote['_id'] = _lotes().insert_one(compatible_json(lote) | {'fecha': lote['fecha']}).inserted_id
    if not simulacion:
        registrar_evento(UUID(g.claims['sub']), 'CREACION', 'LoteIntegracion', str(lote['_id']),
                         f'Importación de {destino} ({formato}): {lote["aplicadas"]} aplicadas, {lote["con_error"]} con error',
                         datos_nuevos={k: lote[k] for k in ('archivo', 'filas', 'aplicadas', 'con_error')})
        db.session.commit()
    return lote_a_dict(lote)


@srv.ruta('/importaciones', 'GET', resumen='Mis lotes de importación', etiqueta='Importación',
          permisos=['integraciones.ejecutar', 'importaciones.ejecutar', 'proveedor.catalogo'],
          consulta=ImportacionesConsulta, raiz_xml='lotes')
def lotes(q):
    documentos = list(_lotes().find({'usuario_id': g.claims['sub']}).sort('fecha', -1).limit(q.limite))
    return {'total': len(documentos), 'lotes': [lote_a_dict(d) for d in documentos]}


@srv.ruta('/importaciones/<id>', 'GET', resumen='Resultado de un lote', etiqueta='Importación',
          permisos=['integraciones.ejecutar', 'importaciones.ejecutar', 'proveedor.catalogo'], raiz_xml='lote')
def lote(id):
    try:
        documento = _lotes().find_one({'_id': ObjectId(id), 'usuario_id': g.claims['sub']})
    except Exception:  # noqa: BLE001
        documento = None
    if not documento:
        raise no_encontrado('El lote')
    return lote_a_dict(documento)


# ---------------------------------------------------------------- conectores

@srv.ruta('/conectores', 'POST', resumen='Guardar un conector (mapeo de columnas)', etiqueta='Conectores',
          permisos=['integraciones.ejecutar', 'proveedor.catalogo'], cuerpo=ConectorEntrada, status=201,
          raiz_xml='conector', entrada_xml='conector_entrada',
          ejemplo_entrada={'nombre': 'Lista de precios Distribuidora Regia', 'destino': 'catalogo_proveedor',
                           'formato': 'csv', 'separador': ';',
                           'mapeo': {'codigo_barras': 'EAN', 'precio_mayoreo': 'PRECIO', 'existencia_disponible': 'STOCK'},
                           'valores_fijos': {'cantidad_minima': '6'}})
def crear_conector(datos):
    modelo = MODELOS[datos.destino]
    desconocidos = sorted(set(datos.mapeo) - set(modelo.model_fields)) + \
        sorted(set(datos.valores_fijos) - set(modelo.model_fields))
    if desconocidos:
        raise ErrorApi(422, 'campos_desconocidos', f'Campos que no existen en {datos.destino}: {desconocidos}.')
    documento = {**datos.model_dump(), 'propietario_id': g.claims['sub'], 'creado': datetime.now(timezone.utc)}
    try:
        documento['_id'] = _conectores().insert_one(documento).inserted_id
    except DuplicateKeyError:
        raise ErrorApi(409, 'conector_duplicado', 'Ya tienes un conector con ese nombre.')
    return conector_a_dict(documento)


@srv.ruta('/conectores', 'GET', resumen='Mis conectores', etiqueta='Conectores',
          permisos=['integraciones.ejecutar', 'proveedor.catalogo'], raiz_xml='conectores')
def conectores():
    return {'conectores': [conector_a_dict(c) for c in
                           _conectores().find({'propietario_id': g.claims['sub']}).sort('nombre', 1)]}


@srv.ruta('/conectores/<id>', 'DELETE', resumen='Eliminar un conector', etiqueta='Conectores',
          permisos=['integraciones.ejecutar', 'proveedor.catalogo'], raiz_xml='resultado')
def eliminar_conector(id):
    try:
        borrado = _conectores().delete_one({'_id': ObjectId(id), 'propietario_id': g.claims['sub']}).deleted_count
    except Exception:  # noqa: BLE001
        borrado = 0
    if not borrado:
        raise no_encontrado('El conector')
    return {'mensaje': 'Conector eliminado', 'id': id}


# ---------------------------------------------------------------- exportación y plantillas

def archivo_de(filas, formato, nombre, raiz):
    if formato == 'json':
        contenido, tipo = json.dumps({'filas': compatible_json(filas)}, ensure_ascii=False, indent=2), 'application/json'
    elif formato == 'xml':
        contenido, tipo = a_xml({'filas': filas}, raiz), 'application/xml'
    else:
        salida = io.StringIO()
        if filas:
            escritor = csv.DictWriter(salida, fieldnames=list(filas[0]))
            escritor.writeheader()
            escritor.writerows(filas)
        contenido, tipo = '﻿' + salida.getvalue(), 'text/csv'   # BOM: Excel abre bien los acentos
    return Response(contenido, mimetype=tipo,
                    headers={'Content-Disposition': f'attachment; filename="{nombre}.{formato}"'})


@srv.ruta('/exportaciones/<tipo>', 'GET', resumen='Exportar inventario, catálogo mayorista o productos',
          etiqueta='Exportación', permisos=['integraciones.ejecutar', 'importaciones.ejecutar', 'proveedor.catalogo',
                                            'inventario.gestionar'], consulta=ExportacionConsulta,
          errores=(400, 401, 403, 404, 422))
def exportar(tipo, q):
    """`tipo`: inventario (de comercio_id), catalogo-proveedor (el mío) o productos (catálogo maestro). Los datos se
    obtienen de la API del servicio dueño, con tus permisos. El XML usa las mismas raíces que la importación."""
    if tipo == 'inventario':
        if not q.comercio_id:
            raise ErrorApi(422, 'comercio_requerido', 'Indica comercio_id.')
        filas = [{'producto_id': r['producto_id'], 'producto': r['producto'], 'existencia': r['existencia'],
                  'stock_minimo': r['stock_minimo'], 'stock_maximo': r['stock_maximo'],
                  'precio_venta': r['precio_venta']} for r in _mapa_inventario(q.comercio_id).values()]
        return archivo_de(filas, q.archivo, 'inventario', 'importacion_inventario')
    if tipo == 'catalogo-proveedor':
        status, cuerpo = _api('proveedores', 'GET', '/mi-catalogo')
        if status != 200:
            raise ErrorApi(403 if status in (401, 403) else 409, 'catalogo_inaccesible', _mensaje(cuerpo))
        filas = [{'producto_id': o['producto_id'], 'producto': o['producto'], 'precio_mayoreo': o['precio_mayoreo'],
                  'cantidad_minima': o['cantidad_minima'], 'existencia_disponible': o['existencia_disponible']}
                 for o in cuerpo['ofertas']]
        return archivo_de(filas, q.archivo, 'catalogo_mayorista', 'importacion_catalogo')
    if tipo == 'productos':
        filas, pagina = [], 1
        while True:
            status, cuerpo = _api('catalogo', 'GET', '/productos', params={'pagina': pagina, 'por_pagina': 200})
            filas += [{'producto_id': p['id'], 'producto': p['nombre'], 'categoria': p['categoria'],
                       'unidad_medida': p['unidad_medida'], 'codigo_barras': p.get('codigo_barras'),
                       'canasta_basica': p['es_canasta_basica']} for p in cuerpo.get('productos', [])]
            if status != 200 or pagina >= cuerpo['paginacion']['paginas']:
                break
            pagina += 1
        return archivo_de(filas, q.archivo, 'productos', 'exportacion_productos')
    raise no_encontrado(f'La exportación {tipo}')


@srv.ruta('/plantillas/<destino>', 'GET', resumen='Plantilla de importación con un ejemplo', etiqueta='Importación',
          publico=True, consulta=ExportacionConsulta, errores=(404,))
def plantilla(destino, q):
    """`archivo=csv|json|xml`. La plantilla en XML es un documento válido contra el XSD de importación."""
    ejemplos = {
        'catalogo_proveedor': {'producto_id': 1, 'codigo_barras': '', 'producto': '', 'precio_mayoreo': '24.50',
                               'cantidad_minima': '12', 'existencia_disponible': '300'},
        'inventario': {'producto_id': '', 'codigo_barras': '', 'producto': 'Arroz blanco 1 kg', 'existencia': '20',
                       'stock_minimo': '6', 'stock_maximo': '40', 'precio_venta': '32.00'},
        'precios': {'producto_id': 3, 'codigo_barras': '', 'producto': '', 'precio': '41.90'},
    }
    if destino not in ejemplos:
        raise no_encontrado(f'La plantilla {destino}')
    formato = q.archivo
    fila = {k: v for k, v in ejemplos[destino].items() if v != '' or formato == 'csv'}
    return archivo_de([fila], formato, f'plantilla_{destino}', RAICES_XML[destino])
