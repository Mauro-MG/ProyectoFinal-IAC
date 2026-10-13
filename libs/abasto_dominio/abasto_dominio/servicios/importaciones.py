"""
Importación masiva de inventario y precios desde un archivo CSV.

Pensada para el minorista que ya lleva su inventario en una hoja de cálculo.
Columnas: producto (nombre exacto o código de barras), existencia, stock_minimo,
stock_maximo, precio. Sólo `producto` y `existencia` son obligatorias.

  * El archivo se guarda en GridFS (evidencia de qué se importó).
  * Un bloqueo en Redis impide dos importaciones simultáneas del mismo comercio.
  * Cada fila se aplica dentro de un savepoint: una fila con error no
    deshace las demás, y los errores se reportan con su número de fila.
  * La existencia se aplica como AJUSTE (conteo físico), así queda en movimientos.
  * El resultado se guarda en MongoDB (colección `importaciones`).
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import func

from abasto_dominio import extensiones
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import InventarioComercio, ProductoMaestro
from abasto_dominio.servicios import ReglaNegocioError, archivos
from abasto_dominio.servicios.auditoria import registrar_evento
from abasto_dominio.servicios.bloqueos import bloqueo
from abasto_dominio.servicios.inventario import actualizar_precio, agregar_al_catalogo, registrar_movimiento
from abasto_dominio.servicios.notificaciones import notificar

OBLIGATORIAS = ('producto', 'existencia')
OPCIONALES = ('stock_minimo', 'stock_maximo', 'precio')
MAX_FILAS = 2000


def _numero(valor, campo, obligatorio=False):
    valor = (valor or '').strip().replace('$', '').replace(',', '')
    if not valor:
        if obligatorio:
            raise ReglaNegocioError(f'Falta {campo}.')
        return None
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        raise ReglaNegocioError(f'{campo} no es un número: "{valor}".')
    if numero < 0:
        raise ReglaNegocioError(f'{campo} no puede ser negativo.')
    return numero


def _buscar_producto(texto):
    texto = (texto or '').strip()
    if not texto:
        raise ReglaNegocioError('Falta el producto.')
    producto = (ProductoMaestro.query.filter_by(activo=True)
                .filter((ProductoMaestro.codigo_barras == texto) |
                        (func.lower(ProductoMaestro.nombre) == texto.lower()))
                .first())
    if not producto:
        raise ReglaNegocioError(f'"{texto}" no está en el catálogo maestro.')
    return producto


def _aplicar_fila(comercio, fila, usuario):
    producto = _buscar_producto(fila.get('producto'))
    existencia = _numero(fila.get('existencia'), 'existencia', obligatorio=True)
    minimo = _numero(fila.get('stock_minimo'), 'stock_minimo')
    maximo = _numero(fila.get('stock_maximo'), 'stock_maximo')
    precio = _numero(fila.get('precio'), 'precio')
    if precio is not None and precio == 0:
        raise ReglaNegocioError('El precio debe ser mayor a cero.')

    renglon = InventarioComercio.query.filter_by(comercio_id=comercio.id, producto_id=producto.id, activo=True).first()
    if not renglon:
        agregar_al_catalogo(comercio, producto, usuario, existencia, minimo or 0, maximo, precio)
        return 'agregado'

    if minimo is not None:
        renglon.stock_minimo = minimo
    if maximo is not None:
        if maximo < renglon.stock_minimo:
            raise ReglaNegocioError('stock_maximo es menor que stock_minimo.')
        renglon.stock_maximo = maximo
    if existencia != renglon.existencia:
        registrar_movimiento(renglon, 'AJUSTE', existencia, usuario, motivo='Importación CSV')
    if precio is not None:
        actualizar_precio(renglon, precio, usuario, metodo_captura='IMPORTACION')
    return 'actualizado'


def importar_inventario(comercio, contenido, nombre_archivo, usuario):
    with bloqueo(f'importacion:{comercio.id}', ttl_segundos=300,
                 mensaje='Ya hay una importación en curso para este comercio.'):
        try:
            texto = contenido.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ReglaNegocioError('El archivo debe estar en UTF-8 (en Excel: Guardar como → CSV UTF-8).')

        lector = csv.DictReader(io.StringIO(texto))
        encabezados = [c.strip().lower() for c in (lector.fieldnames or [])]
        faltan = [c for c in OBLIGATORIAS if c not in encabezados]
        if faltan:
            raise ReglaNegocioError(f'Faltan columnas obligatorias: {", ".join(faltan)}.')
        lector.fieldnames = encabezados

        archivo = archivos.guardar(contenido, nombre_archivo, 'text/csv', 'importacion_csv',
                                   'comercio', comercio.id, usuario.id, 'Importación de inventario')

        conteo = {'agregado': 0, 'actualizado': 0}
        errores = []
        total = 0
        for numero_fila, fila in enumerate(lector, start=2):
            total += 1
            if total > MAX_FILAS:
                errores.append({'fila': numero_fila, 'producto': None,
                                'error': f'Se procesan como máximo {MAX_FILAS} filas.'})
                break
            try:
                with db.session.begin_nested():
                    resultado = _aplicar_fila(comercio, fila, usuario)
                conteo[resultado] += 1
            except ReglaNegocioError as error:
                errores.append({'fila': numero_fila, 'producto': (fila.get('producto') or '').strip(),
                                'error': str(error)})

        resumen = {
            'schema_version': 1,
            'comercio_id': str(comercio.id),
            'usuario_id': str(usuario.id),
            'archivo_id': archivo['id'],
            'nombre_archivo': nombre_archivo,
            'filas_total': total,
            'agregados': conteo['agregado'],
            'actualizados': conteo['actualizado'],
            'con_error': len(errores),
            'errores': errores[:200],
            'fecha': datetime.now(timezone.utc),
        }
        resultado = extensiones.mongo_db()['importaciones'].insert_one(dict(resumen))
        resumen['id'] = str(resultado.inserted_id)

        registrar_evento(usuario.id, 'CREACION', 'Importacion', resumen['id'],
                         f'Importación CSV en {comercio.nombre_comercio}: '
                         f'{conteo["agregado"] + conteo["actualizado"]} de {total} filas aplicadas',
                         datos_nuevos={k: resumen[k] for k in ('filas_total', 'agregados', 'actualizados', 'con_error')})
        notificar(usuario.id, 'importacion', 'Importación de inventario terminada',
                  f'{nombre_archivo}: {conteo["agregado"]} agregados, {conteo["actualizado"]} actualizados, '
                  f'{len(errores)} con error.', url=f'/inventario?comercio_id={comercio.id}',
                  entidad={'tipo': 'comercio', 'id': str(comercio.id)}, origen='inventario')
        return resumen


def historial(comercio_id, limite=10):
    cursor = (extensiones.mongo_db()['importaciones']
              .find({'comercio_id': str(comercio_id)}).sort('fecha', -1).limit(limite))
    resultado = []
    for doc in cursor:
        doc['id'] = str(doc.pop('_id'))
        resultado.append(doc)
    return resultado
