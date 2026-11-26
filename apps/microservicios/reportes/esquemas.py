from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida

TipoReporte = Literal['inventario', 'ventas', 'precios', 'pedidos', 'proveedores', 'cobertura', 'brechas']
FormatoArchivo = Literal['pdf', 'csv', 'xlsx', 'json']
Frecuencia = Literal['diaria', 'semanal', 'mensual']


class Filtros(BaseEntrada):
    comercio_id: str | None = None
    zona_id: int | None = Field(None, ge=1)
    dias: int | None = Field(None, ge=1, le=366)
    solo_canasta: bool | None = None


class ReporteEntrada(BaseEntrada):
    tipo: TipoReporte
    formato: FormatoArchivo = 'pdf'
    filtros: Filtros = Field(default_factory=Filtros)


class ProgramadoEntrada(BaseEntrada):
    nombre: str = Field(min_length=3, max_length=80)
    tipo: TipoReporte
    formato: FormatoArchivo = 'pdf'
    filtros: Filtros = Field(default_factory=Filtros)
    frecuencia: Frecuencia
    hora: int = Field(7, ge=0, le=23, description='Hora de Monterrey en que se genera')


class UrlConsulta(BaseConsulta):
    minutos: int = Field(10, ge=1, le=60, description='Vigencia de la URL firmada')


class ReportesConsulta(BaseConsulta):
    limite: int = Field(20, ge=1, le=100)


# ---------------------------------------------------------------- salidas
class TipoSalida(Salida):
    tipo: str
    descripcion: str
    filtros: list[str]
    formatos: list[str]


class TiposSalida(Salida):
    tipos: list[TipoSalida]


class ReporteSalida(Salida):
    id: str
    tipo: str
    titulo: str
    formato: str
    nombre_archivo: str
    tamano_bytes: int
    renglones: int
    filtros: dict
    generado: datetime
    expira: datetime
    url_archivo: str
    programado_id: str | None = None
    sha256: str | None = None


class UrlFirmadaSalida(Salida):
    id: str
    url: str = Field(description='URL firmada V4 de solo lectura del objeto en Cloud Storage')
    expira: datetime
    minutos: int
    tipo_mime: str
    sha256: str | None = None


class ReportesSalida(Salida):
    total: int
    reportes: list[ReporteSalida]


class ProgramadoSalida(Salida):
    id: str
    nombre: str
    tipo: str
    formato: str
    filtros: dict
    frecuencia: Frecuencia
    hora: int
    activo: bool
    proxima_ejecucion: datetime
    ultima_ejecucion: datetime | None = None
    ultimo_reporte_id: str | None = None
    ultimo_error: str | None = None


class ProgramadosSalida(Salida):
    programados: list[ProgramadoSalida]


class EjecucionSalida(Salida):
    revisados: int
    generados: int
    con_error: int
    reportes: list[ReporteSalida]


CONTRATOS_XML = {
    'reporte_entrada': ReporteEntrada, 'programado_entrada': ProgramadoEntrada,
    'tipos': TiposSalida, 'reporte': ReporteSalida, 'reportes': ReportesSalida, 'programado': ProgramadoSalida,
    'programados': ProgramadosSalida, 'ejecucion': EjecucionSalida, 'url_firmada': UrlFirmadaSalida,
}
