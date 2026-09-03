db = db.getSiblingDB('abastored');

// Create collections
db.createCollection('catalogo_productos');
db.createCollection('audit_logs');
db.createCollection('sync_batches');
db.createCollection('price_snapshots');
db.createCollection('geo_telemetry');
db.createCollection('error_logs');
db.createCollection('notifications');

// Create indexes
db.catalogo_productos.createIndex({ "sku": 1 }, { unique: true });
db.catalogo_productos.createIndex({ "nombre": "text", "categoria_principal": "text" });
db.catalogo_productos.createIndex({ "estado": 1 });

db.audit_logs.createIndex({ "timestamp": -1 });
db.audit_logs.createIndex({ "actor_id": 1, "timestamp": -1 });
db.audit_logs.createIndex({ "entidad_afectada": 1 });

db.sync_batches.createIndex({ "batch_id": 1 }, { unique: true });
db.sync_batches.createIndex({ "status": 1 });
db.sync_batches.createIndex({ "created_at": -1 });

db.price_snapshots.createIndex({ "product_id": 1 });
db.price_snapshots.createIndex({ "zone_id": 1 });
db.price_snapshots.createIndex({ "timestamp": -1 });
db.price_snapshots.createIndex({ "product_id": 1, "zone_id": 1, "timestamp": -1 });

db.geo_telemetry.createIndex({ "device_id": 1, "timestamp": -1 });
db.geo_telemetry.createIndex({ "location": "2dsphere" });

db.error_logs.createIndex({ "timestamp": -1 });
db.error_logs.createIndex({ "level": 1 });

db.notifications.createIndex({ "user_id": 1, "read": 1 });
db.notifications.createIndex({ "created_at": -1 });

// Insert sample documents
db.catalogo_productos.insertMany([
  {
    schema_version: 1,
    sku: "TORTILLA-MAIZ-KG",
    nombre: "Tortilla de maíz",
    categoria_principal: "Abarrotes",
    unidad_medida: "kg",
    atributos: [
      { k: "canasta_basica", v: true },
      { k: "perecedero", v: true }
    ],
    estado: "activo",
    updated_at: new Date()
  },
  {
    schema_version: 1,
    sku: "LIMON-SEMILLA-KG",
    nombre: "Limón con semilla",
    categoria_principal: "Frutas y Verduras",
    unidad_medida: "kg",
    atributos: [
      { k: "origen_frecuente", v: "Michoacán" },
      { k: "perecedero", v: true }
    ],
    estado: "activo",
    updated_at: new Date()
  }
]);

db.price_snapshots.insertMany([
  {
    schema_version: 1,
    product_id: 1, // Tortilla de maíz
    zone_id: 1,
    average_price: 21.00,
    min_price: 20.00,
    max_price: 22.00,
    sample_size: 2,
    timestamp: new Date()
  },
  {
    schema_version: 1,
    product_id: 10, // Tomate saladette
    zone_id: 2,
    average_price: 24.25,
    min_price: 23.50,
    max_price: 25.00,
    sample_size: 2,
    timestamp: new Date()
  }
]);

db.error_logs.insertOne({
  schema_version: 1,
  level: "INFO",
  message: "System initialized",
  service: "database-init",
  timestamp: new Date()
});

db.audit_logs.insertOne({
  schema_version: 1,
  timestamp: new Date(),
  actor_id: null,
  accion: "INICIALIZACION",
  entidad_afectada: "MONGODB",
  datos_anteriores: null,
  datos_nuevos: { colecciones_creadas: true },
  ip_address: null,
  flag_anomalia: false
});

print("MongoDB initialization complete!");
