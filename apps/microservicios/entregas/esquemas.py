from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

EstadoEntrega = Literal['PROGRAMADA', 'ASIGNADA', 'EN_RUTA', 'ENTREGADA', 'CON_INCIDENCIA', 'CANCELADA']
TipoIncidencia = Literal['RETRASO', 'PRODUCTO_DANADO', 'FALTANTE', 'DIRECCION', 'RECHAZO', 'OTRO']


class EntregaEntrada(BaseEntrada):
    pedido_id: str = Field(description='Pedido ACEPTADO o EN_PREPARACION del proveedor')
    fecha_estimada: date | None = Field(None, description='Por omisión, la fecha estimada del pedido')
    responsable_id: str | None = Field(None, description='Operador de la empresa que la llevará')
    responsable_nombre: str | None = Field(None, max_length=150)
    vehiculo: str | None = Field(None, max_length=100)


class AsignacionEntrada(BaseEntrada):
    responsable_id: str | None = None
    responsable_nombre: str | None = Field(None, max_length=150)
    vehiculo: str | None = Field(None, max_length=100)
    fecha_estimada: date | None = None


class UbicacionEntrada(BaseEntrada):
    comentario: str | None = Field(None, max_length=500)
    latitud: Decimal | None = Field(None, ge=-90, le=90)
    longitud: Decimal | None = Field(None, ge=-180, le=180)


class ConfirmacionEntrada(BaseEntrada):
    codigo: str = Field(min_length=6, max_length=12, description='Código del QR que muestra el repartidor')
    recibido_por: str = Field(min_length=2, max_length=150)
    comentario: str | None = Field(None, max_length=500)


class IncidenciaEntrada(BaseEntrada):
    tipo: TipoIncidencia
    descripcion: str = Field(min_length=5, max_length=500)


class ResolucionEntrada(BaseEntrada):
    resolucion: str = Field(min_length=5, max_length=500)


class EntregasConsulta(BaseConsulta):
    estado: EstadoEntrega | None = None
    fecha: date | None = Field(None, description='Fecha estimada')
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


# ---------------------------------------------------------------- salidas
class EventoSalida(Salida):
    estado: str
    comentario: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    usuario_id: str | None = None
    fecha: datetime | None = None


class IncidenciaSalida(Salida):
    id: int
    entrega_id: str
    tipo: TipoIncidencia
    descripcion: str
    estado: Literal['ABIERTA', 'RESUELTA']
    resolucion: str | None = None
    reportada_por: str | None = None
    fecha: datetime | None = None
    resuelta: datetime | None = None


class EntregaSalida(Salida):
    id: str
    pedido_id: str
    folio_pedido: str | None = None
    estado_pedido: str | None = None
    proveedor_id: str
    proveedor: str
    comercio_id: str
    comercio: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    estado: EstadoEntrega
    responsable_id: str | None = None
    responsable_nombre: str | None = None
    vehiculo: str | None = None
    fecha_estimada: date | None = None
    fecha_salida: datetime | None = None
    fecha_entrega: datetime | None = None
    recibido_por: str | None = None
    evidencia_archivo_id: str | None = None
    incidencias_abiertas: int
    eventos: list[EventoSalida] | None = None
    incidencias: list[IncidenciaSalida] | None = None


class EntregasSalida(Salida):
    paginacion: Paginacion
    entregas: list[EntregaSalida]


class QrSalida(Salida):
    entrega_id: str
    codigo: str
    contenido_qr: str
    instrucciones: str


CONTRATOS_XML = {
    'entrega_entrada': EntregaEntrada, 'asignacion_entrada': AsignacionEntrada, 'ubicacion_entrada': UbicacionEntrada,
    'confirmacion_entrada': ConfirmacionEntrada, 'incidencia_entrada': IncidenciaEntrada,
    'resolucion_entrada': ResolucionEntrada,
    'entrega': EntregaSalida, 'entregas': EntregasSalida, 'incidencia': IncidenciaSalida, 'qr': QrSalida,
}
