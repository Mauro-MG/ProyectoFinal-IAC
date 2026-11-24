// AbastoRed - Equipo 01
// Colecciones de MongoDB, índices y validación de esquema.
// Se ejecuta una sola vez, al crear el volumen de datos del contenedor.
//
// Todas las colecciones se relacionan con PostgreSQL por identificadores:
// usuario_id, comercio_id, proveedor_id, pedido_id (UUID como texto) y
// zona_id, producto_id (enteros).

db = db.getSiblingDB('abastored');

// --------------------------------------------------------------- notificaciones
db.createCollection('notificaciones', {
  validator: { $jsonSchema: {
    bsonType: 'object',
    required: ['usuario_id', 'tipo', 'titulo', 'mensaje', 'leida', 'creada_en'],
    properties: {
      usuario_id: { bsonType: 'string' },
      tipo: { enum: ['pedido', 'stock_bajo', 'precio_atipico', 'comercio', 'importacion', 'sistema',
                     'entrega', 'incidencia', 'cotizacion', 'recomendacion', 'venta', 'proveedor'] },
      titulo: { bsonType: 'string', maxLength: 200 },
      mensaje: { bsonType: 'string', maxLength: 1000 },
      prioridad: { enum: ['normal', 'alta'] },
      leida: { bsonType: 'bool' },
      creada_en: { bsonType: 'date' }
    }
  }}
});
db.notificaciones.createIndex({ usuario_id: 1, leida: 1, creada_en: -1 });
db.notificaciones.createIndex({ tipo: 1, creada_en: -1 });
db.notificaciones.createIndex({ expira_en: 1 }, { expireAfterSeconds: 0 });   // borrado automático a los 90 días

// --------------------------------------------------------------- eventos del pedido
db.createCollection('eventos_pedido');
db.eventos_pedido.createIndex({ pedido_id: 1, fecha: 1 });
db.eventos_pedido.createIndex({ proveedor_id: 1, fecha: -1 });
db.eventos_pedido.createIndex({ estado_nuevo: 1, fecha: -1 });

// --------------------------------------------------------------- históricos de algoritmos
db.createCollection('snapshots_precios');
db.snapshots_precios.createIndex({ fecha: 1, zona_id: 1, producto_id: 1, sector: 1 }, { unique: true });
db.snapshots_precios.createIndex({ producto_id: 1, fecha: -1 });

db.createCollection('ejecuciones_analisis');
db.ejecuciones_analisis.createIndex({ fecha: -1 });
db.ejecuciones_analisis.createIndex({ 'zonas.zona_id': 1, fecha: -1 });

// --------------------------------------------------------------- importaciones CSV
db.createCollection('importaciones');
db.importaciones.createIndex({ comercio_id: 1, fecha: -1 });

// --------------------------------------------------------------- bitácora de peticiones a microservicios
db.createCollection('bitacora_peticiones');
db.bitacora_peticiones.createIndex({ servicio: 1, fecha: -1 });
db.bitacora_peticiones.createIndex({ correlation_id: 1 });
db.bitacora_peticiones.createIndex({ status: 1, fecha: -1 });
db.bitacora_peticiones.createIndex({ fecha: 1 }, { expireAfterSeconds: 60 * 60 * 24 * 30 });   // 30 días

// --------------------------------------------------------------- archivos (GridFS, bucket "archivos")
db.createCollection('archivos.files');
db.createCollection('archivos.chunks');
db['archivos.files'].createIndex({ 'metadata.entidad': 1, 'metadata.entidad_id': 1 });
db['archivos.files'].createIndex({ 'metadata.categoria': 1, uploadDate: -1 });
db['archivos.chunks'].createIndex({ files_id: 1, n: 1 }, { unique: true });

// =============================================================== entrega final: servicios 8109-8124
// --------------------------------------------------------------- ms-auditoria: bitácora centralizada
// Copia de cada evento de auditoria_eventos con el servicio y el X-Correlation-ID (ver servicios/auditoria.py)
db.createCollection('eventos_auditoria');
db.eventos_auditoria.createIndex({ correlation_id: 1, fecha: 1 });
db.eventos_auditoria.createIndex({ servicio: 1, fecha: -1 });
db.eventos_auditoria.createIndex({ entidad: 1, entidad_id: 1, fecha: -1 });
db.eventos_auditoria.createIndex({ usuario_id: 1, fecha: -1 });
db.eventos_auditoria.createIndex({ id_postgres: 1 }, { unique: true, partialFilterExpression: { id_postgres: { $type: 'number' } } });

// --------------------------------------------------------------- ms-sincronizacion: lotes offline
db.createCollection('sincronizacion_lotes');
db.sincronizacion_lotes.createIndex({ usuario_id: 1, recibido: -1 });
db.sincronizacion_lotes.createIndex({ dispositivo_id: 1, lote_id: 1 }, { unique: true });
db.createCollection('sincronizacion_operaciones');
// Control de duplicados: la misma operación de un dispositivo se aplica una sola vez
db.sincronizacion_operaciones.createIndex({ dispositivo_id: 1, operacion_id: 1 }, { unique: true });
db.sincronizacion_operaciones.createIndex({ lote_id: 1 });
db.sincronizacion_operaciones.createIndex({ estado: 1, actualizado: -1 });

// --------------------------------------------------------------- ms-demanda
db.createCollection('demanda_busquedas');
db.demanda_busquedas.createIndex({ producto_id: 1, fecha: -1 });
db.demanda_busquedas.createIndex({ zona_id: 1, encontrado: 1, fecha: -1 });
db.demanda_busquedas.createIndex({ fecha: 1 }, { expireAfterSeconds: 60 * 60 * 24 * 400 });   // poco más de un año

// --------------------------------------------------------------- ms-recomendaciones
db.createCollection('recomendaciones_emitidas');
db.recomendaciones_emitidas.createIndex({ comercio_id: 1, emitida: -1 });
db.recomendaciones_emitidas.createIndex({ comercio_id: 1, producto_id: 1, emitida: -1 });

// --------------------------------------------------------------- ms-integraciones
db.createCollection('integraciones_lotes');
db.integraciones_lotes.createIndex({ usuario_id: 1, fecha: -1 });
db.createCollection('integraciones_conectores');
db.integraciones_conectores.createIndex({ propietario_id: 1, nombre: 1 }, { unique: true });

// --------------------------------------------------------------- ms-monitoreo
db.createCollection('alertas_infraestructura');
db.alertas_infraestructura.createIndex({ activa: 1, fecha: -1 });
db.alertas_infraestructura.createIndex({ servicio: 1, regla: 1, activa: 1 });

// --------------------------------------------------------------- ms-reportes (archivos en GridFS, bucket "reportes")
db.createCollection('reportes_programados');
db.reportes_programados.createIndex({ usuario_id: 1 });
db.reportes_programados.createIndex({ activo: 1, proxima_ejecucion: 1 });
db.createCollection('reportes.files');
db.createCollection('reportes.chunks');
db['reportes.chunks'].createIndex({ files_id: 1, n: 1 }, { unique: true });
db['reportes.files'].createIndex({ 'metadata.usuario_id': 1, uploadDate: -1 });
db['reportes.files'].createIndex({ uploadDate: 1 }, { expireAfterSeconds: 60 * 60 * 24 * 30 });

// --------------------------------------------------------------- ms-notificaciones: preferencias, plantillas, dispositivos
db.createCollection('preferencias_notificacion');
db.preferencias_notificacion.createIndex({ usuario_id: 1 }, { unique: true });
db.createCollection('plantillas_notificacion');
db.plantillas_notificacion.createIndex({ clave: 1 }, { unique: true });
db.createCollection('dispositivos_push');
db.dispositivos_push.createIndex({ usuario_id: 1 });
db.dispositivos_push.createIndex({ token: 1 }, { unique: true });
db.createCollection('entregas_canal');
db.entregas_canal.createIndex({ usuario_id: 1, fecha: -1 });

print('MongoDB de AbastoRed inicializada');
