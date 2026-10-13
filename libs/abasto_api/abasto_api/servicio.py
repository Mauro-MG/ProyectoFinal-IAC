"""
Base de cada microservicio.

    srv = Servicio('inventario', 'Servicio de inventario', 'Existencias y movimientos...')

    @srv.ruta('/inventario/<int:id>/movimientos', 'POST', resumen='Registrar movimiento',
              permisos=['inventario.gestionar'], cuerpo=MovimientoEntrada, respuesta=MovimientoSalida,
              entrada_xml='movimiento_entrada', raiz_xml='movimiento', status=201)
    def registrar_movimiento(id, datos):
        ...
        return {...}

Cada ruta queda en /api/v1/..., valida el JWT y los permisos, acepta el cuerpo
en JSON o XML (validado contra su XSD), responde en el formato pedido y se
documenta sola en /openapi.json (Swagger UI en /docs).

Además, en todas las peticiones: identificador de correlación, límite de
peticiones por usuario o IP (Redis), contadores diarios (Redis) y bitácora de
la petición (MongoDB, colección bitacora_peticiones).
"""
import json as jsonlib
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import Flask, Response, g, jsonify, request, send_from_directory
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from sqlalchemy import text

from abasto_dominio import extensiones
from abasto_dominio.configuracion import ConfiguracionBase

from abasto_api import formatos
from abasto_api.errores import ErrorApi, registrar_manejadores
from abasto_api.seguridad import autenticar

ERRORES_DOC = {
    400: 'Petición mal formada (JSON o XML inválido, parámetro con formato incorrecto)',
    401: 'Sin token, token inválido, expirado o revocado',
    403: 'El rol no tiene el permiso requerido o el recurso no es suyo',
    404: 'El recurso no existe',
    409: 'Regla de negocio no cumplida',
    422: 'Datos con formato correcto pero valores no válidos',
    429: 'Se superó el límite de peticiones por minuto',
    503: 'Una dependencia (PostgreSQL, Redis o MongoDB) no está disponible',
}


class Configuracion(ConfiguracionBase):
    RATE_LIMIT_POR_MINUTO = int(os.environ.get('RATE_LIMIT_POR_MINUTO', '120'))
    JSON_AS_ASCII = False
    NOTIFICACIONES_VIA_SERVICIO = os.environ.get('NOTIFICACIONES_VIA_SERVICIO', 'true').lower() == 'true'


def _ruta_openapi(regla):
    """'/inventario/<int:id>' -> ('/inventario/{id}', [('id', 'integer')])"""
    parametros = []

    def reemplazar(m):
        convertidor, nombre = m.group(1), m.group(2)
        tipo = {'int': 'integer', 'uuid': 'string', 'float': 'number'}.get(convertidor, 'string')
        parametros.append((nombre, tipo, convertidor))
        return '{' + nombre + '}'
    return re.sub(r'<(?:(\w+):)?(\w+)>', reemplazar, regla), parametros


class Servicio:
    def __init__(self, nombre, titulo, descripcion, version='1.0.0', dependencias=('postgres', 'redis', 'mongodb'),
                 xsd=None, contratos=None):
        self.nombre = nombre
        self.xsd = xsd
        self.contratos = contratos or {}
        self.titulo = titulo
        self.descripcion = descripcion
        self.version = version
        self.dependencias = dependencias
        self.rutas = []
        self.modelos = set()

        app = Flask(f'ms-{nombre}')
        app.config.from_object(Configuracion)
        app.json.ensure_ascii = False
        app.json.sort_keys = False
        extensiones.init_app(app)
        registrar_manejadores(app)
        self._configurar_log(app)
        self.app = app

        app.before_request(self._antes)
        app.after_request(self._despues)
        self._rutas_tecnicas()

    # ------------------------------------------------------------ registro y bitácora

    def _configurar_log(self, app):
        manejador = logging.StreamHandler(sys.stdout)
        manejador.setFormatter(logging.Formatter('%(message)s'))
        app.logger.handlers = [manejador]
        app.logger.setLevel(logging.INFO)

    def _antes(self):
        g.inicio = time.perf_counter()
        g.correlation_id = request.headers.get('X-Correlation-ID') or uuid4().hex

    def _despues(self, respuesta):
        duracion = round((time.perf_counter() - getattr(g, 'inicio', time.perf_counter())) * 1000, 1)
        respuesta.headers['X-Correlation-ID'] = g.correlation_id
        respuesta.headers['X-Servicio'] = f'ms-{self.nombre}'
        respuesta.headers['X-Tiempo-ms'] = str(duracion)
        for llave, valor in getattr(g, 'limite_headers', {}).items():
            respuesta.headers[llave] = str(valor)

        if request.path.startswith('/api/'):
            claims = getattr(g, 'claims', None) or {}
            registro = {
                'servicio': self.nombre,
                'metodo': request.method,
                'ruta': request.path,
                'endpoint': request.endpoint,
                'status': respuesta.status_code,
                'codigo_error': getattr(g, 'codigo_error', None),
                'duracion_ms': duracion,
                'usuario_id': claims.get('sub'),
                'rol': claims.get('rol'),
                'ip': request.headers.get('X-Forwarded-For', request.remote_addr),
                'formato': 'xml' if respuesta.mimetype == formatos.MIME_XML else 'json',
                'correlation_id': g.correlation_id,
                'fecha': datetime.now(timezone.utc),
            }
            self.app.logger.info(jsonlib.dumps({**registro, 'fecha': registro['fecha'].isoformat()},
                                               ensure_ascii=False))
            try:
                extensiones.mongo_db()['bitacora_peticiones'].insert_one(registro)
            except PyMongoError:
                pass
            try:
                dia = registro['fecha'].strftime('%Y%m%d')
                pipe = extensiones.redis_client.pipeline()
                pipe.incr(f'contador:{self.nombre}:peticiones:{dia}')
                pipe.expire(f'contador:{self.nombre}:peticiones:{dia}', 60 * 60 * 24 * 8)
                if respuesta.status_code >= 400:
                    pipe.incr(f'contador:{self.nombre}:errores:{dia}')
                    pipe.expire(f'contador:{self.nombre}:errores:{dia}', 60 * 60 * 24 * 8)
                pipe.execute()
            except RedisError:
                pass
        return respuesta

    def _limitar(self, sujeto, limite):
        """Ventana fija de un minuto por servicio y sujeto (usuario o IP)."""
        minuto = int(time.time() // 60)
        clave = f'rate:{self.nombre}:{sujeto}:{minuto}'
        try:
            pipe = extensiones.redis_client.pipeline()
            pipe.incr(clave)
            pipe.expire(clave, 70)
            usadas = pipe.execute()[0]
        except RedisError:
            return  # sin Redis no se limita; la autenticación ya habrá respondido 503
        restantes = max(limite - usadas, 0)
        g.limite_headers = {'X-RateLimit-Limit': limite, 'X-RateLimit-Remaining': restantes}
        if usadas > limite:
            espera = 60 - int(time.time() % 60)
            raise ErrorApi(429, 'limite_excedido',
                           f'Superaste {limite} peticiones por minuto en este servicio. Intenta en {espera} s.',
                           headers={'Retry-After': str(espera)})

    # ------------------------------------------------------------ declaración de rutas

    def ruta(self, regla, metodo, *, resumen, descripcion='', etiqueta=None, permisos=None, publico=False,
             cuerpo=None, consulta=None, respuesta=None, status=200, raiz_xml='respuesta', entrada_xml=None,
             ejemplo_entrada=None, ejemplo_salida=None, limite=None, errores=(400, 401, 403, 404, 422),
             multipart=None):
        from abasto_api.modelos_comunes import CONTRATOS_COMUNES
        if respuesta is None:
            respuesta = self.contratos.get(raiz_xml) or CONTRATOS_COMUNES.get(raiz_xml)

        def decorador(funcion):
            @wraps(funcion)
            def vista(**kwargs):
                claims = None if publico else autenticar(permisos or ())
                sujeto = claims['sub'] if claims else request.headers.get('X-Forwarded-For', request.remote_addr)
                self._limitar(sujeto, limite or self.app.config['RATE_LIMIT_POR_MINUTO'])
                if consulta:
                    kwargs['q'] = consulta.model_validate(request.args.to_dict())
                if cuerpo:
                    kwargs['datos'] = self._leer_cuerpo(cuerpo, entrada_xml)
                resultado = funcion(**kwargs)
                if isinstance(resultado, Response):
                    return resultado
                codigo = status
                if isinstance(resultado, tuple):
                    resultado, codigo = resultado
                return formatos.responder(resultado, codigo, raiz_xml)

            self.app.add_url_rule(f'/api/v1{regla}', endpoint=funcion.__name__, view_func=vista, methods=[metodo])
            for modelo in (cuerpo, consulta, respuesta):
                if modelo:
                    self.modelos.add(modelo)
            self.rutas.append({
                'regla': regla, 'metodo': metodo.lower(), 'resumen': resumen,
                'descripcion': (descripcion or funcion.__doc__ or '').strip(),
                'etiqueta': etiqueta or self.titulo, 'permisos': permisos or [], 'publico': publico,
                'cuerpo': cuerpo, 'consulta': consulta, 'respuesta': respuesta, 'status': status,
                'raiz_xml': raiz_xml, 'entrada_xml': entrada_xml,
                'ejemplo_entrada': ejemplo_entrada, 'ejemplo_salida': ejemplo_salida,
                'errores': tuple(errores) + ((409,) if 409 not in errores and metodo != 'GET' else ()) + (429,),
                'limite': limite, 'multipart': multipart,
            })
            return vista
        return decorador

    def _leer_cuerpo(self, modelo, raiz):
        tipo = (request.mimetype or '').lower()
        if not request.get_data():
            return modelo.model_validate({})  # cuerpo vacío: válido si el modelo no tiene campos obligatorios
        if tipo in ('application/xml', 'text/xml'):
            try:
                datos = formatos.leer_xml(request.get_data(), self.xsd, raiz, _campos_lista(modelo))
            except ValueError as error:
                raise ErrorApi(400, 'xml_invalido', str(error))
        elif tipo == 'application/json' or not tipo:
            datos = request.get_json(silent=True)
            if datos is None:
                raise ErrorApi(400, 'json_invalido', 'El cuerpo debe ser un objeto JSON válido.')
        else:
            raise ErrorApi(415, 'tipo_no_soportado', 'Usa Content-Type application/json o application/xml.')
        if not isinstance(datos, dict):
            raise ErrorApi(400, 'cuerpo_invalido', 'El cuerpo debe ser un objeto, no una lista ni un valor suelto.')
        return modelo.model_validate(datos)

    # ------------------------------------------------------------ salud, OpenAPI y Swagger

    def comprobar(self, dependencia):
        inicio = time.perf_counter()
        try:
            if dependencia == 'postgres':
                extensiones.db.session.execute(text('SELECT 1'))
            elif dependencia == 'redis':
                extensiones.redis_client.ping()
            elif dependencia == 'mongodb':
                extensiones.mongo_client.admin.command('ping')
            return {'nombre': dependencia, 'estado': 'ok',
                    'latencia_ms': round((time.perf_counter() - inicio) * 1000, 1)}
        except Exception as error:  # noqa: BLE001 - se reporta cualquier falla de la dependencia
            extensiones.db.session.rollback()
            return {'nombre': dependencia, 'estado': 'caido', 'error': str(error).splitlines()[0][:200]}

    def _salud(self, dependencias):
        resultados = [self.comprobar(d) for d in dependencias]
        caidas = [r for r in resultados if r['estado'] != 'ok']
        estado = 'ok' if not caidas else 'caido'
        cuerpo = {'servicio': f'ms-{self.nombre}', 'version': self.version, 'estado': estado,
                  'fecha': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'dependencias': resultados}
        return formatos.responder(cuerpo, 200 if estado == 'ok' else 503, 'salud')

    def _rutas_tecnicas(self):
        app = self.app

        @app.get('/health')
        def health():
            return self._salud(self.dependencias)

        @app.get('/health/live')
        def health_live():
            return jsonify(servicio=f'ms-{self.nombre}', estado='ok')

        @app.get('/health/ready')
        def health_ready():
            return self._salud(self.dependencias)

        @app.get('/health/database')
        def health_database():
            return self._salud(['postgres'])

        @app.get('/health/redis')
        def health_redis():
            return self._salud(['redis'])

        @app.get('/health/mongodb')
        def health_mongodb():
            return self._salud(['mongodb'])

        @app.get('/openapi.json')
        def openapi():
            return jsonify(self.openapi())

        @app.get('/docs')
        def docs():
            return Response(_HTML_SWAGGER.replace('{{titulo}}', self.titulo), mimetype='text/html')

        @app.get('/docs/static/<path:archivo>')
        def docs_static(archivo):
            from swagger_ui_bundle import swagger_ui_path
            return send_from_directory(swagger_ui_path, archivo)

        @app.get('/xsd')
        def xsd():
            """Contrato XML (XSD) de este servicio."""
            if not self.xsd:
                return jsonify(error='Este servicio no publica contratos XML'), 404
            return send_from_directory(str(self.xsd.parent), self.xsd.name, mimetype='application/xml')

        @app.get('/')
        def inicio():
            return jsonify(servicio=f'ms-{self.nombre}', titulo=self.titulo, version=self.version,
                           documentacion='/docs', openapi='/openapi.json', contrato_xml='/xsd', salud='/health')

    def openapi(self):
        _, definiciones = models_json_schema([(m, 'validation') for m in self.modelos],
                                             ref_template='#/components/schemas/{model}')
        esquemas = definiciones.get('$defs', {})
        esquemas['Error'] = _ESQUEMA_ERROR
        rutas = {}
        for r in self.rutas:
            ruta, params = _ruta_openapi(r['regla'])
            operacion = {
                'tags': [r['etiqueta']],
                'summary': r['resumen'],
                'description': r['descripcion'] + (
                    f"\n\n**Permisos:** {', '.join(r['permisos'])}" if r['permisos'] else '') + (
                    f"\n\n**XML de entrada:** elemento `<{r['entrada_xml']}>`" if r['entrada_xml'] else '') +
                    f"\n\n**XML de salida:** elemento `<{r['raiz_xml']}>`. Contrato completo: `GET /xsd`.",
                'operationId': f"{r['metodo']}_{ruta.strip('/').replace('/', '_').replace('{', '').replace('}', '')}",
                'parameters': [
                    {'name': n, 'in': 'path', 'required': True,
                     'schema': {'type': t, **({'format': 'uuid'} if c == 'uuid' else {})}} for n, t, c in params
                ] + [{'name': 'X-Correlation-ID', 'in': 'header', 'required': False,
                      'description': 'Identificador para rastrear la petición entre servicios (opcional)',
                      'schema': {'type': 'string'}},
                     {'name': 'formato', 'in': 'query', 'required': False,
                      'description': 'Alternativa al encabezado Accept: json o xml',
                      'schema': {'type': 'string', 'enum': ['json', 'xml']}}],
                'responses': {},
            }
            if r['consulta']:
                props = r['consulta'].model_json_schema(ref_template='#/components/schemas/{model}')
                requeridos = set(props.get('required', []))
                for nombre, esquema in props.get('properties', {}).items():
                    operacion['parameters'].append({'name': nombre, 'in': 'query', 'required': nombre in requeridos,
                                                    'description': esquema.get('description', ''),
                                                    'schema': {k: v for k, v in esquema.items() if k != 'title'}})
            if not r['publico']:
                operacion['security'] = [{'bearerAuth': []}]
            if r['cuerpo']:
                contenido = {'application/json': {'schema': {'$ref': f"#/components/schemas/{r['cuerpo'].__name__}"}},
                             'application/xml': {'schema': {'$ref': f"#/components/schemas/{r['cuerpo'].__name__}"}}}
                if r['ejemplo_entrada']:
                    contenido['application/json']['example'] = r['ejemplo_entrada']
                    raiz = r['entrada_xml'] or 'entrada'
                    contenido['application/xml']['example'] = formatos.a_xml(r['ejemplo_entrada'], raiz).decode()
                operacion['requestBody'] = {'required': True, 'content': contenido}
            if r['multipart']:
                operacion['requestBody'] = {'required': True, 'content': {'multipart/form-data': {'schema': r['multipart']}}}
            exito = {'description': 'Operación exitosa', 'content': {'application/json': {}, 'application/xml': {}}}
            if r['respuesta']:
                ref = {'$ref': f"#/components/schemas/{r['respuesta'].__name__}"}
                exito['content']['application/json']['schema'] = ref
                exito['content']['application/xml']['schema'] = ref
            if r['ejemplo_salida'] is not None:
                exito['content']['application/json']['example'] = r['ejemplo_salida']
                exito['content']['application/xml']['example'] = formatos.a_xml(r['ejemplo_salida'], r['raiz_xml']).decode()
            operacion['responses'][str(r['status'])] = exito
            for codigo in sorted(set(r['errores'])):
                if r['publico'] and codigo in (401, 403):
                    continue
                operacion['responses'][str(codigo)] = {
                    'description': ERRORES_DOC.get(codigo, 'Error'),
                    'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}},
                                'application/xml': {'schema': {'$ref': '#/components/schemas/Error'}}}}
            rutas.setdefault(f'/api/v1{ruta}', {})[r['metodo']] = operacion
        return {
            'openapi': '3.1.0',
            'info': {'title': f'AbastoRed · {self.titulo}', 'version': self.version, 'description': self.descripcion},
            'servers': [{'url': '/', 'description': 'Este servicio'}],
            'tags': [{'name': t} for t in dict.fromkeys(r['etiqueta'] for r in self.rutas)],
            'paths': rutas,
            'components': {
                'securitySchemes': {'bearerAuth': {
                    'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT',
                    'description': 'Token de ms-seguridad: POST /api/v1/auth/login'}},
                'schemas': esquemas,
            },
        }


_ESQUEMA_ERROR = {
    'type': 'object',
    'properties': {'error': {'type': 'object', 'properties': {
        'codigo': {'type': 'string', 'example': 'regla_negocio'},
        'mensaje': {'type': 'string'},
        'status': {'type': 'integer'},
        'ruta': {'type': 'string'},
        'correlation_id': {'type': 'string'},
        'fecha': {'type': 'string', 'format': 'date-time'},
        'detalles': {'type': 'array', 'items': {'type': 'object'}},
    }, 'required': ['codigo', 'mensaje', 'status']}},
    'required': ['error'],
}

_HTML_SWAGGER = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{titulo}} · Swagger</title>
<link rel="stylesheet" href="/docs/static/swagger-ui.css"></head>
<body><div id="swagger-ui"></div>
<script src="/docs/static/swagger-ui-bundle.js"></script>
<script>
window.ui = SwaggerUIBundle({url: '/openapi.json', dom_id: '#swagger-ui', persistAuthorization: true,
  displayRequestDuration: true, docExpansion: 'list', defaultModelsExpandDepth: 0});
</script></body></html>"""


def _campos_lista(modelo):
    """Nombres de los campos que son listas (en cualquier nivel): así se reconstruyen al leer XML."""
    nombres = set()

    def recorrer(esquema, definiciones):
        for nombre, sub in esquema.get('properties', {}).items():
            opciones = sub.get('anyOf', [sub])
            for opcion in opciones:
                if opcion.get('type') == 'array':
                    nombres.add(nombre)
                    items = opcion.get('items', {})
                    if '$ref' in items:
                        recorrer(definiciones[items['$ref'].split('/')[-1]], definiciones)
                elif '$ref' in opcion:
                    recorrer(definiciones[opcion['$ref'].split('/')[-1]], definiciones)

    esquema = modelo.model_json_schema()
    recorrer(esquema, esquema.get('$defs', {}))
    return tuple(nombres)


class BaseEntrada(BaseModel):
    """Modelo base de entrada: rechaza campos que no existen en el contrato."""
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}


class BaseConsulta(BaseModel):
    """Modelo base de parámetros de consulta (?pagina=2&...). Ignora parámetros desconocidos como `formato`."""
    model_config = {'extra': 'ignore', 'str_strip_whitespace': True}


def paginar(consulta_sqlalchemy, pagina, por_pagina, convertir):
    """Pagina un query de SQLAlchemy y regresa el sobre estándar de listas."""
    total = consulta_sqlalchemy.order_by(None).count()
    items = consulta_sqlalchemy.limit(por_pagina).offset((pagina - 1) * por_pagina).all()
    return sobre_lista([convertir(i) for i in items], total, pagina, por_pagina)


def sobre_lista(items, total, pagina, por_pagina, nombre='items'):
    return {
        'paginacion': {'pagina': pagina, 'por_pagina': por_pagina, 'total': total,
                       'paginas': (total + por_pagina - 1) // por_pagina if por_pagina else 1},
        nombre: items,
    }
