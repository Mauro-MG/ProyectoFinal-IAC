"""
Cliente de los microservicios para la aplicación de escritorio.

  * Todo pasa por el gateway HTTPS (https://<host>/ms/<servicio>/api/v1/...),
    verificando su certificado (el autofirmado del proyecto, infra/certs).
  * Solo XML: cada petición lleva Content-Type y Accept application/xml, se
    valida contra el XSD antes de enviarse y la respuesta se valida al llegar.
  * Sesión: el JWT del login viaja en Authorization. Si el servicio responde
    401 por token vencido, se renueva una vez con el refresh token
    (POST /auth/renovar) y se repite la petición.
  * Cada petición lleva su X-Correlation-ID: la bitácora local lo guarda para
    poder buscar la operación en ms-auditoria (GET /trazas/{id}).
"""
import base64
import json
import threading
from uuid import uuid4

import requests
from lxml import etree

from abastored_escritorio import configuracion
from abastored_escritorio.contratos import Contrato, ContratoInvalido

XML = 'application/xml'


class ErrorServicio(Exception):
    """Respuesta de error del servicio (sobre <error> del contrato) o servicio inalcanzable."""

    def __init__(self, status, codigo, mensaje, servicio=None, correlation_id=None, detalles=None):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje = status, codigo, mensaje
        self.servicio, self.correlation_id, self.detalles = servicio, correlation_id, detalles or []

    def __str__(self):
        extra = ''.join(f"\n  · {d.get('campo', '')}: {d.get('mensaje', '')}" for d in self.detalles
                        if isinstance(d, dict))
        return f'{self.mensaje}{extra}'


class Respuesta:
    def __init__(self, datos, status, correlation_id, contenido=None, tipo=None):
        self.datos, self.status, self.correlation_id = datos, status, correlation_id
        self.contenido, self.tipo = contenido, tipo


class Cliente:
    def __init__(self, gateway=None, certificado=None, al_registrar=None):
        self.gateway = (gateway or configuracion.GATEWAY).rstrip('/')
        self.http = requests.Session()
        self.http.verify = str(certificado or configuracion.certificado())
        self.http.headers['User-Agent'] = 'AbastoRed-Escritorio/1.0'
        self.contratos = {}
        self.tokens = None
        self.usuario = None
        self._candado = threading.Lock()
        # Callback (metodo, servicio, ruta, status, correlation_id) para la bitácora local
        self.al_registrar = al_registrar

    # ------------------------------------------------------------ contratos
    def contrato(self, servicio):
        with self._candado:
            if servicio not in self.contratos:
                try:
                    r = self.http.get(f'{self.gateway}/ms/{servicio}/xsd', timeout=configuracion.TIEMPO_ESPERA)
                except requests.RequestException as error:
                    raise ErrorServicio(503, 'sin_conexion', f'No se pudo descargar el contrato de ms-{servicio}: '
                                                             f'{error.__class__.__name__}.', servicio)
                if r.status_code != 200:
                    raise ErrorServicio(r.status_code, 'sin_contrato', f'ms-{servicio} no publicó su XSD.', servicio)
                self.contratos[servicio] = Contrato.desde_xsd(servicio, r.content)
            return self.contratos[servicio]

    # ------------------------------------------------------------ sesión
    @property
    def permisos(self):
        return set((self.usuario or {}).get('permisos') or [])

    def puede(self, *permisos):
        return bool(self.permisos & set(permisos))

    def iniciar_sesion(self, email, password):
        r = self.peticion('seguridad', 'POST', '/auth/login', raiz='login', autenticado=False,
                          datos={'email': email, 'password': password, 'origen': 'escritorio'})
        self.tokens = r.datos
        self.usuario = r.datos['usuario']
        return self.usuario

    def cerrar_sesion(self):
        if self.tokens:
            try:
                self.peticion('seguridad', 'POST', '/auth/logout')
            except ErrorServicio:
                pass
        self.tokens = self.usuario = None

    def _renovar(self):
        refresh = (self.tokens or {}).get('refresh_token')
        if not refresh:
            return False
        try:
            r = self.peticion('seguridad', 'POST', '/auth/renovar', raiz='renovar', autenticado=False,
                              datos={'refresh_token': refresh}, reintentar=False)
        except ErrorServicio:
            return False
        self.tokens.update(r.datos)
        return True

    def segundos_restantes(self):
        """Vigencia del token según su propio contenido (exp), sin llamar al servidor."""
        try:
            carga = self.tokens['access_token'].split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(carga + '=' * (-len(carga) % 4)))
            import time
            return int(claims['exp'] - time.time())
        except (TypeError, KeyError, ValueError, IndexError):
            return 0

    # ------------------------------------------------------------ peticiones
    def get(self, servicio, ruta, **params):
        return self.peticion(servicio, 'GET', ruta, params={k: v for k, v in params.items() if v not in (None, '')})

    def peticion(self, servicio, metodo, ruta, raiz=None, datos=None, params=None, files=None, form=None,
                 autenticado=True, reintentar=True, binario=False):
        contrato = self.contrato(servicio)
        correlation_id = f'escritorio-{uuid4().hex[:20]}'
        headers = {'Accept': XML if not binario else '*/*', 'X-Correlation-ID': correlation_id}
        if autenticado and self.tokens:
            headers['Authorization'] = f"Bearer {self.tokens['access_token']}"
        cuerpo = None
        if raiz is not None:
            cuerpo = etree.tostring(contrato.a_xml(raiz, datos or {}), xml_declaration=True, encoding='UTF-8')
            headers['Content-Type'] = XML
        try:
            r = self.http.request(metodo, f'{self.gateway}/ms/{servicio}/api/v1{ruta}', headers=headers,
                                  params=params, data=cuerpo if cuerpo is not None else form, files=files,
                                  timeout=configuracion.TIEMPO_ESPERA)
        except requests.RequestException as error:
            raise ErrorServicio(503, 'sin_conexion', f'ms-{servicio} no respondió ({error.__class__.__name__}). '
                                                     'Revisa tu conexión o que el sistema esté levantado.', servicio)
        if self.al_registrar:
            self.al_registrar(metodo, servicio, ruta, r.status_code, r.headers.get('X-Correlation-ID', correlation_id))

        if r.status_code == 401 and autenticado and reintentar and self._renovar():
            return self.peticion(servicio, metodo, ruta, raiz, datos, params, files, form, autenticado, False, binario)

        tipo = r.headers.get('Content-Type', '')
        if r.ok and binario and not tipo.startswith(XML):
            return Respuesta(None, r.status_code, r.headers.get('X-Correlation-ID'), r.content, tipo)
        if not tipo.startswith(XML):
            raise ErrorServicio(r.status_code, 'respuesta_no_xml',
                                f'ms-{servicio} respondió {r.status_code} sin XML ({tipo or "sin tipo"}).', servicio)
        documento = etree.fromstring(r.content)
        contrato.validar(documento)   # también las respuestas de error cumplen el contrato <error>
        datos_respuesta = contrato.a_datos(documento)
        if not r.ok:
            raise ErrorServicio(r.status_code, datos_respuesta.get('codigo'), datos_respuesta.get('mensaje'), servicio,
                                datos_respuesta.get('correlation_id'), datos_respuesta.get('detalles') or [])
        return Respuesta(datos_respuesta, r.status_code, r.headers.get('X-Correlation-ID'))


__all__ = ['Cliente', 'ErrorServicio', 'ContratoInvalido', 'Respuesta']
