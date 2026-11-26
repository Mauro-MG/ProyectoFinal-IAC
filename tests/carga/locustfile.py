"""
Escenarios de carga de AbastoRed (Locust).

Corre en un contenedor dentro de la red interna «publica» y habla directo con cada servicio
(http://ms-<servicio>:8000) y con el web (http://abastored-web:5000). Ver tests/carga/README.md y
tests/carga/correr.sh. No pasa por el gateway: el gateway limita a 30 peticiones/s por IP, y todos los
usuarios virtuales salen de la misma IP; ese límite se prueba aparte (tests/integracion/test_seguridad.py).
Los demás controles siguen activos: JWT + sesión en Redis en cada petición, permisos por rol y el límite de
120 peticiones/min por usuario y servicio (cada usuario virtual tiene su propia cuenta).

Perfiles (peso = proporción de usuarios virtuales):
  ComercianteMovil (6)   JSON como la app Android: inventario, contador de avisos, ventas, recomendaciones,
                         pedidos y registro de ventas (escribe).
  AnalistaEscritorio (2) XML como la app de escritorio: cobertura, brechas, agrupamientos, comparación de
                         precios, pronóstico de demanda y lista de reportes.
  VisitantePublico (3)   Páginas públicas del web, búsqueda y disponibilidad sin cuenta.
  Auditor (1)            Bitácora de auditoría y resumen.
"""
import itertools
import json
import os
import random
import uuid

from locust import HttpUser, between, events, tag, task

SESIONES = json.load(open(os.environ.get('SESIONES', '/mnt/locust/resultados/sesiones.json'), encoding='utf-8'))
_comerciantes = itertools.cycle(SESIONES['comerciantes'])
_analistas = itertools.cycle(SESIONES['analistas'])
_auditores = itertools.cycle(SESIONES['auditores'])
PRODUCTOS = list(range(1, 29))
XML = {'Accept': 'application/xml'}


def api(servicio, ruta):
    return f'http://ms-{servicio}:8000/api/v1{ruta}'


class ConToken(HttpUser):
    abstract = True
    host = 'http://ms-seguridad:8000'
    fuente = None

    def on_start(self):
        self.client.headers['Authorization'] = 'Bearer ' + next(self.fuente)['token']

    def pedir(self, metodo, servicio, ruta, nombre=None, **kw):
        with self.client.request(metodo, api(servicio, ruta), name=nombre or f'{servicio} {ruta}', catch_response=True,
                                 **kw) as r:
            if r.status_code >= 400:
                r.failure(f'{r.status_code} {r.text[:120]}')
            return r


class ComercianteMovil(ConToken):
    weight = 6
    wait_time = between(1, 4)
    fuente = _comerciantes

    def on_start(self):
        super().on_start()
        r = self.pedir('GET', 'comercios', '/comercios', 'comercios GET /comercios')
        self.comercio = r.json()['items'][0]['id'] if r.ok and r.json().get('items') else None
        self.inventario = []

    @task(4)
    def inventario(self):
        if self.comercio:
            r = self.pedir('GET', 'inventario', f'/comercios/{self.comercio}/inventario',
                           'inventario GET /comercios/{id}/inventario')
            if r.ok:
                self.inventario = [i for i in r.json().get('renglones', []) if float(i.get('existencia') or 0) >= 1]

    @task(3)
    def avisos(self):
        self.pedir('GET', 'notificaciones', '/notificaciones/contador')

    @task(1)
    def resumen_ventas(self):
        if self.comercio:
            self.pedir('GET', 'ventas', f'/ventas/resumen?comercio_id={self.comercio}&dias=30',
                       'ventas GET /ventas/resumen')

    @task(1)
    def mas_vendidos(self):
        if self.comercio:
            self.pedir('GET', 'ventas', f'/ventas/productos?comercio_id={self.comercio}&dias=90',
                       'ventas GET /ventas/productos')

    @task(1)
    def recomendaciones(self):
        if self.comercio:
            self.pedir('GET', 'recomendaciones', f'/recomendaciones/{self.comercio}',
                       'recomendaciones GET /recomendaciones/{id}')

    @task(1)
    def pedidos(self):
        self.pedir('GET', 'pedidos', '/pedidos?por_pagina=20', 'pedidos GET /pedidos')

    @tag('escritura')
    @task(1)
    def vender(self):
        if self.comercio and self.inventario:
            renglon = random.choice(self.inventario)
            self.pedir('POST', 'ventas', '/ventas', 'ventas POST /ventas', json={
                'comercio_id': self.comercio, 'origen': 'android', 'id_cliente': uuid.uuid4().hex,
                'partidas': [{'inventario_id': renglon['id'], 'cantidad': 1}]})


class AnalistaEscritorio(ConToken):
    weight = 2
    wait_time = between(2, 6)
    fuente = _analistas

    @task(3)
    def cobertura(self):
        self.pedir('GET', 'analisis', '/analisis/zonas', 'analisis GET /analisis/zonas [xml]', headers=XML)

    @task(2)
    def brechas(self):
        self.pedir('GET', 'analisis', '/analisis/brechas?canasta_basica=true', 'analisis GET /analisis/brechas [xml]',
                   headers=XML)

    @task(1)
    def agrupamientos(self):
        self.pedir('GET', 'analisis', '/analisis/agrupamientos?radio_m=400&minimo=4',
                   'analisis GET /analisis/agrupamientos [xml]', headers=XML)

    @task(2)
    def comparacion(self):
        self.pedir('GET', 'precios', f'/precios/comparacion?producto_id={random.choice(PRODUCTOS)}',
                   'precios GET /precios/comparacion [xml]', headers=XML)

    @task(1)
    def pronostico(self):
        self.pedir('GET', 'demanda', f'/demanda/estimacion?producto_id={random.choice(PRODUCTOS)}',
                   'demanda GET /demanda/estimacion [xml]', headers=XML)

    @task(1)
    def reportes(self):
        self.pedir('GET', 'reportes', '/reportes', 'reportes GET /reportes [xml]', headers=XML)


class VisitantePublico(HttpUser):
    weight = 3
    wait_time = between(1, 3)
    host = 'http://abastored-web:5000'

    def _get(self, url, nombre):
        with self.client.get(url, name=nombre, catch_response=True) as r:
            if r.status_code >= 400:
                r.failure(str(r.status_code))

    @task(3)
    def inicio(self):
        self._get('/', 'web GET /')

    @task(2)
    def disponibilidad(self):
        self._get('/disponibilidad', 'web GET /disponibilidad')

    @task(2)
    def buscar(self):
        self._get(api('busqueda', f'/buscar?q={random.choice(["arroz", "frijol", "leche", "huevo", "tortilla"])}'),
                  'busqueda GET /buscar')

    @task(2)
    def disponibilidad_api(self):
        self._get(api('disponibilidad', f'/disponibilidad?producto_id={random.choice(PRODUCTOS)}'),
                  'disponibilidad GET /disponibilidad')


class Auditor(ConToken):
    weight = 1
    wait_time = between(2, 5)
    fuente = _auditores

    @task(2)
    def eventos(self):
        self.pedir('GET', 'auditoria', '/eventos?por_pagina=50', 'auditoria GET /eventos')

    @task(1)
    def resumen(self):
        self.pedir('GET', 'auditoria', '/resumen', 'auditoria GET /resumen')


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument('--etiqueta-corrida', default='carga', help='Nombre de la corrida en los resultados')
