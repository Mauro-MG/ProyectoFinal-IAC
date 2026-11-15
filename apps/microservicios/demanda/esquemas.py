from datetime import date, datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida

Periodo = Literal['dia', 'semana', 'mes']


class BusquedaEntrada(BaseEntrada):
    texto: str = Field(min_length=2, max_length=120)
    producto_id: int | None = Field(None, ge=1)
    zona_id: int | None = Field(None, ge=1)
    resultados: int = Field(ge=0, description='Cuántos lugares con existencia encontró')
    origen: Literal['web', 'android', 'escritorio', 'busqueda', 'disponibilidad'] = 'web'


class HistoricaConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1)
    zona_id: int | None = Field(None, ge=1)
    municipio: str | None = None
    periodo: Periodo = 'semana'
    dias: int = Field(90, ge=7, le=730)


class TendenciasConsulta(BaseConsulta):
    zona_id: int | None = Field(None, ge=1)
    dias: int = Field(60, ge=14, le=365)
    limite: int = Field(20, ge=1, le=100)


class ProductoConsulta(BaseConsulta):
    producto_id: int = Field(ge=1)
    zona_id: int | None = Field(None, ge=1)
    dias: int = Field(180, ge=28, le=730)


class NoSatisfechaConsulta(BaseConsulta):
    zona_id: int | None = Field(None, ge=1)
    dias: int = Field(30, ge=1, le=365)
    limite: int = Field(20, ge=1, le=200)


class EstimacionConsulta(BaseConsulta):
    producto_id: int = Field(ge=1)
    zona_id: int | None = Field(None, ge=1)
    horizonte_dias: int = Field(7, ge=1, le=30)
    historia_dias: int = Field(56, ge=14, le=365)


class RegionesConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1)
    nivel: Literal['municipio', 'zona'] = 'municipio'
    dias: int = Field(30, ge=1, le=365)


# ---------------------------------------------------------------- salidas
class BusquedaSalida(Salida):
    id: str
    texto: str
    producto_id: int | None = None
    zona_id: int | None = None
    encontrado: bool
    fecha: datetime


class PuntoHistorico(Salida):
    periodo: date
    unidades: float
    movimientos: int
    comercios: int


class HistoricaSalida(Salida):
    producto_id: int | None = None
    zona_id: int | None = None
    periodo: Periodo
    dias: int
    total_unidades: float
    serie: list[PuntoHistorico]


class TendenciaProducto(Salida):
    producto_id: int
    producto: str
    unidades_periodo_anterior: float
    unidades_periodo_reciente: float
    cambio_pct: float | None = None
    tendencia: Literal['sube', 'baja', 'estable', 'nuevo']


class TendenciasSalida(Salida):
    zona_id: int | None = None
    dias: int
    productos: list[TendenciaProducto]


class IndiceEstacional(Salida):
    clave: str
    nombre: str
    promedio_diario: float
    indice: float


class EstacionalidadSalida(Salida):
    producto_id: int
    producto: str
    zona_id: int | None = None
    dias: int
    promedio_diario: float
    por_dia_semana: list[IndiceEstacional]
    por_mes: list[IndiceEstacional]


class NoSatisfecho(Salida):
    producto_id: int | None = None
    texto: str
    busquedas: int
    zonas: int
    ultima: datetime


class NoSatisfechaSalida(Salida):
    zona_id: int | None = None
    dias: int
    total_busquedas: int
    productos: list[NoSatisfecho]


class Buscado(Salida):
    texto: str
    producto_id: int | None = None
    busquedas: int
    encontradas: int
    tasa_exito_pct: float


class BuscadosSalida(Salida):
    dias: int
    productos: list[Buscado]


class PuntoEstimado(Salida):
    fecha: date
    unidades: float
    minimo: float
    maximo: float


class EstimacionSalida(Salida):
    producto_id: int
    producto: str
    zona_id: int | None = None
    metodo: str
    promedio_diario: float
    pendiente_diaria: float
    error_medio: float
    total_estimado: float
    estimacion: list[PuntoEstimado]


class Region(Salida):
    region: str
    municipio: str | None = None
    unidades: float
    comercios: int
    productos: int


class RegionesSalida(Salida):
    nivel: str
    producto_id: int | None = None
    dias: int
    regiones: list[Region]


CONTRATOS_XML = {
    'busqueda_entrada': BusquedaEntrada,
    'busqueda': BusquedaSalida, 'historica': HistoricaSalida, 'tendencias': TendenciasSalida,
    'estacionalidad': EstacionalidadSalida, 'no_satisfecha': NoSatisfechaSalida, 'buscados': BuscadosSalida,
    'estimacion': EstimacionSalida, 'regiones': RegionesSalida,
}
