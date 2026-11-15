from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida


class ProductosConsulta(BaseConsulta):
    texto: str | None = None
    categoria_id: int | None = Field(None, ge=1)
    marca_id: int | None = Field(None, ge=1)
    canasta_basica: bool | None = None
    orden: Literal['nombre', 'categoria', 'recientes'] = 'nombre'
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(50, ge=1, le=200)


class ProductoEntrada(BaseEntrada):
    nombre: str = Field(min_length=3, max_length=200, description='Nombre y presentación, p. ej. "Arroz blanco 1 kg"')
    categoria_id: int = Field(ge=1)
    unidad_medida: str = Field(min_length=1, max_length=20, description='Clave de GET /unidades (pieza, kg, litro...)')
    codigo_barras: str | None = Field(None, max_length=50, pattern=r'^\d{8,14}$')
    es_canasta_basica: bool = False
    descripcion: str | None = Field(None, max_length=1000)
    marca_id: int | None = Field(None, ge=1)
    clave_estandar: str | None = Field(None, max_length=20, description='Clasificación estandarizada (p. ej. clave SAT)')
    imagen_documento_id: str | None = Field(None, max_length=24, description='Foto subida a ms-documentos')


class MarcaEntrada(BaseEntrada):
    nombre: str = Field(min_length=2, max_length=100)


class CategoriaEntrada(BaseEntrada):
    nombre: str = Field(min_length=3, max_length=100)
    descripcion: str | None = Field(None, max_length=500)
    orden: int = Field(0, ge=0, le=999)


class VarianteEntrada(BaseEntrada):
    nombre: str = Field(min_length=2, max_length=100, description='"Bolsa 500 g", "Caja con 12"')
    codigo_barras: str | None = Field(None, pattern=r'^\d{8,14}$')
    factor: Decimal = Field(1, gt=0, max_digits=10, decimal_places=3, description='Unidades base que contiene')


class EquivalenciaEntrada(BaseEntrada):
    equivalente_id: int = Field(ge=1)
    tipo: Literal['SUSTITUTO', 'MISMO'] = 'SUSTITUTO'


# ---------------------------------------------------------------- salidas
class VarianteSalida(Salida):
    id: int
    producto_id: int
    nombre: str
    codigo_barras: str | None = None
    factor: float


class EquivalenteSalida(Salida):
    producto_id: int
    nombre: str
    tipo: Literal['SUSTITUTO', 'MISMO']


class ProductoSalida(Salida):
    id: int
    nombre: str
    categoria_id: int
    categoria: str
    unidad_medida: str
    codigo_barras: str | None = None
    es_canasta_basica: bool
    descripcion: str | None = None
    marca_id: int | None = None
    marca: str | None = None
    clave_estandar: str | None = None
    imagen_url: str | None = None
    variantes: list[VarianteSalida] | None = None
    equivalentes: list[EquivalenteSalida] | None = None
    coincidencia: str | None = Field(None, description='En búsqueda por código: producto o variante')


class MarcaSalida(Salida):
    id: int
    nombre: str
    productos: int


class MarcasSalida(Salida):
    marcas: list[MarcaSalida]


class UnidadSalida(Salida):
    clave: str
    nombre: str
    tipo: Literal['CONTEO', 'PESO', 'VOLUMEN']


class UnidadesSalida(Salida):
    unidades: list[UnidadSalida]


class ProductosSalida(Salida):
    paginacion: Paginacion
    productos: list[ProductoSalida]
    origen: Literal['cache', 'postgres']


class CategoriaSalida(Salida):
    id: int
    nombre: str
    descripcion: str | None = None
    productos: int


class CategoriasSalida(Salida):
    categorias: list[CategoriaSalida]


CONTRATOS_XML = {
    'producto_entrada': ProductoEntrada, 'marca_entrada': MarcaEntrada, 'categoria_entrada': CategoriaEntrada,
    'variante_entrada': VarianteEntrada, 'equivalencia_entrada': EquivalenciaEntrada,
    'producto': ProductoSalida, 'productos': ProductosSalida, 'categorias': CategoriasSalida,
    'categoria': CategoriaSalida, 'marcas': MarcasSalida, 'marca': MarcaSalida, 'unidades': UnidadesSalida,
    'variante': VarianteSalida,
}
