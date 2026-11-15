"""
ms-seguridad: autenticación, registro, recuperación de acceso, sesiones, usuarios y roles.

Es el servicio responsable del mecanismo común de seguridad: emite los JWT,
registra cada sesión en Redis, la renueva, la revoca y permite a otros
componentes validar un token. Todos los servicios validan con la misma
biblioteca (abasto_dominio.sesiones), así que un token revocado aquí deja de
servir en todos.

Es DUEÑO de: usuarios y roles. La bitácora de auditoría la consulta ms-auditoria y la actividad de
los servicios, ms-monitoreo.
Redis: sesion:*, sesiones_usuario:*, jwt:revocado:*, refresh:*, login_fallidos:*, recuperacion:*.
Bloqueo por intentos fallidos: 5 intentos fallidos bloquean el correo 15 minutos (HTTP 423).
"""
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from flask import g, request
from sqlalchemy import or_

from abasto_api import ErrorApi, Servicio, no_encontrado, paginar, usuario_actual
from abasto_dominio import extensiones, sesiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Rol, Usuario
from abasto_dominio.permisos import PERMISOS
from abasto_dominio.servicios.auditoria import registrar_evento

from esquemas import (CONTRATOS_XML, CambioPasswordEntrada, LoginEntrada, PermisosEntrada, RecuperacionEntrada,
                      RegistroEntrada, RenovarEntrada, RestablecerEntrada, SesionesConsulta, UsuarioCambio,
                      UsuariosConsulta, ValidarEntrada)

srv = Servicio('seguridad', 'Seguridad',
               'Autenticación, registro y recuperación de acceso, JWT y refresh tokens, administración de usuarios, '
               'roles y permisos, control y revocación de sesiones en Redis y bloqueo por intentos fallidos.',
               xsd=Path(__file__).parent / 'xsd' / 'seguridad.xsd', contratos=CONTRATOS_XML)
app = srv.app


def usuario_a_dict(u):
    return {
        'id': str(u.id), 'email': u.email, 'nombre': u.nombre, 'apellido': u.apellido_paterno,
        'telefono': u.telefono, 'rol': u.rol.nombre, 'rol_id': u.rol_id, 'activo': u.activo,
        'proveedor_id': str(u.proveedor_vinculado.id) if u.proveedor_vinculado else None,
        'ultimo_acceso': u.ultimo_acceso, 'permisos': list(u.rol.permisos or []),
    }


EJEMPLO_TOKENS = {'access_token': 'eyJhbGciOiJIUzI1NiIs...', 'token_type': 'Bearer', 'expires_in': 28800,
                  'refresh_token': 'k3J9...', 'usuario': {'id': '2b9e...', 'email': 'comerciante@test.mx',
                                                          'rol': 'Comerciante Informal'}}


# ---------------------------------------------------------------- autenticación

@srv.ruta('/auth/login', 'POST', resumen='Iniciar sesión', etiqueta='Autenticación', publico=True,
          cuerpo=LoginEntrada, raiz_xml='tokens', entrada_xml='login', limite=10,
          ejemplo_entrada={'email': 'comerciante@test.mx', 'password': 'Password123!', 'origen': 'movil'},
          ejemplo_salida=EJEMPLO_TOKENS, errores=(400, 401, 422, 423))
def login(datos):
    """Valida credenciales, emite el JWT (8 h) y un refresh token (7 días) y registra la sesión en Redis.
    Tras 5 intentos fallidos el correo queda bloqueado 15 minutos (HTTP 423)."""
    email = str(datos.email).lower()
    if sesiones.login_bloqueado(email):
        raise ErrorApi(423, 'cuenta_bloqueada', 'Demasiados intentos fallidos. Espera 15 minutos.')
    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario or not usuario.check_password(datos.password):
        intentos = sesiones.registrar_intento_fallido(email)
        restantes = max(sesiones.MAX_INTENTOS - (intentos or 0), 0)
        raise ErrorApi(401, 'credenciales_invalidas', f'Correo o contraseña incorrectos. Intentos restantes: {restantes}.')
    if not usuario.activo:
        raise ErrorApi(401, 'usuario_inactivo', 'La cuenta está desactivada.')
    sesiones.limpiar_intentos(email)
    tokens = sesiones.emitir_tokens(usuario, origen=datos.origen, ip=request.remote_addr)
    usuario.ultimo_acceso = db.func.now()
    registrar_evento(usuario.id, 'LOGIN', 'Usuario', usuario.id, f'Inicio de sesión ({datos.origen}) vía ms-seguridad')
    db.session.commit()
    return {**{k: tokens[k] for k in ('access_token', 'token_type', 'expires_in', 'refresh_token')},
            'usuario': usuario_a_dict(usuario)}


@srv.ruta('/auth/renovar', 'POST', resumen='Renovar token', etiqueta='Autenticación', publico=True,
          cuerpo=RenovarEntrada, raiz_xml='tokens', entrada_xml='renovar', limite=30,
          ejemplo_entrada={'refresh_token': 'k3J9...'}, errores=(400, 401, 422))
def renovar(datos):
    """Cambia un refresh token por un par nuevo. El refresh usado y la sesión anterior se invalidan (rotación)."""
    tokens = sesiones.renovar(datos.refresh_token, ip=request.remote_addr)
    return {k: tokens[k] for k in ('access_token', 'token_type', 'expires_in', 'refresh_token')}


@srv.ruta('/auth/logout', 'POST', resumen='Cerrar sesión', etiqueta='Autenticación', raiz_xml='resultado',
         ejemplo_salida={'mensaje': 'Sesión cerrada', 'jti': 'a1b2...'})
def logout():
    """Revoca el token actual: se borra su sesión en Redis y su jti entra a la lista de revocados."""
    sesiones.revocar(g.claims)
    if g.claims.get('tipo') == 'acceso':
        registrar_evento(UUID(g.claims['sub']), 'LOGOUT', 'Usuario', g.claims['sub'], 'Cierre de sesión vía ms-seguridad')
        db.session.commit()
    return {'mensaje': 'Sesión cerrada', 'jti': g.claims['jti']}


@srv.ruta('/auth/sesion', 'GET', resumen='Datos de la sesión actual', etiqueta='Autenticación', raiz_xml='sesion',
         )
def sesion_actual():
    """Comprueba el token (firma, vigencia, sesión en Redis) y regresa sus datos y el tiempo restante."""
    ttl = extensiones.redis_client.ttl(f"sesion:{g.claims['jti']}")
    return {'usuario_id': g.claims['sub'], 'nombre': g.claims.get('nombre'), 'rol': g.claims['rol'],
            'permisos': g.claims.get('permisos', []), 'origen': g.claims.get('origen'),
            'jti': g.claims['jti'], 'segundos_restantes': ttl, 'proveedor_id': g.claims.get('proveedor_id')}


@srv.ruta('/auth/validar', 'POST', resumen='Validar un token (para otros componentes)', etiqueta='Autenticación',
          publico=True, cuerpo=ValidarEntrada, raiz_xml='validacion', entrada_xml='validar',
         errores=(400, 422))
def validar(datos):
    """Indica si un token es válido y su sesión sigue activa. Responde 200 en ambos casos con `valido`."""
    try:
        claims = sesiones.validar_token(datos.token)
    except sesiones.ErrorSesion as error:
        if error.codigo_http == 503:
            raise
        return {'valido': False, 'motivo': error.codigo, 'mensaje': error.mensaje}
    return {'valido': True, 'usuario_id': claims['sub'], 'rol': claims['rol'],
            'permisos': claims.get('permisos', []), 'expira': datetime.fromtimestamp(claims['exp'], timezone.utc)}


@srv.ruta('/usuarios/me', 'GET', resumen='Mi perfil', etiqueta='Usuarios', raiz_xml='usuario')
def mi_perfil():
    return usuario_a_dict(usuario_actual())


# ---------------------------------------------------------------- registro y recuperación de acceso

TTL_RECUPERACION = 30 * 60


@srv.ruta('/auth/registro', 'POST', resumen='Crear una cuenta', etiqueta='Registro', publico=True,
          cuerpo=RegistroEntrada, status=201, raiz_xml='tokens', entrada_xml='registro', limite=5,
          ejemplo_entrada={'email': 'nuevo@puesto.mx', 'password': 'Nogales2026', 'nombre': 'Rosa',
                           'apellido_paterno': 'Treviño', 'telefono': '8112345678', 'perfil': 'Comerciante Informal',
                           'origen': 'movil'}, errores=(400, 409, 422, 429))
def registrar(datos):
    """Sólo perfiles de autoservicio (comerciante, minorista, proveedor); los demás roles los asigna el
    administrador. La contraseña se guarda con bcrypt. Regresa los tokens: la cuenta queda con sesión iniciada.
    Límite: 5 registros por minuto por IP."""
    email = str(datos.email).lower()
    if Usuario.query.filter_by(email=email).first():
        raise ErrorApi(409, 'correo_registrado', 'Ya existe una cuenta con ese correo.')
    rol = Rol.query.filter_by(nombre=datos.perfil, activo=True).first()
    if not rol:
        raise ErrorApi(422, 'perfil_invalido', 'Ese perfil no está disponible.')
    usuario = Usuario(email=email, nombre=datos.nombre, apellido_paterno=datos.apellido_paterno,
                      telefono=datos.telefono, rol_id=rol.id)
    usuario.set_password(datos.password)
    db.session.add(usuario)
    db.session.flush()
    registrar_evento(usuario.id, 'CREACION', 'Usuario', usuario.id, f'Registro de cuenta ({rol.nombre}, {datos.origen})',
                     datos_nuevos={'email': email, 'rol': rol.nombre, 'origen': datos.origen})
    db.session.commit()
    tokens = sesiones.emitir_tokens(usuario, origen=datos.origen, ip=request.remote_addr)
    return {**{k: tokens[k] for k in ('access_token', 'token_type', 'expires_in', 'refresh_token')},
            'usuario': usuario_a_dict(usuario)}


@srv.ruta('/auth/recuperacion', 'POST', resumen='Solicitar recuperación de acceso', etiqueta='Registro',
          publico=True, cuerpo=RecuperacionEntrada, status=202, raiz_xml='resultado', entrada_xml='recuperacion',
          limite=5, ejemplo_entrada={'email': 'comerciante@test.mx'}, errores=(400, 422, 429))
def recuperacion(datos):
    """Genera un token de un solo uso válido 30 minutos (`recuperacion:{token}` en Redis, el mismo que usa el web).
    Siempre responde lo mismo, exista o no el correo, para no revelar qué cuentas existen. Aún no hay servidor de
    correo: el enlace queda en la bitácora del contenedor (docker compose logs ms-seguridad)."""
    usuario = Usuario.query.filter_by(email=str(datos.email).lower(), activo=True).first()
    if usuario:
        token = secrets.token_urlsafe(32)
        extensiones.redis_client.setex(f'recuperacion:{token}', TTL_RECUPERACION, str(usuario.id))
        app.logger.info('Recuperación de acceso para %s: token %s (válido 30 min)', usuario.email, token)
        registrar_evento(usuario.id, 'ACTUALIZACION', 'Usuario', usuario.id, 'Solicitud de recuperación de acceso')
        db.session.commit()
    return {'mensaje': 'Si el correo está registrado, recibirás las instrucciones. El enlace dura 30 minutos.'}


@srv.ruta('/auth/recuperacion/confirmacion', 'POST', resumen='Restablecer la contraseña con el token',
          etiqueta='Registro', publico=True, cuerpo=RestablecerEntrada, raiz_xml='resultado', entrada_xml='restablecer',
          limite=10, ejemplo_entrada={'token': 'Qm9w...', 'password': 'NuevaClave2026'}, errores=(400, 401, 422, 429))
def restablecer(datos):
    """El token se borra al usarse. Se cierran todas las sesiones abiertas de la cuenta y se limpian los intentos
    fallidos de inicio de sesión."""
    clave = f'recuperacion:{datos.token}'
    usuario_id = extensiones.redis_client.getdel(clave)
    usuario = db.session.get(Usuario, UUID(usuario_id)) if usuario_id else None
    if not usuario or not usuario.activo:
        raise ErrorApi(401, 'token_invalido', 'El enlace de recuperación no es válido o ya expiró.')
    usuario.set_password(datos.password)
    sesiones.revocar_todas(usuario.id)
    sesiones.limpiar_intentos(usuario.email)
    registrar_evento(usuario.id, 'ACTUALIZACION', 'Usuario', usuario.id, 'Contraseña restablecida por recuperación')
    db.session.commit()
    return {'mensaje': 'Contraseña actualizada. Inicia sesión con la nueva contraseña.', 'id': str(usuario.id)}


@srv.ruta('/usuarios/me/password', 'PUT', resumen='Cambiar mi contraseña', etiqueta='Usuarios',
          cuerpo=CambioPasswordEntrada, raiz_xml='resultado', entrada_xml='cambio_password',
          ejemplo_entrada={'password_actual': 'Password123!', 'password_nueva': 'OtraClave2026'})
def cambiar_password(datos):
    """Requiere la contraseña actual. Cierra todas las demás sesiones (la actual sigue vigente)."""
    usuario = usuario_actual()
    if not usuario.check_password(datos.password_actual):
        raise ErrorApi(401, 'credenciales_invalidas', 'La contraseña actual no es correcta.')
    if datos.password_actual == datos.password_nueva:
        raise ErrorApi(422, 'misma_password', 'La contraseña nueva debe ser distinta.')
    usuario.set_password(datos.password_nueva)
    for sesion in sesiones.sesiones_activas(usuario.id):
        if sesion.get('jti') != g.claims['jti']:
            sesiones.revocar_jti(sesion['jti'], usuario.id)
    registrar_evento(usuario.id, 'ACTUALIZACION', 'Usuario', usuario.id, 'Cambio de contraseña')
    db.session.commit()
    return {'mensaje': 'Contraseña actualizada; se cerraron tus otras sesiones.', 'id': str(usuario.id)}


# ---------------------------------------------------------------- sesiones activas

@srv.ruta('/sesiones', 'GET', resumen='Sesiones activas', etiqueta='Sesiones', permisos=['sesiones.gestionar'],
          consulta=SesionesConsulta, raiz_xml='sesiones')
def listar_sesiones(q):
    """Sesiones vivas en Redis (clave sesion:{jti}) con el tiempo que les queda."""
    lista = sesiones.sesiones_activas(q.usuario_id)
    return {'total': len(lista), 'sesiones': lista}


@srv.ruta('/sesiones/<jti>', 'DELETE', resumen='Revocar una sesión', etiqueta='Sesiones',
          permisos=['sesiones.gestionar'], raiz_xml='resultado')
def revocar_sesion(jti):
    import json
    datos = extensiones.redis_client.get(f'sesion:{jti}')
    if not datos:
        raise no_encontrado('La sesión')
    usuario_id = json.loads(datos)['usuario_id']
    sesiones.revocar_jti(jti, usuario_id)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Sesion', jti, f'Sesión revocada del usuario {usuario_id}')
    db.session.commit()
    return {'mensaje': 'Sesión revocada', 'jti': jti}


@srv.ruta('/usuarios/<uuid:id>/sesiones', 'DELETE', resumen='Cerrar todas las sesiones de un usuario',
          etiqueta='Sesiones', permisos=['sesiones.gestionar'], raiz_xml='resultado')
def revocar_sesiones_usuario(id):
    if not db.session.get(Usuario, id):
        raise no_encontrado('El usuario')
    cerradas = sesiones.revocar_todas(id)
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Usuario', id, f'Se cerraron {cerradas} sesiones')
    db.session.commit()
    return {'mensaje': f'Se cerraron {cerradas} sesiones', 'sesiones_cerradas': cerradas}


# ---------------------------------------------------------------- usuarios y roles

@srv.ruta('/usuarios', 'GET', resumen='Buscar usuarios', etiqueta='Usuarios', permisos=['usuarios.gestionar'],
          consulta=UsuariosConsulta, raiz_xml='usuarios')
def listar_usuarios(q):
    consulta = Usuario.query
    if q.texto:
        patron = f'%{q.texto}%'
        consulta = consulta.filter(or_(Usuario.email.ilike(patron), Usuario.nombre.ilike(patron),
                                       Usuario.apellido_paterno.ilike(patron)))
    if q.rol_id:
        consulta = consulta.filter(Usuario.rol_id == q.rol_id)
    if q.activo is not None:
        consulta = consulta.filter(Usuario.activo.is_(q.activo))
    return paginar(consulta.order_by(Usuario.email), q.pagina, q.por_pagina, usuario_a_dict)


@srv.ruta('/usuarios/<uuid:id>', 'GET', resumen='Detalle de usuario', etiqueta='Usuarios',
          permisos=['usuarios.gestionar'], raiz_xml='usuario')
def obtener_usuario(id):
    usuario = db.session.get(Usuario, id)
    if not usuario:
        raise no_encontrado('El usuario')
    return usuario_a_dict(usuario)


@srv.ruta('/usuarios/<uuid:id>', 'PATCH', resumen='Cambiar rol o activar/desactivar', etiqueta='Usuarios',
          permisos=['usuarios.gestionar'], cuerpo=UsuarioCambio, raiz_xml='usuario', entrada_xml='usuario_cambio',
         ejemplo_entrada={'activo': False})
def cambiar_usuario(id, datos):
    """Desactivar una cuenta cierra todas sus sesiones activas."""
    usuario = db.session.get(Usuario, id)
    if not usuario:
        raise no_encontrado('El usuario')
    if str(usuario.id) == g.claims['sub']:
        raise ErrorApi(409, 'regla_negocio', 'No puedes cambiar tu propio rol ni desactivarte.')
    antes = {'rol': usuario.rol.nombre, 'activo': usuario.activo}
    if datos.rol_id is not None:
        if not db.session.get(Rol, datos.rol_id):
            raise ErrorApi(422, 'datos_invalidos', 'El rol indicado no existe.')
        usuario.rol_id = datos.rol_id
    if datos.activo is not None:
        usuario.activo = datos.activo
    db.session.flush()
    db.session.refresh(usuario, ['rol'])
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Usuario', usuario.id, f'Cuenta {usuario.email}',
                     datos_anteriores=antes, datos_nuevos={'rol': usuario.rol.nombre, 'activo': usuario.activo})
    db.session.commit()
    if datos.activo is False or datos.rol_id is not None:
        sesiones.revocar_todas(usuario.id)  # los permisos del token cambiaron: debe volver a entrar
    return usuario_a_dict(usuario)


@srv.ruta('/roles', 'GET', resumen='Roles y permisos', etiqueta='Usuarios',
          permisos=['roles.gestionar', 'usuarios.gestionar'], raiz_xml='roles')
def listar_roles():
    return {'permisos_disponibles': [{'codigo': c, 'descripcion': d} for c, d in PERMISOS.items()],
            'roles': [{'id': r.id, 'nombre': r.nombre, 'descripcion': r.descripcion, 'permisos': r.permisos or []}
                      for r in Rol.query.order_by(Rol.id)]}


@srv.ruta('/roles/<int:id>/permisos', 'PUT', resumen='Reemplazar permisos de un rol', etiqueta='Usuarios',
          permisos=['roles.gestionar'], cuerpo=PermisosEntrada, raiz_xml='rol', entrada_xml='permisos_entrada',
          ejemplo_entrada={'permisos': ['pedidos.atender', 'precios.consultar']})
def cambiar_permisos(id, datos):
    rol = db.session.get(Rol, id)
    if not rol:
        raise no_encontrado('El rol')
    invalidos = [p for p in datos.permisos if p not in PERMISOS]
    if invalidos:
        raise ErrorApi(422, 'permiso_inexistente', f'Permisos que no existen: {", ".join(invalidos)}.')
    antes = rol.permisos
    rol.permisos = sorted(set(datos.permisos))
    registrar_evento(UUID(g.claims['sub']), 'ACTUALIZACION', 'Rol', rol.id, f'Permisos del rol {rol.nombre}',
                     datos_anteriores={'permisos': antes}, datos_nuevos={'permisos': rol.permisos})
    db.session.commit()
    return {'id': rol.id, 'nombre': rol.nombre, 'permisos': rol.permisos}
