from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta
from abasto_api.modelos_comunes import Paginacion, Salida


class BuscarConsulta(BaseConsulta):
    q: str = Field(min_length=2, max_length=100, description='Texto a buscar (sin importar acentos ni mayúsculas)')
    tipo: Literal['todos', 'productos', 'comercios', 'proveedores'] = 'todos'
    zona_id: int | None = Field(None, ge=1)
    categoria_id: int | None = Field(None, ge=1)
    municipio: str | None = Field(None, max_length=100)
    solo_canasta: bool = False
    con_existencia: bool = Field(False, description='Comercios: sólo los que tienen el producto buscado')
    latitud: Decimal | None = Field(None, ge=-90, le=90)
    longitud: Decimal | None = Field(None, ge=-180, le=180)
    orden: Literal['relevancia', 'nombre', 'distancia'] = 'relevancia'
    origen: Literal['web', 'android', 'escritorio'] = 'web'
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class OfertasConsulta(BaseConsulta):
    q: str = Field(min_length=2, max_length=100)
    zona_id: int | None = Field(None, ge=1)
    precio_max: Decimal | None = Field(None, gt=0)
    con_existencia: bool = True
    orden: Literal['relevancia', 'precio', 'tiempo_entrega'] = 'precio'
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class SugerenciasConsulta(BaseConsulta):
    q: str = Field(min_length=1, max_length=50)
    limite: int = Field(8, ge=1, le=20)


# ---------------------------------------------------------------- salidas
class Resultado(Salida):
    tipo: Literal['producto', 'comercio', 'proveedor']
    id: str
    nombre: str
    detalle: str | None = None
    zona: str | None = None
    municipio: str | None = None
    relevancia: float
    distancia_km: float | None = None
    existencia: float | None = None
    precio: float | None = None


class Conteos(Salida):
    productos: int
    comercios: int
    proveedores: int


class BusquedaSalida(Salida):
    q: str
    tipo: str
    origen: Literal['cache', 'postgres']
    conteos: Conteos
    paginacion: Paginacion
    resultados: list[Resultado]


class OfertaEncontrada(Salida):
    oferta_id: int
    producto_id: int
    producto: str
    proveedor_id: str
    proveedor: str
    precio_mayoreo: float
    cantidad_minima: float
    existencia_disponible: float
    tiempo_entrega_dias: int
    cubre_zona: bool | None = None
    relevancia: float


class OfertasSalida(Salida):
    q: str
    paginacion: Paginacion
    ofertas: list[OfertaEncontrada]


class Sugerencia(Salida):
    texto: str
    tipo: Literal['producto', 'categoria', 'popular']
    id: str | None = None


class SugerenciasSalida(Salida):
    q: str
    sugerencias: list[Sugerencia]


class Popular(Salida):
    texto: str
    busquedas: int


class PopularesSalida(Salida):
    populares: list[Popular]


CONTRATOS_XML = {
    'busqueda': BusquedaSalida, 'ofertas': OfertasSalida, 'sugerencias': SugerenciasSalida,
    'populares': PopularesSalida,
}
