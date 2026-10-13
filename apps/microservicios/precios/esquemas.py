from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida


class PrecioEntrada(BaseEntrada):
    precio: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    metodo_captura: Literal['MANUAL', 'MOVIL', 'ESCRITORIO'] = 'MANUAL'


class HistorialConsulta(BaseConsulta):
    comercio_id: str | None = None
    producto_id: int | None = Field(None, ge=1)
    estado_validacion: Literal['VALIDADO', 'PENDIENTE_VALIDACION'] | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=200)


class ValidacionPrecio(BaseEntrada):
    decision: Literal['VALIDAR', 'DESCARTAR']
    comentario: str | None = Field(None, max_length=300)


class ComparacionConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1)
    categoria_id: int | None = Field(None, ge=1)
    zona_id: int | None = Field(None, ge=1)
    municipio: str | None = None
    sector: Literal['Formal', 'Informal'] | None = None
    proveedor_id: str | None = None
    tipo: Literal['ambos', 'consumidor', 'mayoreo'] = 'ambos'
    desde: date | None = Field(None, description='Por omisión, hace 30 días')
    hasta: date | None = Field(None, description='Por omisión, hoy')


class TendenciaConsulta(BaseConsulta):
    producto_id: int = Field(ge=1)
    semanas: int = Field(8, ge=1, le=52)


class SnapshotsConsulta(BaseConsulta):
    producto_id: int | None = Field(None, ge=1)
    zona_id: int | None = Field(None, ge=1)
    sector: Literal['Formal', 'Informal'] | None = None
    desde: str | None = Field(None, description='AAAA-MM-DD')
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(50, ge=1, le=200)


class SerieConsulta(BaseConsulta):
    producto_id: int = Field(ge=1)
    zona_id: int | None = Field(None, ge=1)


# ---------------------------------------------------------------- salidas
class CambioPrecioSalida(Salida):
    inventario_id: int
    producto: str
    precio_anterior: float | None = None
    precio: float
    estado_validacion: Literal['VALIDADO', 'PENDIENTE_VALIDACION']
    promedio_zona_7_dias: float | None = None


class PrecioSalida(Salida):
    id: int
    comercio_id: str
    comercio: str
    producto_id: int
    producto: str
    precio: float
    precio_anterior: float | None = None
    estado_validacion: Literal['VALIDADO', 'PENDIENTE_VALIDACION']
    activo: bool
    metodo_captura: str | None = None
    notas: str | None = None
    fecha: datetime


class PreciosSalida(Salida):
    paginacion: Paginacion | None = None
    total: int | None = None
    precios: list[PrecioSalida]


class ResumenProducto(Salida):
    producto_id: int
    producto: str
    formal: float | None = None
    informal: float | None = None
    diferencia_pct: float | None = None
    mayoreo_min: float | None = None
    margen_pct: float | None = None


class FilaConsumidor(Salida):
    producto_id: int
    producto: str
    categoria: str
    zona: str
    municipio: str
    sector: str
    minimo: float
    promedio: float
    maximo: float
    muestras: int
    comercios: int


class FilaMayoreo(Salida):
    producto_id: int
    producto: str
    proveedor_id: str
    proveedor: str
    minimo: float
    promedio: float
    maximo: float
    muestras: int


class ComparacionSalida(Salida):
    desde: date
    hasta: date
    resumen: list[ResumenProducto]
    consumidor: list[FilaConsumidor]
    mayoreo: list[FilaMayoreo]


class Serie(Salida):
    nombre: str
    datos: list[float | None]


class TendenciaSalida(Salida):
    producto_id: int
    categorias: list[str]
    series: list[Serie]


class SnapshotGenerado(Salida):
    fecha: str
    documentos: int


class Snapshot(Salida):
    fecha: str
    zona_id: int
    producto_id: int
    sector: str
    schema_version: int | None = None
    zona: str
    producto: str
    minimo: float
    promedio: float
    maximo: float
    muestras: int
    ventana_dias: int
    generado_en: datetime


class SnapshotsSalida(Salida):
    paginacion: Paginacion
    snapshots: list[Snapshot]


class PuntoSerie(Salida):
    fecha: str
    sector: str
    promedio: float
    minimo: float
    maximo: float
    muestras: int


class TendenciaSnapshotsSalida(Salida):
    producto_id: int
    zona_id: int | None = None
    tendencia: list[PuntoSerie]


CONTRATOS_XML = {
    'precio_entrada': PrecioEntrada, 'validacion_precio': ValidacionPrecio,
    'cambio_precio': CambioPrecioSalida, 'precio': PrecioSalida, 'precios': PreciosSalida,
    'comparacion': ComparacionSalida, 'tendencia': TendenciaSalida, 'snapshot': SnapshotGenerado,
    'snapshots': SnapshotsSalida, 'tendencia_snapshots': TendenciaSnapshotsSalida,
}
