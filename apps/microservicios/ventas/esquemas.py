from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

MetodoPago = Literal['EFECTIVO', 'TARJETA', 'TRANSFERENCIA', 'FIADO', 'OTRO']
EstadoVenta = Literal['REGISTRADA', 'DEVUELTA_PARCIAL', 'DEVUELTA']


class PartidaVenta(BaseEntrada):
    producto_id: int | None = Field(None, ge=1)
    inventario_id: int | None = Field(None, ge=1, description='Alternativa a producto_id')
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    precio_unitario: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2,
                                            description='Si se omite: precio promocional vigente o precio de venta')

    @model_validator(mode='after')
    def _producto(self):
        if not (self.producto_id or self.inventario_id):
            raise ValueError('indica producto_id o inventario_id')
        return self


class VentaEntrada(BaseEntrada):
    comercio_id: str
    partidas: list[PartidaVenta] = Field(min_length=1, max_length=100)
    metodo_pago: MetodoPago = 'EFECTIVO'
    origen: Literal['web', 'android', 'escritorio', 'api'] = 'web'
    id_cliente: str | None = Field(None, min_length=8, max_length=64,
                                   description='UUID generado por la app: la misma venta no se registra dos veces')
    fecha_venta: datetime | None = Field(None, description='Para ventas capturadas sin conexión; por omisión, ahora')


class PartidaDevolucion(BaseEntrada):
    partida_id: int = Field(ge=1, description='id de la partida de la venta')
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class DevolucionEntrada(BaseEntrada):
    motivo: str = Field(min_length=3, max_length=255)
    partidas: list[PartidaDevolucion] | None = Field(None, max_length=100, description='Si se omite, se devuelve todo')


class VentasConsulta(BaseConsulta):
    comercio_id: str
    desde: date | None = None
    hasta: date | None = None
    metodo_pago: MetodoPago | None = None
    estado: EstadoVenta | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class ResumenConsulta(BaseConsulta):
    comercio_id: str
    periodo: Literal['dia', 'semana', 'mes'] = 'dia'
    dias: int = Field(30, ge=1, le=366)


class ProductosConsulta(BaseConsulta):
    comercio_id: str
    dias: int = Field(30, ge=1, le=366)
    limite: int = Field(10, ge=1, le=100)


# ---------------------------------------------------------------- salidas
class PartidaSalida(Salida):
    id: int
    producto_id: int
    producto: str
    unidad_medida: str
    cantidad: float
    precio_unitario: float
    subtotal: float
    cantidad_devuelta: float


class DevolucionSalida(Salida):
    id: int
    motivo: str
    total: float
    fecha: datetime | None = None


class VentaSalida(Salida):
    id: str
    folio: str | None = None
    comercio_id: str
    comercio: str
    total: float
    total_devuelto: float
    metodo_pago: MetodoPago
    estado: EstadoVenta
    origen: str
    id_cliente: str | None = None
    fecha_venta: datetime
    partidas: list[PartidaSalida] | None = None
    devoluciones: list[DevolucionSalida] | None = None
    duplicada: bool | None = Field(None, description='true si el id_cliente ya existía y no se volvió a registrar')


class VentasSalida(Salida):
    paginacion: Paginacion
    total_periodo: float
    ventas: list[VentaSalida]


class Comprobante(Salida):
    folio: str
    venta_id: str
    comercio: str
    direccion: str | None = None
    rfc: str | None = None
    fecha: datetime
    metodo_pago: str
    partidas: list[PartidaSalida]
    total: float
    total_devuelto: float
    leyenda: str
    huella_sha256: str
    texto: str


class PuntoResumen(Salida):
    periodo: date
    ventas: int
    total: float
    ticket_promedio: float
    devuelto: float


class ResumenSalida(Salida):
    comercio_id: str
    periodo: str
    dias: int
    ventas: int
    total: float
    ticket_promedio: float
    serie: list[PuntoResumen]


class ProductoVendido(Salida):
    producto_id: int
    producto: str
    unidades: float
    importe: float
    ventas: int


class ProductosSalida(Salida):
    comercio_id: str
    dias: int
    productos: list[ProductoVendido]


CONTRATOS_XML = {
    'venta_entrada': VentaEntrada, 'devolucion_entrada': DevolucionEntrada,
    'venta': VentaSalida, 'ventas': VentasSalida, 'comprobante': Comprobante, 'resumen': ResumenSalida,
    'productos': ProductosSalida,
}
