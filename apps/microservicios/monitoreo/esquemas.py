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
    critica: bool | None = None
    latencia_ms: float | None = None
    detalle: str | None = None
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
    responsable: str | None = Field(None, description='Dependencia caída que explica el estado (p. ej. storage)')
    error: str | None = None


class DisponibilidadServicio(Salida):
    servicio: str
    estado: str
    ultima_verificacion: datetime | None = None
    latencia_ms: float | None = None
    responsable: str | None = None
    disponibilidad_24h_pct: float | None = None
    verificaciones_24h: int = 0
    fallas_24h: int = 0
    ultimo_error: str | None = None
    ultimo_error_fecha: datetime | None = None


class DisponibilidadSalida(Salida):
    fuente: Literal['historial', 'ultima_verificacion', 'en_vivo'] = Field(
        description='historial (MongoDB); ultima_verificacion (Redis, si MongoDB no responde); en_vivo (sin ninguna)')
    ultima_verificacion: datetime | None = None
    intervalo_segundos: int
    ok: int
    degradados: int
    caidos: int
    servicios: list[DisponibilidadServicio]
    avisos: list[str] = []


class PuntoHistorial(Salida):
    fecha: datetime
    estado: str
    latencia_ms: float | None = None
    responsable: str | None = None
    error: str | None = None


class HistorialSalida(Salida):
    servicio: str
    horas: int
    puntos: list[PuntoHistorial]


class VerificacionSalida(Salida):
    revisado: datetime
    servicios: int
    ok: int
    degradados: int
    caidos: int
    guardado_en: list[str]
    alertas_nuevas: int | None = None


class HistorialConsulta(BaseConsulta):
    servicio: str = Field(min_length=2, max_length=40)
    horas: int = Field(24, ge=1, le=720)


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
    'disponibilidad': DisponibilidadSalida, 'historial': HistorialSalida, 'verificacion': VerificacionSalida,
}
