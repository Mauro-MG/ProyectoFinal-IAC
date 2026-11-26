"""
Almacenamiento de objetos en Google Cloud Storage.

El contenido de los archivos (fotos, documentos, evidencias, reportes) vive en un
bucket PRIVADO de GCS; la base de datos solo guarda sus metadatos. Los clientes
no reciben acceso al bucket: reciben una URL firmada V4 que vence en minutos y
que solo se emite después de revisar el permiso sobre el recurso.

Configuración (variables de entorno):
    GCS_BUCKET              nombre del bucket (obligatorio)
    GCS_PROYECTO            proyecto de GCP
    GCS_CUENTA_FIRMA        cuenta de servicio DEDICADA (solo tiene permiso sobre el bucket). En Compute Engine
                            los servicios la suplantan con las credenciales de la VM (impersonation): tanto las
                            operaciones del bucket como la firma de URLs (IAM signBlob) se hacen como esa
                            cuenta, sin llaves descargadas en el servidor.
    GOOGLE_APPLICATION_CREDENTIALS
                            alternativa: archivo de llave de una cuenta de servicio (montado como secreto)
    STORAGE_EMULATOR_HOST   solo desarrollo y pruebas: fake-gcs-server. El código es el mismo cliente de GCS;
                            como el emulador no valida firmas, la expiración solo se comprueba contra el bucket real.
    GCS_URL_PUBLICA         con el emulador: dirección por la que el cliente lo alcanza (el gateway lo publica en
                            /almacenamiento/)
"""
import os
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

_cliente = None
_candado = threading.Lock()
_firmante_emulador = None


class AlmacenamientoNoDisponible(Exception):
    """GCS no respondió o rechazó la operación; el servicio responde 503 y no deja metadatos huérfanos."""


def _config(clave, por_omision=None):
    try:
        return current_app.config.get(clave) or os.environ.get(clave, por_omision)
    except RuntimeError:   # fuera de una petición de Flask (scripts)
        return os.environ.get(clave, por_omision)


def emulador():
    return bool(os.environ.get('STORAGE_EMULATOR_HOST'))


def cliente():
    global _cliente
    with _candado:
        if _cliente is None:
            from google.cloud import storage
            if emulador():
                from google.auth.credentials import AnonymousCredentials
                _cliente = storage.Client(project=_config('GCS_PROYECTO', 'abastored-local'),
                                          credentials=AnonymousCredentials())
            else:
                _cliente = storage.Client(project=_config('GCS_PROYECTO'), credentials=_credenciales())
        return _cliente


_creds = None


def _credenciales():
    """Credenciales de la cuenta dedicada (suplantada) si GCS_CUENTA_FIRMA está definida; si no, las de la VM o la
    llave de GOOGLE_APPLICATION_CREDENTIALS. La cuenta de la VM solo necesita poder suplantar a la dedicada
    (roles/iam.serviceAccountTokenCreator sobre ella); los permisos del bucket los tiene solo la dedicada."""
    global _creds
    if _creds is None:
        import google.auth
        from google.auth import impersonated_credentials
        base, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        cuenta = _config('GCS_CUENTA_FIRMA')
        _creds = impersonated_credentials.Credentials(
            source_credentials=base, target_principal=cuenta,
            target_scopes=['https://www.googleapis.com/auth/devstorage.read_write'], lifetime=3600) if cuenta else base
    return _creds


_bucket_listo = False


def bucket():
    global _bucket_listo
    nombre = _config('GCS_BUCKET')
    if not nombre:
        raise AlmacenamientoNoDisponible('GCS_BUCKET no está configurado.')
    b = cliente().bucket(nombre)
    if emulador() and not _bucket_listo:
        # Solo el emulador local: el bucket se crea la primera vez. En Google Cloud lo crea la infraestructura
        # (apps/infra) con su política de acceso; el servicio nunca crea ni hace público un bucket real.
        try:
            if not b.exists(timeout=5, retry=None):
                cliente().create_bucket(nombre)
            _bucket_listo = True
        except Exception as error:  # noqa: BLE001
            raise AlmacenamientoNoDisponible(f'El emulador de Cloud Storage no responde ({error.__class__.__name__}).')
    return b


def _reintentos():
    """La biblioteca reintenta por omisión hasta 120 s: demasiado para una petición de un usuario. Se limita a
    5 s y después se responde 503 (el cliente puede reintentar)."""
    from google.cloud.storage.retry import DEFAULT_RETRY
    return DEFAULT_RETRY.with_deadline(5)


def _error(operacion, error):
    return AlmacenamientoNoDisponible(f'Cloud Storage no respondió al {operacion} ({error.__class__.__name__}).')


def subir(objeto, contenido, tipo_mime, metadatos=None):
    """Sube el contenido. if_generation_match=0: nunca sobrescribe un objeto existente."""
    try:
        blob = bucket().blob(objeto)
        blob.metadata = {k: str(v) for k, v in (metadatos or {}).items() if v is not None}
        blob.upload_from_string(contenido, content_type=tipo_mime, if_generation_match=0, timeout=20,
                                retry=_reintentos())
    except AlmacenamientoNoDisponible:
        raise
    except Exception as error:  # noqa: BLE001 - google.api_core, requests y urllib3 tienen jerarquías distintas
        raise _error('subir', error)


def descargar(objeto):
    from google.api_core.exceptions import NotFound
    try:
        return bucket().blob(objeto).download_as_bytes(timeout=20, retry=_reintentos())
    except NotFound:
        return None
    except AlmacenamientoNoDisponible:
        raise
    except Exception as error:  # noqa: BLE001
        raise _error('descargar', error)


def borrar(objeto):
    from google.api_core.exceptions import NotFound
    try:
        bucket().blob(objeto).delete(timeout=10, retry=_reintentos())
        return True
    except NotFound:
        return False
    except Exception as error:  # noqa: BLE001
        raise _error('borrar', error)


def existe(objeto):
    try:
        return bucket().blob(objeto).exists(timeout=10, retry=_reintentos())
    except Exception as error:  # noqa: BLE001
        raise _error('consultar', error)


# ---------------------------------------------------------------- URLs firmadas

def _credenciales_firma():
    """Credenciales capaces de firmar V4: la cuenta suplantada (firma con IAM signBlob) o una llave de cuenta de
    servicio. Las credenciales de usuario o de la VM sin suplantar no pueden firmar."""
    credenciales = _credenciales()
    if hasattr(credenciales, 'sign_bytes'):
        return {'credentials': credenciales}
    raise AlmacenamientoNoDisponible('No hay cuenta de servicio para firmar URLs: define GCS_CUENTA_FIRMA.')


def _firmante_desarrollo():
    """Solo con el emulador: llave RSA efímera generada en memoria para producir URLs con el formato V4 real.
    El emulador no comprueba la firma; por eso las pruebas de expiración usan el bucket real."""
    global _firmante_emulador
    if _firmante_emulador is None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from google.oauth2 import service_account
        privada = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        info = {'type': 'service_account', 'client_email': 'emulador@abastored-local.iam.gserviceaccount.com',
                'private_key': privada, 'token_uri': 'https://oauth2.googleapis.com/token',
                'project_id': 'abastored-local', 'private_key_id': 'emulador', 'client_id': '0'}
        _firmante_emulador = service_account.Credentials.from_service_account_info(info)
    return _firmante_emulador


def url_firmada(objeto, nombre_descarga, tipo_mime, minutos=10):
    """URL V4 de solo lectura que vence en `minutos` (1 a 60). Regresa (url, expira_en)."""
    minutos = max(1, min(int(minutos), 60))
    expira = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    opciones = {'version': 'v4', 'expiration': timedelta(minutes=minutos), 'method': 'GET',
                'response_type': tipo_mime,
                'response_disposition': f'inline; filename="{nombre_descarga}"'}
    try:
        blob = bucket().blob(objeto)
        if emulador():
            opciones['credentials'] = _firmante_desarrollo()
            opciones['api_access_endpoint'] = _config('GCS_URL_PUBLICA', 'https://localhost/almacenamiento')
        else:
            opciones.update(_credenciales_firma())
        return blob.generate_signed_url(**opciones), expira
    except AlmacenamientoNoDisponible:
        raise
    except Exception as error:  # noqa: BLE001
        raise _error('firmar la URL', error)


# ---------------------------------------------------------------- salud

def salud():
    """Para /health/storage: el bucket existe y responde. No lista ni expone objetos."""
    inicio = datetime.now(timezone.utc)
    try:
        b = bucket()
        b.reload(timeout=4, retry=None)   # salud: sin reintentos, un intento corto
        ms = round((datetime.now(timezone.utc) - inicio).total_seconds() * 1000)
        return {'nombre': 'storage', 'estado': 'ok', 'tiempo_ms': ms,
                'detalle': f"gs://{b.name} ({'emulador' if emulador() else b.location})"}
    except Exception as error:  # noqa: BLE001
        ms = round((datetime.now(timezone.utc) - inicio).total_seconds() * 1000)
        return {'nombre': 'storage', 'estado': 'caido', 'tiempo_ms': ms,
                'detalle': f'{error.__class__.__name__}: {str(error)[:120]}'}

