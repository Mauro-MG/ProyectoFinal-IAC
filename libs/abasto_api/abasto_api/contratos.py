"""
Generación de los esquemas XSD a partir de los modelos Pydantic de cada servicio.

Cada servicio declara en esquemas.py un diccionario CONTRATOS_XML:
    {'pedido_entrada': PedidoEntrada, 'pedido': PedidoSalida, ...}
(nombre del elemento raíz -> modelo). Con ese mapa se genera un solo XSD por
servicio (apps/microservicios/<servicio>/xsd/<servicio>.xsd) con un elemento
global por raíz. Así el contrato XML sale de los mismos modelos que validan el
JSON, y no puede desfasarse: una prueba compara el XSD guardado con el generado.

Reglas de traducción:
  objeto            -> complexType con <xs:all> (los campos pueden venir en cualquier orden)
  campo obligatorio -> minOccurs="1"; opcional o nulo -> minOccurs="0"
  lista             -> elemento contenedor con hijos en singular, maxOccurs="unbounded"
  str               -> xs:string con minLength / maxLength / pattern / enumeration
  int / float       -> xs:integer / xs:decimal con minInclusive / maxInclusive / minExclusive
  bool / fecha      -> xs:boolean / xs:date / xs:time / xs:dateTime
  dict libre        -> contenido abierto (<xs:any processContents="lax">)

Uso:  python -m abasto_api.contratos apps/microservicios/pedidos
"""
import importlib.util
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from lxml import etree
from pydantic.json_schema import models_json_schema

from abasto_api.formatos import NS, SINGULARES
from abasto_api.modelos_comunes import CONTRATOS_COMUNES

_FORMATOS = {'date-time': 'xs:dateTime', 'date': 'xs:date', 'time': 'xs:time'}


class _Generador:
    def __init__(self, contratos):
        self.contratos = {**CONTRATOS_COMUNES, **contratos}
        modelos = list(dict.fromkeys(self.contratos.values()))
        nombres, definiciones = models_json_schema([(m, 'validation') for m in modelos],
                                                   ref_template='#/$defs/{model}')
        self.defs = definiciones.get('$defs', {})
        self.raices = {raiz: nombres[(m, 'validation')]['$ref'].split('/')[-1]
                       for raiz, m in self.contratos.items()}

    # ---------------------------------------------------------------- tipos simples
    @staticmethod
    def _restriccion(base, esquema):
        facetas = []
        if 'enum' in esquema:
            facetas += [f'<xs:enumeration value="{escape(str(v))}"/>' for v in esquema['enum']]
        if 'const' in esquema:
            facetas.append(f'<xs:enumeration value="{escape(str(esquema["const"]))}"/>')
        for clave, faceta in (('minLength', 'minLength'), ('maxLength', 'maxLength'),
                              ('minimum', 'minInclusive'), ('maximum', 'maxInclusive'),
                              ('exclusiveMinimum', 'minExclusive'), ('exclusiveMaximum', 'maxExclusive')):
            if clave in esquema:
                facetas.append(f'<xs:{faceta} value="{esquema[clave]}"/>')
        if 'pattern' in esquema:
            facetas.append(f'<xs:pattern value="{escape(esquema["pattern"].lstrip("^").rstrip("$"))}"/>')
        if not facetas:
            return None
        return f'<xs:simpleType><xs:restriction base="{base}">{"".join(facetas)}</xs:restriction></xs:simpleType>'

    def _simple(self, esquema):
        """(atributo type, tipo anónimo) para un esquema JSON escalar."""
        tipo = esquema.get('type')
        if 'enum' in esquema or 'const' in esquema:
            return None, self._restriccion('xs:string', esquema)
        if tipo == 'string':
            base = _FORMATOS.get(esquema.get('format'), 'xs:string')
            anonimo = self._restriccion(base, esquema) if base == 'xs:string' else None
            return (None, anonimo) if anonimo else (base, None)
        base = {'integer': 'xs:integer', 'number': 'xs:decimal', 'boolean': 'xs:boolean'}.get(tipo, 'xs:string')
        anonimo = self._restriccion(base, esquema) if tipo in ('integer', 'number') else None
        return (None, anonimo) if anonimo else (base, None)

    # ---------------------------------------------------------------- elementos
    @staticmethod
    def _sin_nulo(esquema):
        """anyOf [X, null] -> (X, admite_nulo)."""
        opciones = esquema.get('anyOf') or esquema.get('oneOf')
        if not opciones:
            return esquema, False
        no_nulas = [o for o in opciones if o.get('type') != 'null']
        nulo = len(no_nulas) < len(opciones)
        numericas = [o for o in no_nulas if o.get('type') in ('number', 'integer')]
        if len(no_nulas) > 1 and numericas:
            no_nulas = numericas[:1]  # Decimal: Pydantic acepta número o texto; el contrato es numérico
        if len(no_nulas) == 1:
            return {**{k: v for k, v in esquema.items() if k not in ('anyOf', 'oneOf')}, **no_nulas[0]}, nulo
        return {'type': 'string'}, nulo  # unión de varios tipos: se trata como texto

    def _elemento(self, nombre, esquema, minimo):
        esquema, _ = self._sin_nulo(esquema)
        ocurrencias = f' minOccurs="{minimo}"'
        if '$ref' in esquema:
            return f'<xs:element name="{nombre}" type="{esquema["$ref"].split("/")[-1]}"{ocurrencias}/>'
        if esquema.get('type') == 'array':
            hijo = SINGULARES.get(nombre, 'item')
            maximo = esquema.get('maxItems', 'unbounded')
            interior = self._elemento(hijo, esquema.get('items', {}), esquema.get('minItems', 0)).replace(
                f'<xs:element name="{hijo}"', f'<xs:element name="{hijo}" maxOccurs="{maximo}"', 1)
            return (f'<xs:element name="{nombre}"{ocurrencias}><xs:complexType><xs:sequence>{interior}'
                    f'</xs:sequence></xs:complexType></xs:element>')
        if esquema.get('type') == 'object' or (not esquema.get('type') and 'properties' not in esquema
                                                and not any(k in esquema for k in ('enum', 'const'))):
            return (f'<xs:element name="{nombre}"{ocurrencias}><xs:complexType mixed="true"><xs:sequence>'
                    '<xs:any processContents="lax" minOccurs="0" maxOccurs="unbounded"/>'
                    '</xs:sequence></xs:complexType></xs:element>')
        tipo, anonimo = self._simple(esquema)
        if anonimo:
            return f'<xs:element name="{nombre}"{ocurrencias}>{anonimo}</xs:element>'
        return f'<xs:element name="{nombre}" type="{tipo}"{ocurrencias}/>'

    def _complejo(self, nombre, esquema):
        requeridos = set(esquema.get('required', []))
        hijos = []
        for campo, sub in esquema.get('properties', {}).items():
            _, nulo = self._sin_nulo(sub)
            hijos.append(self._elemento(campo, sub, 1 if campo in requeridos and not nulo else 0))
        documentacion = esquema.get('description', '').strip()
        doc = f'<xs:annotation><xs:documentation>{escape(documentacion)}</xs:documentation></xs:annotation>' \
            if documentacion else ''
        return f'  <xs:complexType name="{nombre}">{doc}<xs:all>{"".join(hijos)}</xs:all></xs:complexType>'

    def xsd(self, servicio):
        raices = '\n'.join(f'  <xs:element name="{r}" type="{t}"/>' for r, t in sorted(self.raices.items()))
        tipos = '\n'.join(self._complejo(n, e) for n, e in sorted(self.defs.items()))
        return (
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"\n'
            f'           targetNamespace="{NS}" xmlns="{NS}" elementFormDefault="qualified" version="1.0">\n'
            f'  <xs:annotation><xs:documentation>Contratos XML v1 de ms-{servicio} (AbastoRed). '
            'Codificación UTF-8. Los campos opcionales se omiten cuando no tienen valor.</xs:documentation>'
            '</xs:annotation>\n'
            '  <!-- Elementos raíz: uno por petición o respuesta -->\n'
            f'{raices}\n  <!-- Tipos -->\n{tipos}\n</xs:schema>\n'
        )


def generar_xsd(servicio, contratos):
    """XSD del servicio, con sangría, listo para guardarse."""
    crudo = _Generador(contratos).xsd(servicio)
    documento = etree.fromstring(crudo.encode('utf-8'), etree.XMLParser(remove_blank_text=True))
    return ('<?xml version="1.0" encoding="UTF-8"?>' + chr(10)
            + f'<!-- Generado con: python -m abasto_api.contratos apps/microservicios/{servicio} -->' + chr(10)
            + etree.tostring(documento, pretty_print=True, encoding='unicode'))


def cargar_contratos(directorio):
    ruta = Path(directorio) / 'esquemas.py'
    spec = importlib.util.spec_from_file_location(f'esquemas_{Path(directorio).name}', ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(directorio)))
    spec.loader.exec_module(modulo)
    return modulo.CONTRATOS_XML


def main(directorio):
    directorio = Path(directorio)
    servicio = directorio.name
    contenido = generar_xsd(servicio, cargar_contratos(directorio))
    destino = directorio / 'xsd' / f'{servicio}.xsd'
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(contenido, encoding='utf-8')
    print(f'{destino}: {contenido.count("<xs:element name=") } elementos')


if __name__ == '__main__':
    for d in sys.argv[1:]:
        main(d)
