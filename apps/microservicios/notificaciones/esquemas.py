from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

Tipo = Literal['pedido', 'stock_bajo', 'precio_atipico', 'comercio', 'importacion', 'sistema',
               'entrega', 'incidencia', 'cotizacion', 'recomendacion', 'venta', 'proveedor']


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


Canal = Literal['interno', 'push', 'correo']


class Silencio(BaseEntrada):
    desde: int = Field(22, ge=0, le=23, description='Hora (Monterrey) en que empieza el silencio de push')
    hasta: int = Field(7, ge=0, le=23)


class PreferenciasEntrada(BaseEntrada):
    canales: dict[str, list[Canal]] = Field(description='tipo (o "todos" para el resto) -> canales')
    silencio: Silencio = Field(default_factory=Silencio)


class PlantillaEntrada(BaseEntrada):
    clave: str = Field(pattern=r'^[a-z][a-z0-9_]{2,40}$')
    tipo: Tipo
    titulo: str = Field(min_length=3, max_length=200, description='Puede tener variables {asi}')
    mensaje: str = Field(min_length=3, max_length=1000)
    prioridad: Literal['normal', 'alta'] = 'normal'


class EnvioPlantillaEntrada(BaseEntrada):
    clave: str
    usuarios: list[str] = Field(min_length=1, max_length=200)
    variables: dict[str, str] = Field(default_factory=dict)
    url: str | None = Field(None, max_length=300)


class DispositivoEntrada(BaseEntrada):
    token: str = Field(min_length=20, max_length=300, description='Token de Firebase Cloud Messaging o equivalente')
    plataforma: Literal['android', 'escritorio']
    nombre: str | None = Field(None, max_length=80)


class HistorialConsulta(BaseConsulta):
    canal: Canal | None = None
    limite: int = Field(50, ge=1, le=200)


class PreferenciasSalida(Salida):
    usuario_id: str
    canales: dict
    silencio: dict
    actualizado: datetime | None = None


class PlantillaSalida(Salida):
    clave: str
    tipo: str
    titulo: str
    mensaje: str
    prioridad: str
    variables: list[str]


class PlantillasSalida(Salida):
    plantillas: list[PlantillaSalida]


class DispositivoSalida(Salida):
    token_final: str
    plataforma: str
    nombre: str | None = None
    activo: bool
    registrado: datetime


class DispositivosSalida(Salida):
    dispositivos: list[DispositivoSalida]


class EntregaCanal(Salida):
    notificacion_id: str | None = None
    canal: str
    estado: str
    detalle: str | None = None
    proveedor: str
    fecha: datetime


class HistorialSalida(Salida):
    total: int
    entregas: list[EntregaCanal]


CONTRATOS_XML = {
    'lectura_entrada': LecturaEntrada, 'notificacion_entrada': NotificacionEntrada, 'lote_entrada': LoteEntrada,
    'notificacion': NotificacionSalida, 'notificaciones': NotificacionesSalida, 'contador': ContadorSalida,
    'lote': LoteSalida, 'resumen': ResumenSalida,
    'preferencias_entrada': PreferenciasEntrada, 'plantilla_entrada': PlantillaEntrada,
    'envio_plantilla_entrada': EnvioPlantillaEntrada, 'dispositivo_entrada': DispositivoEntrada,
    'preferencias': PreferenciasSalida, 'plantilla': PlantillaSalida, 'plantillas': PlantillasSalida,
    'dispositivo': DispositivoSalida, 'dispositivos': DispositivosSalida, 'historial': HistorialSalida,
}
