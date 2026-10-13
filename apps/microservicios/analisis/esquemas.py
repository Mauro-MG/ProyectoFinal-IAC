from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta
from abasto_api.modelos_comunes import Paginacion, Salida


class BrechasConsulta(BaseConsulta):
    zona_id: int | None = Field(None, ge=1)
    categoria_id: int | None = Field(None, ge=1)
    producto_id: int | None = Field(None, ge=1)
    canasta_basica: bool = False
    nivel: Literal['ALTA', 'MEDIA', 'BAJA', 'SIN_BRECHA'] | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(50, ge=1, le=500)


class MapaConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1, description='Colorea los comercios por existencia de este producto')


class EvolucionConsulta(BaseConsulta):
    zona_id: int | None = Field(None, ge=1)
    dias: int = Field(90, ge=1, le=365)


class OportunidadesConsulta(BaseConsulta):
    limite: int = Field(50, ge=1, le=500)


# ---------------------------------------------------------------- salidas
class Umbrales(Salida):
    alta: float
    media: float
    baja: float


class ZonaIndicador(Salida):
    id: int
    nombre: str
    municipio: str
    poblacion: int
    latitud: float
    longitud: float
    radio_km: float
    comercios: int
    formales: int
    informales: int
    proveedores: int
    productos_disponibles: int
    densidad_km2: float
    habitantes_por_comercio: int | None = None
    indice_acceso: float = Field(description='0 a 100: promedio de cobertura de la canasta básica')
    canasta_critica: int
    canasta_total: int
    clasificacion: str
    ranking: int = Field(description='1 = peor acceso')


class ZonasSalida(Salida):
    umbrales: Umbrales
    zonas: list[ZonaIndicador]


class Brecha(Salida):
    zona_id: int
    zona: str
    municipio: str
    producto_id: int
    producto: str
    canasta_basica: bool
    comercios_analizados: int
    lo_venden: int
    con_disponibilidad: int
    sin_disponibilidad: int
    agotados: int
    existencia_total: float
    cobertura: float
    puntos_requeridos: int | None = None
    deficit_puntos: int | None = None
    ventas: float
    proveedores: int
    precio_mayoreo_min: float | None = None
    precio_promedio: float | None = None
    ultima_actualizacion: datetime | None = None
    nivel: Literal['ALTA', 'MEDIA', 'BAJA', 'SIN_BRECHA']


class TotalesBrecha(Salida):
    ALTA: int
    MEDIA: int
    BAJA: int
    SIN_BRECHA: int


class BrechasSalida(Salida):
    paginacion: Paginacion
    brechas: list[Brecha]
    totales: TotalesBrecha


class Recomendacion(Salida):
    producto_id: int
    producto: str
    canasta_basica: bool
    motivo: str
    cobertura: float
    con_disponibilidad: int
    comercios_analizados: int
    ventas: float
    proveedores: int
    precio_mayoreo_min: float | None = None
    precio_promedio: float | None = None
    margen_estimado: float | None = None
    puntaje: int


class RecomendacionesSalida(Salida):
    comercio_id: str
    zona: str
    umbral_cobertura: float
    recomendaciones: list[Recomendacion]


class PuntoComercio(Salida):
    nombre: str
    tipo: str
    sector: str
    zona: str | None = None
    lat: float
    lon: float
    existencia: float | None = None


class PuntoProveedor(Salida):
    nombre: str
    lat: float
    lon: float
    zonas: int
    plan: str


class MapaSalida(Salida):
    comercios: list[PuntoComercio]
    proveedores: list[PuntoProveedor]


class Oportunidad(Salida):
    zona_id: int
    zona: str
    producto_id: int
    producto: str
    cobertura: float
    nivel: Literal['ALTA', 'MEDIA']
    sin_disponibilidad: int
    comercios_analizados: int
    ventas: float
    proveedores: int
    precio_mayoreo_min: float | None = None
    precio_promedio: float | None = None


class OportunidadesSalida(Salida):
    total: int
    oportunidades: list[Oportunidad]


class EjecucionSalida(Salida):
    id: str
    zonas: int
    criticas: int


class PuntoEvolucion(Salida):
    zona_id: int
    zona: str
    dia: str
    indice_acceso: float
    ejecuciones: int


class EvolucionSalida(Salida):
    dias: int
    zona_id: int | None = None
    datos: list[PuntoEvolucion]


CONTRATOS_XML = {
    'zonas': ZonasSalida, 'brechas': BrechasSalida, 'recomendaciones': RecomendacionesSalida, 'mapa': MapaSalida,
    'oportunidades': OportunidadesSalida, 'ejecucion': EjecucionSalida, 'evolucion': EvolucionSalida,
}
