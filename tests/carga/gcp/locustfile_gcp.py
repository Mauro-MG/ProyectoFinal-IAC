"""
Escenarios de carga contra el DESPLIEGUE (Google Cloud): todo entra por la URL pública HTTPS y pasa por NGINX.

    Lo corre tests/carga/gcp/correr_gcp.sh (ver tests/carga/gcp/README.md).

Diferencias con tests/carga/locustfile.py (local, sin gateway):
  - Cada petición va a  <ABASTO_HOST>/ms/<servicio>/api/v1/...  o al web  <ABASTO_HOST>/...  (no a
    http://ms-<servicio>:8000 dentro de Docker).
  - TLS verificado contra el certificado público del gateway desplegado (ABASTO_CA). No se usa verify=False.
  - Cuentas y comercios exclusivos de la corrida (prefijo), preparados con preparar_cuentas_vm.py y
    preparar_datos.py. Un usuario virtual = una cuenta; no se comparte una cuenta entre todos.
  - Cada respuesta se clasifica: ok, 429 del gateway (X-Limitado-Por: gateway), 429 del servicio
    (X-RateLimit-Limit), 409 de negocio, 401/403, otros 4xx, 5xx, timeout y error de conexión.
    Además de las estadísticas de Locust (que mezclan éxitos y fallas en los percentiles) se guardan
    latencias SOLO de las respuestas exitosas.
  - Forma de carga por etapas (ETAPAS) con condiciones de parada automáticas (guardia) y una fase de
    recuperación (RECUPERACION) al terminar o al dispararse una condición.

Locust simula las PETICIONES de cada cliente (Android: JSON; escritorio: XML; navegador: páginas del web).
No mide el renderizado de las interfaces.

Perfiles (peso = proporción de usuarios virtuales), los mismos que en local:
  ComercianteMovil (6)   JSON: inventario, precios, avisos, ventas, recomendaciones, pedidos y una venta.
  AnalistaEscritorio (2) XML: cobertura, brechas, agrupamientos, comparación de precios, pronóstico, reportes.
  VisitantePublico (3)   Páginas públicas del web, búsqueda y disponibilidad sin cuenta.
  Auditor (1)            Bitácora, resumen y traza de una operación (correlation_id).
"""
import collections
import csv
import itertools
import json
import os
import random
import threading
import time
import uuid
from pathlib import Path

import gevent
import psutil
import requests
from locust import HttpUser, LoadTestShape, between, events, task

from comun import CA, CATEGORIAS, HOST, clasificar, leer_sesiones, ruta

PREFIJO = os.environ['PREFIJO']
DESTINO = Path(os.environ['DESTINO'])
SESIONES = leer_sesiones(PREFIJO)
PRODUCTOS = list(range(1, 29))
XML = {'Accept': 'application/xml'}
TIMEOUT = float(os.environ.get('TIMEOUT_S', 30))

# ---------------------------------------------------------------- umbrales y condiciones de parada
UMBRAL_ERRORES = float(os.environ.get('UMBRAL_ERRORES', 0.05))      # 5xx + timeout + conexión / total
UMBRAL_P95_MS = float(os.environ.get('UMBRAL_P95_MS', 3000))       # p95 de respuestas exitosas
VENTANA_S = 30
MEM_MIN_MB = int(os.environ.get('MEM_MIN_MB', 1500))               # memoria disponible mínima en la VM
DISCO_MIN_GB = int(os.environ.get('DISCO_MIN_GB', 5))
MUESTRAS_VM = DESTINO / 'muestras_vm.csv'


def _etapas(texto):
    """'10:180,25:180,125?:180' -> [(10, 180, False), ...]; '?' = solo si la etapa anterior fue sana."""
    salida = []
    for parte in filter(None, (texto or '').split(',')):
        usuarios, segundos = parte.split(':')
        salida.append((int(usuarios.rstrip('?')), int(segundos), usuarios.endswith('?')))
    return salida


ETAPAS = _etapas(os.environ.get('ETAPAS', '3:120'))
RECUPERACION = _etapas(os.environ.get('RECUPERACION', ''))
TASA = float(os.environ.get('TASA', 2))
MAX_USUARIOS = int(os.environ.get('MAX_USUARIOS', 150))
assert all(u <= MAX_USUARIOS for u, _, _ in ETAPAS + RECUPERACION), 'una etapa supera MAX_USUARIOS'

# ---------------------------------------------------------------- registro propio de cada respuesta
REGISTRO = collections.deque()           # (t, categoria, ms, nombre) de la ventana reciente
TODO = []                                # (t, categoria, ms, nombre) de toda la corrida
CANDADO = threading.Lock()
ESTADO = {'parar': None, 'fase': 'carga', 'etapa': None, 'eventos': []}
VENTAS = []                              # (t, id_cliente, comercio, inventario_id, status, intento)
CUENTAS_REPETIDAS = collections.Counter()


def evento(texto):
    ESTADO['eventos'].append((time.strftime('%H:%M:%S'), round(time.time(), 1), texto))
    print(f'[guardia] {texto}', flush=True)


@events.request.add_listener
def _registrar(request_type, name, response_time, response_length, response=None, exception=None, **kw):
    status = getattr(response, 'status_code', 0) or 0
    categoria = clasificar(status, getattr(response, 'headers', None), exception if not status else None)
    if categoria == 'ok' and exception is not None:
        categoria = 'falla_contrato'          # 2xx pero con otro formato del pedido (p. ej. JSON en vez de XML)
    fila = (time.time(), categoria, response_time, f'{request_type} {name}')
    with CANDADO:
        REGISTRO.append(fila)
        TODO.append(fila)


def _cuentas(clave):
    contador = itertools.count()
    lista = SESIONES[clave]

    def siguiente():
        i = next(contador)
        if i >= len(lista):
            CUENTAS_REPETIDAS[clave] += 1
        return lista[i % len(lista)]
    return siguiente


_comerciante, _analista, _auditor = _cuentas('com'), _cuentas('ana'), _cuentas('aud')


class Base(HttpUser):
    abstract = True
    host = HOST
    cuenta = None

    def on_start(self):
        self.client.verify = CA
        if self.cuenta:
            self.datos = self.cuenta()
            self.client.headers['Authorization'] = 'Bearer ' + self.datos['token']

    def pedir(self, metodo, servicio, camino, nombre, xml=False, **kw):
        kw.setdefault('timeout', TIMEOUT)
        if xml:
            kw['headers'] = {**kw.get('headers', {}), **XML}
        with self.client.request(metodo, ruta(servicio, camino), name=nombre, catch_response=True, **kw) as r:
            if not r.status_code:
                r.failure(f'0 {type(r.error).__name__}: {str(r.error)[:120]}')
            elif r.status_code >= 400:
                r.failure(f'{r.status_code} {(r.text or "")[:120]}')
            elif xml and 'xml' not in r.headers.get('Content-Type', ''):
                r.failure(f'contrato: se pidió XML y llegó {r.headers.get("Content-Type")}')
            return r


class ComercianteMovil(Base):
    weight = 6
    wait_time = between(1, 4)
    cuenta = staticmethod(_comerciante)

    def on_start(self):
        super().on_start()
        self.comercio = self.datos['comercio']
        self.renglones = self.datos['renglones']
        self.pedir('GET', 'comercios', '/comercios', 'comercios GET /comercios')

    @task(4)
    def inventario(self):
        self.pedir('GET', 'inventario', f'/comercios/{self.comercio}/inventario',
                   'inventario GET /comercios/{id}/inventario')

    @task(3)
    def avisos(self):
        self.pedir('GET', 'notificaciones', '/notificaciones/contador', 'notificaciones GET /notificaciones/contador')

    @task(1)
    def precios(self):
        self.pedir('GET', 'precios', f'/precios/comparacion?producto_id={random.choice(self.renglones)["producto_id"]}',
                   'precios GET /precios/comparacion')

    @task(1)
    def resumen_ventas(self):
        self.pedir('GET', 'ventas', f'/ventas/resumen?comercio_id={self.comercio}&dias=30',
                   'ventas GET /ventas/resumen')

    @task(1)
    def recomendaciones(self):
        self.pedir('GET', 'recomendaciones', f'/recomendaciones/{self.comercio}',
                   'recomendaciones GET /recomendaciones/{id}')

    @task(1)
    def pedidos(self):
        self.pedir('GET', 'pedidos', '/pedidos?por_pagina=20', 'pedidos GET /pedidos')

    @task(1)
    def vender(self):
        """Una venta de 1 unidad con id_cliente propio. Si falla por red, timeout o 502-504, se reintenta UNA vez
        con el MISMO id_cliente, como la app Android: el servidor debe responder la venta original (duplicada)."""
        renglon = random.choice(self.renglones)
        partida = {'inventario_id': renglon['id'], 'cantidad': 1}
        if not renglon.get('precio'):
            partida['precio_unitario'] = 20
        cuerpo = {'comercio_id': self.comercio, 'origen': 'android', 'id_cliente': uuid.uuid4().hex,
                  'partidas': [partida]}
        for intento in (1, 2):
            r = self.pedir('POST', 'ventas', '/ventas', 'ventas POST /ventas' + (' (reintento)' if intento > 1 else ''),
                           json=cuerpo)
            VENTAS.append((round(time.time(), 3), cuerpo['id_cliente'], self.comercio, renglon['id'], r.status_code,
                           intento, bool(r.status_code == 200 and r.json().get('duplicada'))))
            if r.status_code and r.status_code not in (502, 503, 504):
                break


class AnalistaEscritorio(Base):
    weight = 2
    wait_time = between(2, 6)
    cuenta = staticmethod(_analista)

    @task(3)
    def cobertura(self):
        self.pedir('GET', 'analisis', '/analisis/zonas', 'analisis GET /analisis/zonas [xml]', xml=True)

    @task(2)
    def brechas(self):
        self.pedir('GET', 'analisis', '/analisis/brechas?canasta_basica=true', 'analisis GET /analisis/brechas [xml]',
                   xml=True)

    @task(1)
    def agrupamientos(self):
        self.pedir('GET', 'analisis', '/analisis/agrupamientos?radio_m=400&minimo=4',
                   'analisis GET /analisis/agrupamientos [xml]', xml=True)

    @task(2)
    def comparacion(self):
        self.pedir('GET', 'precios', f'/precios/comparacion?producto_id={random.choice(PRODUCTOS)}',
                   'precios GET /precios/comparacion [xml]', xml=True)

    @task(1)
    def pronostico(self):
        self.pedir('GET', 'demanda', f'/demanda/estimacion?producto_id={random.choice(PRODUCTOS)}',
                   'demanda GET /demanda/estimacion [xml]', xml=True)

    @task(1)
    def reportes(self):
        self.pedir('GET', 'reportes', '/reportes', 'reportes GET /reportes [xml]', xml=True)


class VisitantePublico(Base):
    weight = 3
    wait_time = between(1, 3)

    def _web(self, camino, nombre):
        with self.client.get(camino, name=nombre, catch_response=True, timeout=TIMEOUT) as r:
            if not r.status_code:
                r.failure(f'0 {type(r.error).__name__}: {str(r.error)[:120]}')
            elif r.status_code >= 400:
                r.failure(str(r.status_code))

    @task(3)
    def inicio(self):
        self._web('/', 'web GET /')

    @task(2)
    def disponibilidad_web(self):
        self._web('/disponibilidad', 'web GET /disponibilidad')

    @task(2)
    def buscar(self):
        self.pedir('GET', 'busqueda', f'/buscar?q={random.choice(["arroz", "frijol", "leche", "huevo", "tortilla"])}',
                   'busqueda GET /buscar')

    @task(2)
    def disponibilidad_api(self):
        self.pedir('GET', 'disponibilidad', f'/disponibilidad?producto_id={random.choice(PRODUCTOS)}',
                   'disponibilidad GET /disponibilidad')


class Auditor(Base):
    weight = 1
    wait_time = between(2, 5)
    cuenta = staticmethod(_auditor)
    correlacion = None

    @task(2)
    def eventos(self):
        r = self.pedir('GET', 'auditoria', '/eventos?por_pagina=50', 'auditoria GET /eventos')
        if r.ok:
            ids = [e.get('correlation_id') for e in r.json().get('eventos', []) if e.get('correlation_id')]
            self.correlacion = random.choice(ids) if ids else self.correlacion

    @task(1)
    def resumen(self):
        self.pedir('GET', 'auditoria', '/resumen', 'auditoria GET /resumen')

    @task(1)
    def traza(self):
        if self.correlacion:
            self.pedir('GET', 'auditoria', f'/trazas/{self.correlacion}', 'auditoria GET /trazas/{correlation_id}')


# ---------------------------------------------------------------- forma de la carga
class Etapas(LoadTestShape):
    """Etapas en orden; una etapa con '?' solo se ejecuta si la anterior fue sana. Al terminar, o si la guardia
    dispara una condición de parada, pasa a RECUPERACION (carga baja) y después termina."""

    def __init__(self):
        super().__init__()
        self.plan = list(ETAPAS)
        self.indice = 0
        self.inicio_etapa = 0
        self.en_recuperacion = False

    def tick(self):
        t = self.get_run_time()
        if self.indice == 0 and ESTADO['etapa'] is None:
            self._iniciar(0, t)
        usuarios, segundos, _ = self.plan[self.indice]
        if ESTADO['parar'] and not self.en_recuperacion:
            return self._a_recuperacion(t, ESTADO['parar'])
        if t - self.inicio_etapa >= segundos:
            if self.indice + 1 >= len(self.plan):
                return self._a_recuperacion(t, 'fin de las etapas') if not self.en_recuperacion else None
            siguiente = self.plan[self.indice + 1]
            if siguiente[2] and not self.en_recuperacion:
                sana, motivo = etapa_sana(segundos)
                if not sana:
                    return self._a_recuperacion(t, f'no se escala a {siguiente[0]} usuarios: {motivo}')
            self._iniciar(self.indice + 1, t)
            usuarios = self.plan[self.indice][0]
        return usuarios, TASA

    def _iniciar(self, i, t):
        self.indice, self.inicio_etapa = i, t
        u, s, _ = self.plan[i]
        ESTADO['etapa'] = f'{"recuperacion" if self.en_recuperacion else "carga"} {u} usuarios'
        evento(f'etapa {ESTADO["etapa"]} durante {s} s')

    def _a_recuperacion(self, t, motivo):
        evento(f'fin de la fase de carga: {motivo}')
        if not RECUPERACION:
            return None
        self.en_recuperacion = True
        ESTADO['fase'] = 'recuperacion'
        self.plan = list(RECUPERACION)
        self._iniciar(0, t)
        return self.plan[0][0], max(TASA, 10)


def _ventana(segundos):
    limite = time.time() - segundos
    with CANDADO:
        return [f for f in TODO[-20000:] if f[0] >= limite]


def _p(valores, q):
    if not valores:
        return None
    valores = sorted(valores)
    return valores[min(len(valores) - 1, int(round(q / 100 * (len(valores) - 1))))]


def etapa_sana(segundos):
    """¿Se puede escalar? Revisa la etapa que termina (sin sus primeros 30 s) y la VM."""
    filas = _ventana(max(segundos - 30, 30))
    total = len(filas) or 1
    graves = sum(1 for f in filas if f[1] in ('5xx', 'timeout', 'conexion'))
    p95 = _p([f[2] for f in filas if f[1] == 'ok'], 95) or 0
    cpu = _cpu_vm(60)
    if graves / total > 0.01:
        return False, f'{graves / total:.1%} de 5xx/timeouts/conexión'
    if p95 > UMBRAL_P95_MS / 2:
        return False, f'p95 de éxitos {p95:.0f} ms'
    if cpu is not None and cpu > 75:
        return False, f'CPU de la VM {cpu:.0f} %'
    return True, ''


def _muestras_vm(segundos):
    """Líneas VM,<t>,<mem_disp_mb>,<disco_gb>,<carga1>,<us>,<sy>,<id>,<wa>,<st> recientes."""
    try:
        lineas = MUESTRAS_VM.read_text(encoding='utf-8', errors='ignore').splitlines()[-400:]
    except OSError:
        return []
    limite = time.time() - segundos
    salida = []
    for linea in lineas:
        partes = linea.strip().split(',')
        if partes[0] == 'VM' and len(partes) >= 10:
            try:
                valores = [float(x) for x in partes[1:10]]
            except ValueError:
                continue
            if valores[0] >= limite:
                salida.append(valores)
    return salida


def _cpu_vm(segundos):
    m = _muestras_vm(segundos)
    return sum(100 - v[6] for v in m) / len(m) if m else None


def guardia(entorno):
    """Revisa cada 5 s las condiciones de parada y guarda la línea de tiempo por categoría (10 s)."""
    linea = open(DESTINO / 'linea_tiempo.csv', 'w', newline='', encoding='utf-8')
    escritor = csv.writer(linea)
    escritor.writerow(['hora', 't', 'fase', 'usuarios', 'peticiones', 'rps', *CATEGORIAS, 'p50_ok_ms', 'p95_ok_ms',
                       'p99_ok_ms', 'cpu_vm_pct', 'mem_disp_vm_mb', 'cpu_generador_pct', 'servicios_ok',
                       'servicios_degradados', 'servicios_caidos'])
    estado_http = requests.Session()
    estado_http.verify = CA
    errores_seguidos = lentos_desde = None
    ultimo_estado = (None, None, None)
    psutil.cpu_percent()
    vueltas = 0
    while True:
        gevent.sleep(5)
        vueltas += 1
        ahora = time.time()
        usuarios = entorno.runner.user_count if entorno.runner else 0
        with CANDADO:
            while REGISTRO and REGISTRO[0][0] < ahora - VENTANA_S:
                REGISTRO.popleft()
            ventana = list(REGISTRO)
        total = len(ventana)
        graves = sum(1 for f in ventana if f[1] in ('5xx', 'timeout', 'conexion'))
        exitos = [f[2] for f in ventana if f[1] == 'ok']
        p95 = _p(exitos, 95)
        vm = _muestras_vm(15)
        mem = vm[-1][1] if vm else None
        disco = vm[-1][2] if vm else None
        if vueltas % 3 == 0:            # estado de los 24 servicios cada 15 s (no cuenta en las estadísticas)
            try:
                e = estado_http.get(HOST + ruta('monitoreo', '/estado/publico'), timeout=10).json()
                ultimo_estado = (e['ok'], e['degradados'], e['caidos'])
            except (requests.RequestException, ValueError, KeyError) as error:
                ultimo_estado = (None, None, f'sin respuesta: {type(error).__name__}')
        if vueltas % 2 == 0:            # línea de tiempo cada 10 s con lo ocurrido en los últimos 10 s
            ult = [f for f in ventana if f[0] >= ahora - 10]
            cuenta = collections.Counter(f[1] for f in ult)
            ok10 = [f[2] for f in ult if f[1] == 'ok']
            escritor.writerow([time.strftime('%H:%M:%S'), round(ahora, 1), ESTADO['fase'], usuarios, len(ult),
                               round(len(ult) / 10, 2), *[cuenta.get(c, 0) for c in CATEGORIAS],
                               _p(ok10, 50), _p(ok10, 95), _p(ok10, 99),
                               round(_cpu_vm(10), 1) if _cpu_vm(10) is not None else '', mem or '',
                               psutil.cpu_percent(), *ultimo_estado])
            linea.flush()
        if ESTADO['parar']:
            continue
        motivo = None
        if total >= 20 and graves / total > UMBRAL_ERRORES:
            errores_seguidos = (errores_seguidos or 0) + 1
            if errores_seguidos >= 6:          # 30 s sostenidos (6 revisiones de 5 s)
                motivo = f'{graves / total:.1%} de 5xx/timeouts/conexión sostenido 30 s'
        else:
            errores_seguidos = 0
        if p95 and p95 > UMBRAL_P95_MS:
            lentos_desde = lentos_desde or ahora
            if ahora - lentos_desde >= 60:
                motivo = f'p95 de respuestas exitosas {p95:.0f} ms > {UMBRAL_P95_MS:.0f} ms durante 60 s'
        else:
            lentos_desde = None
        if usuarios and total == 0 and entorno.runner and entorno.runner.state == 'running' and \
                ahora - ESTADO.get('arranque', ahora) > 30:
            motivo = 'sin respuestas durante 30 s'
        if mem is not None and mem < MEM_MIN_MB:
            motivo = f'memoria disponible en la VM {mem:.0f} MB < {MEM_MIN_MB} MB'
        if disco is not None and disco < DISCO_MIN_GB:
            motivo = f'disco libre en la VM {disco:.0f} GB < {DISCO_MIN_GB} GB'
        if _alerta_contenedores():
            motivo = f'contenedor reiniciado o sin memoria: {_alerta_contenedores()}'
        if (DESTINO / 'PARAR').exists():
            motivo = 'parada manual (archivo PARAR)'
        if motivo:
            ESTADO['parar'] = motivo
            evento(f'CONDICIÓN DE PARADA: {motivo}')


def _alerta_contenedores():
    try:
        for linea in MUESTRAS_VM.read_text(encoding='utf-8', errors='ignore').splitlines()[-200:]:
            if linea.startswith('ALERTA,'):
                return linea.split(',', 2)[2]
    except OSError:
        pass
    return None


@events.test_start.add_listener
def _inicio(environment, **kw):
    ESTADO['arranque'] = time.time()
    evento(f'inicio · prefijo {PREFIJO} · etapas {ETAPAS} · recuperación {RECUPERACION} · tasa {TASA}/s')
    gevent.spawn(guardia, environment)


@events.quitting.add_listener
def _fin(environment, **kw):
    evento('fin de la corrida')
    with open(DESTINO / 'eventos_guardia.csv', 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows([('hora', 't', 'evento'), *ESTADO['eventos']])
    with open(DESTINO / 'ventas_enviadas.csv', 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows([('t', 'id_cliente', 'comercio_id', 'inventario_id', 'status', 'intento',
                                  'respondio_duplicada'), *VENTAS])
    with CANDADO:
        filas = list(TODO)
    por_nombre = collections.defaultdict(list)
    for f in filas:
        por_nombre[f[3]].append(f)
    with open(DESTINO / 'resultados_por_categoria.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['endpoint', 'total', *CATEGORIAS, 'ok_prom_ms', 'ok_p50_ms', 'ok_p95_ms', 'ok_p99_ms',
                    'ok_max_ms'])
        for nombre in sorted(por_nombre) + ['TOTAL']:
            grupo = filas if nombre == 'TOTAL' else por_nombre[nombre]
            cuenta = collections.Counter(x[1] for x in grupo)
            ok = [x[2] for x in grupo if x[1] == 'ok']
            w.writerow([nombre, len(grupo), *[cuenta.get(c, 0) for c in CATEGORIAS],
                        round(sum(ok) / len(ok), 1) if ok else '', _p(ok, 50), _p(ok, 95), _p(ok, 99),
                        round(max(ok), 1) if ok else ''])
    (DESTINO / 'cuentas.json').write_text(json.dumps({
        'cuentas_disponibles': {k: len(SESIONES[k]) for k in ('com', 'ana', 'aud')},
        'asignaciones_repetidas': dict(CUENTAS_REPETIDAS)}, indent=2), encoding='utf-8')
