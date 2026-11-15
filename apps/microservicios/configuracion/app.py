"""
ms-configuracion: reglas comerciales y parámetros centralizados.

Es DUEÑO de: configuracion_sistema y catalogos_administrativos.

- Parámetros por categoría (análisis, inventario, pedidos, precios, sincronización...), con
  tipo de dato y rango permitido: un valor fuera de rango se rechaza con 422.
- Cada cambio queda en la auditoría con el valor anterior y el nuevo, e incrementa
  `config:version` en Redis: los demás servicios leen los parámetros con
  abasto_dominio.servicios.parametros (caché de 60 s por versión) y ven el valor nuevo de
  inmediato. Si cambia un umbral del análisis también se invalida la caché de análisis.
- Parámetros públicos (versión de la app, límites de sincronización...) sin sesión, para que las
  apps Android y de escritorio se configuren al arrancar.
- Catálogos administrativos: métodos de pago, motivos de rechazo, tipos de incidencia, giros...
"""
import json
from pathlib import Path
from uuid import UUID

from flask import g
from redis.exceptions import RedisError
from sqlalchemy import func, text

from abasto_api import ErrorApi, Servicio, no_encontrado
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import ConfiguracionSistema
from abasto_dominio.servicios import parametros as servicio_parametros
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.cache import invalidar_analisis
from abasto_dominio.servicios.parametros import parametro

from esquemas import (CONTRATOS_XML, ElementoCambio, ElementoEntrada, ParametroCambio, ParametroEntrada,
                      ParametrosConsulta)

srv = Servicio('configuracion', 'Configuración',
               'Configuración centralizada de reglas comerciales, parámetros de inventario, catálogos administrativos, '
               'límites operativos, políticas de pedidos y parámetros públicos de funcionamiento.',
               xsd=Path(__file__).parent / 'xsd' / 'configuracion.xsd', contratos=CONTRATOS_XML)
app = srv.app

CLAVE_PUBLICOS = 'config:publicos'


def parametro_a_dict(p):
    return {'clave': p.clave, 'valor': p.valor, 'descripcion': p.descripcion, 'tipo_dato': p.tipo_dato,
            'categoria': p.categoria, 'publico': p.publico,
            'valor_minimo': float(p.valor_minimo) if p.valor_minimo is not None else None,
            'valor_maximo': float(p.valor_maximo) if p.valor_maximo is not None else None,
            'actualizado': p.updated_at, 'actualizado_por': str(p.updated_by) if p.updated_by else None}


def validar_valor(valor, tipo, minimo, maximo):
    """Convierte y valida; regresa el texto normalizado que se guarda."""
    try:
        if tipo == 'int':
            numero = int(valor)
        elif tipo == 'float':
            numero = float(valor)
        elif tipo == 'bool':
            if valor.lower() not in ('true', 'false'):
                raise ValueError
            return valor.lower()
        else:
            return valor
    except ValueError:
        raise ErrorApi(422, 'valor_invalido', f'El valor debe ser de tipo {tipo}.')
    if minimo is not None and numero < float(minimo):
        raise ErrorApi(422, 'fuera_de_rango', f'El valor mínimo permitido es {float(minimo):g}.')
    if maximo is not None and numero > float(maximo):
        raise ErrorApi(422, 'fuera_de_rango', f'El valor máximo permitido es {float(maximo):g}.')
    return str(numero)


def _invalidar(categoria):
    servicio_parametros.invalidar()
    try:
        extensiones.redis_client.delete(CLAVE_PUBLICOS)
    except RedisError:
        pass
    if categoria == 'ANALISIS':
        invalidar_analisis()


def _parametro(clave):
    registro = ConfiguracionSistema.query.filter_by(clave=clave).first()
    if not registro:
        raise no_encontrado(f'El parámetro {clave}')
    return registro


def elementos(catalogo, solo_activos=True):
    filas = db.session.execute(text(
        'SELECT clave, nombre, orden, activo FROM catalogos_administrativos WHERE catalogo = :c '
        f'{"AND activo" if solo_activos else ""} ORDER BY orden, nombre'), {'c': catalogo}).all()
    return [{'clave': f.clave, 'nombre': f.nombre, 'orden': f.orden, 'activo': f.activo} for f in filas]


# ---------------------------------------------------------------- parámetros

@srv.ruta('/parametros', 'GET', resumen='Todos los parámetros', etiqueta='Parámetros',
          permisos=['config.gestionar'], consulta=ParametrosConsulta, raiz_xml='parametros')
def listar(q):
    consulta = ConfiguracionSistema.query
    if q.categoria:
        consulta = consulta.filter_by(categoria=q.categoria)
    registros = consulta.order_by(ConfiguracionSistema.categoria, ConfiguracionSistema.clave).all()
    return {'total': len(registros), 'parametros': [parametro_a_dict(p) for p in registros]}


@srv.ruta('/parametros/publicos', 'GET', resumen='Parámetros públicos (apps)', etiqueta='Parámetros', publico=True,
          raiz_xml='publicos')
def publicos():
    """Sin sesión. Las apps los leen al arrancar. 5 minutos en Redis; `version` cambia con cada ajuste."""
    try:
        version = extensiones.redis_client.get(servicio_parametros.CLAVE_VERSION) or '0'
        guardado = extensiones.redis_client.get(CLAVE_PUBLICOS)
        if guardado:
            return {'origen': 'cache', 'version': version, 'parametros': json.loads(guardado)}
    except RedisError:
        version = '0'
    lista = [{'clave': p.clave, 'valor': p.valor, 'descripcion': p.descripcion}
             for p in ConfiguracionSistema.query.filter_by(publico=True).order_by(ConfiguracionSistema.clave)]
    try:
        extensiones.redis_client.setex(CLAVE_PUBLICOS, 300, json.dumps(lista, ensure_ascii=False))
    except RedisError:
        pass
    return {'origen': 'postgres', 'version': version, 'parametros': lista}


@srv.ruta('/parametros/<clave>', 'GET', resumen='Un parámetro', etiqueta='Parámetros', permisos=['config.gestionar'],
          raiz_xml='parametro')
def obtener(clave):
    return parametro_a_dict(_parametro(clave))


@srv.ruta('/parametros/<clave>', 'PUT', resumen='Cambiar el valor de un parámetro', etiqueta='Parámetros',
          permisos=['config.gestionar'], cuerpo=ParametroCambio, raiz_xml='parametro', entrada_xml='parametro_cambio',
          ejemplo_entrada={'valor': '35', 'motivo': 'Ajuste acordado con el municipio'})
def cambiar(clave, datos):
    """Valida tipo y rango, registra el cambio (antes y después) en auditoría e invalida las cachés."""
    registro = _parametro(clave)
    nuevo = validar_valor(datos.valor, registro.tipo_dato, registro.valor_minimo, registro.valor_maximo)
    if clave.startswith('UMBRAL_BRECHA_'):
        umbrales = {k: parametro(k) for k in ('UMBRAL_BRECHA_ALTA', 'UMBRAL_BRECHA_MEDIA', 'UMBRAL_BRECHA_BAJA')}
        umbrales[clave] = float(nuevo)
        if not umbrales['UMBRAL_BRECHA_ALTA'] < umbrales['UMBRAL_BRECHA_MEDIA'] < umbrales['UMBRAL_BRECHA_BAJA']:
            raise ErrorApi(422, 'umbrales_incongruentes', 'Debe cumplirse ALTA < MEDIA < BAJA en los umbrales de brecha.')
    if nuevo == registro.valor:
        raise ErrorApi(409, 'sin_cambio', 'El parámetro ya tiene ese valor.')
    anterior = registro.valor
    registro.valor = nuevo
    registro.updated_by = UUID(g.claims['sub'])
    registro.updated_at = func.now()
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'ConfiguracionSistema', clave,
                     f'{clave}: {anterior} -> {nuevo}' + (f' ({datos.motivo})' if datos.motivo else ''),
                     datos_anteriores={'valor': anterior}, datos_nuevos={'valor': nuevo, 'motivo': datos.motivo})
    db.session.commit()
    _invalidar(registro.categoria)
    return parametro_a_dict(registro)


@srv.ruta('/parametros', 'POST', resumen='Alta de un parámetro', etiqueta='Parámetros', permisos=['config.gestionar'],
          cuerpo=ParametroEntrada, status=201, raiz_xml='parametro', entrada_xml='parametro_entrada',
          ejemplo_entrada={'clave': 'VENTA_MAX_PARTIDAS', 'valor': '50', 'descripcion': 'Partidas máximas por venta',
                           'tipo_dato': 'int', 'categoria': 'INVENTARIO', 'valor_minimo': 1, 'valor_maximo': 500})
def crear(datos):
    if ConfiguracionSistema.query.filter_by(clave=datos.clave).first():
        raise ErrorApi(409, 'parametro_duplicado', 'Ya existe un parámetro con esa clave.')
    if datos.valor_minimo is not None and datos.valor_maximo is not None and datos.valor_minimo > datos.valor_maximo:
        raise ErrorApi(422, 'rango_invalido', 'valor_minimo no puede ser mayor que valor_maximo.')
    valor = validar_valor(datos.valor, datos.tipo_dato, datos.valor_minimo, datos.valor_maximo)
    registro = ConfiguracionSistema(**{**datos.model_dump(), 'valor': valor}, updated_by=UUID(g.claims['sub']))
    db.session.add(registro)
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'ConfiguracionSistema', datos.clave,
                     f'Alta del parámetro {datos.clave}', datos_nuevos=datos.model_dump())
    db.session.commit()
    _invalidar(registro.categoria)
    return parametro_a_dict(registro)


@srv.ruta('/politicas/pedidos', 'GET', resumen='Políticas vigentes de pedidos y abasto', etiqueta='Políticas',
          publico=True, raiz_xml='politica')
def politica_pedidos():
    """Resumen de las reglas que aplican ms-pedidos, ms-inventario, ms-precios y ms-abastecimiento."""
    return {'pedido_max_partidas': int(parametro('PEDIDO_MAX_PARTIDAS')),
            'pedido_horas_respuesta': int(parametro('PEDIDO_HORAS_RESPUESTA')),
            'comision_pedido_pct': float(parametro('COMISION_PEDIDO_PCT')),
            'reserva_minutos': int(parametro('RESERVA_MINUTOS')),
            'cotizacion_dias_limite': int(parametro('COTIZACION_DIAS_LIMITE')),
            'variacion_precio_atipico_pct': float(parametro('VARIACION_PRECIO_ATIPICO_PCT')),
            'motivos_rechazo': elementos('motivos_rechazo')}


# ---------------------------------------------------------------- catálogos administrativos

@srv.ruta('/catalogos', 'GET', resumen='Catálogos administrativos', etiqueta='Catálogos', publico=True,
          raiz_xml='catalogos')
def catalogos():
    filas = db.session.execute(text(
        'SELECT catalogo, count(*) AS n FROM catalogos_administrativos WHERE activo GROUP BY catalogo ORDER BY catalogo'))
    return {'catalogos': [{'catalogo': f.catalogo, 'elementos': f.n} for f in filas]}


@srv.ruta('/catalogos/<catalogo>', 'GET', resumen='Elementos de un catálogo', etiqueta='Catálogos', publico=True,
          raiz_xml='catalogo')
def catalogo(catalogo):
    lista = elementos(catalogo)
    if not lista:
        raise no_encontrado(f'El catálogo {catalogo}')
    return {'catalogo': catalogo, 'elementos': lista}


@srv.ruta('/catalogos/<catalogo>', 'POST', resumen='Agregar un elemento', etiqueta='Catálogos',
          permisos=['config.gestionar'], cuerpo=ElementoEntrada, status=201, raiz_xml='elemento',
          entrada_xml='elemento_entrada', ejemplo_entrada={'clave': 'VALES', 'nombre': 'Vales de despensa', 'orden': 5})
def agregar_elemento(catalogo, datos):
    if not catalogo.replace('_', '').isalpha() or len(catalogo) > 40:
        raise ErrorApi(422, 'catalogo_invalido', 'El nombre del catálogo sólo admite letras y guion bajo.')
    if db.session.execute(text('SELECT 1 FROM catalogos_administrativos WHERE catalogo = :c AND clave = :k'),
                          {'c': catalogo, 'k': datos.clave}).first():
        raise ErrorApi(409, 'elemento_duplicado', 'Ese elemento ya existe en el catálogo.')
    db.session.execute(text('INSERT INTO catalogos_administrativos (catalogo, clave, nombre, orden) '
                            'VALUES (:c, :k, :n, :o)'), {'c': catalogo, 'k': datos.clave, 'n': datos.nombre,
                                                        'o': datos.orden})
    registrar_evento(UUID(g.claims['sub']), 'CREACION', 'CatalogoAdministrativo', f'{catalogo}:{datos.clave}',
                     f'{datos.nombre} agregado a {catalogo}', datos_nuevos=datos.model_dump())
    db.session.commit()
    return {**datos.model_dump(), 'activo': True}


@srv.ruta('/catalogos/<catalogo>/<clave>', 'PATCH', resumen='Cambiar o desactivar un elemento', etiqueta='Catálogos',
          permisos=['config.gestionar'], cuerpo=ElementoCambio, raiz_xml='elemento', entrada_xml='elemento_cambio',
          ejemplo_entrada={'activo': False})
def cambiar_elemento(catalogo, clave, datos):
    fila = db.session.execute(text('SELECT clave, nombre, orden, activo FROM catalogos_administrativos '
                                   'WHERE catalogo = :c AND clave = :k'), {'c': catalogo, 'k': clave}).first()
    if not fila:
        raise no_encontrado('El elemento')
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise ErrorApi(422, 'sin_cambios', 'Indica al menos un campo a cambiar.')
    asignaciones = ', '.join(f'{campo} = :{campo}' for campo in cambios)   # campos fijos del modelo, no del usuario
    db.session.execute(text(f'UPDATE catalogos_administrativos SET {asignaciones} WHERE catalogo = :c AND clave = :k'),
                       {**cambios, 'c': catalogo, 'k': clave})
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'CatalogoAdministrativo', f'{catalogo}:{clave}',
                     f'Cambio en {catalogo}: {clave}', datos_anteriores={k: getattr(fila, k) for k in cambios},
                     datos_nuevos=cambios)
    db.session.commit()
    return {'clave': clave, 'nombre': cambios.get('nombre', fila.nombre), 'orden': cambios.get('orden', fila.orden),
            'activo': cambios.get('activo', fila.activo)}
