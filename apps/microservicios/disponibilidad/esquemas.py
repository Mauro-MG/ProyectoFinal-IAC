from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta
from abasto_api.modelos_comunes import Paginacion, Salida


class DisponibilidadConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1)
    texto: str | None = Field(None, description='Parte del nombre del producto')
    zona_id: int | None = Field(None, ge=1)
    categoria_id: int | None = Field(None, ge=1)
    con_existencia: bool = False
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=100)


class ZonaConsulta(BaseConsulta):
    categoria_id: int | None = Field(None, ge=1)
    solo_canasta: bool = False


class ProveedoresConsulta(BaseConsulta):
    producto_id: int = Field(ge=1)
    zona_id: int | None = Field(None, ge=1)
    cantidad: float | None = Field(None, gt=0, description='Cantidad que se necesita surtir')


class CambiosConsulta(BaseConsulta):
    desde: datetime = Field(description='ISO 8601; regresa lo que cambió después de esta fecha')
    zona_id: int | None = Field(None, ge=1)
    limite: int = Field(500, ge=1, le=2000)


# ---------------------------------------------------------------- salidas
class Disponible(Salida):
    producto_id: int
    producto: str
    unidad_medida: str
    comercio_id: str
    comercio: str
    sector: str
    zona_id: int | None = None
    zona: str | None = None
    existencia: float
    reservada: float
    disponible: float
    estado: Literal['DISPONIBLE', 'BAJO', 'AGOTADO']
    precio: float | None = None
    actualizado: datetime | None = None


class DisponibilidadSalida(Salida):
    paginacion: Paginacion
    renglones: list[Disponible]
    origen: Literal['cache', 'postgres']


class RenglonComercio(Salida):
    inventario_id: int
    producto_id: int
    producto: str
    unidad_medida: str
    existencia: float
    reservada: float
    disponible: float
    estado: str
    precio: float | None = None
    actualizado: datetime | None = None


class ComercioSalida(Salida):
    comercio_id: str
    comercio: str
    zona: str | None = None
    productos: int
    agotados: int
    renglones: list[RenglonComercio]


class RenglonZona(Salida):
    producto_id: int
    producto: str
    canasta_basica: bool
    comercios_con_existencia: int
    disponible_total: float
    precio_minimo: float | None = None
    precio_promedio: float | None = None
    proveedores_con_existencia: int
    tiempo_surtido_dias: int | None = Field(None, description='Menor tiempo de entrega de un proveedor que surte la zona')


class ZonaSalida(Salida):
    zona_id: int
    zona: str
    origen: Literal['cache', 'postgres']
    productos: list[RenglonZona]


class ProveedorDisponible(Salida):
    proveedor_id: str
    proveedor: str
    existencia_disponible: float
    cantidad_minima: float
    precio_mayoreo: float
    cubre_zona: bool | None = None
    alcanza: bool | None = None
    tiempo_entrega_dias: int
    fecha_estimada: datetime


class ProveedoresSalida(Salida):
    producto_id: int
    zona_id: int | None = None
    total_disponible: float
    tiempo_surtido_dias: int | None = None
    proveedores: list[ProveedorDisponible]


class Cambio(Salida):
    inventario_id: int
    comercio_id: str
    producto_id: int
    existencia: float
    reservada: float
    disponible: float
    estado: str
    precio: float | None = None
    activo: bool
    actualizado: datetime


class CambiosSalida(Salida):
    desde: datetime
    hasta: datetime
    total: int
    completo: bool
    cambios: list[Cambio]


CONTRATOS_XML = {
    'disponibilidad': DisponibilidadSalida, 'comercio': ComercioSalida, 'zona': ZonaSalida,
    'proveedores': ProveedoresSalida, 'cambios': CambiosSalida,
}
