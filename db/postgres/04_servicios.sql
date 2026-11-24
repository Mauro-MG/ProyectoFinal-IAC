-- =====================================================================
-- AbastoRed - Equipo 01
-- Tablas de los microservicios de la entrega final (8109-8124) y
-- ampliaciones de los ocho originales.
--
-- Cada bloque indica el servicio DUEÑO: el único que escribe en esas
-- tablas (ver docs/propiedad_de_datos.md y 05_roles.sql). Los demás
-- servicios las consultan por la API del dueño.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Permisos nuevos por rol
-- ---------------------------------------------------------------------
UPDATE roles SET permisos = permisos || '["proveedores.verificar","ventas.registrar","entregas.gestionar","abastecimiento.solicitar","sincronizacion.enviar","integraciones.ejecutar","demanda.ver"]'::jsonb
 WHERE nombre = 'Administrador General';
UPDATE roles SET permisos = permisos || '["ventas.registrar","abastecimiento.solicitar","sincronizacion.enviar","entregas.recibir"]'::jsonb
 WHERE nombre IN ('Comerciante Informal', 'Minorista Formal');
UPDATE roles SET permisos = permisos || '["integraciones.ejecutar"]'::jsonb WHERE nombre = 'Minorista Formal';
UPDATE roles SET permisos = permisos || '["abastecimiento.cotizar","entregas.gestionar","integraciones.ejecutar","sincronizacion.enviar"]'::jsonb
 WHERE nombre = 'Proveedor';
UPDATE roles SET permisos = permisos || '["entregas.gestionar","sincronizacion.enviar"]'::jsonb WHERE nombre = 'Operador de Proveedor';
UPDATE roles SET permisos = permisos || '["demanda.ver"]'::jsonb WHERE nombre IN ('Analista de Mercado', 'Coordinador Municipal');
UPDATE roles SET permisos = permisos || '["proveedores.verificar"]'::jsonb WHERE nombre = 'Coordinador Municipal';

-- =====================================================================
-- ms-comercios: datos fiscales opcionales, giro y responsables
-- =====================================================================
ALTER TABLE comercios
    ADD COLUMN giro VARCHAR(100),
    ADD COLUMN rfc VARCHAR(13),
    ADD COLUMN razon_social VARCHAR(255),
    ADD COLUMN regimen_fiscal VARCHAR(100),
    ADD COLUMN email_contacto VARCHAR(255),
    ADD CONSTRAINT ck_comercios_rfc CHECK (rfc IS NULL OR rfc ~ '^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$');

CREATE TABLE responsables_comercio (
    id BIGSERIAL PRIMARY KEY,
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    nombre VARCHAR(150) NOT NULL,
    puesto VARCHAR(20) NOT NULL DEFAULT 'ENCARGADO' CHECK (puesto IN ('DUENO', 'ENCARGADO', 'EMPLEADO')),
    telefono VARCHAR(20),
    email VARCHAR(255),
    usuario_id UUID REFERENCES usuarios(id),
    activo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_responsables_comercio ON responsables_comercio (comercio_id) WHERE activo;

-- =====================================================================
-- ms-catalogo: marcas, unidades, variantes y productos equivalentes
-- =====================================================================
CREATE TABLE unidades_medida (
    clave VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('CONTEO', 'PESO', 'VOLUMEN'))
);
INSERT INTO unidades_medida (clave, nombre, tipo) VALUES
('pieza', 'Pieza', 'CONTEO'), ('paquete', 'Paquete', 'CONTEO'), ('caja', 'Caja', 'CONTEO'),
('docena', 'Docena', 'CONTEO'), ('kg', 'Kilogramo', 'PESO'), ('g', 'Gramo', 'PESO'),
('litro', 'Litro', 'VOLUMEN'), ('ml', 'Mililitro', 'VOLUMEN');
-- Las unidades que ya usa el catálogo quedan registradas aunque no estén en la lista anterior
INSERT INTO unidades_medida (clave, nombre, tipo)
SELECT DISTINCT unidad_medida, initcap(unidad_medida), 'CONTEO' FROM productos_maestros
ON CONFLICT (clave) DO NOTHING;
ALTER TABLE productos_maestros ADD CONSTRAINT fk_productos_unidad
    FOREIGN KEY (unidad_medida) REFERENCES unidades_medida(clave);

CREATE TABLE marcas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO marcas (nombre) VALUES ('Genérica'), ('Del Valle Regio'), ('La Norteña'), ('Campo Nuevo León');
ALTER TABLE productos_maestros ADD COLUMN marca_id INTEGER REFERENCES marcas(id);
-- Clasificación estandarizada: clave de producto (p. ej. de la canasta básica o del SAT)
ALTER TABLE productos_maestros ADD COLUMN clave_estandar VARCHAR(20);
CREATE UNIQUE INDEX uq_productos_codigo_barras ON productos_maestros (codigo_barras) WHERE codigo_barras IS NOT NULL;

CREATE TABLE variantes_producto (
    id SERIAL PRIMARY KEY,
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    nombre VARCHAR(100) NOT NULL,                 -- "Bolsa 500 g", "Caja con 12"
    codigo_barras VARCHAR(50) UNIQUE,
    factor DECIMAL(10,3) NOT NULL DEFAULT 1 CHECK (factor > 0),   -- cuántas unidades base contiene
    activo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (producto_id, nombre)
);

CREATE TABLE equivalencias_producto (
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    equivalente_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    tipo VARCHAR(12) NOT NULL DEFAULT 'SUSTITUTO' CHECK (tipo IN ('SUSTITUTO', 'MISMO')),
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (producto_id, equivalente_id),
    CHECK (producto_id <> equivalente_id)
);

-- =====================================================================
-- ms-inventario: reservas, transferencias e idempotencia de movimientos
-- =====================================================================
-- referencia: identificador del origen (venta, sincronización, pedido) para no aplicar dos veces
ALTER TABLE movimientos_inventario ADD COLUMN referencia VARCHAR(100);
CREATE UNIQUE INDEX uq_movimientos_referencia ON movimientos_inventario (referencia, inventario_id)
    WHERE referencia IS NOT NULL;

CREATE TABLE reservas_inventario (
    id BIGSERIAL PRIMARY KEY,
    inventario_id BIGINT NOT NULL REFERENCES inventario_comercio(id),
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    motivo VARCHAR(255),
    referencia VARCHAR(100),
    estado VARCHAR(10) NOT NULL DEFAULT 'ACTIVA' CHECK (estado IN ('ACTIVA', 'CONSUMIDA', 'LIBERADA', 'VENCIDA')),
    expira_at TIMESTAMP NOT NULL,
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_reservas_activas ON reservas_inventario (inventario_id) WHERE estado = 'ACTIVA';

CREATE TABLE transferencias_inventario (
    id BIGSERIAL PRIMARY KEY,
    origen_id BIGINT NOT NULL REFERENCES inventario_comercio(id),
    destino_id BIGINT NOT NULL REFERENCES inventario_comercio(id),
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    motivo VARCHAR(255),
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW(),
    CHECK (origen_id <> destino_id)
);

-- =====================================================================
-- ms-precios: promociones
-- =====================================================================
CREATE TABLE promociones (
    id BIGSERIAL PRIMARY KEY,
    inventario_id BIGINT NOT NULL REFERENCES inventario_comercio(id),
    precio_promocional DECIMAL(10,2) NOT NULL CHECK (precio_promocional > 0),
    descripcion VARCHAR(255),
    inicio DATE NOT NULL,
    fin DATE NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT true,
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW(),
    CHECK (fin >= inicio)
);
CREATE INDEX idx_promociones_vigentes ON promociones (inventario_id, inicio, fin) WHERE activa;

-- =====================================================================
-- ms-proveedores: verificación, capacidad y evaluación
-- (dueño también de proveedores, proveedor_zonas, catalogo_proveedor y precios_mayoreo)
-- =====================================================================
ALTER TABLE proveedores
    ADD COLUMN estado_verificacion VARCHAR(12) NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado_verificacion IN ('PENDIENTE', 'VERIFICADO', 'RECHAZADO', 'SUSPENDIDO')),
    ADD COLUMN verificado_por UUID REFERENCES usuarios(id),
    ADD COLUMN fecha_verificacion TIMESTAMP,
    -- Capacidad de surtido: pedidos que puede atender por día y monto máximo por pedido
    ADD COLUMN capacidad_pedidos_dia INTEGER CHECK (capacidad_pedidos_dia IS NULL OR capacidad_pedidos_dia > 0),
    ADD COLUMN monto_maximo_pedido DECIMAL(12,2) CHECK (monto_maximo_pedido IS NULL OR monto_maximo_pedido > 0),
    ADD COLUMN dias_entrega VARCHAR(3)[];
UPDATE proveedores SET estado_verificacion = 'VERIFICADO', fecha_verificacion = NOW(), capacidad_pedidos_dia = 25,
       dias_entrega = ARRAY['LUN','MAR','MIE','JUE','VIE','SAB'];

CREATE TABLE evaluaciones_proveedor (
    id BIGSERIAL PRIMARY KEY,
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    pedido_id UUID NOT NULL UNIQUE REFERENCES pedidos_abasto(id),   -- una evaluación por pedido entregado
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    calificacion SMALLINT NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    puntualidad SMALLINT CHECK (puntualidad BETWEEN 1 AND 5),
    calidad SMALLINT CHECK (calidad BETWEEN 1 AND 5),
    comentario VARCHAR(500),
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_evaluaciones_proveedor ON evaluaciones_proveedor (proveedor_id, created_at DESC);

-- Salidas de existencia del catálogo mayorista pedidas por otros servicios (ms-pedidos al despachar).
-- La referencia (p. ej. pedido:<uuid>) evita descontar dos veces si la llamada se reintenta.
CREATE TABLE salidas_catalogo (
    referencia VARCHAR(100) PRIMARY KEY,
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    partidas JSONB NOT NULL,
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================================
-- ms-abastecimiento: cotizaciones, consolidación y órdenes de compra
-- =====================================================================
CREATE TABLE solicitudes_cotizacion (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    folio BIGSERIAL UNIQUE,
    zona_id INTEGER NOT NULL REFERENCES zonas_municipales(id),
    creada_por UUID NOT NULL REFERENCES usuarios(id),
    titulo VARCHAR(150) NOT NULL,
    -- CONSOLIDADA: otros comerciantes de la zona pueden sumar sus necesidades
    consolidada BOOLEAN NOT NULL DEFAULT false,
    estado VARCHAR(12) NOT NULL DEFAULT 'ABIERTA' CHECK (estado IN ('ABIERTA', 'CERRADA', 'ADJUDICADA', 'CANCELADA')),
    fecha_limite TIMESTAMP NOT NULL,
    notas VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_solicitudes_updated_at BEFORE UPDATE ON solicitudes_cotizacion
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE necesidades_solicitud (
    id BIGSERIAL PRIMARY KEY,
    solicitud_id UUID NOT NULL REFERENCES solicitudes_cotizacion(id),
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (solicitud_id, comercio_id, producto_id)
);

CREATE TABLE cotizaciones (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    solicitud_id UUID NOT NULL REFERENCES solicitudes_cotizacion(id),
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    tiempo_entrega_dias INTEGER NOT NULL CHECK (tiempo_entrega_dias >= 0),
    vigencia DATE NOT NULL,
    notas VARCHAR(500),
    estado VARCHAR(12) NOT NULL DEFAULT 'ENVIADA' CHECK (estado IN ('ENVIADA', 'ADJUDICADA', 'DESCARTADA')),
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (solicitud_id, proveedor_id)
);

CREATE TABLE partidas_cotizacion (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id UUID NOT NULL REFERENCES cotizaciones(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    precio_unitario DECIMAL(10,2) NOT NULL CHECK (precio_unitario > 0),
    cantidad_disponible DECIMAL(12,2) NOT NULL CHECK (cantidad_disponible >= 0),
    UNIQUE (cotizacion_id, producto_id)
);

CREATE TABLE ordenes_compra (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    folio BIGSERIAL UNIQUE,
    solicitud_id UUID NOT NULL REFERENCES solicitudes_cotizacion(id),
    cotizacion_id UUID NOT NULL REFERENCES cotizaciones(id),
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    total DECIMAL(12,2) NOT NULL,
    estado VARCHAR(12) NOT NULL DEFAULT 'GENERADA' CHECK (estado IN ('GENERADA', 'CONVERTIDA', 'CANCELADA')),
    pedido_id UUID,             -- pedido creado en ms-pedidos al convertir la orden (sin FK: es de otro servicio)
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (solicitud_id, comercio_id)
);

CREATE TABLE partidas_orden (
    id BIGSERIAL PRIMARY KEY,
    orden_id UUID NOT NULL REFERENCES ordenes_compra(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL
);

-- =====================================================================
-- ms-ventas: ventas, partidas y devoluciones
-- =====================================================================
CREATE TABLE ventas (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    folio BIGSERIAL UNIQUE,
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    usuario_id UUID REFERENCES usuarios(id),
    total DECIMAL(12,2) NOT NULL CHECK (total >= 0),
    metodo_pago VARCHAR(15) NOT NULL DEFAULT 'EFECTIVO'
        CHECK (metodo_pago IN ('EFECTIVO', 'TARJETA', 'TRANSFERENCIA', 'FIADO', 'OTRO')),
    estado VARCHAR(18) NOT NULL DEFAULT 'REGISTRADA'
        CHECK (estado IN ('REGISTRADA', 'DEVUELTA_PARCIAL', 'DEVUELTA')),
    origen VARCHAR(12) NOT NULL DEFAULT 'web' CHECK (origen IN ('web', 'android', 'escritorio', 'api')),
    -- Identificador generado por el cliente (apps offline): la misma venta no se registra dos veces
    id_cliente VARCHAR(64) UNIQUE,
    fecha_venta TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_ventas_comercio_fecha ON ventas (comercio_id, fecha_venta DESC);

CREATE TABLE detalle_ventas (
    id BIGSERIAL PRIMARY KEY,
    venta_id UUID NOT NULL REFERENCES ventas(id),
    inventario_id BIGINT NOT NULL REFERENCES inventario_comercio(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    precio_unitario DECIMAL(10,2) NOT NULL CHECK (precio_unitario >= 0),
    subtotal DECIMAL(12,2) NOT NULL,
    cantidad_devuelta DECIMAL(10,2) NOT NULL DEFAULT 0,
    CHECK (cantidad_devuelta >= 0 AND cantidad_devuelta <= cantidad)
);

CREATE TABLE devoluciones (
    id BIGSERIAL PRIMARY KEY,
    venta_id UUID NOT NULL REFERENCES ventas(id),
    motivo VARCHAR(255) NOT NULL,
    total DECIMAL(12,2) NOT NULL,
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE detalle_devoluciones (
    id BIGSERIAL PRIMARY KEY,
    devolucion_id BIGINT NOT NULL REFERENCES devoluciones(id),
    detalle_venta_id BIGINT NOT NULL REFERENCES detalle_ventas(id),
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0)
);

-- =====================================================================
-- ms-entregas: logística del pedido
-- =====================================================================
CREATE TABLE entregas (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    pedido_id UUID NOT NULL UNIQUE,          -- de ms-pedidos (sin FK de escritura cruzada)
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    estado VARCHAR(16) NOT NULL DEFAULT 'PROGRAMADA'
        CHECK (estado IN ('PROGRAMADA', 'ASIGNADA', 'EN_RUTA', 'ENTREGADA', 'CON_INCIDENCIA', 'CANCELADA')),
    responsable_id UUID REFERENCES usuarios(id),
    responsable_nombre VARCHAR(150),
    vehiculo VARCHAR(100),
    fecha_estimada DATE,
    fecha_salida TIMESTAMP,
    fecha_entrega TIMESTAMP,
    -- Código que el comercio escanea (QR) o captura para confirmar la recepción
    codigo_confirmacion VARCHAR(12) NOT NULL,
    recibido_por VARCHAR(150),
    evidencia_archivo_id VARCHAR(24),        -- archivo en ms-documentos (GridFS)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_entregas_updated_at BEFORE UPDATE ON entregas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE INDEX idx_entregas_proveedor ON entregas (proveedor_id, estado);

CREATE TABLE eventos_entrega (
    id BIGSERIAL PRIMARY KEY,
    entrega_id UUID NOT NULL REFERENCES entregas(id),
    estado VARCHAR(16) NOT NULL,
    comentario VARCHAR(500),
    latitud DECIMAL(10,7),
    longitud DECIMAL(10,7),
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_eventos_entrega ON eventos_entrega (entrega_id, created_at);

CREATE TABLE incidencias_entrega (
    id BIGSERIAL PRIMARY KEY,
    entrega_id UUID NOT NULL REFERENCES entregas(id),
    tipo VARCHAR(16) NOT NULL CHECK (tipo IN ('RETRASO', 'PRODUCTO_DANADO', 'FALTANTE', 'DIRECCION', 'RECHAZO', 'OTRO')),
    descripcion VARCHAR(500) NOT NULL,
    estado VARCHAR(10) NOT NULL DEFAULT 'ABIERTA' CHECK (estado IN ('ABIERTA', 'RESUELTA')),
    resolucion VARCHAR(500),
    reportada_por UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW(),
    resuelta_at TIMESTAMP
);

-- =====================================================================
-- ms-geolocalizacion: colonias para geocodificación
-- (dueño también de zonas_municipales)
-- =====================================================================
CREATE TABLE colonias (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    codigo_postal VARCHAR(10),
    latitud DECIMAL(10,7) NOT NULL,
    longitud DECIMAL(10,7) NOT NULL,
    geom GEOMETRY(POINT, 4326),
    UNIQUE (nombre, municipio)
);
CREATE INDEX idx_colonias_geom ON colonias USING GIST (geom);
CREATE INDEX idx_colonias_nombre ON colonias (lower(nombre));
CREATE TRIGGER trg_colonias_geom BEFORE INSERT OR UPDATE OF latitud, longitud ON colonias
    FOR EACH ROW EXECUTE FUNCTION sincronizar_geom_punto();

-- Colonias del área metropolitana (coordenadas aproximadas del centro de cada una)
INSERT INTO colonias (nombre, municipio, codigo_postal, latitud, longitud) VALUES
('Centro', 'Monterrey', '64000', 25.6714, -100.3090),
('Obispado', 'Monterrey', '64060', 25.6750, -100.3400),
('Mitras Centro', 'Monterrey', '64460', 25.6930, -100.3420),
('Independencia', 'Monterrey', '64720', 25.6580, -100.3170),
('Topo Chico', 'Monterrey', '64260', 25.7330, -100.3330),
('San Bernabé', 'Monterrey', '64100', 25.7470, -100.3780),
('Contry', 'Monterrey', '64860', 25.6290, -100.2780),
('Valle de Infonavit', 'Monterrey', '64200', 25.7370, -100.3060),
('Del Valle', 'San Pedro Garza García', '66220', 25.6530, -100.3610),
('Fuentes del Valle', 'San Pedro Garza García', '66220', 25.6460, -100.3770),
('San Pedro Centro', 'San Pedro Garza García', '66230', 25.6570, -100.4020),
('Centro de Guadalupe', 'Guadalupe', '67100', 25.6770, -100.2590),
('Linda Vista', 'Guadalupe', '67130', 25.6870, -100.2440),
('Contry Guadalupe', 'Guadalupe', '67174', 25.6460, -100.2410),
('Centro de San Nicolás', 'San Nicolás de los Garza', '66400', 25.7420, -100.3020),
('Anáhuac', 'San Nicolás de los Garza', '66450', 25.7330, -100.2950),
('Las Puentes', 'San Nicolás de los Garza', '66460', 25.7520, -100.2770),
('Centro de Apodaca', 'Apodaca', '66600', 25.7810, -100.1880),
('Pueblo Nuevo', 'Apodaca', '66646', 25.7650, -100.2150),
('Centro de Escobedo', 'General Escobedo', '66050', 25.7960, -100.3200),
('Centro de Santa Catarina', 'Santa Catarina', '66350', 25.6730, -100.4580),
('Centro de García', 'García', '66000', 25.8070, -100.5920),
('Valle de Lincoln', 'García', '66023', 25.7680, -100.4900),
('Centro de Juárez', 'Juárez', '67250', 25.6480, -100.0960);

-- =====================================================================
-- ms-configuracion: categorías de parámetros y catálogos administrativos
-- (dueño también de configuracion_sistema)
-- =====================================================================
ALTER TABLE configuracion_sistema
    ADD COLUMN categoria VARCHAR(30) NOT NULL DEFAULT 'GENERAL',
    ADD COLUMN publico BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN valor_minimo DECIMAL(14,2),
    ADD COLUMN valor_maximo DECIMAL(14,2);
UPDATE configuracion_sistema SET categoria = 'ANALISIS' WHERE clave LIKE 'UMBRAL_%' OR clave IN ('HABITANTES_POR_PUNTO', 'DIAS_DEMANDA');
UPDATE configuracion_sistema SET categoria = 'COMERCIAL' WHERE clave IN ('COMISION_PEDIDO_PCT', 'PRECIO_DESTACADO_MENSUAL');
UPDATE configuracion_sistema SET categoria = 'INVENTARIO' WHERE clave = 'DIAS_DATO_VIGENTE';
UPDATE configuracion_sistema SET publico = true WHERE clave IN ('APP_VERSION', 'PRECIO_DESTACADO_MENSUAL');
UPDATE configuracion_sistema SET valor_minimo = 0, valor_maximo = 100
 WHERE clave IN ('COMISION_PEDIDO_PCT', 'UMBRAL_BRECHA_ALTA', 'UMBRAL_BRECHA_MEDIA', 'UMBRAL_BRECHA_BAJA', 'UMBRAL_COBERTURA_RECOMENDACION');

INSERT INTO configuracion_sistema (clave, valor, descripcion, tipo_dato, categoria, publico, valor_minimo, valor_maximo) VALUES
('PEDIDO_MAX_PARTIDAS', '100', 'Partidas máximas por pedido de abasto', 'int', 'PEDIDOS', false, 1, 500),
('PEDIDO_HORAS_RESPUESTA', '24', 'Horas que tiene el proveedor para responder un pedido enviado', 'int', 'PEDIDOS', true, 1, 168),
('RESERVA_MINUTOS', '30', 'Minutos que dura una reserva de inventario antes de vencer', 'int', 'INVENTARIO', false, 1, 1440),
('VARIACION_PRECIO_ATIPICO_PCT', '40', 'Variación (%) contra el promedio de la zona para marcar un precio como atípico', 'float', 'PRECIOS', false, 5, 300),
('COTIZACION_DIAS_LIMITE', '3', 'Días por omisión para que los proveedores coticen', 'int', 'ABASTECIMIENTO', false, 1, 30),
('SINCRONIZACION_MAX_OPERACIONES', '200', 'Operaciones máximas por lote de sincronización offline', 'int', 'SINCRONIZACION', true, 1, 1000),
('SINCRONIZACION_POLITICA_CONFLICTO', 'servidor_gana', 'Qué versión se conserva si un dato cambió en el servidor y en el dispositivo', 'string', 'SINCRONIZACION', true, NULL, NULL),
('DOCUMENTO_MAX_MB', '10', 'Tamaño máximo de un archivo subido (MB)', 'int', 'DOCUMENTOS', true, 1, 50),
('MONITOREO_LATENCIA_ALERTA_MS', '1500', 'Latencia p95 (ms) a partir de la cual se genera una alerta', 'int', 'MONITOREO', false, 100, 60000),
('MONITOREO_ERRORES_ALERTA_PCT', '10', 'Porcentaje de respuestas 5xx a partir del cual se genera una alerta', 'float', 'MONITOREO', false, 1, 100);

CREATE TABLE catalogos_administrativos (
    id SERIAL PRIMARY KEY,
    catalogo VARCHAR(40) NOT NULL,     -- metodos_pago, motivos_rechazo, tipos_incidencia, giros...
    clave VARCHAR(40) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    orden SMALLINT NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (catalogo, clave)
);
INSERT INTO catalogos_administrativos (catalogo, clave, nombre, orden) VALUES
('metodos_pago', 'EFECTIVO', 'Efectivo', 1), ('metodos_pago', 'TARJETA', 'Tarjeta', 2),
('metodos_pago', 'TRANSFERENCIA', 'Transferencia', 3), ('metodos_pago', 'FIADO', 'Fiado (crédito al cliente)', 4),
('motivos_rechazo', 'SIN_EXISTENCIA', 'Sin existencia suficiente', 1),
('motivos_rechazo', 'FUERA_DE_ZONA', 'Fuera de la zona de entrega', 2),
('motivos_rechazo', 'CAPACIDAD', 'Capacidad del día agotada', 3),
('tipos_incidencia', 'RETRASO', 'Retraso en la entrega', 1), ('tipos_incidencia', 'PRODUCTO_DANADO', 'Producto dañado', 2),
('tipos_incidencia', 'FALTANTE', 'Faltó producto', 3), ('tipos_incidencia', 'DIRECCION', 'No se encontró la dirección', 4),
('giros', 'ABARROTES', 'Abarrotes', 1), ('giros', 'FRUTAS_VERDURAS', 'Frutas y verduras', 2),
('giros', 'CARNES', 'Carnes y salchichonería', 3), ('giros', 'LACTEOS', 'Lácteos y huevo', 4), ('giros', 'MIXTO', 'Mixto', 5);
