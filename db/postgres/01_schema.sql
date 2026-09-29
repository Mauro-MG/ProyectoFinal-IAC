-- =====================================================================
-- AbastoRed - Equipo 01
-- Esquema relacional principal (PostgreSQL 16)
-- Las columnas geoespaciales (PostGIS) se agregan en 02_geo.sql
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------
-- Tipos enumerados
-- ---------------------------------------------------------------------
CREATE TYPE tipo_comercio AS ENUM (
    'FORMAL_ABARROTES', 'FORMAL_MINISUPER', 'FORMAL_RECAUDERIA',
    'INFORMAL_TIANGUIS', 'INFORMAL_FIJO', 'INFORMAL_AMBULANTE', 'MAYORISTA'
);

CREATE TYPE estado_comercio AS ENUM ('PENDIENTE', 'VERIFICADO', 'SUSPENDIDO', 'RECHAZADO');

-- Ciclo de vida de un pedido de abasto (ver docs/reglas_negocio.md RN-010)
CREATE TYPE estado_pedido AS ENUM (
    'BORRADOR', 'ENVIADO', 'ACEPTADO', 'EN_PREPARACION',
    'ENVIADO_A_COMERCIO', 'ENTREGADO', 'CANCELADO', 'RECHAZADO'
);

CREATE TYPE tipo_movimiento AS ENUM ('ENTRADA', 'SALIDA', 'AJUSTE');

CREATE TYPE tipo_evento_auditoria AS ENUM (
    'CREACION', 'LECTURA', 'ACTUALIZACION', 'ELIMINACION',
    'CAMBIO_ESTADO', 'LOGIN', 'LOGOUT', 'ERROR'
);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- Seguridad: roles y usuarios
-- ---------------------------------------------------------------------
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) UNIQUE NOT NULL,
    descripcion TEXT,
    -- Arreglo de códigos de permiso, p. ej. ["inventario.gestionar", "pedidos.crear"]
    permisos JSONB NOT NULL DEFAULT '[]',
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_roles_updated_at BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE usuarios (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellido_paterno VARCHAR(100) NOT NULL,
    apellido_materno VARCHAR(100),
    telefono VARCHAR(20),
    rol_id INTEGER NOT NULL REFERENCES roles(id),
    activo BOOLEAN DEFAULT true,
    email_verificado BOOLEAN DEFAULT false,
    ultimo_acceso TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_usuarios_updated_at BEFORE UPDATE ON usuarios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ---------------------------------------------------------------------
-- Territorio
-- ---------------------------------------------------------------------
CREATE TABLE zonas_municipales (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    estado VARCHAR(100) NOT NULL,
    codigo_postal VARCHAR(10),
    latitud_centro DECIMAL(10,7) NOT NULL,
    longitud_centro DECIMAL(10,7) NOT NULL,
    radio_km DECIMAL(5,2) NOT NULL DEFAULT 2 CHECK (radio_km > 0),
    -- Población estimada de la zona; se usa para la demanda y el índice de acceso
    poblacion INTEGER NOT NULL DEFAULT 0 CHECK (poblacion >= 0),
    activa BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (nombre, municipio)
);

-- ---------------------------------------------------------------------
-- Comercios
-- ---------------------------------------------------------------------
CREATE TABLE comercios (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    usuario_id UUID NOT NULL REFERENCES usuarios(id),
    nombre_comercio VARCHAR(255) NOT NULL,
    tipo_comercio tipo_comercio NOT NULL,
    descripcion TEXT,
    direccion VARCHAR(255) NOT NULL,
    colonia VARCHAR(100),
    municipio VARCHAR(100) NOT NULL,
    estado VARCHAR(100) NOT NULL,
    codigo_postal VARCHAR(10),
    latitud DECIMAL(10,7),
    longitud DECIMAL(10,7),
    telefono_comercio VARCHAR(20),
    horario_apertura TIME,
    horario_cierre TIME,
    dias_operacion VARCHAR(20)[],
    zona_id INTEGER REFERENCES zonas_municipales(id),
    estado_registro estado_comercio DEFAULT 'PENDIENTE',
    verificado_por UUID REFERENCES usuarios(id),
    fecha_verificacion TIMESTAMP,
    foto_url VARCHAR(255),
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CHECK (latitud IS NULL OR latitud BETWEEN -90 AND 90),
    CHECK (longitud IS NULL OR longitud BETWEEN -180 AND 180)
);
CREATE TRIGGER update_comercios_updated_at BEFORE UPDATE ON comercios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE INDEX idx_comercios_zona ON comercios (zona_id) WHERE activo;
CREATE INDEX idx_comercios_usuario ON comercios (usuario_id);

-- ---------------------------------------------------------------------
-- Catálogo maestro
-- ---------------------------------------------------------------------
CREATE TABLE categorias (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    descripcion TEXT,
    icono VARCHAR(100),
    orden INTEGER DEFAULT 0,
    activa BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE productos_maestros (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL,
    descripcion TEXT,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    -- Unidad en la que se vende y se cuenta la existencia (pieza, kg, litro...)
    unidad_medida VARCHAR(20) NOT NULL,
    codigo_barras VARCHAR(50),
    imagen_url VARCHAR(255),
    es_canasta_basica BOOLEAN DEFAULT false,
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (nombre, unidad_medida)
);
CREATE TRIGGER update_productos_maestros_updated_at BEFORE UPDATE ON productos_maestros
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ---------------------------------------------------------------------
-- Catálogo del comercio + inventario
-- Un renglón = "este comercio vende este producto maestro".
-- Si no hay renglón (o activo = false), el comercio no lo comercializa.
-- ---------------------------------------------------------------------
CREATE TABLE inventario_comercio (
    id BIGSERIAL PRIMARY KEY,
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    existencia DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (existencia >= 0),
    stock_minimo DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    stock_maximo DECIMAL(10,2),
    precio_venta DECIMAL(10,2) CHECK (precio_venta > 0),
    estado VARCHAR(12) GENERATED ALWAYS AS (
        CASE
            WHEN existencia <= 0 THEN 'AGOTADO'
            WHEN existencia <= stock_minimo THEN 'BAJO'
            ELSE 'DISPONIBLE'
        END
    ) STORED,
    activo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (comercio_id, producto_id),
    CHECK (stock_maximo IS NULL OR stock_maximo >= stock_minimo)
);
CREATE TRIGGER update_inventario_comercio_updated_at BEFORE UPDATE ON inventario_comercio
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE INDEX idx_inventario_producto ON inventario_comercio (producto_id) WHERE activo;

-- Historial de precios al consumidor (cada cambio de precio_venta genera un renglón)
CREATE TABLE precios_comercio (
    id BIGSERIAL PRIMARY KEY,
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    precio DECIMAL(10,2) NOT NULL CHECK (precio > 0),
    precio_anterior DECIMAL(10,2),
    fecha_registro TIMESTAMP DEFAULT NOW(),
    metodo_captura VARCHAR(20) DEFAULT 'MANUAL',
    estado_validacion VARCHAR(30) DEFAULT 'VALIDADO'
        CHECK (estado_validacion IN ('VALIDADO', 'PENDIENTE_VALIDACION')),
    usuario_registro_id UUID REFERENCES usuarios(id),
    notas TEXT,
    activo BOOLEAN DEFAULT true
);
CREATE INDEX idx_precios_comercio_producto ON precios_comercio (comercio_id, producto_id, fecha_registro DESC);
CREATE INDEX idx_precios_producto_fecha ON precios_comercio (producto_id, fecha_registro DESC);

-- ---------------------------------------------------------------------
-- Proveedores y catálogo mayorista
-- ---------------------------------------------------------------------
CREATE TABLE proveedores (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    usuario_id UUID NOT NULL UNIQUE REFERENCES usuarios(id),
    nombre_empresa VARCHAR(255) NOT NULL,
    rfc VARCHAR(13),
    descripcion TEXT,
    telefono_contacto VARCHAR(20),
    email_contacto VARCHAR(255),
    direccion VARCHAR(255),
    municipio VARCHAR(100),
    latitud DECIMAL(10,7),
    longitud DECIMAL(10,7),
    -- Condiciones comerciales
    pedido_minimo DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (pedido_minimo >= 0),
    tiempo_entrega_dias INTEGER NOT NULL DEFAULT 1 CHECK (tiempo_entrega_dias >= 0),
    condiciones_venta TEXT,
    -- Modelo de negocio: BASICO (gratuito) o DESTACADO (suscripción mensual)
    plan VARCHAR(20) NOT NULL DEFAULT 'BASICO' CHECK (plan IN ('BASICO', 'DESTACADO')),
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_proveedores_updated_at BEFORE UPDATE ON proveedores
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Zonas a las que el proveedor entrega
CREATE TABLE proveedor_zonas (
    proveedor_id UUID NOT NULL REFERENCES proveedores(id) ON DELETE CASCADE,
    zona_id INTEGER NOT NULL REFERENCES zonas_municipales(id),
    PRIMARY KEY (proveedor_id, zona_id)
);

CREATE TABLE catalogo_proveedor (
    id BIGSERIAL PRIMARY KEY,
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    precio_mayoreo DECIMAL(10,2) NOT NULL CHECK (precio_mayoreo > 0),
    cantidad_minima DECIMAL(10,2) NOT NULL DEFAULT 1 CHECK (cantidad_minima > 0),
    existencia_disponible DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (existencia_disponible >= 0),
    activo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (proveedor_id, producto_id)
);
CREATE TRIGGER update_catalogo_proveedor_updated_at BEFORE UPDATE ON catalogo_proveedor
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE INDEX idx_catalogo_proveedor_producto ON catalogo_proveedor (producto_id) WHERE activo;

-- Historial de precios de mayoreo
CREATE TABLE precios_mayoreo (
    id BIGSERIAL PRIMARY KEY,
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    precio DECIMAL(10,2) NOT NULL CHECK (precio > 0),
    fecha_registro TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_precios_mayoreo_producto_fecha ON precios_mayoreo (producto_id, fecha_registro DESC);

-- ---------------------------------------------------------------------
-- Pedidos de abasto
-- ---------------------------------------------------------------------
CREATE TABLE pedidos_abasto (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    folio BIGSERIAL UNIQUE,
    comercio_id UUID NOT NULL REFERENCES comercios(id),
    proveedor_id UUID NOT NULL REFERENCES proveedores(id),
    estado estado_pedido NOT NULL DEFAULT 'BORRADOR',
    fecha_envio TIMESTAMP,
    fecha_respuesta TIMESTAMP,
    fecha_entrega_estimada DATE,
    fecha_entrega_real TIMESTAMP,
    subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
    -- Comisión que cobra la plataforma al proveedor cuando el pedido se entrega
    comision_plataforma DECIMAL(12,2) NOT NULL DEFAULT 0,
    motivo_rechazo TEXT,
    notas TEXT,
    usuario_creacion_id UUID NOT NULL REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_pedidos_abasto_updated_at BEFORE UPDATE ON pedidos_abasto
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE INDEX idx_pedidos_comercio ON pedidos_abasto (comercio_id, created_at DESC);
CREATE INDEX idx_pedidos_proveedor_estado ON pedidos_abasto (proveedor_id, estado);

CREATE TABLE detalle_pedidos (
    id BIGSERIAL PRIMARY KEY,
    pedido_id UUID NOT NULL REFERENCES pedidos_abasto(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos_maestros(id),
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    precio_unitario DECIMAL(10,2) NOT NULL CHECK (precio_unitario > 0),
    subtotal DECIMAL(12,2) NOT NULL,
    UNIQUE (pedido_id, producto_id)
);

CREATE TABLE historial_pedido (
    id BIGSERIAL PRIMARY KEY,
    pedido_id UUID NOT NULL REFERENCES pedidos_abasto(id) ON DELETE CASCADE,
    estado_anterior estado_pedido,
    estado_nuevo estado_pedido NOT NULL,
    usuario_id UUID REFERENCES usuarios(id),
    comentario TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_historial_pedido ON historial_pedido (pedido_id, created_at);

-- Movimientos de inventario (entradas, salidas/ventas y ajustes)
CREATE TABLE movimientos_inventario (
    id BIGSERIAL PRIMARY KEY,
    inventario_id BIGINT NOT NULL REFERENCES inventario_comercio(id),
    tipo tipo_movimiento NOT NULL,
    cantidad DECIMAL(10,2) NOT NULL CHECK (cantidad >= 0),
    existencia_anterior DECIMAL(10,2) NOT NULL,
    existencia_nueva DECIMAL(10,2) NOT NULL,
    motivo VARCHAR(255),
    pedido_id UUID REFERENCES pedidos_abasto(id),
    usuario_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_movimientos_inventario ON movimientos_inventario (inventario_id, created_at DESC);
CREATE INDEX idx_movimientos_tipo_fecha ON movimientos_inventario (tipo, created_at DESC);

-- ---------------------------------------------------------------------
-- Auditoría (append-only)
-- ---------------------------------------------------------------------
CREATE TABLE auditoria_eventos (
    id BIGSERIAL PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id),
    tipo_evento tipo_evento_auditoria NOT NULL,
    entidad VARCHAR(100) NOT NULL,
    entidad_id VARCHAR(100),
    descripcion TEXT,
    datos_anteriores JSONB,
    datos_nuevos JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_auditoria_eventos_usuario ON auditoria_eventos (usuario_id, created_at DESC);
CREATE INDEX idx_auditoria_eventos_entidad ON auditoria_eventos (entidad, entidad_id);
CREATE INDEX idx_auditoria_eventos_fecha ON auditoria_eventos (created_at DESC);

CREATE OR REPLACE FUNCTION prevent_auditoria_modifications()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Los registros de auditoría son inmutables';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prevent_auditoria_update BEFORE UPDATE ON auditoria_eventos
    FOR EACH ROW EXECUTE FUNCTION prevent_auditoria_modifications();
CREATE TRIGGER prevent_auditoria_delete BEFORE DELETE ON auditoria_eventos
    FOR EACH ROW EXECUTE FUNCTION prevent_auditoria_modifications();

-- ---------------------------------------------------------------------
-- Parámetros del sistema
-- ---------------------------------------------------------------------
CREATE TABLE configuracion_sistema (
    id SERIAL PRIMARY KEY,
    clave VARCHAR(100) UNIQUE NOT NULL,
    valor TEXT,
    descripcion TEXT,
    tipo_dato VARCHAR(20),
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by UUID REFERENCES usuarios(id)
);
CREATE TRIGGER update_configuracion_sistema_updated_at BEFORE UPDATE ON configuracion_sistema
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
