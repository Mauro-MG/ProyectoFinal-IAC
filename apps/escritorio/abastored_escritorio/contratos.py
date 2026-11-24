"""
Contratos XML de los microservicios.

Cada servicio publica su esquema en GET /ms/<servicio>/xsd. La aplicación lo
descarga una vez por sesión y lo usa para tres cosas:

  * validar cada petición antes de enviarla y cada respuesta al recibirla;
  * recorrer el documento con el tipo exacto de cada elemento: qué es objeto,
    qué es lista (maxOccurs distinto de 1, aunque traiga uno o ningún
    elemento) y a qué tipo se convierte cada texto (xs:integer, xs:decimal,
    xs:boolean, xs:dateTime…);
  * armar las peticiones con los nombres que espera el servicio.

No hay modelos escritos a mano: si un servicio agrega un campo a su contrato,
la aplicación lo recibe sin cambios.
"""
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from lxml import etree

NS = 'https://abastored.mx/esquemas/v1'
XS = '{http://www.w3.org/2001/XMLSchema}'


class ContratoInvalido(Exception):
    """El documento no cumple el XSD del servicio."""

    def __init__(self, servicio, raiz, errores):
        self.errores = errores
        super().__init__(f'ms-{servicio}: <{raiz}> no cumple el contrato XSD: {errores[0] if errores else ""}')


def _convertir(texto, tipo):
    if texto is None:
        return None
    try:
        if tipo == 'integer':
            return int(texto)
        if tipo == 'decimal':
            return Decimal(texto)
        if tipo == 'boolean':
            return texto in ('true', '1')
        if tipo == 'dateTime':
            return datetime.fromisoformat(texto)
        if tipo == 'date':
            return date.fromisoformat(texto)
        if tipo == 'time':
            return time.fromisoformat(texto)
    except (ValueError, InvalidOperation):
        pass
    return texto


def _texto(valor):
    if isinstance(valor, bool):
        return 'true' if valor else 'false'
    if isinstance(valor, Decimal):
        return format(valor, 'f')
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    return str(valor)


def _elementos(nodo):
    """Elementos declarados directamente en un complexType (dentro de all, sequence o choice)."""
    for grupo in nodo:
        if grupo.tag in (f'{XS}all', f'{XS}sequence', f'{XS}choice'):
            yield from (e for e in grupo if e.tag == f'{XS}element')


class Contrato:
    """
    Un campo se describe como:
        ('simple', 'integer')            texto con su tipo
        ('tipo', 'ComercioSalida')       objeto de un complexType con nombre
        ('objeto', {hijo: campo})        objeto anónimo
        ('lista', 'comercio', campo)     contenedor cuyos hijos <comercio> se repiten
    """

    def __init__(self, servicio, documento):
        self.servicio = servicio
        self.esquema = etree.XMLSchema(documento)
        self.tipos = {t.get('name'): self._campos(t) for t in documento.findall(f'{XS}complexType')}
        self.raices = {e.get('name'): self._campo(e) for e in documento.findall(f'{XS}element')}

    @classmethod
    def desde_xsd(cls, servicio, contenido):
        return cls(servicio, etree.fromstring(contenido))

    def _campos(self, tipo_complejo):
        return {e.get('name'): self._campo(e) for e in _elementos(tipo_complejo)}

    def _campo(self, elemento):
        tipo = elemento.get('type')
        if tipo:
            return ('simple', tipo[3:]) if tipo.startswith('xs:') else ('tipo', tipo)
        simple = elemento.find(f'{XS}simpleType/{XS}restriction')
        if simple is not None:
            return ('simple', simple.get('base', 'xs:string')[3:])
        complejo = elemento.find(f'{XS}complexType')
        if complejo is None:
            return ('simple', 'string')
        hijos = list(_elementos(complejo))
        if len(hijos) == 1 and hijos[0].get('maxOccurs', '1') != '1':
            return ('lista', hijos[0].get('name'), self._campo(hijos[0]))
        return ('objeto', {h.get('name'): self._campo(h) for h in hijos})

    def _hijos(self, campo):
        if campo[0] == 'tipo':
            return self.tipos.get(campo[1], {})
        return campo[1] if campo[0] == 'objeto' else {}

    # ------------------------------------------------------------ validación
    def validar(self, raiz):
        if not self.esquema.validate(raiz):
            errores = [f'línea {e.line}: {e.message}' for e in self.esquema.error_log]
            raise ContratoInvalido(self.servicio, etree.QName(raiz).localname, errores)

    # ------------------------------------------------------------ XML -> datos
    def a_datos(self, elemento, campo=None):
        if campo is None:
            campo = self.raices.get(etree.QName(elemento).localname, ('objeto', {}))
        if campo[0] == 'lista':
            return [self.a_datos(h, campo[2]) for h in elemento]
        if campo[0] == 'simple':
            return _convertir(elemento.text, campo[1])
        hijos = self._hijos(campo)
        return {etree.QName(h).localname: self.a_datos(h, hijos.get(etree.QName(h).localname, ('simple', 'string')))
                for h in elemento}

    # ------------------------------------------------------------ datos -> XML
    def a_xml(self, raiz, datos):
        """Arma el documento de una petición y lo valida. Los campos None se omiten (así lo pide el contrato)."""
        elemento = etree.Element(f'{{{NS}}}{raiz}', nsmap={None: NS})
        self._llenar(elemento, datos, self.raices.get(raiz, ('objeto', {})))
        self.validar(elemento)
        return elemento

    def _llenar(self, nodo, valor, campo):
        if campo[0] == 'lista':
            for v in valor:
                self._llenar(etree.SubElement(nodo, f'{{{NS}}}{campo[1]}'), v, campo[2])
        elif isinstance(valor, dict):
            hijos = self._hijos(campo)
            for clave, v in valor.items():
                if v is not None and v != {}:     # opcionales sin valor (o sin ningún campo) se omiten
                    self._llenar(etree.SubElement(nodo, f'{{{NS}}}{clave}'), v, hijos.get(clave, ('simple', 'string')))
        else:
            nodo.text = _texto(valor)
