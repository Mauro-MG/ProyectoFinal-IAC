from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

EstadoSolicitud = Literal['ABIERTA', 'CERRADA', 'ADJUDICADA', 'CANCELADA']


class Necesidad(BaseEntrada):
    producto_id: int = Field(ge=1)
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class SolicitudEntrada(BaseEntrada):
    comercio_id: str = Field(description='Comercio que solicita (define la zona)')
    titulo: str = Field(min_length=3, max_length=150)
    consolidada: bool = Field(False, description='Permite que otros comercios de la zona sumen sus necesidades')
    fecha_limite: datetime | None = Field(None, description='Por omisión, hoy + COTIZACION_DIAS_LIMITE')
    notas: str | None = Field(None, max_length=500)
    necesidades: list[Necesidad] = Field(min_length=1, max_length=100)


class NecesidadesEntrada(BaseEntrada):
    comercio_id: str
    necesidades: list[Necesidad] = Field(min_length=1, max_length=100)


class PartidaCotizada(BaseEntrada):
    producto_id: int = Field(ge=1)
    precio_unitario: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    cantidad_disponible: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class CotizacionEntrada(BaseEntrada):
    tiempo_entrega_dias: int = Field(ge=0, le=30)
    vigencia: date
    notas: str | None = Field(None, max_length=500)
    partidas: list[PartidaCotizada] = Field(min_length=1, max_length=100)


class AdjudicacionEntrada(BaseEntrada):
    cotizacion_id: str


class SolicitudesConsulta(BaseConsulta):
    estado: EstadoSolicitud | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class OrdenesConsulta(BaseConsulta):
    comercio_id: str | None = None
    estado: Literal['GENERADA', 'CONVERTIDA', 'CANCELADA'] | None = None


# ---------------------------------------------------------------- salidas
class NecesidadSalida(Salida):
    producto_id: int
    producto: str
    unidad_medida: str
    cantidad: float
    comercios: int


class Participante(Salida):
    comercio_id: str
    comercio: str
    productos: int


class PartidaCotizadaSalida(Salida):
    producto_id: int
    producto: str
    precio_unitario: float
    cantidad_disponible: float


class CotizacionSalida(Salida):
    id: str
    proveedor_id: str
    proveedor: str
    tiempo_entrega_dias: int
    vigencia: date
    notas: str | None = None
    estado: Literal['ENVIADA', 'ADJUDICADA', 'DESCARTADA']
    fecha: datetime | None = None
    partidas: list[PartidaCotizadaSalida]


class SolicitudSalida(Salida):
    id: str
    folio: str | None = None
    titulo: str
    zona_id: int
    zona: str
    consolidada: bool
    estado: EstadoSolicitud
    fecha_limite: datetime
    notas: str | None = None
    creada_por_mi: bool
    fecha: datetime | None = None
    participantes: list[Participante]
    necesidades: list[NecesidadSalida]
    cotizaciones: list[CotizacionSalida] | None = None


class SolicitudesSalida(Salida):
    paginacion: Paginacion
    solicitudes: list[SolicitudSalida]


class ComparacionRenglon(Salida):
    cotizacion_id: str
    proveedor: str
    tiempo_entrega_dias: int
    total: float
    productos_cubiertos: int
    productos_solicitados: int
    cobertura_pct: float
    pedido_minimo: float
    cumple_minimo: bool
    vigente: bool
    calificacion: float | None = None
    recomendada: bool


class MejorPrecio(Salida):
    producto_id: int
    producto: str
    cantidad: float
    proveedor: str | None = None
    precio_unitario: float | None = None
    cotizaciones: int


class ComparacionSalida(Salida):
    solicitud_id: str
    criterio: str
    cotizaciones: list[ComparacionRenglon]
    mejores_precios: list[MejorPrecio]


class Sugerido(Salida):
    inventario_id: int
    producto_id: int
    producto: str
    existencia: float
    stock_minimo: float
    cantidad_sugerida: float
    proveedor_id: str | None = None
    proveedor: str | None = None
    precio_mayoreo: float | None = None
    subtotal: float | None = None


class GrupoProveedor(Salida):
    proveedor_id: str
    proveedor: str
    productos: int
    total: float
    pedido_minimo: float
    cumple_minimo: bool
    tiempo_entrega_dias: int


class SugerenciaSalida(Salida):
    comercio_id: str
    productos: list[Sugerido]
    por_proveedor: list[GrupoProveedor]


class PartidaOrdenSalida(Salida):
    producto_id: int
    producto: str
    cantidad: float
    precio_unitario: float
    subtotal: float


class OrdenSalida(Salida):
    id: str
    folio: str | None = None
    solicitud_id: str
    comercio_id: str
    comercio: str
    proveedor_id: str
    proveedor: str
    total: float
    estado: Literal['GENERADA', 'CONVERTIDA', 'CANCELADA']
    pedido_id: str | None = None
    fecha: datetime | None = None
    partidas: list[PartidaOrdenSalida]


class OrdenesSalida(Salida):
    total: int
    ordenes: list[OrdenSalida]


class AdjudicacionSalida(Salida):
    solicitud: SolicitudSalida
    ordenes: list[OrdenSalida]


CONTRATOS_XML = {
    'solicitud_entrada': SolicitudEntrada, 'necesidades_entrada': NecesidadesEntrada,
    'cotizacion_entrada': CotizacionEntrada, 'adjudicacion_entrada': AdjudicacionEntrada,
    'solicitud': SolicitudSalida, 'solicitudes': SolicitudesSalida, 'cotizacion': CotizacionSalida,
    'comparacion': ComparacionSalida, 'sugerencia': SugerenciaSalida, 'orden': OrdenSalida, 'ordenes': OrdenesSalida,
    'adjudicacion': AdjudicacionSalida,
}
