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
      tipo: { enum: ['pedido', 'stock_bajo', 'precio_atipico', 'comercio', 'importacion', 'sistema'] },
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

print('MongoDB de AbastoRed inicializada');
