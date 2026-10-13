from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

Tipo = Literal['pedido', 'stock_bajo', 'precio_atipico', 'comercio', 'importacion', 'sistema']


class NotificacionesConsulta(BaseConsulta):
    solo_no_leidas: bool = False
    tipo: Tipo | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class Entidad(BaseEntrada):
    tipo: str = Field(max_length=40)
    id: str = Field(max_length=64)


class LoteEntrada(BaseEntrada):
    usuarios: list[str] = Field(min_length=1, max_length=200, description='UUID de los destinatarios')
    tipo: Tipo
    titulo: str = Field(min_length=1, max_length=200)
    mensaje: str = Field(min_length=1, max_length=1000)
    url: str | None = Field(None, max_length=300)
    entidad: Entidad | None = None
    prioridad: Literal['normal', 'alta'] = 'normal'
    origen: str = Field('servicio', max_length=40)


class NotificacionEntrada(BaseEntrada):
    usuario_id: str
    tipo: Tipo = 'sistema'
    titulo: str = Field(min_length=1, max_length=200)
    mensaje: str = Field(min_length=1, max_length=1000)
    url: str | None = Field(None, max_length=300)
    prioridad: Literal['normal', 'alta'] = 'normal'


class LecturaEntrada(BaseEntrada):
    leida: bool


class ResumenConsulta(BaseConsulta):
    dias: int = Field(30, ge=1, le=365)
    todos: bool = Field(False, description='Sólo administración: todas las cuentas')


# ---------------------------------------------------------------- salidas
class EntidadSalida(Salida):
    tipo: str
    id: str


class NotificacionSalida(Salida):
    id: str
    usuario_id: str
    tipo: Tipo
    titulo: str
    mensaje: str
    url: str | None = None
    entidad: EntidadSalida | None = None
    prioridad: Literal['normal', 'alta']
    leida: bool
    origen: str | None = None
    creada_en: datetime


class NotificacionesSalida(Salida):
    paginacion: Paginacion
    notificaciones: list[NotificacionSalida]
    no_leidas: int


class ContadorSalida(Salida):
    usuario_id: str
    no_leidas: int


class LoteSalida(Salida):
    creadas: int
    ids: list[str]


class ResumenTipo(Salida):
    tipo: str
    total: int
    no_leidas: int
    ultima: datetime


class ResumenSalida(Salida):
    dias: int
    resumen: list[ResumenTipo]


CONTRATOS_XML = {
    'lectura_entrada': LecturaEntrada, 'notificacion_entrada': NotificacionEntrada, 'lote_entrada': LoteEntrada,
    'notificacion': NotificacionSalida, 'notificaciones': NotificacionesSalida, 'contador': ContadorSalida,
    'lote': LoteSalida, 'resumen': ResumenSalida,
}
