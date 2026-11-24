"""
Lectura de parámetros de configuracion_sistema con valor por omisión.

ms-configuracion es el DUEÑO de la tabla (el único que la cambia). Los demás servicios sólo
leen el valor con `parametro(clave)`; para no consultar PostgreSQL en cada petición, el valor
se guarda 60 s en Redis (`config:v{version}:{clave}`). Cuando ms-configuracion cambia un
parámetro incrementa `config:version`, así que todos ven el valor nuevo de inmediato.
"""
from redis.exceptions import RedisError

from abasto_dominio import extensiones
from abasto_dominio.modelos import ConfiguracionSistema

CLAVE_VERSION = 'config:version'

VALORES_POR_OMISION = {
    'COMISION_PEDIDO_PCT': 3,
    'PRECIO_DESTACADO_MENSUAL': 499,
    'UMBRAL_BRECHA_ALTA': 30,
    'UMBRAL_BRECHA_MEDIA': 60,
    'UMBRAL_BRECHA_BAJA': 80,
    'HABITANTES_POR_PUNTO': 8000,
    'DIAS_DEMANDA': 30,
    'UMBRAL_COBERTURA_RECOMENDACION': 50,
    'DIAS_DATO_VIGENTE': 7,
    'PEDIDO_MAX_PARTIDAS': 100,
    'PEDIDO_HORAS_RESPUESTA': 24,
    'RESERVA_MINUTOS': 30,
    'VARIACION_PRECIO_ATIPICO_PCT': 40,
    'COTIZACION_DIAS_LIMITE': 3,
    'SINCRONIZACION_MAX_OPERACIONES': 200,
    'DOCUMENTO_MAX_MB': 10,
    'MONITOREO_LATENCIA_ALERTA_MS': 1500,
    'MONITOREO_ERRORES_ALERTA_PCT': 10,
}


def _crudo(clave):
    redis_client = extensiones.redis_client
    try:
        version = redis_client.get(CLAVE_VERSION) or '0'
        guardado = redis_client.get(f'config:v{version}:{clave}')
        if guardado is not None:
            return guardado
    except (RedisError, AttributeError):
        version = None
    registro = ConfiguracionSistema.query.filter_by(clave=clave).first()
    valor = registro.valor if registro and registro.valor not in (None, '') else None
    if version is not None and valor is not None:
        try:
            redis_client.setex(f'config:v{version}:{clave}', 60, valor)
        except RedisError:
            pass
    return valor


def parametro(clave):
    """Devuelve el parámetro como número (float o int)."""
    valor = _crudo(clave)
    numero = float(valor if valor is not None else VALORES_POR_OMISION[clave])
    return int(numero) if numero.is_integer() else numero


def parametro_texto(clave, por_omision=''):
    valor = _crudo(clave)
    return valor if valor is not None else por_omision


def invalidar():
    try:
        extensiones.redis_client.incr(CLAVE_VERSION)
    except RedisError:
        pass
