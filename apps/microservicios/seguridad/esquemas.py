from datetime import datetime
from typing import Literal

import re
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Paginacion, Salida


class LoginEntrada(BaseEntrada):
    email: EmailStr = Field(description='Correo de la cuenta')
    password: str = Field(min_length=1, max_length=128)
    origen: Literal['web', 'movil', 'escritorio', 'api'] = Field('api', description='Aplicación que inicia sesión')


def _password_segura(valor):
    if not (re.search(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]', valor) and re.search(r'\d', valor)):
        raise ValueError('la contraseña debe tener al menos una letra y un número')
    return valor


Password = Annotated[str, Field(min_length=8, max_length=128), AfterValidator(_password_segura)]


class RegistroEntrada(BaseEntrada):
    email: EmailStr
    password: Password
    nombre: str = Field(min_length=2, max_length=100)
    apellido_paterno: str = Field(min_length=2, max_length=100)
    telefono: str | None = Field(None, pattern=r'^\d{10}$')
    perfil: Literal['Comerciante Informal', 'Minorista Formal', 'Proveedor']
    origen: Literal['web', 'movil', 'escritorio', 'api'] = 'api'


class OperadorEntrada(BaseEntrada):
    """Empleado de la empresa proveedora; entra con la contraseña temporal que le da el dueño."""
    email: EmailStr
    password: Password
    nombre: str = Field(min_length=2, max_length=100)
    apellido_paterno: str = Field(min_length=2, max_length=100)
    telefono: str | None = Field(None, pattern=r'^\d{10}$')


class OperadorCambio(BaseEntrada):
    activo: bool = Field(description='false le quita el acceso y cierra sus sesiones')


class RecuperacionEntrada(BaseEntrada):
    email: EmailStr


class RestablecerEntrada(BaseEntrada):
    token: str = Field(min_length=20, max_length=100)
    password: Password


class CambioPasswordEntrada(BaseEntrada):
    password_actual: str = Field(min_length=1, max_length=128)
    password_nueva: Password


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


CONTRATOS_XML = {
    'login': LoginEntrada, 'renovar': RenovarEntrada, 'validar': ValidarEntrada,
    'usuario_cambio': UsuarioCambio, 'permisos_entrada': PermisosEntrada,
    'tokens': TokensSalida, 'usuario': UsuarioSalida, 'usuarios': UsuariosSalida, 'sesion': SesionSalida,
    'validacion': ValidacionSalida, 'sesiones': SesionesSalida, 'roles': RolesSalida, 'rol': RolSalida,
    'registro': RegistroEntrada, 'recuperacion': RecuperacionEntrada, 'restablecer': RestablecerEntrada,
    'cambio_password': CambioPasswordEntrada, 'operador_entrada': OperadorEntrada, 'operador_cambio': OperadorCambio,
    'operadores': UsuariosSalida,
}
