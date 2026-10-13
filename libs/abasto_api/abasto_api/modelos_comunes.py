"""Modelos de salida comunes a todos los servicios (también se incluyen en cada XSD)."""
from datetime import datetime

from pydantic import BaseModel, Field


class Salida(BaseModel):
    """Base de los modelos de respuesta (sólo documentan el contrato; no validan la salida en Python)."""


class Paginacion(Salida):
    """Datos de paginación de toda lista."""
    pagina: int = Field(ge=1)
    por_pagina: int = Field(ge=1)
    total: int = Field(ge=0)
    paginas: int = Field(ge=0)


class DetalleError(Salida):
    campo: str
    mensaje: str
    tipo: str | None = None


class ErrorSalida(Salida):
    """Error estandarizado (en JSON viene dentro de la llave `error`)."""
    codigo: str = Field(description='Identificador estable del error, p. ej. regla_negocio, token_revocado')
    mensaje: str
    status: int = Field(ge=400, le=599)
    ruta: str | None = None
    correlation_id: str | None = None
    fecha: datetime | None = None
    detalles: list[DetalleError] | None = None


class Dependencia(Salida):
    nombre: str
    estado: str
    latencia_ms: float | None = None
    error: str | None = None


class Salud(Salida):
    servicio: str
    version: str
    estado: str = Field(description='ok o caido')
    fecha: datetime
    dependencias: list[Dependencia]


class Resultado(Salida):
    """Respuesta de operaciones que no regresan un recurso (bajas, revocaciones, marcados)."""
    mensaje: str
    id: str | None = None
    jti: str | None = None
    sesiones_cerradas: int | None = None
    cambiadas: int | None = None


CONTRATOS_COMUNES = {'error': ErrorSalida, 'salud': Salud, 'resultado': Resultado}
