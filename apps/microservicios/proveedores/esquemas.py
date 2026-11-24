from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

Dia = Literal['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB', 'DOM']
EstadoVerificacion = Literal['PENDIENTE', 'VERIFICADO', 'RECHAZADO', 'SUSPENDIDO']


class ProveedoresConsulta(BaseConsulta):
    zona_id: int | None = Field(None, ge=1, description='Sólo los que entregan en esta zona')
    producto_id: int | None = Field(None, ge=1, description='Sólo los que ofrecen este producto')
    texto: str | None = None
    estado_verificacion: EstadoVerificacion | None = None
    orden: Literal['nombre', 'calificacion', 'tiempo_entrega'] = 'nombre'
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class ProveedorEntrada(BaseEntrada):
    nombre_empresa: str = Field(min_length=3, max_length=255)
    rfc: str | None = Field(None, pattern=r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
    descripcion: str | None = Field(None, max_length=1000)
    telefono_contacto: str | None = Field(None, max_length=20)
    email_contacto: str | None = Field(None, max_length=255)
    direccion: str | None = Field(None, max_length=255)
    municipio: str | None = Field(None, max_length=100)
    latitud: Decimal | None = Field(None, ge=-90, le=90)
    longitud: Decimal | None = Field(None, ge=-180, le=180)
    pedido_minimo: Decimal = Field(0, ge=0, max_digits=10, decimal_places=2)
    tiempo_entrega_dias: int = Field(1, ge=0, le=30)
    condiciones_venta: str | None = Field(None, max_length=1000)


class CondicionesEntrada(BaseEntrada):
    """Datos de la empresa, condiciones comerciales y capacidad de surtido (sólo los campos enviados cambian).
    Cambiar el RFC de un proveedor verificado lo regresa a PENDIENTE."""
    nombre_empresa: str | None = Field(None, min_length=3, max_length=255)
    rfc: str | None = Field(None, pattern=r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
    municipio: str | None = Field(None, max_length=100)
    latitud: Decimal | None = Field(None, ge=-90, le=90)
    longitud: Decimal | None = Field(None, ge=-180, le=180)
    descripcion: str | None = Field(None, max_length=1000)
    telefono_contacto: str | None = Field(None, max_length=20)
    email_contacto: str | None = Field(None, max_length=255)
    direccion: str | None = Field(None, max_length=255)
    pedido_minimo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    tiempo_entrega_dias: int | None = Field(None, ge=0, le=30)
    condiciones_venta: str | None = Field(None, max_length=1000)
    capacidad_pedidos_dia: int | None = Field(None, ge=1, le=1000)
    monto_maximo_pedido: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    dias_entrega: list[Dia] | None = Field(None, min_length=1, max_length=7)


class VerificacionEntrada(BaseEntrada):
    estado: Literal['VERIFICADO', 'RECHAZADO', 'SUSPENDIDO']
    observaciones: str | None = Field(None, max_length=500)


class ZonasEntrada(BaseEntrada):
    zonas: list[int] = Field(min_length=1, max_length=50, description='Ids de las zonas donde entrega')


class OfertaEntrada(BaseEntrada):
    producto_id: int = Field(ge=1)
    precio_mayoreo: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    cantidad_minima: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    existencia_disponible: Decimal = Field(0, ge=0, max_digits=12, decimal_places=2)


class OfertaCambio(BaseEntrada):
    precio_mayoreo: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    cantidad_minima: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    existencia_disponible: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)


class OfertasConsulta(BaseConsulta):
    producto_id: int = Field(ge=1)
    zona_id: int | None = Field(None, ge=1, description='Marca y ordena primero a quienes entregan en la zona')


class EvaluacionEntrada(BaseEntrada):
    pedido_id: str = Field(description='UUID de un pedido ENTREGADO del comercio a este proveedor')
    calificacion: int = Field(ge=1, le=5)
    puntualidad: int | None = Field(None, ge=1, le=5)
    calidad: int | None = Field(None, ge=1, le=5)
    comentario: str | None = Field(None, max_length=500)


class PartidaSalidaEntrada(BaseEntrada):
    producto_id: int = Field(ge=1)
    cantidad: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class SalidaEntrada(BaseEntrada):
    referencia: str = Field(min_length=3, max_length=100, description='p. ej. pedido:<uuid>; no se aplica dos veces')
    partidas: list[PartidaSalidaEntrada] = Field(min_length=1, max_length=100)


class PaginaConsulta(BaseConsulta):
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


# ---------------------------------------------------------------- salidas
class ZonaBreve(Salida):
    id: int
    nombre: str


class OfertaSalida(Salida):
    id: int
    proveedor_id: str
    proveedor: str
    producto_id: int
    producto: str
    unidad_medida: str
    precio_mayoreo: float
    cantidad_minima: float
    existencia_disponible: float
    actualizado: datetime | None = None
    cubre_zona: bool | None = None
    pedido_minimo: float | None = None
    tiempo_entrega_dias: int | None = None
    condiciones_venta: str | None = None
    plan: str | None = None


class OfertasSalida(Salida):
    producto_id: int | None = None
    zona_id: int | None = None
    proveedor_id: str | None = None
    total: int
    ofertas: list[OfertaSalida]


class Evaluacion(Salida):
    promedio: float | None = None
    puntualidad: float | None = None
    calidad: float | None = None
    total: int


class ProveedorSalida(Salida):
    id: str
    nombre_empresa: str
    municipio: str | None = None
    pedido_minimo: float
    tiempo_entrega_dias: int
    condiciones_venta: str | None = None
    plan: Literal['BASICO', 'DESTACADO']
    estado_verificacion: EstadoVerificacion
    capacidad_pedidos_dia: int | None = None
    monto_maximo_pedido: float | None = None
    dias_entrega: list[str] | None = None
    zonas: list[ZonaBreve]
    evaluacion: Evaluacion
    descripcion: str | None = None
    rfc: str | None = None
    telefono_contacto: str | None = None
    email_contacto: str | None = None
    direccion: str | None = None
    fecha_verificacion: datetime | None = None
    ofertas: list[OfertaSalida] | None = None


class ProveedoresSalida(Salida):
    paginacion: Paginacion
    proveedores: list[ProveedorSalida]


class EvaluacionSalida(Salida):
    id: int
    pedido_id: str
    comercio_id: str
    calificacion: int
    puntualidad: int | None = None
    calidad: int | None = None
    comentario: str | None = None
    fecha: datetime | None = None


class EvaluacionesSalida(Salida):
    proveedor_id: str
    resumen: Evaluacion
    paginacion: Paginacion
    evaluaciones: list[EvaluacionSalida]


class CapacidadSalida(Salida):
    proveedor_id: str
    capacidad_pedidos_dia: int | None = None
    pedidos_hoy: int
    disponibles_hoy: int | None = None
    pedidos_en_proceso: int
    monto_maximo_pedido: float | None = None
    dias_entrega: list[str] | None = None
    tiempo_entrega_dias: int


class SalidaRenglon(Salida):
    producto_id: int
    cantidad: float
    existencia_anterior: float | None = None
    existencia_nueva: float | None = None


class SalidaSalida(Salida):
    referencia: str
    proveedor_id: str
    ya_aplicada: bool
    partidas: list[SalidaRenglon]


CONTRATOS_XML = {
    'proveedor_entrada': ProveedorEntrada, 'condiciones_entrada': CondicionesEntrada,
    'verificacion_entrada': VerificacionEntrada, 'zonas_entrada': ZonasEntrada,
    'oferta_entrada': OfertaEntrada, 'oferta_cambio': OfertaCambio, 'evaluacion_entrada': EvaluacionEntrada,
    'proveedor': ProveedorSalida, 'proveedores': ProveedoresSalida, 'oferta': OfertaSalida, 'ofertas': OfertasSalida,
    'evaluacion': EvaluacionSalida, 'evaluaciones': EvaluacionesSalida, 'capacidad': CapacidadSalida,
    'salida_entrada': SalidaEntrada, 'salida': SalidaSalida,
}
