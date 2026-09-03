-- Insert Roles
INSERT INTO roles (nombre, descripcion, permisos) VALUES
('Administrador General', 'Control total del sistema', '{"all": true}'),
('Comerciante Informal', 'Gestión de sus propios comercios y pedidos', '{"comercios": ["read", "write"], "pedidos": ["read", "write"]}'),
('Minorista Formal', 'Gestión de comercios formales y pedidos', '{"comercios": ["read", "write"], "pedidos": ["read", "write"]}'),
('Proveedor', 'Gestión de productos y recepción de pedidos', '{"productos": ["read", "write"], "pedidos": ["read", "update"]}'),
('Analista de Mercado', 'Acceso de solo lectura a datos analíticos', '{"reportes": ["read"], "precios": ["read"]}'),
('Coordinador Municipal', 'Gestión de zonas y verificación de comercios', '{"zonas": ["read", "write"], "comercios": ["read", "verify"]}'),
('Auditor', 'Revisión de logs y auditoría', '{"auditoria": ["read"]}');

-- Insert Users
INSERT INTO usuarios (email, password_hash, nombre, apellido_paterno, rol_id) VALUES
('admin@abastored.mx', crypt('Admin123!', gen_salt('bf')), 'Admin', 'General', (SELECT id FROM roles WHERE nombre = 'Administrador General')),
('comerciante@test.mx', crypt('Password123!', gen_salt('bf')), 'Juan', 'Pérez', (SELECT id FROM roles WHERE nombre = 'Comerciante Informal')),
('minorista@test.mx', crypt('Password123!', gen_salt('bf')), 'María', 'García', (SELECT id FROM roles WHERE nombre = 'Minorista Formal')),
('analista@test.mx', crypt('Password123!', gen_salt('bf')), 'Carlos', 'López', (SELECT id FROM roles WHERE nombre = 'Analista de Mercado'));

-- Insert Categorias
INSERT INTO categorias (nombre, descripcion) VALUES
('Frutas y Verduras', 'Productos frescos del campo'),
('Carnes y Embutidos', 'Proteína animal y derivados'),
('Lácteos', 'Leche, quesos y derivados'),
('Abarrotes', 'Productos empaquetados y secos'),
('Bebidas', 'Jugos, refrescos, aguas'),
('Limpieza', 'Productos de limpieza para el hogar'),
('Higiene Personal', 'Cuidado personal y baño'),
('Otros', 'Productos varios');

-- Insert Productos Maestros
INSERT INTO productos_maestros (nombre, categoria_id, unidad_medida, es_canasta_basica) VALUES
('Tortilla de maíz', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'kg', true),
('Frijol pinto', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'kg', true),
('Arroz blanco', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'kg', true),
('Aceite vegetal', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'litro', true),
('Huevo blanco', (SELECT id FROM categorias WHERE nombre = 'Carnes y Embutidos'), 'kg', true),
('Leche entera', (SELECT id FROM categorias WHERE nombre = 'Lácteos'), 'litro', true),
('Azúcar estándar', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'kg', true),
('Sal de mesa', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'kg', true),
('Chile jalapeño', (SELECT id FROM categorias WHERE nombre = 'Frutas y Verduras'), 'kg', true),
('Tomate saladette', (SELECT id FROM categorias WHERE nombre = 'Frutas y Verduras'), 'kg', true),
('Cebolla blanca', (SELECT id FROM categorias WHERE nombre = 'Frutas y Verduras'), 'kg', true),
('Manzana golden', (SELECT id FROM categorias WHERE nombre = 'Frutas y Verduras'), 'kg', false),
('Pollo entero', (SELECT id FROM categorias WHERE nombre = 'Carnes y Embutidos'), 'kg', true),
('Carne de res', (SELECT id FROM categorias WHERE nombre = 'Carnes y Embutidos'), 'kg', false),
('Limón con semilla', (SELECT id FROM categorias WHERE nombre = 'Frutas y Verduras'), 'kg', true),
('Atún en agua', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'lata', true),
('Sardina en tomate', (SELECT id FROM categorias WHERE nombre = 'Abarrotes'), 'lata', true),
('Queso fresco', (SELECT id FROM categorias WHERE nombre = 'Lácteos'), 'kg', false),
('Jabón de lavandería', (SELECT id FROM categorias WHERE nombre = 'Limpieza'), 'pieza', true),
('Papel higiénico', (SELECT id FROM categorias WHERE nombre = 'Higiene Personal'), 'paquete', true);

-- Insert Zonas Municipales
INSERT INTO zonas_municipales (nombre, municipio, estado, latitud_centro, longitud_centro, radio_km) VALUES
('Centro', 'Toluca', 'Estado de México', 19.2891, -99.6538, 2.5),
('Norte', 'Toluca', 'Estado de México', 19.3150, -99.6400, 3.0),
('Sur', 'Metepec', 'Estado de México', 19.2500, -99.6000, 2.0);

-- Insert Comercios
INSERT INTO comercios (
    usuario_id, nombre_comercio, tipo_comercio, direccion, municipio, estado,
    latitud, longitud, geom, zona_id, estado_registro
) VALUES
((SELECT id FROM usuarios WHERE email = 'minorista@test.mx'), 'Abarrotes La Esperanza', 'FORMAL_ABARROTES', 'Av. Independencia 101', 'Toluca', 'Estado de México', 19.2899000, -99.6529000, ST_SetSRID(ST_MakePoint(-99.6529000, 19.2899000), 4326), 1, 'VERIFICADO'),
((SELECT id FROM usuarios WHERE email = 'minorista@test.mx'), 'Minisuper El Centro', 'FORMAL_MINISUPER', 'Calle Hidalgo 210', 'Toluca', 'Estado de México', 19.2878000, -99.6542000, ST_SetSRID(ST_MakePoint(-99.6542000, 19.2878000), 4326), 1, 'VERIFICADO'),
((SELECT id FROM usuarios WHERE email = 'comerciante@test.mx'), 'Puesto de Frutas Juan', 'INFORMAL_FIJO', 'Mercado Norte Local 12', 'Toluca', 'Estado de México', 19.3155000, -99.6409000, ST_SetSRID(ST_MakePoint(-99.6409000, 19.3155000), 4326), 2, 'VERIFICADO'),
((SELECT id FROM usuarios WHERE email = 'comerciante@test.mx'), 'Verduras El Mercado', 'INFORMAL_TIANGUIS', 'Tianguis Norte Pasillo B', 'Toluca', 'Estado de México', 19.3162000, -99.6396000, ST_SetSRID(ST_MakePoint(-99.6396000, 19.3162000), 4326), 2, 'VERIFICADO'),
((SELECT id FROM usuarios WHERE email = 'comerciante@test.mx'), 'Antojitos María', 'INFORMAL_AMBULANTE', 'Parque Sur', 'Metepec', 'Estado de México', 19.2503000, -99.6008000, ST_SetSRID(ST_MakePoint(-99.6008000, 19.2503000), 4326), 3, 'PENDIENTE');

UPDATE zonas_municipales
SET poligono = ST_MakeEnvelope(longitud_centro - 0.01, latitud_centro - 0.01, longitud_centro + 0.01, latitud_centro + 0.01, 4326);

-- Insert Precios Comercio
INSERT INTO precios_comercio (comercio_id, producto_id, precio, usuario_registro_id) VALUES
((SELECT id FROM comercios WHERE nombre_comercio = 'Abarrotes La Esperanza'), (SELECT id FROM productos_maestros WHERE nombre = 'Tortilla de maíz'), 20.00, (SELECT id FROM usuarios WHERE email = 'minorista@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Minisuper El Centro'), (SELECT id FROM productos_maestros WHERE nombre = 'Tortilla de maíz'), 22.00, (SELECT id FROM usuarios WHERE email = 'minorista@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Puesto de Frutas Juan'), (SELECT id FROM productos_maestros WHERE nombre = 'Tomate saladette'), 25.00, (SELECT id FROM usuarios WHERE email = 'comerciante@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Verduras El Mercado'), (SELECT id FROM productos_maestros WHERE nombre = 'Tomate saladette'), 23.50, (SELECT id FROM usuarios WHERE email = 'comerciante@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Puesto de Frutas Juan'), (SELECT id FROM productos_maestros WHERE nombre = 'Cebolla blanca'), 18.00, (SELECT id FROM usuarios WHERE email = 'comerciante@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Abarrotes La Esperanza'), (SELECT id FROM productos_maestros WHERE nombre = 'Huevo blanco'), 38.00, (SELECT id FROM usuarios WHERE email = 'minorista@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Minisuper El Centro'), (SELECT id FROM productos_maestros WHERE nombre = 'Huevo blanco'), 40.00, (SELECT id FROM usuarios WHERE email = 'minorista@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Abarrotes La Esperanza'), (SELECT id FROM productos_maestros WHERE nombre = 'Leche entera'), 24.50, (SELECT id FROM usuarios WHERE email = 'minorista@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Puesto de Frutas Juan'), (SELECT id FROM productos_maestros WHERE nombre = 'Limón con semilla'), 35.00, (SELECT id FROM usuarios WHERE email = 'comerciante@test.mx')),
((SELECT id FROM comercios WHERE nombre_comercio = 'Verduras El Mercado'), (SELECT id FROM productos_maestros WHERE nombre = 'Limón con semilla'), 32.00, (SELECT id FROM usuarios WHERE email = 'comerciante@test.mx'));

-- Insert Configuracion Sistema
INSERT INTO configuracion_sistema (clave, valor, descripcion, tipo_dato) VALUES
('APP_VERSION', '1.0.0', 'Versión actual de la aplicación', 'string'),
('MAINTENANCE_MODE', 'false', 'Modo de mantenimiento del sistema', 'boolean'),
('TAX_RATE', '0.16', 'Tasa de IVA por defecto', 'float');
