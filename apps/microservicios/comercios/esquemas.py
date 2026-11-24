from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

TipoComercio = Literal['FORMAL_ABARROTES', 'FORMAL_MINISUPER', 'FORMAL_RECAUDERIA',
                       'INFORMAL_TIANGUIS', 'INFORMAL_FIJO', 'INFORMAL_AMBULANTE']


class ComerciosConsulta(BaseConsulta):
    texto: str | None = Field(None, description='Busca en el nombre, la dirección o la razón social')
    giro: str | None = Field(None, max_length=100)
    municipio: str | None = Field(None, max_length=100)
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
    dias_operacion: list[Literal['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB', 'DOM']] | None = Field(None, max_length=7)
    descripcion: str | None = Field(None, max_length=1000)
    giro: str | None = Field(None, max_length=100, description='Clave del catálogo «giros» de ms-configuracion')
    email_contacto: str | None = Field(None, max_length=255)
    # Datos fiscales opcionales: un comercio informal puede no tenerlos
    rfc: str | None = Field(None, pattern=r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
    razon_social: str | None = Field(None, max_length=255)
    regimen_fiscal: str | None = Field(None, max_length=100)


class ResponsableEntrada(BaseEntrada):
    nombre: str = Field(min_length=3, max_length=150)
    puesto: Literal['DUENO', 'ENCARGADO', 'EMPLEADO'] = 'ENCARGADO'
    telefono: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    usuario_id: str | None = Field(None, description='Si la persona tiene cuenta en AbastoRed')


class FotoEntrada(BaseEntrada):
    documento_id: str = Field(min_length=24, max_length=24, description='id del documento subido a ms-documentos')


class CercanosConsulta(BaseConsulta):
    latitud: Decimal = Field(ge=-90, le=90)
    longitud: Decimal = Field(ge=-180, le=180)
    radio_km: Decimal = Field(2, gt=0, le=30)
    tipo_comercio: TipoComercio | None = None
    limite: int = Field(20, ge=1, le=100)


class ValidacionEntrada(BaseEntrada):
    estado: Literal['VERIFICADO', 'RECHAZADO', 'SUSPENDIDO']
    observaciones: str | None = Field(None, max_length=500)


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
    dias_operacion: list[str] | None = None
    descripcion: str | None = None
    giro: str | None = None
    email_contacto: str | None = None
    rfc: str | None = None
    razon_social: str | None = None
    regimen_fiscal: str | None = None
    foto_url: str | None = None
    fecha_verificacion: datetime | None = None
    creado_en: datetime | None = None
    responsables: list['ResponsableSalida'] | None = None
    distancia_km: float | None = None


class ResponsableSalida(Salida):
    id: int
    comercio_id: str
    nombre: str
    puesto: Literal['DUENO', 'ENCARGADO', 'EMPLEADO']
    telefono: str | None = None
    email: str | None = None
    usuario_id: str | None = None
    alta: datetime | None = None


class ResponsablesSalida(Salida):
    comercio_id: str
    responsables: list[ResponsableSalida]


class CercanosSalida(Salida):
    latitud: float
    longitud: float
    radio_km: float
    total: int
    comercios: list[ComercioSalida]


class ComerciosSalida(Salida):
    paginacion: Paginacion
    items: list[ComercioSalida]


ComercioSalida.model_rebuild()

CONTRATOS_XML = {
    'comercio_entrada': ComercioEntrada, 'validacion_entrada': ValidacionEntrada,
    'responsable_entrada': ResponsableEntrada, 'foto_entrada': FotoEntrada,
    'comercio': ComercioSalida, 'comercios': ComerciosSalida, 'responsable': ResponsableSalida,
    'responsables': ResponsablesSalida, 'cercanos': CercanosSalida,
}
