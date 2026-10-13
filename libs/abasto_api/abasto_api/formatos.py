"""
Negociación de formato JSON / XML.

Respuesta: XML si el cliente manda `Accept: application/xml` (o `?formato=xml`),
JSON en cualquier otro caso. Petición: se lee XML si `Content-Type` es
`application/xml`; antes de convertirlo se valida contra su XSD.

Reglas de conversión a XML (contrato v1; XSD de cada servicio en apps/microservicios/<servicio>/xsd):
  * espacio de nombres https://abastored.mx/esquemas/v1, UTF-8;
  * cada llave de un objeto es un elemento hijo;
  * una lista es un elemento contenedor cuyos hijos se llaman en singular
    (`renglones` -> `renglon`); el nombre lo da el mapa SINGULARES;
  * valores nulos se omiten (minOccurs="0"); booleanos como true/false;
    fechas en ISO 8601; números con punto decimal.
"""
from datetime import date, datetime, time
from decimal import Decimal
from functools import lru_cache
from uuid import UUID

from flask import Response, json, request
from lxml import etree

NS = 'https://abastored.mx/esquemas/v1'
MIME_XML = 'application/xml'
MIME_JSON = 'application/json'

SINGULARES = {
    'items': 'item', 'renglones': 'renglon', 'movimientos': 'movimiento', 'partidas': 'partida',
    'historial': 'evento', 'eventos': 'evento', 'comercios': 'comercio', 'productos': 'producto',
    'proveedores': 'proveedor', 'ofertas': 'oferta', 'zonas': 'zona', 'pedidos': 'pedido',
    'precios': 'precio', 'brechas': 'brecha', 'recomendaciones': 'recomendacion', 'notificaciones': 'notificacion',
    'archivos': 'archivo', 'detalles': 'detalle', 'permisos': 'permiso', 'acciones': 'accion',
    'sesiones': 'sesion', 'errores': 'error', 'series': 'serie', 'datos': 'dato', 'categorias': 'categoria',
    'usuarios': 'usuario', 'snapshots': 'snapshot', 'resumen': 'renglon', 'consumidor': 'renglon',
    'mayoreo': 'renglon', 'faltantes': 'faltante', 'dependencias': 'dependencia', 'tendencia': 'punto',
    'roles': 'rol', 'permisos_disponibles': 'permiso', 'servicios': 'servicio', 'pasos': 'paso',
    'cercanas': 'cercana', 'importaciones': 'importacion', 'oportunidades': 'oportunidad', 'ids': 'id',
}


def quiere_xml():
    if request.args.get('formato', '').lower() == 'xml':
        return True
    if request.args.get('formato', '').lower() == 'json':
        return False
    mejor = request.accept_mimetypes.best_match([MIME_JSON, MIME_XML], default=MIME_JSON)
    return mejor == MIME_XML and request.accept_mimetypes[MIME_XML] > request.accept_mimetypes[MIME_JSON]


def _texto(valor):
    if isinstance(valor, bool):
        return 'true' if valor else 'false'
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return format(valor.normalize(), 'f')
    if isinstance(valor, UUID):
        return str(valor)
    return str(valor)


def _agregar(padre, nombre, valor):
    if valor is None:
        return
    elemento = etree.SubElement(padre, f'{{{NS}}}{nombre}')
    if isinstance(valor, dict):
        for llave, sub in valor.items():
            _agregar(elemento, llave, sub)
    elif isinstance(valor, (list, tuple)):
        hijo = SINGULARES.get(nombre, 'item')
        for sub in valor:
            _agregar(elemento, hijo, sub)
    else:
        elemento.text = _texto(valor)


def a_xml(datos, raiz):
    """dict -> bytes XML con declaración y espacio de nombres."""
    elemento = etree.Element(f'{{{NS}}}{raiz}', nsmap={None: NS})
    if isinstance(datos, dict):
        for llave, valor in datos.items():
            _agregar(elemento, llave, valor)
    elif isinstance(datos, (list, tuple)):
        hijo = SINGULARES.get(raiz, 'item')
        for valor in datos:
            _agregar(elemento, hijo, valor)
    return etree.tostring(elemento, xml_declaration=True, encoding='UTF-8', pretty_print=True)


def compatible_json(valor):
    if isinstance(valor, dict):
        return {k: compatible_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [compatible_json(v) for v in valor]
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    return valor


def responder(datos, status=200, raiz='respuesta', headers=None):
    """Respuesta en el formato que pidió el cliente."""
    if quiere_xml():
        if isinstance(datos, dict) and list(datos) == [raiz] and isinstance(datos[raiz], dict):
            # {"error": {...}} se vuelve <error>...</error>. Una lista ({"categorias": [...]}) no se
            # desenvuelve: el contrato pide <categorias><categorias><categoria/>...</categorias></categorias>
            datos = datos[raiz]
        cuerpo = a_xml(datos, raiz)
        return Response(cuerpo, status=status, mimetype=MIME_XML, headers=headers,
                        content_type=f'{MIME_XML}; charset=utf-8')
    cuerpo = json.dumps(compatible_json(datos), ensure_ascii=False, indent=2)
    return Response(cuerpo, status=status, mimetype=MIME_JSON, headers=headers)


# ---------------------------------------------------------------- lectura de XML

@lru_cache(maxsize=None)
def esquema(ruta):
    """Carga (una vez) el XSD de un servicio."""
    return etree.XMLSchema(etree.parse(str(ruta)))


def _local(tag):
    return etree.QName(tag).localname


def _a_dict(elemento, listas):
    hijos = list(elemento)
    if not hijos:
        return elemento.text.strip() if elemento.text and elemento.text.strip() else None
    nombre = _local(elemento.tag)
    if nombre in listas:
        return [_a_dict(h, listas) for h in hijos]
    return {_local(h.tag): _a_dict(h, listas) for h in hijos}


def leer_xml(cuerpo, xsd=None, raiz=None, listas=()):
    """
    bytes XML -> dict. Valida contra el XSD del servicio y que el elemento raíz
    sea el esperado; lanza ValueError con los mensajes del validador.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        documento = etree.fromstring(cuerpo, parser)
    except etree.XMLSyntaxError as error:
        raise ValueError(f'XML mal formado: {error}')
    if raiz and etree.QName(documento.tag) != etree.QName(NS, raiz):
        raise ValueError(f'Se esperaba el elemento raíz <{raiz} xmlns="{NS}">, llegó <{etree.QName(documento.tag).localname}>.')
    if xsd:
        validador = esquema(xsd)
        if not validador.validate(documento):
            mensajes = [f'línea {e.line}: {e.message}' for e in validador.error_log]
            raise ValueError('El XML no cumple el esquema: ' + '; '.join(mensajes[:5]))
    return _a_dict(documento, set(listas))


def validar_xml(cuerpo, xsd):
    """Para pruebas: True o lista de errores al validar un XML contra el XSD (ruta)."""
    documento = etree.fromstring(cuerpo)
    validador = esquema(str(xsd))
    if validador.validate(documento):
        return True
    return [f'línea {e.line}: {e.message}' for e in validador.error_log]
