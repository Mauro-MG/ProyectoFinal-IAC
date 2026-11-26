from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida

Latitud = Field(ge=-90, le=90)
Longitud = Field(ge=-180, le=180)


class PuntoConsulta(BaseConsulta):
    latitud: Decimal = Latitud
    longitud: Decimal = Longitud


class PuntoEntrada(BaseEntrada):
    latitud: Decimal = Latitud
    longitud: Decimal = Longitud


class GeocodificarConsulta(BaseConsulta):
    direccion: str = Field(min_length=3, max_length=255, description='Calle, colonia o referencia')
    municipio: str | None = Field(None, max_length=100)


class DistanciaConsulta(BaseConsulta):
    origen_latitud: Decimal = Latitud
    origen_longitud: Decimal = Longitud
    destino_latitud: Decimal = Latitud
    destino_longitud: Decimal = Longitud


class CercanosConsulta(BaseConsulta):
    latitud: Decimal = Latitud
    longitud: Decimal = Longitud
    radio_km: Decimal = Field(3, gt=0, le=50)
    tipo: Literal['comercios', 'proveedores'] = 'comercios'
    producto_id: int | None = Field(None, ge=1, description='Sólo los que tienen existencia (comercios) u ofrecen el producto (proveedores)')
    limite: int = Field(20, ge=1, le=100)


class CoberturaConsulta(BaseConsulta):
    nivel: Literal['municipio', 'colonia', 'zona'] = 'municipio'
    municipio: str | None = Field(None, max_length=100)


class ZonasConsulta(BaseConsulta):
    incluir_inactivas: bool = False


class ZonaEntrada(BaseEntrada):
    nombre: str = Field(min_length=3, max_length=100)
    municipio: str = Field(min_length=2, max_length=100)
    estado: str = Field('Nuevo León', max_length=100)
    codigo_postal: str | None = Field(None, pattern=r'^\d{5}$')
    latitud_centro: Decimal = Latitud
    longitud_centro: Decimal = Longitud
    radio_km: Decimal = Field(gt=0, le=20)
    poblacion: int = Field(0, ge=0)


class ZonaCambio(BaseEntrada):
    nombre: str | None = Field(None, min_length=3, max_length=100)
    codigo_postal: str | None = Field(None, pattern=r'^\d{5}$')
    latitud_centro: Decimal | None = Field(None, ge=-90, le=90)
    longitud_centro: Decimal | None = Field(None, ge=-180, le=180)
    radio_km: Decimal | None = Field(None, gt=0, le=20)
    poblacion: int | None = Field(None, ge=0)
    activa: bool | None = None


# ---------------------------------------------------------------- salidas
class ZonaSalida(Salida):
    id: int
    nombre: str
    municipio: str
    estado: str
    codigo_postal: str | None = None
    latitud_centro: float
    longitud_centro: float
    radio_km: float
    poblacion: int
    area_km2: float | None = None
    comercios: int | None = None
    activa: bool | None = None


class ZonasSalida(Salida):
    origen: Literal['cache', 'postgres']
    zonas: list[ZonaSalida]


class ZonaCercana(Salida):
    zona_id: int
    zona: str
    distancia_km: float
    radio_km: float


class LocalizacionSalida(Salida):
    zona: ZonaSalida
    metodo: str
    cercanas: list[ZonaCercana]


class ColoniaSalida(Salida):
    id: int
    nombre: str
    municipio: str
    codigo_postal: str | None = None
    latitud: float
    longitud: float
    distancia_km: float | None = None


class GeocodificacionSalida(Salida):
    consulta: str
    precision: Literal['colonia', 'municipio']
    latitud: float
    longitud: float
    colonia: ColoniaSalida | None = None
    municipio: str
    zona: ZonaSalida | None = None
    alternativas: list[ColoniaSalida]


class GeocodificacionInversaSalida(Salida):
    latitud: float
    longitud: float
    colonia: ColoniaSalida
    municipio: str
    zona: ZonaSalida | None = None


class ValidacionSalida(Salida):
    valida: bool
    latitud: float
    longitud: float
    dentro_area_metropolitana: bool
    zona: ZonaSalida | None = None
    colonia_cercana: ColoniaSalida | None = None
    avisos: list[str]


class DistanciaSalida(Salida):
    distancia_km: float
    distancia_haversine_km: float
    metodo: str


class Cercano(Salida):
    id: str
    nombre: str
    tipo: str
    latitud: float
    longitud: float
    distancia_km: float
    zona_id: int | None = None
    existencia: float | None = None
    precio: float | None = None


class CercanosSalida(Salida):
    latitud: float
    longitud: float
    radio_km: float
    tipo: str
    total: int
    resultados: list[Cercano]


class CoberturaRenglon(Salida):
    nombre: str
    municipio: str | None = None
    comercios: int
    comercios_formales: int
    comercios_informales: int
    proveedores_que_entregan: int
    poblacion: int | None = None
    habitantes_por_comercio: float | None = None


class CoberturaSalida(Salida):
    nivel: str
    municipio: str | None = None
    renglones: list[CoberturaRenglon]


CONTRATOS_XML = {
    'punto_entrada': PuntoEntrada, 'zona_entrada': ZonaEntrada, 'zona_cambio': ZonaCambio,
    'zona': ZonaSalida, 'zonas': ZonasSalida, 'localizacion': LocalizacionSalida,
    'geocodificacion': GeocodificacionSalida, 'geocodificacion_inversa': GeocodificacionInversaSalida,
    'validacion': ValidacionSalida, 'distancia': DistanciaSalida, 'cercanos': CercanosSalida,
    'cobertura': CoberturaSalida,
}
