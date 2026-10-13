from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida


class LoginEntrada(BaseEntrada):
    email: EmailStr = Field(description='Correo de la cuenta')
    password: str = Field(min_length=1, max_length=128)
    origen: Literal['web', 'movil', 'escritorio', 'api'] = Field('api', description='Aplicación que inicia sesión')


class RenovarEntrada(BaseEntrada):
    refresh_token: str = Field(min_length=20, max_length=200)


class ValidarEntrada(BaseEntrada):
    token: str = Field(min_length=20)


class UsuariosConsulta(BaseConsulta):
    texto: str | None = Field(None, description='Busca en nombre, apellido o correo')
    rol_id: int | None = None
    activo: bool | None = None
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(20, ge=1, le=100)


class UsuarioCambio(BaseEntrada):
    rol_id: int | None = Field(None, ge=1)
    activo: bool | None = None


class PermisosEntrada(BaseEntrada):
    permisos: list[str] = Field(min_length=0, max_length=50)


class SesionesConsulta(BaseConsulta):
    usuario_id: str | None = None


class AuditoriaConsulta(BaseConsulta):
    entidad: str | None = None
    entidad_id: str | None = None
    tipo_evento: str | None = None
    usuario_id: str | None = None
    desde: str | None = Field(None, description='AAAA-MM-DD')
    hasta: str | None = Field(None, description='AAAA-MM-DD')
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(30, ge=1, le=200)


class ActividadConsulta(BaseConsulta):
    horas: int = Field(24, ge=1, le=24 * 30)
    servicio: str | None = None


# ---------------------------------------------------------------- salidas
class UsuarioSalida(Salida):
    id: str = Field(json_schema_extra={'format': 'uuid'})
    email: str
    nombre: str
    apellido: str
    telefono: str | None = None
    rol: str
    rol_id: int
    activo: bool
    proveedor_id: str | None = None
    ultimo_acceso: datetime | None = None
    permisos: list[str]


class TokensSalida(Salida):
    access_token: str
    token_type: Literal['Bearer']
    expires_in: int = Field(description='Segundos de vigencia del token de acceso')
    refresh_token: str | None = None
    usuario: UsuarioSalida | None = None


class SesionSalida(Salida):
    usuario_id: str
    nombre: str | None = None
    rol: str
    permisos: list[str]
    origen: str | None = None
    jti: str
    segundos_restantes: int
    proveedor_id: str | None = None


class ValidacionSalida(Salida):
    valido: bool
    motivo: str | None = None
    mensaje: str | None = None
    usuario_id: str | None = None
    rol: str | None = None
    permisos: list[str] | None = None
    expira: datetime | None = None


class SesionActiva(Salida):
    jti: str
    usuario_id: str
    rol: str
    nombre: str | None = None
    origen: str | None = None
    ip: str | None = None
    creada: str | None = None
    ttl: int


class SesionesSalida(Salida):
    total: int
    sesiones: list[SesionActiva]


class UsuariosSalida(Salida):
    paginacion: Paginacion
    items: list[UsuarioSalida]


class PermisoDisponible(Salida):
    codigo: str
    descripcion: str


class RolSalida(Salida):
    id: int
    nombre: str
    descripcion: str | None = None
    permisos: list[str]


class RolesSalida(Salida):
    permisos_disponibles: list[PermisoDisponible]
    roles: list[RolSalida]


class EventoAuditoria(Salida):
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


class AuditoriaSalida(Salida):
    paginacion: Paginacion
    items: list[EventoAuditoria]


class ActividadServicio(Salida):
    servicio: str
    peticiones: int
    errores_cliente: int
    errores_servidor: int
    respuestas_xml: int
    duracion_prom_ms: float
    duracion_max_ms: float
    ultima: datetime
    contador_hoy: int


class ActividadSalida(Salida):
    horas: int
    servicios: list[ActividadServicio]


class RastreoSalida(Salida):
    correlation_id: str
    pasos: list[dict]


CONTRATOS_XML = {
    'login': LoginEntrada, 'renovar': RenovarEntrada, 'validar': ValidarEntrada,
    'usuario_cambio': UsuarioCambio, 'permisos_entrada': PermisosEntrada,
    'tokens': TokensSalida, 'usuario': UsuarioSalida, 'usuarios': UsuariosSalida, 'sesion': SesionSalida,
    'validacion': ValidacionSalida, 'sesiones': SesionesSalida, 'roles': RolesSalida, 'rol': RolSalida,
    'auditoria': AuditoriaSalida, 'actividad': ActividadSalida, 'rastreo': RastreoSalida,
}
