from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

TipoEvento = Literal['CREACION', 'LECTURA', 'ACTUALIZACION', 'ELIMINACION', 'CAMBIO_ESTADO', 'LOGIN', 'LOGOUT',
                     'ERROR']


class EventosConsulta(BaseConsulta):
    servicio: str | None = Field(None, description='ms-pedidos, ms-ventas, web, escritorio...')
    usuario_id: str | None = None
    entidad: str | None = None
    entidad_id: str | None = None
    tipo_evento: TipoEvento | None = None
    correlation_id: str | None = None
    texto: str | None = Field(None, max_length=100, description='Busca en la descripción')
    desde: str | None = Field(None, description='AAAA-MM-DD')
    hasta: str | None = Field(None, description='AAAA-MM-DD')
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=200)


class RegistrosConsulta(BaseConsulta):
    entidad: str | None = None
    entidad_id: str | None = None
    tipo_evento: TipoEvento | None = None
    usuario_id: str | None = None
    desde: str | None = Field(None, description='AAAA-MM-DD')
    hasta: str | None = Field(None, description='AAAA-MM-DD')
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=200)


class ResumenConsulta(BaseConsulta):
    dias: int = Field(7, ge=1, le=365)


class EventoEntrada(BaseEntrada):
    """Evento sensible ocurrido en un cliente (app de escritorio o Android) o en un sistema externo."""
    tipo_evento: TipoEvento
    entidad: str = Field(min_length=2, max_length=100)
    entidad_id: str | None = Field(None, max_length=100)
    descripcion: str = Field(min_length=3, max_length=500)
    origen: Literal['escritorio', 'android', 'web', 'externo'] = 'externo'
    datos: dict | None = Field(None, description='Detalle libre del evento (se guarda como está)')


class ConciliacionEntrada(BaseEntrada):
    dias: int = Field(7, ge=1, le=90, description='Revisa los eventos de PostgreSQL de los últimos N días')


# ---------------------------------------------------------------- salidas
class Cambio(Salida):
    campo: str
    antes: str | None = Field(None, description="Valor anterior como texto")
    despues: str | None = Field(None, description="Valor nuevo como texto")


class EventoSalida(Salida):
    id: str
    id_postgres: int | None = None
    fecha: datetime
    servicio: str | None = None
    correlation_id: str | None = None
    usuario_id: str | None = None
    rol: str | None = None
    tipo_evento: str
    entidad: str
    entidad_id: str | None = None
    descripcion: str | None = None
    metodo: str | None = None
    ruta: str | None = None
    ip: str | None = None
    cambios: list[Cambio]


class EventosSalida(Salida):
    paginacion: Paginacion
    eventos: list[EventoSalida]


class RegistroSalida(Salida):
    id: int
    fecha: datetime
    usuario_id: str | None = None
    tipo_evento: str
    entidad: str
    entidad_id: str | None = None
    descripcion: str | None = None
    datos_anteriores: dict | None = None
    datos_nuevos: dict | None = None
    ip: str | None = None


class RegistrosSalida(Salida):
    paginacion: Paginacion
    registros: list[RegistroSalida]


class PasoTraza(Salida):
    fecha: datetime
    tipo: Literal['peticion', 'evento']
    servicio: str | None = None
    metodo: str | None = None
    ruta: str | None = None
    status: int | None = None
    duracion_ms: float | None = None
    usuario_id: str | None = None
    entidad: str | None = None
    entidad_id: str | None = None
    tipo_evento: str | None = None
    descripcion: str | None = None
    cambios: list[Cambio] | None = None


class TrazaSalida(Salida):
    correlation_id: str
    servicios: list[str]
    peticiones: int
    eventos: int
    duracion_total_ms: float | None = None
    pasos: list[PasoTraza]


class HistorialSalida(Salida):
    entidad: str
    entidad_id: str
    total: int
    eventos: list[EventoSalida]


class ResumenRenglon(Salida):
    servicio: str | None = None
    tipo_evento: str
    total: int
    usuarios: int
    ultimo: datetime


class ResumenSalida(Salida):
    dias: int
    total: int
    renglones: list[ResumenRenglon]


class ConciliacionSalida(Salida):
    dias: int
    revisados: int
    faltaban: int
    copiados: int


CONTRATOS_XML = {
    'evento_entrada': EventoEntrada, 'conciliacion_entrada': ConciliacionEntrada,
    'evento': EventoSalida, 'eventos': EventosSalida, 'registros': RegistrosSalida, 'traza': TrazaSalida,
    'historial': HistorialSalida, 'resumen': ResumenSalida, 'conciliacion': ConciliacionSalida,
}
