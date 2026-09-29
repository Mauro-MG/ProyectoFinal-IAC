"""Lectura de parámetros de configuracion_sistema con valor por omisión."""
from app.models import ConfiguracionSistema

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
}


def parametro(clave):
    """Devuelve el parámetro como número (float o int)."""
    registro = ConfiguracionSistema.query.filter_by(clave=clave).first()
    valor = registro.valor if registro and registro.valor not in (None, '') else VALORES_POR_OMISION[clave]
    numero = float(valor)
    return int(numero) if numero.is_integer() else numero
