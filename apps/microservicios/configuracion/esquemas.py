from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida

Categoria = Literal['GENERAL', 'COMERCIAL', 'ANALISIS', 'INVENTARIO', 'PEDIDOS', 'PRECIOS', 'ABASTECIMIENTO',
                    'SINCRONIZACION', 'DOCUMENTOS', 'MONITOREO']
TipoDato = Literal['int', 'float', 'string', 'bool']


class ParametrosConsulta(BaseConsulta):
    categoria: Categoria | None = None


class ParametroCambio(BaseEntrada):
    valor: str = Field(min_length=1, max_length=500, description='Se valida contra el tipo y el rango del parámetro')
    motivo: str | None = Field(None, max_length=300)


class ParametroEntrada(BaseEntrada):
    clave: str = Field(pattern=r'^[A-Z][A-Z0-9_]{2,99}$')
    valor: str = Field(min_length=1, max_length=500)
    descripcion: str = Field(min_length=5, max_length=500)
    tipo_dato: TipoDato
    categoria: Categoria = 'GENERAL'
    publico: bool = False
    valor_minimo: float | None = None
    valor_maximo: float | None = None


class ElementoEntrada(BaseEntrada):
    clave: str = Field(pattern=r'^[A-Z0-9_]{2,40}$')
    nombre: str = Field(min_length=2, max_length=120)
    orden: int = Field(0, ge=0, le=999)


class ElementoCambio(BaseEntrada):
    nombre: str | None = Field(None, min_length=2, max_length=120)
    orden: int | None = Field(None, ge=0, le=999)
    activo: bool | None = None


# ---------------------------------------------------------------- salidas
class ParametroSalida(Salida):
    clave: str
    valor: str | None = None
    descripcion: str | None = None
    tipo_dato: str | None = None
    categoria: str
    publico: bool
    valor_minimo: float | None = None
    valor_maximo: float | None = None
    actualizado: datetime | None = None
    actualizado_por: str | None = None


class ParametrosSalida(Salida):
    total: int
    parametros: list[ParametroSalida]


class ParametroPublico(Salida):
    clave: str
    valor: str | None = None
    descripcion: str | None = None


class PublicosSalida(Salida):
    origen: Literal['cache', 'postgres']
    version: str
    parametros: list[ParametroPublico]


class ElementoSalida(Salida):
    clave: str
    nombre: str
    orden: int
    activo: bool


class CatalogoSalida(Salida):
    catalogo: str
    elementos: list[ElementoSalida]


class CatalogoResumen(Salida):
    catalogo: str
    elementos: int


class CatalogosSalida(Salida):
    catalogos: list[CatalogoResumen]


class PoliticaSalida(Salida):
    pedido_max_partidas: int
    pedido_horas_respuesta: int
    comision_pedido_pct: float
    reserva_minutos: int
    cotizacion_dias_limite: int
    variacion_precio_atipico_pct: float
    motivos_rechazo: list[ElementoSalida]


CONTRATOS_XML = {
    'parametro_cambio': ParametroCambio, 'parametro_entrada': ParametroEntrada, 'elemento_entrada': ElementoEntrada,
    'elemento_cambio': ElementoCambio,
    'parametro': ParametroSalida, 'parametros': ParametrosSalida, 'publicos': PublicosSalida,
    'catalogo': CatalogoSalida, 'catalogos': CatalogosSalida, 'elemento': ElementoSalida, 'politica': PoliticaSalida,
}
