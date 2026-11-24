from datetime import datetime
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida


class MetricasConsulta(BaseConsulta):
    horas: int = Field(24, ge=1, le=24 * 30)
    servicio: str | None = None


class AlertasConsulta(BaseConsulta):
    activas: bool = True
    servicio: str | None = None
    limite: int = Field(50, ge=1, le=500)


class AlertaCierre(BaseEntrada):
    comentario: str | None = Field(None, max_length=300)


# ---------------------------------------------------------------- salidas
class DependenciaEstado(Salida):
    nombre: str
    estado: str
    latencia_ms: float | None = None
    error: str | None = None


class ServicioEstado(Salida):
    servicio: str
    puerto_desarrollo: int
    descripcion: str
    estado: Literal['ok', 'degradado', 'caido', 'sin_respuesta']
    http: int | None = None
    tiempo_ms: float | None = None
    version: str | None = None
    dependencias: list[DependenciaEstado]
    error: str | None = None


class EstadoGeneral(Salida):
    revisado: datetime
    total: int
    ok: int
    degradados: int
    caidos: int
    disponibilidad_pct: float
    servicios: list[ServicioEstado]


class BaseDatos(Salida):
    nombre: str
    estado: str
    latencia_ms: float | None = None
    version: str | None = None
    conexiones: int | None = None
    tamano_mb: float | None = None
    detalle: str | None = None


class BasesDatosSalida(Salida):
    revisado: datetime
    bases: list[BaseDatos]


class MetricaServicio(Salida):
    servicio: str
    peticiones: int
    errores_cliente: int
    errores_servidor: int
    tasa_error_servidor_pct: float
    latencia_prom_ms: float
    latencia_p95_ms: float | None = None
    latencia_max_ms: float
    respuestas_xml: int
    ultima: datetime | None = None
    peticiones_hoy: int
    errores_hoy: int


class MetricasSalida(Salida):
    horas: int
    servicios: list[MetricaServicio]


class PuntoSerie(Salida):
    hora: datetime
    peticiones: int
    errores: int
    latencia_prom_ms: float


class SerieSalida(Salida):
    servicio: str
    horas: int
    puntos: list[PuntoSerie]


class Alerta(Salida):
    id: str
    servicio: str
    regla: str
    severidad: Literal['advertencia', 'critica']
    mensaje: str
    valor: float | None = None
    umbral: float | None = None
    activa: bool
    fecha: datetime
    actualizada: datetime | None = None
    cerrada: datetime | None = None
    comentario: str | None = None


class AlertasSalida(Salida):
    total: int
    alertas: list[Alerta]


class EvaluacionSalida(Salida):
    revisado: datetime
    nuevas: int
    vigentes: int
    resueltas: int
    alertas: list[Alerta]


CONTRATOS_XML = {
    'alerta_cierre': AlertaCierre,
    'estado': EstadoGeneral, 'servicio': ServicioEstado, 'bases_datos': BasesDatosSalida, 'metricas': MetricasSalida,
    'serie': SerieSalida, 'alertas': AlertasSalida, 'alerta': Alerta, 'evaluacion': EvaluacionSalida,
}
