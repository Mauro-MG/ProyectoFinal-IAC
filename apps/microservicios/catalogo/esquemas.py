from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida


class ProductosConsulta(BaseConsulta):
    texto: str | None = None
    categoria_id: int | None = Field(None, ge=1)
    canasta_basica: bool | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(50, ge=1, le=200)


class ProductoEntrada(BaseEntrada):
    nombre: str = Field(min_length=3, max_length=200, description='Nombre y presentación, p. ej. "Arroz blanco 1 kg"')
    categoria_id: int = Field(ge=1)
    unidad_medida: Literal['pieza', 'kg', 'litro', 'paquete', 'caja']
    codigo_barras: str | None = Field(None, max_length=50, pattern=r'^\d{8,14}$')
    es_canasta_basica: bool = False
    descripcion: str | None = Field(None, max_length=1000)


class ProveedoresConsulta(BaseConsulta):
    zona_id: int | None = Field(None, ge=1, description='Sólo los que entregan en esta zona')
    texto: str | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class OfertaEntrada(BaseEntrada):
    producto_id: int = Field(ge=1)
    precio_mayoreo: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    cantidad_minima: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    existencia_disponible: Decimal = Field(0, ge=0, max_digits=12, decimal_places=2)


class OfertaCambio(BaseEntrada):
    precio_mayoreo: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    cantidad_minima: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    existencia_disponible: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)


class OfertasConsulta(BaseConsulta):
    producto_id: int = Field(ge=1)
    zona_id: int | None = Field(None, ge=1, description='Marca y ordena primero a quienes entregan en la zona')


# ---------------------------------------------------------------- salidas
class ProductoSalida(Salida):
    id: int
    nombre: str
    categoria_id: int
    categoria: str
    unidad_medida: str
    codigo_barras: str | None = None
    es_canasta_basica: bool
    descripcion: str | None = None


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


class ZonaBreve(Salida):
    id: int
    nombre: str


class OfertaSalida(Salida):
    id: int
    proveedor_id: str
    proveedor: str
    producto_id: int
    producto: str
    unidad_medida: str
    precio_mayoreo: float
    cantidad_minima: float
    existencia_disponible: float
    actualizado: datetime | None = None
    cubre_zona: bool | None = None
    pedido_minimo: float | None = None
    tiempo_entrega_dias: int | None = None
    condiciones_venta: str | None = None
    plan: str | None = None


class OfertasSalida(Salida):
    producto_id: int | None = None
    zona_id: int | None = None
    proveedor_id: str | None = None
    total: int
    ofertas: list[OfertaSalida]


class ProveedorSalida(Salida):
    id: str
    nombre_empresa: str
    municipio: str | None = None
    pedido_minimo: float
    tiempo_entrega_dias: int
    condiciones_venta: str | None = None
    plan: Literal['BASICO', 'DESTACADO']
    zonas: list[ZonaBreve]
    descripcion: str | None = None
    telefono_contacto: str | None = None
    email_contacto: str | None = None
    direccion: str | None = None
    ofertas: list[OfertaSalida] | None = None


class ProveedoresSalida(Salida):
    paginacion: Paginacion
    proveedores: list[ProveedorSalida]


CONTRATOS_XML = {
    'producto_entrada': ProductoEntrada, 'oferta_entrada': OfertaEntrada, 'oferta_cambio': OfertaCambio,
    'producto': ProductoSalida, 'productos': ProductosSalida, 'categorias': CategoriasSalida,
    'proveedor': ProveedorSalida, 'proveedores': ProveedoresSalida, 'oferta': OfertaSalida, 'ofertas': OfertasSalida,
}
