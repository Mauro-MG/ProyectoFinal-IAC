"""
Archivos en Google Cloud Storage con URLs firmadas (ms-documentos y ms-reportes).

En local el bucket es el emulador (fake-gcs-server) con el mismo cliente de GCS. El emulador no
valida firmas, así que la EXPIRACIÓN de una URL solo se comprueba contra el bucket real: esa prueba
corre cuando existe la variable PRUEBAS_GCS_REAL=1 (sistema desplegado con un bucket real) y en otro
caso queda como «no aplica».
"""
import os
import re
import subprocess
import time
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from apoyo import MODO, sesion_de, url

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


@pytest.fixture(scope='module')
def comerciante():
    return sesion_de('comerciante')


@pytest.fixture(scope='module')
def comercio(comerciante):
    return comerciante.get('comercios', '/comercios').json()['items'][0]


def _subir(api, comercio, contenido=PNG, nombre='fachada.png', tipo='image/png', **datos):
    return api.post('documentos', '/documentos', files={'archivo': (nombre, contenido, tipo)},
                    data={'categoria': 'foto_comercio', 'entidad': 'comercio', 'entidad_id': comercio['id'], **datos})


def _docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True, timeout=120)


def test_salud_del_bucket():
    r = requests.get(url('documentos', '').replace('/api/v1', '/health/storage'), timeout=10)
    assert r.status_code == 200 and r.json()['estado'] == 'ok'
    dependencia = r.json()['dependencias'][0]
    assert dependencia['nombre'] == 'storage' and dependencia['critica'] and dependencia['latencia_ms'] >= 0
    otro = requests.get(url('catalogo', '').replace('/api/v1', '/health/storage'), timeout=10).json()
    assert otro['estado'] == 'no_aplica'


def test_metadatos_en_la_base_y_contenido_en_el_bucket(comerciante, comercio):
    r = _subir(comerciante, comercio, nombre='../../fotos/fachada "nueva".png', descripcion='Fachada')
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc['almacenamiento'] == 'gcs'
    assert doc['nombre'] == 'fachada nueva.png'           # sin rutas ni comillas del nombre original
    assert doc['tamano_bytes'] == len(PNG) and len(doc['sha256']) == 64
    assert doc['usuario_id'] == comerciante.tokens['usuario']['id'] and doc['visibilidad'] == 'entidad'
    assert 'objeto' not in doc                             # la ruta interna del bucket no se expone

    firmada = comerciante.get('documentos', f"/documentos/{doc['id']}/url", params={'minutos': 2})
    assert firmada.status_code == 200, firmada.text
    datos = firmada.json()
    consulta = parse_qs(urlparse(datos['url']).query)
    assert consulta['X-Goog-Algorithm'] == ['GOOG4-RSA-SHA256'] and consulta['X-Goog-Expires'] == ['120']
    assert doc['id'] in datos['url'] and 'fachada' not in urlparse(datos['url']).path   # el nombre no forma la ruta
    descarga = requests.get(datos['url'], timeout=20)
    assert descarga.status_code == 200 and descarga.content == PNG


def test_acceso_denegado_inexistente_e_invalido(comerciante, comercio):
    doc = _subir(comerciante, comercio).json()
    ajeno = sesion_de('minorista')
    assert ajeno.get('documentos', f"/documentos/{doc['id']}/url").status_code == 403
    assert ajeno.get('documentos', f"/documentos/{doc['id']}/contenido").status_code == 403
    assert comerciante.get('documentos', '/documentos/0123456789abcdef01234567/url').status_code == 404
    assert comerciante.get('documentos', '/documentos/no-es-un-id/url').status_code == 404
    falso = _subir(comerciante, comercio, contenido=b'MZ\x90\x00 ejecutable', nombre='foto.png')
    assert falso.status_code == 415 and falso.json()['error']['codigo'] == 'tipo_no_coincide'
    vacio = _subir(comerciante, comercio, contenido=b'', nombre='vacio.png')
    assert vacio.status_code in (409, 415, 422)
    # Fuera de rango de vigencia
    assert comerciante.get('documentos', f"/documentos/{doc['id']}/url", params={'minutos': 999}).status_code == 422


def test_el_bucket_no_es_publico_ni_acepta_escrituras(comerciante, comercio):
    doc = _subir(comerciante, comercio).json()
    datos = comerciante.get('documentos', f"/documentos/{doc['id']}/url").json()
    sin_firma = datos['url'].split('?')[0]
    if MODO == 'gateway' and '/almacenamiento/' in sin_firma:
        # El emulador no valida firmas; el gateway solo deja leer, nunca escribir
        assert requests.put(sin_firma, data=b'x', timeout=10).status_code == 403
        assert requests.delete(sin_firma, timeout=10).status_code == 403
    else:
        assert requests.get(sin_firma, timeout=10).status_code in (401, 403)


def test_borrar_quita_el_objeto_y_conserva_el_registro_para_auditoria(comerciante, comercio):
    doc = _subir(comerciante, comercio).json()
    firmada = comerciante.get('documentos', f"/documentos/{doc['id']}/url").json()['url']
    assert comerciante.delete('documentos', f"/documentos/{doc['id']}").status_code == 200
    assert comerciante.get('documentos', f"/documentos/{doc['id']}").status_code == 404
    assert requests.get(firmada, timeout=10).status_code in (403, 404)     # el objeto ya no existe
    eventos = sesion_de('auditor').get('auditoria', f"/entidades/Documento/{doc['id']}/historial").json()['eventos']
    assert {e['tipo_evento'] for e in eventos} >= {'CREACION', 'LECTURA', 'ELIMINACION'}


def test_reporte_en_el_bucket_con_url_firmada(comerciante, comercio):
    r = comerciante.post('reportes', '/reportes', json={'tipo': 'inventario', 'formato': 'pdf',
                                                         'filtros': {'comercio_id': comercio['id']}})
    assert r.status_code == 201, r.text
    firmada = comerciante.get('reportes', f"/reportes/{r.json()['id']}/url").json()
    assert requests.get(firmada['url'], timeout=20).content.startswith(b'%PDF')
    assert sesion_de('minorista').get('reportes', f"/reportes/{r.json()['id']}/url").status_code == 403


@pytest.fixture
def docker():
    if MODO != 'gateway' or not _docker('version').stdout:
        pytest.skip('No aplica: requiere el CLI de Docker en el equipo anfitrión para detener el almacenamiento')
    if 'abastored-gcs-emulador' not in _docker('ps', '--format', '{{.Names}}').stdout:
        pytest.skip('No aplica: la caída se simula deteniendo el emulador local (no se detiene un bucket real)')
    return _docker


def test_caida_del_almacenamiento_no_deja_registros_a_medias(comerciante, comercio, docker):
    antes = comerciante.get('documentos', '/documentos', params={'entidad': 'comercio', 'entidad_id': comercio['id'],
                                                                  'por_pagina': 100}).json()['paginacion']['total']
    docker('stop', 'abastored-gcs-emulador')
    try:
        inicio = time.time()
        salud = requests.get(url('documentos', '').replace('/api/v1', '/health/ready'), timeout=60)
        assert salud.status_code == 503 and 'storage' in salud.json()['dependencias_caidas']
        assert time.time() - inicio < 15                      # la caída se detecta rápido, sin colgar la petición
        r = comerciante.post('documentos', '/documentos', timeout=60, files={'archivo': ('a.png', PNG, 'image/png')},
                             data={'categoria': 'foto_comercio', 'entidad': 'comercio', 'entidad_id': comercio['id']})
        assert r.status_code == 503 and r.json()['error']['codigo'] == 'almacenamiento_no_disponible'
        assert 'intenta' in r.json()['error']['mensaje']
    finally:
        docker('start', 'abastored-gcs-emulador')
    for _ in range(30):
        if requests.get(url('documentos', '').replace('/api/v1', '/health/storage'), timeout=10).status_code == 200:
            break
        time.sleep(1)
    despues = comerciante.get('documentos', '/documentos', params={'entidad': 'comercio', 'entidad_id': comercio['id'],
                                                                    'por_pagina': 100}).json()['paginacion']['total']
    assert despues == antes                                   # el intento fallido no dejó metadatos huérfanos
    assert _subir(comerciante, comercio).status_code == 201   # se recupera sola


def test_migracion_de_gridfs_no_destructiva(comerciante, comercio, docker):
    """Se crea un archivo «anterior» en GridFS, se sirve por el servicio, se migra y queda en el bucket con el
    mismo id y la misma huella; el original de GridFS se conserva."""
    script = (
        "from abasto_dominio import extensiones; from app import app; import hashlib, datetime\n"
        "with app.app_context():\n"
        f"    c = open('/dev/stdin','rb').read()\n"
        "    i = extensiones.gridfs_archivos().put(c, filename='anterior.png', metadata={'tipo_mime': 'image/png',"
        f" 'categoria': 'foto_comercio', 'entidad': 'comercio', 'entidad_id': '{comercio['id']}',"
        f" 'usuario_id': '{comerciante.tokens['usuario']['id']}', 'sha256': hashlib.sha256(c).hexdigest(),"
        " 'visibilidad': 'entidad'})\n"
        "    print(i)\n")
    r = subprocess.run(['docker', 'exec', '-i', 'ms-documentos', 'python', '-c', script], input=PNG,
                       capture_output=True, timeout=60)
    archivo_id = r.stdout.decode().strip().splitlines()[-1]
    assert re.fullmatch(r'[0-9a-f]{24}', archivo_id), r.stderr.decode()[-500:]

    antes = comerciante.get('documentos', f'/documentos/{archivo_id}').json()
    assert antes['almacenamiento'] == 'gridfs'
    assert comerciante.get('documentos', f'/documentos/{archivo_id}/url').status_code == 409   # aún sin URL directa
    assert comerciante.get('documentos', f'/documentos/{archivo_id}/contenido').content == PNG

    migracion = sesion_de('admin').post('documentos', '/documentos/migracion')
    assert migracion.status_code == 200 and migracion.json()['migrados'] >= 1, migracion.text
    despues = comerciante.get('documentos', f'/documentos/{archivo_id}').json()
    assert despues['almacenamiento'] == 'gcs' and despues['sha256'] == antes['sha256']
    firmada = comerciante.get('documentos', f'/documentos/{archivo_id}/url').json()['url']
    assert requests.get(firmada, timeout=20).content == PNG
    # Repetirla no duplica y GridFS conserva el original
    assert sesion_de('admin').post('documentos', '/documentos/migracion').json()['migrados'] == 0
    sigue = subprocess.run(['docker', 'exec', 'ms-documentos', 'python', '-c',
                            "from abasto_dominio import extensiones; from app import app; from bson import ObjectId\n"
                            f"with app.app_context(): print(extensiones.gridfs_archivos().exists(ObjectId('{archivo_id}')))"],
                           capture_output=True, text=True, timeout=60)
    assert sigue.stdout.strip().endswith('True')


@pytest.mark.skipif(os.environ.get('PRUEBAS_GCS_REAL') != '1',
                    reason='No aplica: la expiración solo se comprueba contra el bucket real (PRUEBAS_GCS_REAL=1)')
def test_url_firmada_vence_en_el_bucket_real(comerciante, comercio):
    doc = _subir(comerciante, comercio).json()
    firmada = comerciante.get('documentos', f"/documentos/{doc['id']}/url", params={'minutos': 1}).json()['url']
    assert 'storage.googleapis.com' in firmada
    assert requests.get(firmada, timeout=20).status_code == 200
    alterada = re.sub(r'X-Goog-Signature=[0-9a-f]{8}', 'X-Goog-Signature=00000000', firmada)
    assert requests.get(alterada, timeout=20).status_code in (400, 403)    # firma inválida
    time.sleep(65)
    vencida = requests.get(firmada, timeout=20)
    assert vencida.status_code in (400, 403) and b'expired' in vencida.content.lower()
