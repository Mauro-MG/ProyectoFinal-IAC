from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida

Prioridad = Literal['alta', 'media', 'baja']
Respuesta = Literal['aceptada', 'descartada', 'pospuesta']


class RecomendacionesConsulta(BaseConsulta):
    limite: int = Field(10, ge=1, le=50)
    prioridad: Prioridad | None = None


class RespuestaEntrada(BaseEntrada):
    producto_id: int = Field(ge=1)
    respuesta: Respuesta
    motivo: str | None = Field(None, max_length=300)


class ResultadosConsulta(BaseConsulta):
    dias: int = Field(90, ge=7, le=365)


class ZonaConsulta(BaseConsulta):
    limite: int = Field(15, ge=1, le=50)


# ---------------------------------------------------------------- salidas
class Razon(Salida):
    factor: str
    detalle: str
    peso: float


class Recomendacion(Salida):
    producto_id: int
    producto: str
    canasta_basica: bool
    prioridad: Prioridad
    puntaje: int
    motivo: str
    explicacion: list[Razon]
    cobertura: float
    ventas: float
    busquedas_no_satisfechas: int
    proveedores: int
    precio_mayoreo_min: float | None = None
    precio_promedio: float | None = None
    margen_estimado: float | None = None
    respuesta: Respuesta | None = None


class RecomendacionesSalida(Salida):
    comercio_id: str
    zona: str
    umbral_cobertura: float
    generadas: datetime
    fuente_demanda: Literal['ms-demanda', 'no_disponible']
    recomendaciones: list[Recomendacion]


class RespuestaSalida(Salida):
    comercio_id: str
    producto_id: int
    respuesta: Respuesta
    registrada: datetime


class Resultado(Salida):
    producto_id: int
    producto: str
    emitida: datetime
    prioridad: Prioridad
    respuesta: Respuesta | None = None
    adoptada: bool
    fecha_adopcion: datetime | None = None
    unidades_vendidas: float


class ResultadosSalida(Salida):
    comercio_id: str
    dias: int
    emitidas: int
    aceptadas: int
    adoptadas: int
    con_ventas: int
    tasa_adopcion_pct: float
    unidades_vendidas: float
    resultados: list[Resultado]


class EfectividadMotivo(Salida):
    motivo: str
    emitidas: int
    adoptadas: int
    tasa_adopcion_pct: float


class EfectividadSalida(Salida):
    dias: int
    comercios: int
    emitidas: int
    adoptadas: int
    tasa_adopcion_pct: float
    motivos: list[EfectividadMotivo]


class ProductoZona(Salida):
    producto_id: int
    producto: str
    canasta_basica: bool
    cobertura: float
    brecha: str | None = None
    ventas: float
    proveedores: int
    puntaje: int


class ZonaSalida(Salida):
    zona_id: int
    productos: list[ProductoZona]


CONTRATOS_XML = {
    'respuesta_entrada': RespuestaEntrada,
    'recomendaciones': RecomendacionesSalida, 'respuesta': RespuestaSalida, 'resultados': ResultadosSalida,
    'efectividad': EfectividadSalida, 'zona': ZonaSalida,
}
