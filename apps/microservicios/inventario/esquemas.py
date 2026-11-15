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
    referencia: str | None = Field(None, max_length=100, description='Si se repite, el movimiento no se aplica dos veces')


class MovimientoLote(BaseEntrada):
    inventario_id: int | None = Field(None, ge=1)
    producto_id: int | None = Field(None, ge=1, description='Alternativa a inventario_id')
    tipo: Literal['ENTRADA', 'SALIDA', 'AJUSTE']
    cantidad: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    motivo: str | None = Field(None, max_length=255)

    @model_validator(mode='after')
    def _renglon(self):
        if not (self.inventario_id or self.producto_id):
            raise ValueError('indica inventario_id o producto_id')
        return self


class LoteEntrada(BaseEntrada):
    referencia: str = Field(min_length=3, max_length=100, description='p. ej. venta:<uuid>, sync:<operacion>')
    pedido_id: str | None = Field(None, description='Si los movimientos son la recepción de un pedido')
    movimientos: list[MovimientoLote] = Field(min_length=1, max_length=200)


class ReservaEntrada(BaseEntrada):
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    motivo: str | None = Field(None, max_length=255)
    referencia: str | None = Field(None, max_length=100)
    minutos: int | None = Field(None, ge=1, le=10080, description='Por omisión RESERVA_MINUTOS (ms-configuracion)')


class TransferenciaEntrada(BaseEntrada):
    origen_id: int = Field(ge=1, description='Renglón de inventario de donde sale')
    destino_comercio_id: str = Field(description='Sucursal (comercio del mismo dueño) a la que llega')
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    motivo: str | None = Field(None, max_length=255)


class SucursalesConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1)


class MovimientosConsulta(BaseConsulta):
    tipo: Literal['ENTRADA', 'SALIDA', 'AJUSTE'] | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=200)



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
    referencia: str | None = None
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


class LoteSalida(Salida):
    referencia: str
    comercio_id: str
    ya_aplicado: bool
    movimientos: list[MovimientoSalida]


class ReservaSalida(Salida):
    id: int
    inventario_id: int
    producto: str
    cantidad: float
    motivo: str | None = None
    referencia: str | None = None
    estado: Literal['ACTIVA', 'CONSUMIDA', 'LIBERADA', 'VENCIDA']
    expira: datetime
    creada: datetime | None = None
    existencia: float
    reservado_total: float
    disponible: float


class ReservasSalida(Salida):
    inventario_id: int
    existencia: float
    reservado_total: float
    disponible: float
    reservas: list[ReservaSalida]


class TransferenciaSalida(Salida):
    id: int
    origen_id: int
    origen_comercio: str
    destino_id: int
    destino_comercio: str
    producto: str
    cantidad: float
    motivo: str | None = None
    fecha: datetime | None = None
    existencia_origen: float | None = None
    existencia_destino: float | None = None


class TransferenciasSalida(Salida):
    comercio_id: str
    transferencias: list[TransferenciaSalida]


class Sucursal(Salida):
    comercio_id: str
    comercio: str
    zona: str | None = None
    productos: int
    bajo: int
    agotado: int
    existencia_producto: float | None = None
    estado_producto: str | None = None


class SucursalesSalida(Salida):
    producto_id: int | None = None
    total_producto: float | None = None
    sucursales: list[Sucursal]


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


CONTRATOS_XML = {
    'renglon_entrada': RenglonEntrada, 'limites_entrada': LimitesEntrada, 'movimiento_entrada': MovimientoEntrada,
    'renglon': RenglonSalida, 'inventario': InventarioSalida, 'movimiento': MovimientoSalida,
    'movimientos': MovimientosSalida, 'faltantes': FaltantesSalida, 'importacion': ImportacionSalida,
    'importaciones': ImportacionesSalida,
    'lote_entrada': LoteEntrada, 'reserva_entrada': ReservaEntrada, 'transferencia_entrada': TransferenciaEntrada,
    'lote': LoteSalida, 'reserva': ReservaSalida, 'reservas': ReservasSalida, 'transferencia': TransferenciaSalida,
    'transferencias': TransferenciasSalida, 'sucursales': SucursalesSalida,
}
