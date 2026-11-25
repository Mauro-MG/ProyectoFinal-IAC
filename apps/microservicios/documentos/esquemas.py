from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida

Entidad = Literal['comercio', 'producto', 'pedido', 'proveedor', 'importacion', 'entrega', 'venta']
Categoria = Literal['foto_comercio', 'evidencia_validacion', 'foto_producto', 'comprobante_pedido', 'importacion_csv',
                    'documento', 'documento_fiscal', 'evidencia_entrega', 'comprobante_venta']
Visibilidad = Literal['privada', 'entidad', 'publica']


class DocumentosConsulta(BaseConsulta):
    entidad: Entidad | None = None
    entidad_id: str | None = Field(None, max_length=64)
    categoria: Categoria | None = None
    mios: bool = Field(False, description='Sólo los que subí yo')
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class DocumentoCambio(BaseEntrada):
    descripcion: str | None = Field(None, max_length=500)
    visibilidad: Visibilidad | None = None


# ---------------------------------------------------------------- salidas
class DocumentoSalida(Salida):
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
    visibilidad: Visibilidad
    subido_en: datetime
    almacenamiento: Literal['gcs', 'gridfs'] = Field('gcs', description='gridfs: archivo anterior aún sin migrar')
    url_contenido: str | None = Field(None, description='Descarga a través del servicio (siempre disponible)')


class UrlConsulta(BaseConsulta):
    minutos: int = Field(10, ge=1, le=60, description='Vigencia de la URL firmada')


class UrlFirmadaSalida(Salida):
    id: str
    url: str = Field(description='URL firmada V4 de solo lectura del objeto en Cloud Storage')
    expira: datetime
    minutos: int
    tipo_mime: str
    sha256: str | None = None


class MigracionSalida(Salida):
    migrados: int
    pendientes: int
    errores: int


class DocumentosSalida(Salida):
    paginacion: Paginacion
    documentos: list[DocumentoSalida]


class UsoCategoria(Salida):
    categoria: str | None = None
    archivos: int
    megabytes: float


class UsoSalida(Salida):
    total_archivos: int
    total_megabytes: float
    categorias: list[UsoCategoria]


class LimitesSalida(Salida):
    tipos_permitidos: list[str]
    categorias: list[str]
    entidades: list[str]
    max_megabytes: int


CONTRATOS_XML = {
    'documento_cambio': DocumentoCambio,
    'documento': DocumentoSalida, 'documentos': DocumentosSalida, 'uso': UsoSalida, 'limites': LimitesSalida,
    'url_firmada': UrlFirmadaSalida, 'migracion': MigracionSalida,
}
