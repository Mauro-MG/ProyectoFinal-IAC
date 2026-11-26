"""
ms-reportes: reportes operativos y gerenciales en PDF, CSV, Excel y JSON.

Es DUEÑO de los objetos reportes/ del bucket privado de Cloud Storage (archivos generados, 30 días),
de su colección de metadatos `reportes_generados` y de `reportes_programados`. El archivo se descarga
por el servicio o con una URL firmada que vence (GET /reportes/{id}/url). Los datos se LEEN (consultas de sólo lectura y funciones de análisis del
dominio); nunca escribe en tablas de negocio.

- Tipos: inventario, ventas, precios, pedidos, proveedores, cobertura y brechas. Cada tipo revisa
  los permisos del usuario (p. ej. el inventario sólo de sus comercios; cobertura sólo analistas).
- Filtros por comercio, zona, días y canasta básica.
- Formatos: PDF (reportlab, horizontal si hay muchas columnas), Excel (openpyxl, con hoja de
  resumen), CSV (UTF-8 con BOM) y JSON.
- Programación: diaria, semanal o mensual a una hora; POST /programados/ejecucion genera los que
  tocan (en producción lo invoca Cloud Scheduler cada hora) y avisa al dueño por ms-notificaciones.
  Cada programado se genera con los permisos ACTUALES de su dueño.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import hashlib

import gridfs
import gridfs.errors
from bson import ObjectId
from flask import Response, g, request
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado, prohibido, tiene
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.servicios import almacenamiento
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.notificaciones import notificar

from esquemas import CONTRATOS_XML, ProgramadoEntrada, ReporteEntrada, ReportesConsulta, UrlConsulta
from formatos_archivo import GENERADORES, TIPOS_MIME
from generadores import TIPOS

srv = Servicio('reportes', 'Reportes',
               'Generación de reportes operativos y gerenciales de inventario, precios, ventas, pedidos, proveedores, '
               'cobertura y brechas, con filtros, exportación a PDF, CSV y Excel, y programación periódica.',
               xsd=Path(__file__).parent / 'xsd' / 'reportes.xsd', contratos=CONTRATOS_XML,
               dependencias=('postgres', 'redis', 'mongodb', 'storage'), opcionales=())
app = srv.app

MONTERREY = timezone(timedelta(hours=-6))
VIGENCIA_DIAS = 30
FRECUENCIAS = {'diaria': timedelta(days=1), 'semanal': timedelta(weeks=1), 'mensual': timedelta(days=30)}


def _generados():
    """Metadatos de cada reporte; el archivo está en el bucket (reportes/<usuario>/<id>.<formato>)."""
    return extensiones.mongo_db()['reportes_generados']


def _gridfs_anterior():
    """Reportes generados antes de Cloud Storage: solo lectura hasta que venzan (30 días)."""
    return gridfs.GridFS(extensiones.mongo_db(), collection='reportes')


def _programados():
    return extensiones.mongo_db()['reportes_programados']


def reporte_a_dict(doc):
    return {'id': str(doc['_id']), 'tipo': doc.get('tipo'), 'titulo': doc.get('titulo'), 'formato': doc.get('formato'),
            'nombre_archivo': doc['nombre_archivo'], 'tamano_bytes': doc['tamano_bytes'],
            'renglones': doc.get('renglones', 0), 'filtros': doc.get('filtros') or {}, 'generado': doc['generado'],
            'expira': doc['generado'] + timedelta(days=VIGENCIA_DIAS),
            'url_archivo': f'{request.script_root}/api/v1/reportes/{doc["_id"]}/archivo' if request else '',
            'programado_id': doc.get('programado_id'), 'sha256': doc.get('sha256')}


def _de_gridfs(archivo):
    m = archivo.metadata or {}
    return {'_id': archivo._id, 'usuario_id': m.get('usuario_id'), 'tipo': m.get('tipo'), 'titulo': m.get('titulo'),
            'formato': m.get('formato'), 'nombre_archivo': archivo.filename, 'tamano_bytes': archivo.length,
            'renglones': m.get('renglones', 0), 'filtros': m.get('filtros'), 'generado': archivo.upload_date,
            'programado_id': m.get('programado_id'), 'objeto': None}


def generar(tipo, formato, filtros, programado_id=None):
    """Arma el reporte con los permisos de g.claims, lo sube al bucket y registra sus metadatos."""
    funcion = TIPOS[tipo][0]
    titulo, columnas, filas, resumen = funcion({k: v for k, v in filtros.items() if v is not None})
    contenido = GENERADORES[formato](titulo, columnas, filas, resumen)
    nombre = f"{tipo}_{datetime.now(MONTERREY):%Y%m%d_%H%M}.{formato}"
    reporte_id = ObjectId()
    objeto = f"reportes/{g.claims['sub']}/{reporte_id}.{formato}"
    sha256 = hashlib.sha256(contenido).hexdigest()
    almacenamiento.subir(objeto, contenido, TIPOS_MIME[formato], {'sha256': sha256, 'tipo': tipo})
    doc = {'_id': reporte_id, 'usuario_id': g.claims['sub'], 'tipo': tipo, 'titulo': titulo, 'formato': formato,
           'filtros': filtros, 'renglones': len(filas), 'programado_id': programado_id, 'nombre_archivo': nombre,
           'tamano_bytes': len(contenido), 'sha256': sha256, 'objeto': objeto, 'generado': datetime.now(timezone.utc)}
    try:
        _generados().insert_one(doc)
    except Exception:
        almacenamiento.borrar(objeto)
        raise
    registrar_evento(UUID(g.claims['sub']), 'LECTURA', 'Reporte', str(reporte_id),
                     f'Reporte {tipo} en {formato.upper()}: {titulo} ({len(filas)} renglones)',
                     datos_nuevos={'filtros': filtros, 'formato': formato})
    db.session.commit()
    return doc


def _mi_reporte(id):
    try:
        oid = ObjectId(id)
    except Exception:  # noqa: BLE001 - id inválido
        raise no_encontrado('El reporte')
    doc = _generados().find_one({'_id': oid})
    if not doc:
        try:
            doc = _de_gridfs(_gridfs_anterior().get(oid))
        except gridfs.errors.NoFile:
            raise no_encontrado('El reporte')
    if doc.get('usuario_id') != g.claims['sub'] and not tiene('servicios.monitorear'):
        raise prohibido('El reporte es de otro usuario.')
    return doc


# ---------------------------------------------------------------- reportes bajo demanda

@srv.ruta('/reportes/tipos', 'GET', resumen='Reportes disponibles', etiqueta='Reportes', permisos=['reportes.ver',
          'inventario.gestionar', 'pedidos.atender'], raiz_xml='tipos')
def tipos():
    return {'tipos': [{'tipo': t, 'descripcion': d, 'filtros': f, 'formatos': list(GENERADORES)}
                      for t, (_, d, f) in TIPOS.items()]}


@srv.ruta('/reportes', 'POST', resumen='Generar un reporte', etiqueta='Reportes',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], cuerpo=ReporteEntrada, status=201,
          raiz_xml='reporte', entrada_xml='reporte_entrada',
          ejemplo_entrada={'tipo': 'inventario', 'formato': 'xlsx', 'filtros': {'comercio_id': '3122a5b1-...'}})
def crear(datos):
    """Se guarda 30 días; se descarga con `url_archivo`."""
    return reporte_a_dict(generar(datos.tipo, datos.formato, datos.filtros.model_dump(exclude_none=True)))


@srv.ruta('/reportes', 'GET', resumen='Mis reportes generados', etiqueta='Reportes',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], consulta=ReportesConsulta,
          raiz_xml='reportes')
def listar(q):
    docs = list(_generados().find({'usuario_id': g.claims['sub']}).sort('generado', -1).limit(q.limite))
    return {'total': len(docs), 'reportes': [reporte_a_dict(d) for d in docs]}


@srv.ruta('/reportes/<id>', 'GET', resumen='Datos de un reporte', etiqueta='Reportes',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], raiz_xml='reporte')
def detalle(id):
    return reporte_a_dict(_mi_reporte(id))


@srv.ruta('/reportes/<id>/archivo', 'GET', resumen='Descargar el archivo', etiqueta='Reportes',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], errores=(401, 403, 404))
def descargar(id):
    doc = _mi_reporte(id)
    if doc.get('objeto'):
        contenido = almacenamiento.descargar(doc['objeto'])
    else:
        contenido = _gridfs_anterior().get(doc['_id']).read()
    if contenido is None:
        raise ErrorApi(404, 'contenido_no_encontrado', 'El reporte venció o ya no está en el almacenamiento.')
    return Response(contenido, mimetype=TIPOS_MIME.get(doc.get('formato'), 'application/octet-stream'),
                    headers={'Content-Disposition': f'attachment; filename="{doc["nombre_archivo"]}"'})


@srv.ruta('/reportes/<id>/url', 'GET', resumen='URL firmada temporal del archivo', etiqueta='Reportes',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], consulta=UrlConsulta,
          raiz_xml='url_firmada', errores=(401, 403, 404, 409, 503))
def url_firmada(id, q):
    """Solo para el dueño del reporte. Descarga directa del bucket privado; vence en `minutos`."""
    doc = _mi_reporte(id)
    if not doc.get('objeto'):
        raise ErrorApi(409, 'sin_url_directa', 'Reporte anterior a Cloud Storage: descárgalo con /archivo.')
    url, expira = almacenamiento.url_firmada(doc['objeto'], doc['nombre_archivo'], TIPOS_MIME[doc['formato']],
                                             q.minutos)
    return {'id': id, 'url': url, 'expira': expira, 'minutos': q.minutos, 'tipo_mime': TIPOS_MIME[doc['formato']],
            'sha256': doc.get('sha256')}


# ---------------------------------------------------------------- programados

def proxima(frecuencia, hora, desde=None):
    ahora = (desde or datetime.now(timezone.utc)).astimezone(MONTERREY)
    siguiente = ahora.replace(hour=hora, minute=0, second=0, microsecond=0)
    if siguiente <= ahora:
        siguiente += timedelta(days=1)
    if frecuencia == 'semanal':
        siguiente += timedelta(days=(7 - siguiente.weekday()) % 7)   # los lunes
    elif frecuencia == 'mensual':
        while siguiente.day != 1:                                    # el día 1
            siguiente += timedelta(days=1)
    return siguiente.astimezone(timezone.utc)


def programado_a_dict(p):
    return {'id': str(p['_id']), 'nombre': p['nombre'], 'tipo': p['tipo'], 'formato': p['formato'],
            'filtros': p['filtros'], 'frecuencia': p['frecuencia'], 'hora': p['hora'], 'activo': p['activo'],
            'proxima_ejecucion': p['proxima_ejecucion'], 'ultima_ejecucion': p.get('ultima_ejecucion'),
            'ultimo_reporte_id': p.get('ultimo_reporte_id'), 'ultimo_error': p.get('ultimo_error')}


@srv.ruta('/programados', 'POST', resumen='Programar un reporte', etiqueta='Programación',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], cuerpo=ProgramadoEntrada, status=201,
          raiz_xml='programado', entrada_xml='programado_entrada',
          ejemplo_entrada={'nombre': 'Inventario de los lunes', 'tipo': 'inventario', 'formato': 'pdf',
                           'filtros': {'comercio_id': '3122a5b1-...'}, 'frecuencia': 'semanal', 'hora': 7})
def programar(datos):
    """Se valida generando una vez los datos (si no tienes permiso para ese reporte, se rechaza ahora)."""
    TIPOS[datos.tipo][0](datos.filtros.model_dump(exclude_none=True))
    documento = {**datos.model_dump(mode='json'), 'filtros': datos.filtros.model_dump(exclude_none=True),
                 'usuario_id': g.claims['sub'], 'activo': True, 'creado': datetime.now(timezone.utc),
                 'proxima_ejecucion': proxima(datos.frecuencia, datos.hora)}
    documento['_id'] = _programados().insert_one(documento).inserted_id
    return programado_a_dict(documento)


@srv.ruta('/programados', 'GET', resumen='Mis reportes programados', etiqueta='Programación',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], raiz_xml='programados')
def programados():
    return {'programados': [programado_a_dict(p) for p in
                            _programados().find({'usuario_id': g.claims['sub']}).sort('creado', -1)]}


@srv.ruta('/programados/<id>', 'DELETE', resumen='Cancelar un programado', etiqueta='Programación',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], raiz_xml='resultado')
def cancelar(id):
    try:
        resultado = _programados().update_one({'_id': ObjectId(id), 'usuario_id': g.claims['sub']},
                                              {'$set': {'activo': False}})
    except Exception:  # noqa: BLE001
        resultado = None
    if not resultado or not resultado.matched_count:
        raise no_encontrado('El programado')
    return {'mensaje': 'Reporte programado cancelado', 'id': id}


def claims_de(usuario_id):
    """Permisos actuales del dueño del programado (si lo desactivaron o le quitaron el permiso, ya no se genera)."""
    fila = db.session.execute(text(
        'SELECT u.id::text AS sub, u.activo, r.nombre AS rol, r.permisos, '
        'COALESCE((SELECT p.id::text FROM proveedores p WHERE p.usuario_id = u.id), u.proveedor_id::text) AS proveedor_id '
        'FROM usuarios u JOIN roles r ON r.id = u.rol_id WHERE u.id = :u'), {'u': usuario_id}).first()
    if not fila or not fila.activo:
        return None
    claims = {'sub': fila.sub, 'tipo': 'acceso', 'rol': fila.rol, 'permisos': list(fila.permisos or [])}
    if fila.proveedor_id:
        claims['proveedor_id'] = fila.proveedor_id
    return claims


@srv.ruta('/programados/ejecucion', 'POST', resumen='Generar los programados que ya tocan', etiqueta='Programación',
          permisos=['servicios.monitorear'], raiz_xml='ejecucion')
def ejecutar():
    """Para cada programado activo con `proxima_ejecucion` vencida: genera el reporte con los permisos de su dueño,
    lo avisa por ms-notificaciones y calcula la siguiente fecha."""
    ahora = datetime.now(timezone.utc)
    pendientes = list(_programados().find({'activo': True, 'proxima_ejecucion': {'$lte': ahora}}).limit(50))
    claims_operador = g.claims
    generados, errores = [], 0
    for p in pendientes:
        cambios = {'ultima_ejecucion': ahora, 'proxima_ejecucion': proxima(p['frecuencia'], p['hora'], ahora)}
        try:
            claims = claims_de(p['usuario_id'])
            if not claims:
                raise ErrorApi(409, 'usuario_inactivo', 'El dueño del programado ya no está activo.')
            g.claims = claims
            reporte = generar(p['tipo'], p['formato'], p['filtros'], programado_id=str(p['_id']))
            cambios.update(ultimo_reporte_id=str(reporte['_id']), ultimo_error=None)
            generados.append(reporte_a_dict(reporte))
            notificar(p['usuario_id'], 'sistema', f"Tu reporte «{p['nombre']}» está listo",
                      f"{reporte['titulo']} ({p['formato'].upper()}).",
                      url=f"/ms/reportes/api/v1/reportes/{reporte['_id']}/archivo", origen='reportes')
        except ErrorApi as error:
            db.session.rollback()
            errores += 1
            cambios['ultimo_error'] = error.mensaje
        finally:
            g.claims = claims_operador
        _programados().update_one({'_id': p['_id']}, {'$set': cambios})
    return {'revisados': len(pendientes), 'generados': len(generados), 'con_error': errores, 'reportes': generados}
