from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

Estado = Literal['BORRADOR', 'ENVIADO', 'ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO', 'ENTREGADO',
                 'CANCELADO', 'RECHAZADO']


class PedidosConsulta(BaseConsulta):
    estado: Estado | None = None
    comercio_id: str | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class PartidaEntrada(BaseEntrada):
    producto_id: int = Field(ge=1)
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class PedidoEntrada(BaseEntrada):
    comercio_id: str = Field(description='UUID del comercio que pide')
    proveedor_id: str = Field(description='UUID del proveedor')
    partidas: list[PartidaEntrada] = Field(min_length=1, max_length=100)
    notas: str | None = Field(None, max_length=500)


class AccionEntrada(BaseEntrada):
    comentario: str | None = Field(None, max_length=500, description='Obligatorio al rechazar')


class EstadisticasConsulta(BaseConsulta):
    dias: int = Field(90, ge=1, le=365)
    zona_id: int | None = Field(None, ge=1)


# ---------------------------------------------------------------- salidas
class PartidaSalida(Salida):
    id: int
    producto_id: int
    producto: str
    unidad_medida: str
    cantidad: float
    precio_unitario: float
    subtotal: float


class Transicion(Salida):
    accion: str
    de: Estado
    a: Estado


class PedidoSalida(Salida):
    id: str
    folio: str
    estado: Estado
    estado_legible: str
    comercio_id: str
    comercio: str
    proveedor_id: str
    proveedor: str
    subtotal: float
    pedido_minimo: float
    fecha_envio: datetime | None = None
    fecha_entrega_estimada: date | None = None
    actualizado: datetime | None = None
    fecha_respuesta: datetime | None = None
    fecha_entrega_real: datetime | None = None
    motivo_rechazo: str | None = None
    comision_plataforma: float | None = None
    notas: str | None = None
    partidas: list[PartidaSalida] | None = None
    acciones: list[str] | None = Field(None, description='Transiciones que puede ejecutar el usuario del token')
    transicion: Transicion | None = None


class PedidosSalida(Salida):
    paginacion: Paginacion
    pedidos: list[PedidoSalida]


class PasoHistorial(Salida):
    de: Estado | None = None
    a: Estado
    a_legible: str
    usuario_id: str | None = None
    comentario: str | None = None
    fecha: datetime


class HistorialSalida(Salida):
    pedido_id: str
    folio: str
    historial: list[PasoHistorial]
    eventos: list[dict] = Field(description='Documentos de MongoDB (eventos_pedido)')


class DesempenoProveedor(Salida):
    proveedor_id: str
    proveedor: str | None = None
    pedidos: int
    entregados: int
    rechazados: int
    monto_total: float
    horas_respuesta_prom: float | None = None
    horas_entrega_prom: float | None = None
    tasa_rechazo: float = Field(description='Porcentaje de pedidos rechazados')


class DesempenoSalida(Salida):
    dias: int
    proveedores: list[DesempenoProveedor]


class ProductoPedido(Salida):
    producto_id: int
    producto: str
    cantidad: float
    pedidos: int


class ProductosPedidosSalida(Salida):
    dias: int
    zona_id: int | None = None
    productos: list[ProductoPedido]


CONTRATOS_XML = {
    'pedido_entrada': PedidoEntrada, 'partida_entrada': PartidaEntrada, 'accion_entrada': AccionEntrada,
    'pedido': PedidoSalida, 'pedidos': PedidosSalida, 'historial': HistorialSalida, 'desempeno': DesempenoSalida,
    'productos_pedidos': ProductosPedidosSalida,
}
