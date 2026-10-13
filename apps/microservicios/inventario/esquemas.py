from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida


class InventarioConsulta(BaseConsulta):
    estado: Literal['DISPONIBLE', 'BAJO', 'AGOTADO'] | None = None
    categoria_id: int | None = Field(None, ge=1)
    texto: str | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(50, ge=1, le=200)


class RenglonEntrada(BaseEntrada):
    producto_id: int = Field(ge=1)
    existencia: Decimal = Field(0, ge=0, max_digits=10, decimal_places=2)
    stock_minimo: Decimal = Field(0, ge=0, max_digits=10, decimal_places=2)
    stock_maximo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    precio_venta: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)

    @model_validator(mode='after')
    def _maximo(self):
        if self.stock_maximo is not None and self.stock_maximo < self.stock_minimo:
            raise ValueError('stock_maximo debe ser mayor o igual que stock_minimo')
        return self


class LimitesEntrada(BaseEntrada):
    stock_minimo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    stock_maximo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)


class MovimientoEntrada(BaseEntrada):
    tipo: Literal['ENTRADA', 'SALIDA', 'AJUSTE'] = Field(description='AJUSTE fija la existencia al conteo físico')
    cantidad: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    motivo: str | None = Field(None, max_length=255)


class MovimientosConsulta(BaseConsulta):
    tipo: Literal['ENTRADA', 'SALIDA', 'AJUSTE'] | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=200)


class DisponibilidadConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1)
    texto: str | None = Field(None, description='Parte del nombre del producto')
    zona_id: int | None = Field(None, ge=1)
    categoria_id: int | None = Field(None, ge=1)
    con_existencia: bool = False
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=100)


# ---------------------------------------------------------------- salidas
class MovimientoSalida(Salida):
    id: int
    inventario_id: int
    tipo: Literal['ENTRADA', 'SALIDA', 'AJUSTE']
    cantidad: float
    existencia_anterior: float
    existencia_nueva: float
    motivo: str | None = None
    pedido_id: str | None = None
    usuario_id: str | None = None
    fecha: datetime
    estado_inventario: Literal['DISPONIBLE', 'BAJO', 'AGOTADO'] | None = None


class RenglonSalida(Salida):
    id: int
    comercio_id: str
    producto_id: int
    producto: str
    categoria: str
    unidad_medida: str
    existencia: float
    stock_minimo: float
    stock_maximo: float | None = None
    precio_venta: float | None = None
    estado: Literal['DISPONIBLE', 'BAJO', 'AGOTADO']
    cantidad_sugerida: float
    actualizado: datetime | None = None
    movimientos: list[MovimientoSalida] | None = None
    proveedores: int | None = Field(None, description='Sólo en faltantes: proveedores que lo surten en la zona')
    precio_mayoreo_min: float | None = None


class ResumenInventario(Salida):
    comercio_id: str
    comercio: str
    productos: int
    bajo: int
    agotado: int
    valor_inventario: float


class InventarioSalida(Salida):
    paginacion: Paginacion
    resumen: ResumenInventario
    renglones: list[RenglonSalida]


class MovimientosSalida(Salida):
    paginacion: Paginacion
    movimientos: list[MovimientoSalida]


class FaltantesSalida(Salida):
    comercio_id: str
    faltantes: list[RenglonSalida]


class ErrorFila(Salida):
    fila: int
    producto: str | None = None
    error: str


class ImportacionSalida(Salida):
    id: str | None = None
    schema_version: int | None = None
    comercio_id: str
    usuario_id: str
    archivo_id: str
    nombre_archivo: str
    filas_total: int
    agregados: int
    actualizados: int
    con_error: int
    errores: list[ErrorFila]
    fecha: datetime


class ImportacionesSalida(Salida):
    comercio_id: str
    importaciones: list[ImportacionSalida]


class Disponible(Salida):
    producto_id: int
    producto: str
    unidad_medida: str
    comercio: str
    sector: str
    zona: str | None = None
    existencia: float
    estado: Literal['DISPONIBLE', 'BAJO', 'AGOTADO']
    precio: float | None = None
    actualizado: datetime | None = None


class DisponibilidadSalida(Salida):
    paginacion: Paginacion
    renglones: list[Disponible]
    origen: Literal['cache', 'postgres']


CONTRATOS_XML = {
    'renglon_entrada': RenglonEntrada, 'limites_entrada': LimitesEntrada, 'movimiento_entrada': MovimientoEntrada,
    'renglon': RenglonSalida, 'inventario': InventarioSalida, 'movimiento': MovimientoSalida,
    'movimientos': MovimientosSalida, 'faltantes': FaltantesSalida, 'importacion': ImportacionSalida,
    'importaciones': ImportacionesSalida, 'disponibilidad': DisponibilidadSalida,
}
