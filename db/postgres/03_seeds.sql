-- =====================================================================
-- AbastoRed - Equipo 01
-- Carga inicial de datos (área metropolitana de Monterrey)
--
-- Catálogos, usuarios, comercios y proveedores se capturan explícitamente.
-- Inventarios, historial de precios y ventas se generan con random()
-- usando una semilla fija para que la carga sea reproducible.
-- Contraseña de todos los usuarios de prueba: Password123!  (admin: Admin123!)
-- =====================================================================

SELECT setseed(0.2026);

-- ---------------------------------------------------------------------
-- Roles y permisos
-- ---------------------------------------------------------------------
INSERT INTO roles (nombre, descripcion, permisos) VALUES
('Administrador General', 'Administra usuarios, roles, catálogos y parámetros del sistema',
 '["usuarios.gestionar","roles.gestionar","config.gestionar","catalogos.gestionar","comercios.ver_todos","comercios.validar","comercios.gestionar","inventario.gestionar","precios.consultar","proveedores.consultar","pedidos.ver_todos","analisis.ver","recomendaciones.ver","reportes.ver","auditoria.ver"]'),
('Comerciante Informal', 'Puesto de tianguis, mercado o ambulante. Administra su comercio, inventario y pedidos',
 '["comercios.gestionar","inventario.gestionar","precios.consultar","proveedores.consultar","pedidos.crear","recomendaciones.ver"]'),
('Minorista Formal', 'Tienda de abarrotes, minisúper o recaudería establecida',
 '["comercios.gestionar","inventario.gestionar","precios.consultar","proveedores.consultar","pedidos.crear","recomendaciones.ver","reportes.ver"]'),
('Proveedor', 'Mayorista o distribuidor. Publica su catálogo y atiende pedidos de abasto',
 '["proveedor.catalogo","pedidos.atender","precios.consultar"]'),
('Analista de Mercado', 'Consulta precios, cobertura, brechas, tendencias y reportes',
 '["comercios.ver_todos","precios.consultar","proveedores.consultar","analisis.ver","reportes.ver"]'),
('Coordinador Municipal', 'Consulta zonas, cobertura e indicadores; valida comercios de su municipio',
 '["comercios.ver_todos","comercios.validar","precios.consultar","analisis.ver","reportes.ver"]'),
('Auditor', 'Consulta la bitácora, el historial de pedidos y las operaciones críticas',
 '["auditoria.ver","pedidos.ver_todos"]');

-- ---------------------------------------------------------------------
-- Usuarios
-- ---------------------------------------------------------------------
INSERT INTO usuarios (email, password_hash, nombre, apellido_paterno, rol_id, email_verificado)
SELECT u.email, crypt(u.pwd, gen_salt('bf')), u.nombre, u.apellido, r.id, true
FROM (VALUES
    ('admin@abastored.mx',       'Admin123!',    'Admin',   'General',    'Administrador General'),
    ('comerciante@test.mx',      'Password123!', 'Juan',    'Pérez',      'Comerciante Informal'),
    ('rosa.hernandez@test.mx',   'Password123!', 'Rosa',    'Hernández',  'Comerciante Informal'),
    ('beto.garza@test.mx',       'Password123!', 'Alberto', 'Garza',      'Comerciante Informal'),
    ('lucia.rodriguez@test.mx',  'Password123!', 'Lucía',   'Rodríguez',  'Comerciante Informal'),
    ('minorista@test.mx',        'Password123!', 'María',   'García',     'Minorista Formal'),
    ('jorge.trevino@test.mx',    'Password123!', 'Jorge',   'Treviño',    'Minorista Formal'),
    ('martha.salinas@test.mx',   'Password123!', 'Martha',  'Salinas',    'Minorista Formal'),
    ('raul.cantu@test.mx',       'Password123!', 'Raúl',    'Cantú',      'Minorista Formal'),
    ('proveedor@test.mx',        'Password123!', 'Laura',   'Martínez',   'Proveedor'),
    ('proveedor2@test.mx',       'Password123!', 'Ernesto', 'Villarreal', 'Proveedor'),
    ('proveedor3@test.mx',       'Password123!', 'Silvia',  'Elizondo',   'Proveedor'),
    ('proveedor4@test.mx',       'Password123!', 'Hugo',    'Leal',       'Proveedor'),
    ('analista@test.mx',         'Password123!', 'Carlos',  'López',      'Analista de Mercado'),
    ('coordinador@test.mx',      'Password123!', 'Miguel',  'Torres',     'Coordinador Municipal'),
    ('auditor@test.mx',          'Password123!', 'Ana',     'Sánchez',    'Auditor')
) AS u(email, pwd, nombre, apellido, rol)
JOIN roles r ON r.nombre = u.rol;

-- ---------------------------------------------------------------------
-- Zonas (población estimada por zona, no por municipio completo)
-- ---------------------------------------------------------------------
INSERT INTO zonas_municipales (nombre, municipio, estado, latitud_centro, longitud_centro, radio_km, poblacion) VALUES
('Monterrey Centro',        'Monterrey',        'Nuevo León', 25.6714, -100.3095, 2.0, 38000),
('García Norte',            'García',           'Nuevo León', 25.8200, -100.5900, 2.5, 52000),
('Escobedo Poniente',       'General Escobedo', 'Nuevo León', 25.7950, -100.3400, 2.0, 41000),
('Apodaca Centro',          'Apodaca',          'Nuevo León', 25.7800, -100.1900, 2.0, 36000),
('Guadalupe Oriente',       'Guadalupe',        'Nuevo León', 25.6780, -100.2300, 2.0, 44000),
('Santa Catarina Poniente', 'Santa Catarina',   'Nuevo León', 25.6750, -100.4700, 2.0, 30000);

-- ---------------------------------------------------------------------
-- Catálogo maestro
-- ---------------------------------------------------------------------
INSERT INTO categorias (nombre, descripcion, orden) VALUES
('Abarrotes',          'Productos empacados y secos', 1),
('Frutas y Verduras',  'Productos frescos a granel', 2),
('Lácteos',            'Leche, quesos y derivados', 3),
('Carnes y Huevo',     'Proteína animal', 4),
('Bebidas',            'Refrescos, jugos y agua', 5),
('Limpieza',           'Limpieza del hogar', 6),
('Higiene Personal',   'Cuidado personal', 7);

-- Precio de referencia al consumidor; sólo se usa para generar la carga inicial
CREATE TEMP TABLE precio_referencia (producto VARCHAR(200) PRIMARY KEY, precio NUMERIC(10,2));

INSERT INTO precio_referencia VALUES
('Arroz blanco 1 kg', 32), ('Frijol pinto 1 kg', 38), ('Aceite vegetal 1 L', 44),
('Azúcar estándar 1 kg', 33), ('Sal de mesa 1 kg', 14), ('Harina de maíz 1 kg', 24),
('Pasta para sopa 200 g', 11), ('Atún en agua 140 g', 22), ('Sardina en tomate 425 g', 36),
('Café soluble 120 g', 75), ('Tortilla de maíz', 23),
('Tomate saladette', 26), ('Cebolla blanca', 24), ('Papa blanca', 30), ('Chile jalapeño', 34),
('Limón con semilla', 38), ('Plátano tabasco', 24), ('Manzana golden', 48),
('Leche entera 1 L', 28), ('Queso fresco', 140),
('Huevo blanco 12 pzas', 48), ('Pollo entero', 72), ('Carne molida de res', 170),
('Coca-Cola 600 ml', 19), ('Agua purificada 1.5 L', 15),
('Detergente en polvo 1 kg', 45), ('Jabón de lavandería 400 g', 22),
('Papel higiénico 4 rollos', 32);

INSERT INTO productos_maestros (nombre, categoria_id, unidad_medida, es_canasta_basica)
SELECT p.nombre, c.id, p.unidad, p.canasta
FROM (VALUES
    ('Arroz blanco 1 kg',         'Abarrotes',         'pieza', true),
    ('Frijol pinto 1 kg',         'Abarrotes',         'pieza', true),
    ('Aceite vegetal 1 L',        'Abarrotes',         'pieza', true),
    ('Azúcar estándar 1 kg',      'Abarrotes',         'pieza', true),
    ('Sal de mesa 1 kg',          'Abarrotes',         'pieza', true),
    ('Harina de maíz 1 kg',       'Abarrotes',         'pieza', true),
    ('Pasta para sopa 200 g',     'Abarrotes',         'pieza', true),
    ('Atún en agua 140 g',        'Abarrotes',         'pieza', true),
    ('Sardina en tomate 425 g',   'Abarrotes',         'pieza', true),
    ('Café soluble 120 g',        'Abarrotes',         'pieza', false),
    ('Tortilla de maíz',          'Abarrotes',         'kg',    true),
    ('Tomate saladette',          'Frutas y Verduras', 'kg',    true),
    ('Cebolla blanca',            'Frutas y Verduras', 'kg',    true),
    ('Papa blanca',               'Frutas y Verduras', 'kg',    true),
    ('Chile jalapeño',            'Frutas y Verduras', 'kg',    true),
    ('Limón con semilla',         'Frutas y Verduras', 'kg',    true),
    ('Plátano tabasco',           'Frutas y Verduras', 'kg',    false),
    ('Manzana golden',            'Frutas y Verduras', 'kg',    false),
    ('Leche entera 1 L',          'Lácteos',           'pieza', true),
    ('Queso fresco',              'Lácteos',           'kg',    false),
    ('Huevo blanco 12 pzas',      'Carnes y Huevo',    'pieza', true),
    ('Pollo entero',              'Carnes y Huevo',    'kg',    true),
    ('Carne molida de res',       'Carnes y Huevo',    'kg',    false),
    ('Coca-Cola 600 ml',          'Bebidas',           'pieza', false),
    ('Agua purificada 1.5 L',     'Bebidas',           'pieza', false),
    ('Detergente en polvo 1 kg',  'Limpieza',          'pieza', true),
    ('Jabón de lavandería 400 g', 'Limpieza',          'pieza', true),
    ('Papel higiénico 4 rollos',  'Higiene Personal',  'pieza', true)
) AS p(nombre, categoria, unidad, canasta)
JOIN categorias c ON c.nombre = p.categoria;

-- ---------------------------------------------------------------------
-- Comercios (ubicación = centro de la zona + desplazamiento en grados)
-- ---------------------------------------------------------------------
INSERT INTO comercios (usuario_id, nombre_comercio, tipo_comercio, direccion, colonia, municipio, estado,
                       latitud, longitud, zona_id, estado_registro, horario_apertura, horario_cierre,
                       verificado_por, fecha_verificacion)
SELECT u.id, c.nombre, c.tipo::tipo_comercio, c.direccion, c.colonia, z.municipio, z.estado,
       z.latitud_centro + c.dlat, z.longitud_centro + c.dlon, z.id, c.estado_reg::estado_comercio,
       c.abre::time, c.cierra::time,
       CASE WHEN c.estado_reg = 'VERIFICADO' THEN (SELECT id FROM usuarios WHERE email = 'coordinador@test.mx') END,
       CASE WHEN c.estado_reg = 'VERIFICADO' THEN NOW() - INTERVAL '60 days' END
FROM (VALUES
    -- Monterrey Centro
    ('Abarrotes La Esperanza',            'FORMAL_ABARROTES',   'Monterrey Centro',  'minorista@test.mx',       'Av. Juárez 1203',                 'Centro',               0.0030, -0.0020, 'VERIFICADO', '07:00', '22:00'),
    ('Mini Súper MX Juárez',              'FORMAL_MINISUPER',   'Monterrey Centro',  'minorista@test.mx',       'Calle Colegio Civil 845',         'Centro',              -0.0040,  0.0025, 'VERIFICADO', '07:00', '23:00'),
    ('Abarrotes López',                   'FORMAL_ABARROTES',   'Monterrey Centro',  'jorge.trevino@test.mx',   'Calle Arista 310',                'Centro',               0.0065,  0.0040, 'VERIFICADO', '08:00', '21:00'),
    ('Mercado Juárez Local 18',           'INFORMAL_FIJO',      'Monterrey Centro',  'rosa.hernandez@test.mx',  'Mercado Juárez, local 18',        'Centro',              -0.0020, -0.0060, 'VERIFICADO', '06:00', '16:00'),
    ('Frutas y Verduras Colegio Civil',   'INFORMAL_FIJO',      'Monterrey Centro',  'beto.garza@test.mx',      'Colegio Civil y Ruperto Martínez','Centro',               0.0010,  0.0080, 'VERIFICADO', '07:00', '18:00'),
    -- García Norte
    ('Tianguis Los Nogales - Puesto 7',   'INFORMAL_TIANGUIS',  'García Norte',      'comerciante@test.mx',     'Tianguis Los Nogales, pasillo B', 'Valle de Lincoln',     0.0040,  0.0030, 'VERIFICADO', '07:00', '15:00'),
    ('Abarrotes Mary',                    'FORMAL_ABARROTES',   'García Norte',      'martha.salinas@test.mx',  'Av. Lincoln 2210',                'Valle de Lincoln',    -0.0050,  0.0070, 'VERIFICADO', '07:00', '22:00'),
    ('Tiendita La Güera',                 'INFORMAL_FIJO',      'García Norte',      'lucia.rodriguez@test.mx', 'Calle Nogal 118',                 'Paseo de los Nogales', 0.0090, -0.0040, 'VERIFICADO', '08:00', '21:00'),
    ('Tianguis Los Nogales - Puesto 22',  'INFORMAL_TIANGUIS',  'García Norte',      'rosa.hernandez@test.mx',  'Tianguis Los Nogales, pasillo D', 'Valle de Lincoln',     0.0045,  0.0036, 'VERIFICADO', '07:00', '15:00'),
    ('Carretón Don Beto',                 'INFORMAL_AMBULANTE', 'García Norte',      'beto.garza@test.mx',      'Recorrido Col. Las Villas',       'Las Villas',          -0.0080, -0.0060, 'VERIFICADO', '09:00', '14:00'),
    ('Minisúper Valle de Lincoln',        'FORMAL_MINISUPER',   'García Norte',      'raul.cantu@test.mx',      'Av. Heberto Castillo 450',        'Valle de Lincoln',    -0.0020, -0.0110, 'VERIFICADO', '07:00', '23:00'),
    ('Abarrotes El Nogal',                'FORMAL_ABARROTES',   'García Norte',      'jorge.trevino@test.mx',   'Calle Encino 77',                 'Paseo de los Nogales', 0.0120,  0.0060, 'PENDIENTE',  '08:00', '21:00'),
    -- Escobedo Poniente
    ('Abarrotes Hermanos Treviño',        'FORMAL_ABARROTES',   'Escobedo Poniente', 'jorge.trevino@test.mx',   'Av. Raúl Caballero 905',          'Fomerrey 9',           0.0030,  0.0050, 'VERIFICADO', '07:00', '22:00'),
    ('Tianguis Fomerrey 9 - Puesto 3',    'INFORMAL_TIANGUIS',  'Escobedo Poniente', 'lucia.rodriguez@test.mx', 'Tianguis dominical Fomerrey 9',   'Fomerrey 9',          -0.0035,  0.0020, 'VERIFICADO', '07:00', '14:00'),
    ('Recaudería El Güero',               'FORMAL_RECAUDERIA',  'Escobedo Poniente', 'martha.salinas@test.mx',  'Calle Juárez 402',                'Centro de Escobedo',   0.0060, -0.0045, 'VERIFICADO', '07:00', '20:00'),
    ('Depósito y Abarrotes Lupita',       'FORMAL_ABARROTES',   'Escobedo Poniente', 'raul.cantu@test.mx',      'Av. Las Torres 1500',             'Lomas de San Genaro', -0.0070, -0.0030, 'VERIFICADO', '09:00', '23:00'),
    -- Apodaca Centro
    ('Mini Súper Huinalá',                'FORMAL_MINISUPER',   'Apodaca Centro',    'raul.cantu@test.mx',      'Carretera Huinalá 220',           'Huinalá',              0.0050,  0.0040, 'VERIFICADO', '07:00', '23:00'),
    ('Tianguis Pueblo Nuevo - Puesto 11', 'INFORMAL_TIANGUIS',  'Apodaca Centro',    'rosa.hernandez@test.mx',  'Tianguis Pueblo Nuevo',           'Pueblo Nuevo',        -0.0045, -0.0020, 'VERIFICADO', '07:00', '15:00'),
    ('Abarrotes San Miguel',              'FORMAL_ABARROTES',   'Apodaca Centro',    'jorge.trevino@test.mx',   'Calle Morelos 118',               'Centro de Apodaca',    0.0010, -0.0070, 'VERIFICADO', '08:00', '22:00'),
    ('Puesto Doña Chuy',                  'INFORMAL_FIJO',      'Apodaca Centro',    'lucia.rodriguez@test.mx', 'Calle Hidalgo esq. Allende',      'Centro de Apodaca',   -0.0080,  0.0060, 'PENDIENTE',  '07:00', '14:00'),
    -- Guadalupe Oriente
    ('Abarrotes La Joya',                 'FORMAL_ABARROTES',   'Guadalupe Oriente', 'martha.salinas@test.mx',  'Av. Benito Juárez 3300',          'Linda Vista',          0.0040, -0.0030, 'VERIFICADO', '07:00', '22:00'),
    ('Recaudería Linda Vista',            'FORMAL_RECAUDERIA',  'Guadalupe Oriente', 'jorge.trevino@test.mx',   'Calle Linda Vista 540',           'Linda Vista',         -0.0030,  0.0060, 'VERIFICADO', '07:00', '20:00'),
    ('Tianguis Linda Vista - Puesto 5',   'INFORMAL_TIANGUIS',  'Guadalupe Oriente', 'beto.garza@test.mx',      'Tianguis de los martes, Linda Vista','Linda Vista',        0.0070,  0.0020, 'VERIFICADO', '07:00', '15:00'),
    ('Mini Súper Contry',                 'FORMAL_MINISUPER',   'Guadalupe Oriente', 'minorista@test.mx',       'Av. Eugenio Garza Sada 4500',     'Contry',              -0.0060, -0.0070, 'VERIFICADO', '07:00', '23:00'),
    -- Santa Catarina Poniente
    ('Tianguis La Fama - Puesto 9',       'INFORMAL_TIANGUIS',  'Santa Catarina Poniente', 'lucia.rodriguez@test.mx', 'Tianguis La Fama',          'La Fama',              0.0030,  0.0040, 'VERIFICADO', '07:00', '15:00'),
    ('Abarrotes El Puente',               'FORMAL_ABARROTES',   'Santa Catarina Poniente', 'raul.cantu@test.mx',      'Av. Manuel Ordóñez 780',    'Centro de Santa Catarina', -0.0050, 0.0010, 'VERIFICADO', '08:00', '22:00'),
    ('Puesto Don Toño',                   'INFORMAL_AMBULANTE', 'Santa Catarina Poniente', 'beto.garza@test.mx',      'Recorrido Col. Infonavit La Huasteca', 'La Huasteca', 0.0060, -0.0070, 'VERIFICADO', '09:00', '14:00')
) AS c(nombre, tipo, zona, email, direccion, colonia, dlat, dlon, estado_reg, abre, cierra)
JOIN zonas_municipales z ON z.nombre = c.zona
JOIN usuarios u ON u.email = c.email;

-- ---------------------------------------------------------------------
-- Inventario del comercio demo (comerciante@test.mx).
-- Queda con tomate bajo y cebolla agotada, y no vende leche/huevo/aceite,
-- para que el flujo de abasto y las recomendaciones tengan qué mostrar.
-- ---------------------------------------------------------------------
INSERT INTO inventario_comercio (comercio_id, producto_id, existencia, stock_minimo, stock_maximo, precio_venta)
SELECT c.id, p.id, i.existencia, i.minimo, i.maximo, i.precio
FROM (VALUES
    ('Tomate saladette',   4, 10, 40, 25.00),
    ('Cebolla blanca',     0,  8, 30, 22.50),
    ('Papa blanca',       18,  8, 35, 29.00),
    ('Chile jalapeño',     6,  3, 15, 33.00),
    ('Limón con semilla',  9,  5, 25, 36.00),
    ('Frijol pinto 1 kg',  7,  6, 24, 37.50),
    ('Arroz blanco 1 kg', 11,  6, 24, 31.50)
) AS i(producto, existencia, minimo, maximo, precio)
JOIN productos_maestros p ON p.nombre = i.producto
CROSS JOIN comercios c
WHERE c.nombre_comercio = 'Tianguis Los Nogales - Puesto 7';

-- ---------------------------------------------------------------------
-- Inventario del resto de comercios.
--  * Qué vende cada comercio depende de su giro (tipo) y la categoría.
--  * La probabilidad de tener existencia depende de la zona; García Norte
--    y Santa Catarina tienen menor disponibilidad (escenario de brecha).
-- ---------------------------------------------------------------------
CREATE TEMP TABLE disponibilidad_zona (zona VARCHAR(100) PRIMARY KEY, factor NUMERIC);
INSERT INTO disponibilidad_zona VALUES
('Monterrey Centro', 0.90), ('García Norte', 0.40), ('Escobedo Poniente', 0.65),
('Apodaca Centro', 0.75), ('Guadalupe Oriente', 0.85), ('Santa Catarina Poniente', 0.55);

WITH candidatos AS (
    SELECT c.id AS comercio_id, c.tipo_comercio::text AS tipo, z.nombre AS zona,
           p.id AS producto_id, p.nombre AS producto, cat.nombre AS categoria, p.unidad_medida,
           random() AS r_vende, random() AS r_disp, random() AS r_cant, random() AS r_precio
    FROM comercios c
    JOIN zonas_municipales z ON z.id = c.zona_id
    CROSS JOIN productos_maestros p
    JOIN categorias cat ON cat.id = p.categoria_id
    WHERE c.nombre_comercio <> 'Tianguis Los Nogales - Puesto 7'
),
con_probabilidad AS (
    SELECT cand.*,
        CASE
            WHEN tipo IN ('FORMAL_ABARROTES', 'FORMAL_MINISUPER') THEN
                CASE categoria
                    WHEN 'Frutas y Verduras' THEN 0.30
                    WHEN 'Carnes y Huevo' THEN CASE WHEN producto LIKE 'Huevo%' THEN 0.85 ELSE 0.20 END
                    ELSE 0.85 END
            WHEN tipo = 'FORMAL_RECAUDERIA' THEN
                CASE categoria
                    WHEN 'Frutas y Verduras' THEN 0.95
                    WHEN 'Carnes y Huevo' THEN 0.50
                    ELSE 0.15 END
            WHEN tipo IN ('INFORMAL_TIANGUIS', 'INFORMAL_FIJO') THEN
                CASE categoria
                    WHEN 'Frutas y Verduras' THEN 0.85
                    WHEN 'Abarrotes' THEN 0.30
                    WHEN 'Carnes y Huevo' THEN 0.35
                    ELSE 0.10 END
            ELSE -- ambulante
                CASE categoria
                    WHEN 'Frutas y Verduras' THEN 0.60
                    WHEN 'Bebidas' THEN 0.50
                    ELSE 0.05 END
        END AS p_vende
    FROM candidatos cand
)
INSERT INTO inventario_comercio (comercio_id, producto_id, existencia, stock_minimo, stock_maximo, precio_venta)
SELECT cp.comercio_id, cp.producto_id,
       CASE
           -- Leche, huevo y aceite casi no se consiguen en García Norte
           WHEN cp.zona = 'García Norte' AND cp.producto IN ('Leche entera 1 L', 'Huevo blanco 12 pzas', 'Aceite vegetal 1 L')
                AND cp.r_disp > 0.20 THEN 0
           WHEN cp.r_disp > dz.factor THEN 0
           ELSE CEIL(cp.r_cant * 38) + 1
       END,
       CASE WHEN cp.unidad_medida = 'kg' THEN 4 ELSE 6 END,
       CASE WHEN cp.unidad_medida = 'kg' THEN 30 ELSE 48 END,
       -- Precio redondeado a 50 centavos; el sector informal suele vender un poco más barato
       ROUND(pr.precio * CASE WHEN cp.tipo LIKE 'INFORMAL%' THEN 0.95 ELSE 1.04 END
             * (0.93 + cp.r_precio * 0.14) * 2) / 2
FROM con_probabilidad cp
JOIN disponibilidad_zona dz ON dz.zona = cp.zona
JOIN precio_referencia pr ON pr.producto = cp.producto
WHERE cp.r_vende < cp.p_vende;

-- ---------------------------------------------------------------------
-- Historial de precios al consumidor: 8 semanas hacia atrás con una
-- ligera tendencia al alza, más el precio vigente.
-- ---------------------------------------------------------------------
INSERT INTO precios_comercio (comercio_id, producto_id, precio, fecha_registro, metodo_captura, usuario_registro_id)
SELECT i.comercio_id, i.producto_id,
       ROUND(i.precio_venta * (1 - 0.012 * s.semana) * (0.97 + random() * 0.06) * 2) / 2,
       NOW() - (s.semana * 7 || ' days')::interval - (random() * 48 || ' hours')::interval,
       'CARGA_INICIAL', c.usuario_id
FROM inventario_comercio i
JOIN comercios c ON c.id = i.comercio_id
CROSS JOIN generate_series(1, 8) AS s(semana);

INSERT INTO precios_comercio (comercio_id, producto_id, precio, fecha_registro, metodo_captura, usuario_registro_id)
SELECT i.comercio_id, i.producto_id, i.precio_venta,
       NOW() - (random() * 36 || ' hours')::interval, 'CARGA_INICIAL', c.usuario_id
FROM inventario_comercio i
JOIN comercios c ON c.id = i.comercio_id;

-- ---------------------------------------------------------------------
-- Ventas de los últimos 30 días (movimientos de SALIDA).
-- Son la señal de demanda que usan brechas y recomendaciones.
-- ---------------------------------------------------------------------
INSERT INTO movimientos_inventario (inventario_id, tipo, cantidad, existencia_anterior, existencia_nueva,
                                    motivo, usuario_id, created_at)
SELECT v.inventario_id, 'SALIDA', v.cantidad, v.existencia + v.cantidad, v.existencia,
       'Venta (carga inicial)', v.usuario_id, v.fecha
FROM (
    -- Los productos de canasta básica se venden con más frecuencia
    SELECT i.id AS inventario_id, i.existencia, c.usuario_id,
           CEIL(random() * 4) AS cantidad,
           NOW() - (random() * 30 || ' days')::interval AS fecha
    FROM inventario_comercio i
    JOIN comercios c ON c.id = i.comercio_id
    JOIN productos_maestros p ON p.id = i.producto_id
    CROSS JOIN LATERAL generate_series(1, 2 + (i.id % 6)::int + CASE WHEN p.es_canasta_basica THEN 3 ELSE 0 END) AS g(n)
) v;

-- ---------------------------------------------------------------------
-- Proveedores
-- ---------------------------------------------------------------------
INSERT INTO proveedores (usuario_id, nombre_empresa, rfc, descripcion, telefono_contacto, email_contacto,
                         direccion, municipio, latitud, longitud, pedido_minimo, tiempo_entrega_dias,
                         condiciones_venta, plan)
SELECT u.id, p.empresa, p.rfc, p.descripcion, p.telefono, u.email, p.direccion, p.municipio,
       p.lat, p.lon, p.minimo, p.entrega, p.condiciones, p.plan
FROM (VALUES
    ('proveedor@test.mx',  'Distribuidora Regia de Abarrotes', 'DRA150312KL4',
     'Abarrotes, lácteos, huevo, bebidas y limpieza para tiendas y puestos.', '8183001122',
     'Av. Ruiz Cortines 2800', 'Monterrey', 25.7050, -100.3150, 600, 1,
     'Pago contra entrega en efectivo o transferencia. Entrega sin costo en zonas de cobertura.', 'DESTACADO'),
    ('proveedor2@test.mx', 'Lácteos y Huevo del Norte', 'LHN180901QW2',
     'Leche, queso fresco y huevo directo de productores de la región.', '8183345566',
     'Carretera a Laredo km 12', 'General Escobedo', 25.8050, -100.3300, 400, 1,
     'Pago contra entrega. Cambios por producto dañado dentro de 24 horas.', 'BASICO'),
    ('proveedor3@test.mx', 'Bodega 14 - Mercado de Abastos Estrella', 'BEE090615AB1',
     'Frutas, verduras, frijol y arroz a granel desde el Mercado de Abastos.', '8183778899',
     'Mercado de Abastos Estrella, bodega 14', 'San Nicolás de los Garza', 25.7380, -100.2750, 350, 1,
     'Pago de contado. Pedidos antes de las 18:00 se entregan al día siguiente.', 'BASICO'),
    ('proveedor4@test.mx', 'Abarrotera del Poniente', 'ADP200117ZX9',
     'Abarrotes y limpieza para el poniente del área metropolitana.', '8184112233',
     'Av. Díaz Ordaz 1450', 'Santa Catarina', 25.6800, -100.4500, 1200, 2,
     'Crédito a 7 días para clientes con más de 3 pedidos entregados.', 'BASICO')
) AS p(email, empresa, rfc, descripcion, telefono, direccion, municipio, lat, lon, minimo, entrega, condiciones, plan)
JOIN usuarios u ON u.email = p.email;

INSERT INTO proveedor_zonas (proveedor_id, zona_id)
SELECT pv.id, z.id
FROM (VALUES
    ('Distribuidora Regia de Abarrotes', 'Monterrey Centro'),
    ('Distribuidora Regia de Abarrotes', 'García Norte'),
    ('Distribuidora Regia de Abarrotes', 'Escobedo Poniente'),
    ('Distribuidora Regia de Abarrotes', 'Apodaca Centro'),
    ('Distribuidora Regia de Abarrotes', 'Guadalupe Oriente'),
    ('Distribuidora Regia de Abarrotes', 'Santa Catarina Poniente'),
    ('Lácteos y Huevo del Norte', 'Monterrey Centro'),
    ('Lácteos y Huevo del Norte', 'García Norte'),
    ('Lácteos y Huevo del Norte', 'Escobedo Poniente'),
    ('Bodega 14 - Mercado de Abastos Estrella', 'Monterrey Centro'),
    ('Bodega 14 - Mercado de Abastos Estrella', 'García Norte'),
    ('Bodega 14 - Mercado de Abastos Estrella', 'Escobedo Poniente'),
    ('Bodega 14 - Mercado de Abastos Estrella', 'Apodaca Centro'),
    ('Bodega 14 - Mercado de Abastos Estrella', 'Guadalupe Oriente'),
    ('Abarrotera del Poniente', 'García Norte'),
    ('Abarrotera del Poniente', 'Santa Catarina Poniente')
) AS pz(empresa, zona)
JOIN proveedores pv ON pv.nombre_empresa = pz.empresa
JOIN zonas_municipales z ON z.nombre = pz.zona;

-- Catálogo mayorista: qué categorías maneja cada proveedor
WITH surtido AS (
    SELECT pv.id AS proveedor_id, pv.nombre_empresa, p.id AS producto_id, p.nombre, p.unidad_medida, cat.nombre AS categoria
    FROM proveedores pv
    CROSS JOIN productos_maestros p
    JOIN categorias cat ON cat.id = p.categoria_id
    WHERE (pv.nombre_empresa = 'Distribuidora Regia de Abarrotes'
               AND cat.nombre IN ('Abarrotes', 'Lácteos', 'Bebidas', 'Limpieza', 'Higiene Personal')
               AND p.nombre NOT IN ('Tortilla de maíz', 'Queso fresco'))
       OR (pv.nombre_empresa = 'Distribuidora Regia de Abarrotes' AND p.nombre = 'Huevo blanco 12 pzas')
       OR (pv.nombre_empresa = 'Lácteos y Huevo del Norte'
               AND (cat.nombre = 'Lácteos' OR p.nombre = 'Huevo blanco 12 pzas'))
       OR (pv.nombre_empresa = 'Bodega 14 - Mercado de Abastos Estrella'
               AND (cat.nombre = 'Frutas y Verduras' OR p.nombre IN ('Frijol pinto 1 kg', 'Arroz blanco 1 kg', 'Huevo blanco 12 pzas')))
       OR (pv.nombre_empresa = 'Abarrotera del Poniente'
               AND cat.nombre IN ('Abarrotes', 'Limpieza') AND p.nombre <> 'Tortilla de maíz')
)
INSERT INTO catalogo_proveedor (proveedor_id, producto_id, precio_mayoreo, cantidad_minima, existencia_disponible)
SELECT s.proveedor_id, s.producto_id,
       ROUND(pr.precio * 0.78 * (0.95 + random() * 0.10)::numeric, 2),
       CASE WHEN s.unidad_medida = 'kg' THEN 5 ELSE 12 END,
       100 + FLOOR(random() * 500)
FROM surtido s
JOIN precio_referencia pr ON pr.producto = s.nombre;

-- Un producto sin existencia para que se vea el caso en la consulta de proveedores
UPDATE catalogo_proveedor SET existencia_disponible = 0
WHERE proveedor_id = (SELECT id FROM proveedores WHERE nombre_empresa = 'Abarrotera del Poniente')
  AND producto_id = (SELECT id FROM productos_maestros WHERE nombre = 'Aceite vegetal 1 L');

INSERT INTO precios_mayoreo (proveedor_id, producto_id, precio, fecha_registro)
SELECT cp.proveedor_id, cp.producto_id,
       ROUND(cp.precio_mayoreo * (1 - 0.010 * s.semana) * (0.98 + random() * 0.04)::numeric, 2),
       NOW() - (s.semana * 7 || ' days')::interval
FROM catalogo_proveedor cp
CROSS JOIN generate_series(0, 8) AS s(semana);

-- ---------------------------------------------------------------------
-- Pedidos históricos en distintos estados
-- ---------------------------------------------------------------------
CREATE FUNCTION pg_temp.crear_pedido_demo(
    p_comercio TEXT, p_proveedor TEXT, p_estado estado_pedido, p_dias_atras INT,
    p_productos TEXT[], p_cantidades NUMERIC[]
) RETURNS VOID AS $$
DECLARE
    v_pedido UUID;
    v_comercio UUID;
    v_proveedor UUID;
    v_usuario_comercio UUID;
    v_usuario_proveedor UUID;
    v_ruta estado_pedido[];
    v_anterior estado_pedido := NULL;
    v_fecha TIMESTAMP := NOW() - (p_dias_atras || ' days')::interval;
    i INT;
BEGIN
    SELECT id, usuario_id INTO v_comercio, v_usuario_comercio FROM comercios WHERE nombre_comercio = p_comercio;
    SELECT id, usuario_id INTO v_proveedor, v_usuario_proveedor FROM proveedores WHERE nombre_empresa = p_proveedor;

    INSERT INTO pedidos_abasto (comercio_id, proveedor_id, estado, usuario_creacion_id, created_at)
    VALUES (v_comercio, v_proveedor, p_estado, v_usuario_comercio, v_fecha)
    RETURNING id INTO v_pedido;

    FOR i IN 1 .. array_length(p_productos, 1) LOOP
        INSERT INTO detalle_pedidos (pedido_id, producto_id, cantidad, precio_unitario, subtotal)
        SELECT v_pedido, cp.producto_id, p_cantidades[i], cp.precio_mayoreo, cp.precio_mayoreo * p_cantidades[i]
        FROM catalogo_proveedor cp
        JOIN productos_maestros p ON p.id = cp.producto_id
        WHERE cp.proveedor_id = v_proveedor AND p.nombre = p_productos[i];
    END LOOP;

    UPDATE pedidos_abasto
    SET subtotal = (SELECT COALESCE(SUM(subtotal), 0) FROM detalle_pedidos WHERE pedido_id = v_pedido)
    WHERE id = v_pedido;

    v_ruta := CASE p_estado
        WHEN 'RECHAZADO' THEN ARRAY['BORRADOR', 'ENVIADO', 'RECHAZADO']::estado_pedido[]
        ELSE (ARRAY['BORRADOR', 'ENVIADO', 'ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO', 'ENTREGADO']::estado_pedido[])
             [1 : array_position(ARRAY['BORRADOR', 'ENVIADO', 'ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO', 'ENTREGADO']::estado_pedido[], p_estado)]
    END;

    FOR i IN 1 .. array_length(v_ruta, 1) LOOP
        INSERT INTO historial_pedido (pedido_id, estado_anterior, estado_nuevo, usuario_id, comentario, created_at)
        VALUES (v_pedido, v_anterior, v_ruta[i],
                CASE WHEN v_ruta[i] IN ('BORRADOR', 'ENVIADO', 'ENTREGADO') THEN v_usuario_comercio ELSE v_usuario_proveedor END,
                CASE WHEN v_ruta[i] = 'RECHAZADO' THEN 'Sin existencia suficiente para surtir el pedido' END,
                v_fecha + ((i - 1) * 6 || ' hours')::interval);
        v_anterior := v_ruta[i];
    END LOOP;

    UPDATE pedidos_abasto SET
        fecha_envio = v_fecha + INTERVAL '6 hours',
        fecha_respuesta = CASE WHEN p_estado NOT IN ('ENVIADO') THEN v_fecha + INTERVAL '12 hours' END,
        fecha_entrega_estimada = CASE WHEN p_estado IN ('ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO', 'ENTREGADO')
                                      THEN (v_fecha + INTERVAL '1 day')::date END,
        fecha_entrega_real = CASE WHEN p_estado = 'ENTREGADO' THEN v_fecha + INTERVAL '30 hours' END,
        comision_plataforma = CASE WHEN p_estado = 'ENTREGADO' THEN ROUND(subtotal * 0.03, 2) ELSE 0 END,
        motivo_rechazo = CASE WHEN p_estado = 'RECHAZADO' THEN 'Sin existencia suficiente para surtir el pedido' END
    WHERE id = v_pedido;
END;
$$ LANGUAGE plpgsql;

SELECT pg_temp.crear_pedido_demo('Abarrotes La Esperanza', 'Distribuidora Regia de Abarrotes', 'ENTREGADO', 12,
    ARRAY['Arroz blanco 1 kg', 'Aceite vegetal 1 L', 'Azúcar estándar 1 kg'], ARRAY[24, 12, 24]);
SELECT pg_temp.crear_pedido_demo('Mini Súper Contry', 'Distribuidora Regia de Abarrotes', 'ENTREGADO', 8,
    ARRAY['Leche entera 1 L', 'Huevo blanco 12 pzas', 'Coca-Cola 600 ml'], ARRAY[36, 12, 48]);
SELECT pg_temp.crear_pedido_demo('Abarrotes Mary', 'Lácteos y Huevo del Norte', 'EN_PREPARACION', 1,
    ARRAY['Leche entera 1 L', 'Huevo blanco 12 pzas'], ARRAY[24, 12]);
SELECT pg_temp.crear_pedido_demo('Tianguis Los Nogales - Puesto 22', 'Bodega 14 - Mercado de Abastos Estrella', 'ENVIADO', 0,
    ARRAY['Tomate saladette', 'Cebolla blanca', 'Limón con semilla'], ARRAY[20, 15, 10]);
SELECT pg_temp.crear_pedido_demo('Abarrotes La Joya', 'Distribuidora Regia de Abarrotes', 'ENVIADO', 0,
    ARRAY['Frijol pinto 1 kg', 'Aceite vegetal 1 L', 'Detergente en polvo 1 kg'], ARRAY[24, 12, 12]);
SELECT pg_temp.crear_pedido_demo('Abarrotes El Puente', 'Abarrotera del Poniente', 'RECHAZADO', 5,
    ARRAY['Aceite vegetal 1 L', 'Sal de mesa 1 kg'], ARRAY[48, 24]);

-- ---------------------------------------------------------------------
-- Parámetros del sistema
-- ---------------------------------------------------------------------
INSERT INTO configuracion_sistema (clave, valor, descripcion, tipo_dato) VALUES
('APP_VERSION', '1.1.0', 'Versión actual de la aplicación', 'string'),
('COMISION_PEDIDO_PCT', '3', 'Comisión (%) que cobra la plataforma al proveedor por pedido entregado', 'float'),
('PRECIO_DESTACADO_MENSUAL', '499', 'Costo mensual (MXN) del plan Destacado para proveedores', 'float'),
('UMBRAL_BRECHA_ALTA', '30', 'Cobertura (%) por debajo de la cual una zona tiene brecha ALTA', 'float'),
('UMBRAL_BRECHA_MEDIA', '60', 'Cobertura (%) por debajo de la cual la brecha es MEDIA', 'float'),
('UMBRAL_BRECHA_BAJA', '80', 'Cobertura (%) por debajo de la cual la brecha es BAJA', 'float'),
('HABITANTES_POR_PUNTO', '8000', 'Habitantes por cada punto de venta con existencia que se considera suficiente', 'int'),
('DIAS_DEMANDA', '30', 'Días de ventas que se consideran para estimar la demanda', 'int'),
('UMBRAL_COBERTURA_RECOMENDACION', '50', 'Cobertura (%) máxima en la zona para recomendar un producto', 'float'),
('DIAS_DATO_VIGENTE', '7', 'Días después de los cuales un inventario se considera desactualizado', 'int');
