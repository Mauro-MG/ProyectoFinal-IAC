"""
Registro único de los 24 microservicios de AbastoRed.

Es la fuente de verdad que usan la configuración (direcciones internas), el web,
ms-monitoreo (a quién revisar) y las pruebas (puertos de desarrollo). Agregar un
servicio aquí no lo publica: también hay que darlo de alta en docker-compose.yml
y en la lista del gateway (infra/gateway/nginx.conf).

El puerto es el de desarrollo (docker-compose.dev.yml lo publica en 127.0.0.1);
dentro de la red de Docker todos escuchan en el 8000 y fuera de ella sólo se
llega por el gateway: https://<host>/ms/<nombre>/...
"""
SERVICIOS = {
    # nombre: (puerto de desarrollo, descripción corta)
    'seguridad':        (8101, 'Autenticación, usuarios, roles, sesiones y bloqueo por intentos'),
    'comercios':        (8102, 'Comercios formales e informales, verificación y responsables'),
    'catalogo':         (8103, 'Catálogo maestro: productos, categorías, marcas, unidades y equivalencias'),
    'inventario':       (8104, 'Existencias, movimientos, reservas, transferencias e importación CSV'),
    'precios':          (8105, 'Precio al consumidor, historial, promociones, atípicos y estadísticas'),
    'pedidos':          (8106, 'Pedidos de abasto y su ciclo completo'),
    'analisis':         (8107, 'Cobertura, brechas, índice de acceso y datos para gráficas'),
    'notificaciones':   (8108, 'Avisos internos, preferencias, plantillas e historial'),
    'proveedores':      (8109, 'Proveedores, verificación, zonas de servicio y catálogo mayorista'),
    'abastecimiento':   (8110, 'Cotizaciones, comparación de ofertas, órdenes de compra y consolidación'),
    'disponibilidad':   (8111, 'Disponibilidad por comercio, zona y proveedor'),
    'geolocalizacion':  (8112, 'Geocodificación, distancias, radios y cobertura con PostGIS'),
    'sincronizacion':   (8113, 'Lotes offline de Android y escritorio: duplicados, conflictos y confirmación'),
    'documentos':       (8114, 'Imágenes, CSV, comprobantes y evidencias en GridFS con control de acceso'),
    'reportes':         (8115, 'Reportes operativos y gerenciales en PDF, CSV y Excel'),
    'recomendaciones':  (8116, 'Recomendación de surtido explicada y medición de resultados'),
    'demanda':          (8117, 'Demanda histórica, búsquedas no satisfechas, tendencias y estimaciones'),
    'ventas':           (8118, 'Ventas y devoluciones con actualización de inventario y comprobante'),
    'entregas':         (8119, 'Entregas de pedidos: responsable, estados logísticos, QR e incidencias'),
    'auditoria':        (8120, 'Bitácora centralizada y trazabilidad por identificador de correlación'),
    'integraciones':    (8121, 'Importación y exportación CSV/JSON/XML con validación y mapeo por lote'),
    'configuracion':    (8122, 'Reglas comerciales y parámetros centralizados'),
    'monitoreo':        (8123, 'Salud, latencia, métricas y alertas de los servicios'),
    'busqueda':         (8124, 'Búsqueda unificada de productos, comercios, proveedores y ofertas'),
}

NOMBRES = tuple(SERVICIOS)


def url_interna(nombre):
    return f'http://ms-{nombre}:8000'


def puerto(nombre):
    return SERVICIOS[nombre][0]
