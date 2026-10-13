from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

TipoComercio = Literal['FORMAL_ABARROTES', 'FORMAL_MINISUPER', 'FORMAL_RECAUDERIA',
                       'INFORMAL_TIANGUIS', 'INFORMAL_FIJO', 'INFORMAL_AMBULANTE']


class ComerciosConsulta(BaseConsulta):
    texto: str | None = Field(None, description='Busca en el nombre o la dirección')
    zona_id: int | None = Field(None, ge=1)
    estado_registro: Literal['PENDIENTE', 'VERIFICADO', 'SUSPENDIDO', 'RECHAZADO'] | None = None
    tipo_comercio: TipoComercio | None = None
    sector: Literal['Formal', 'Informal'] | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class ComercioEntrada(BaseEntrada):
    nombre_comercio: str = Field(min_length=3, max_length=255)
    tipo_comercio: TipoComercio
    direccion: str = Field(min_length=3, max_length=255)
    colonia: str | None = Field(None, max_length=100)
    municipio: str = Field(min_length=2, max_length=100)
    estado: str = Field('Nuevo León', max_length=100)
    latitud: Decimal | None = Field(None, ge=-90, le=90)
    longitud: Decimal | None = Field(None, ge=-180, le=180)
    zona_id: int | None = Field(None, ge=1, description='Si se omite, se asigna por ubicación')
    telefono_comercio: str | None = Field(None, max_length=20)
    horario_apertura: time | None = None
    horario_cierre: time | None = None
    descripcion: str | None = Field(None, max_length=1000)


class ValidacionEntrada(BaseEntrada):
    estado: Literal['VERIFICADO', 'RECHAZADO', 'SUSPENDIDO']
    observaciones: str | None = Field(None, max_length=500)


class LocalizarConsulta(BaseConsulta):
    latitud: Decimal = Field(ge=-90, le=90)
    longitud: Decimal = Field(ge=-180, le=180)


class ArchivosConsulta(BaseConsulta):
    categoria: str | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


# ---------------------------------------------------------------- salidas
class ComercioSalida(Salida):
    id: str
    nombre_comercio: str
    tipo_comercio: TipoComercio
    sector: Literal['Formal', 'Informal', 'Mayorista']
    direccion: str
    colonia: str | None = None
    municipio: str
    estado: str
    zona_id: int | None = None
    zona: str | None = None
    estado_registro: Literal['PENDIENTE', 'VERIFICADO', 'SUSPENDIDO', 'RECHAZADO']
    usuario_id: str
    latitud: float | None = None
    longitud: float | None = None
    telefono_comercio: str | None = None
    horario_apertura: time | None = None
    horario_cierre: time | None = None
    descripcion: str | None = None
    fecha_verificacion: datetime | None = None
    creado_en: datetime | None = None


class ComerciosSalida(Salida):
    paginacion: Paginacion
    items: list[ComercioSalida]


class ZonaSalida(Salida):
    id: int
    nombre: str
    municipio: str
    estado: str
    latitud_centro: float
    longitud_centro: float
    radio_km: float
    poblacion: int


class ZonasSalida(Salida):
    origen: Literal['cache', 'postgres']
    zonas: list[ZonaSalida]


class ZonaCercana(Salida):
    zona_id: int
    zona: str
    distancia_km: float
    radio_km: float


class LocalizacionSalida(Salida):
    zona: ZonaSalida
    cercanas: list[ZonaCercana]


class ArchivoSalida(Salida):
    id: str
    nombre: str
    tipo_mime: str | None = None
    tamano_bytes: int
    categoria: str | None = None
    entidad: str | None = None
    entidad_id: str | None = None
    descripcion: str | None = None
    usuario_id: str | None = None
    sha256: str | None = None
    subido_en: datetime


class ArchivosSalida(Salida):
    paginacion: Paginacion
    archivos: list[ArchivoSalida]


CONTRATOS_XML = {
    'comercio_entrada': ComercioEntrada, 'validacion_entrada': ValidacionEntrada,
    'comercio': ComercioSalida, 'comercios': ComerciosSalida, 'zonas': ZonasSalida,
    'localizacion': LocalizacionSalida, 'archivo': ArchivoSalida, 'archivos': ArchivosSalida,
}
