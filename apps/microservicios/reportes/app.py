"""
ms-reportes: reportes operativos y gerenciales en PDF, CSV, Excel y JSON.

Es DUEÑO del bucket GridFS `reportes` (los archivos generados, 30 días) y de la colección
`reportes_programados`. Los datos se LEEN (consultas de sólo lectura y funciones de análisis del
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

import gridfs
from bson import ObjectId
from flask import Response, g, request
from sqlalchemy import text

from abasto_api import ErrorApi, Servicio, no_encontrado, prohibido, tiene
from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.notificaciones import notificar

from esquemas import CONTRATOS_XML, ProgramadoEntrada, ReporteEntrada, ReportesConsulta
from formatos_archivo import GENERADORES, TIPOS_MIME
from generadores import TIPOS

srv = Servicio('reportes', 'Reportes',
               'Generación de reportes operativos y gerenciales de inventario, precios, ventas, pedidos, proveedores, '
               'cobertura y brechas, con filtros, exportación a PDF, CSV y Excel, y programación periódica.',
               xsd=Path(__file__).parent / 'xsd' / 'reportes.xsd', contratos=CONTRATOS_XML)
app = srv.app

MONTERREY = timezone(timedelta(hours=-6))
VIGENCIA_DIAS = 30
FRECUENCIAS = {'diaria': timedelta(days=1), 'semanal': timedelta(weeks=1), 'mensual': timedelta(days=30)}


def _bucket():
    return gridfs.GridFS(extensiones.mongo_db(), collection='reportes')


def _programados():
    return extensiones.mongo_db()['reportes_programados']


def reporte_a_dict(archivo):
    m = archivo.metadata or {}
    return {'id': str(archivo._id), 'tipo': m.get('tipo'), 'titulo': m.get('titulo'), 'formato': m.get('formato'),
            'nombre_archivo': archivo.filename, 'tamano_bytes': archivo.length, 'renglones': m.get('renglones', 0),
            'filtros': m.get('filtros') or {}, 'generado': archivo.upload_date,
            'expira': archivo.upload_date + timedelta(days=VIGENCIA_DIAS),
            'url_archivo': f'{request.script_root}/api/v1/reportes/{archivo._id}/archivo' if request else '',
            'programado_id': m.get('programado_id')}


def generar(tipo, formato, filtros, programado_id=None):
    """Arma el reporte con los permisos de g.claims y lo guarda en GridFS."""
    funcion = TIPOS[tipo][0]
    titulo, columnas, filas, resumen = funcion({k: v for k, v in filtros.items() if v is not None})
    contenido = GENERADORES[formato](titulo, columnas, filas, resumen)
    nombre = f"{tipo}_{datetime.now(MONTERREY):%Y%m%d_%H%M}.{formato}"
    archivo_id = _bucket().put(contenido, filename=nombre, contentType=TIPOS_MIME[formato], metadata={
        'usuario_id': g.claims['sub'], 'tipo': tipo, 'titulo': titulo, 'formato': formato, 'filtros': filtros,
        'renglones': len(filas), 'programado_id': programado_id})
    registrar_evento(UUID(g.claims['sub']), 'LECTURA', 'Reporte', str(archivo_id),
                     f'Reporte {tipo} en {formato.upper()}: {titulo} ({len(filas)} renglones)',
                     datos_nuevos={'filtros': filtros, 'formato': formato})
    db.session.commit()
    return _bucket().get(archivo_id)


def _mi_reporte(id):
    try:
        archivo = _bucket().get(ObjectId(id))
    except Exception:  # noqa: BLE001 - id inválido o inexistente
        raise no_encontrado('El reporte')
    if (archivo.metadata or {}).get('usuario_id') != g.claims['sub'] and not tiene('servicios.monitorear'):
        raise prohibido('El reporte es de otro usuario.')
    return archivo


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
    archivos = list(_bucket().find({'metadata.usuario_id': g.claims['sub']}).sort('uploadDate', -1).limit(q.limite))
    return {'total': len(archivos), 'reportes': [reporte_a_dict(a) for a in archivos]}


@srv.ruta('/reportes/<id>', 'GET', resumen='Datos de un reporte', etiqueta='Reportes',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], raiz_xml='reporte')
def detalle(id):
    return reporte_a_dict(_mi_reporte(id))


@srv.ruta('/reportes/<id>/archivo', 'GET', resumen='Descargar el archivo', etiqueta='Reportes',
          permisos=['reportes.ver', 'inventario.gestionar', 'pedidos.atender'], errores=(401, 403, 404))
def descargar(id):
    archivo = _mi_reporte(id)
    return Response(archivo.read(), mimetype=TIPOS_MIME.get((archivo.metadata or {}).get('formato'), 'application/octet-stream'),
                    headers={'Content-Disposition': f'attachment; filename="{archivo.filename}"'})


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
            archivo = generar(p['tipo'], p['formato'], p['filtros'], programado_id=str(p['_id']))
            cambios.update(ultimo_reporte_id=str(archivo._id), ultimo_error=None)
            generados.append(reporte_a_dict(archivo))
            notificar(p['usuario_id'], 'sistema', f"Tu reporte «{p['nombre']}» está listo",
                      f"{(archivo.metadata or {}).get('titulo')} ({p['formato'].upper()}).",
                      url=f"/ms/reportes/api/v1/reportes/{archivo._id}/archivo", origen='reportes')
        except ErrorApi as error:
            db.session.rollback()
            errores += 1
            cambios['ultimo_error'] = error.mensaje
        finally:
            g.claims = claims_operador
        _programados().update_one({'_id': p['_id']}, {'$set': cambios})
    return {'revisados': len(pendientes), 'generados': len(generados), 'con_error': errores, 'reportes': generados}
