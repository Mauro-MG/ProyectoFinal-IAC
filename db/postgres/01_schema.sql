CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "postgis";

CREATE TYPE tipo_comercio AS ENUM (
    'FORMAL_ABARROTES', 'FORMAL_MINISUPER', 'FORMAL_RECAUDERIA',
    'INFORMAL_TIANGUIS', 'INFORMAL_FIJO', 'INFORMAL_AMBULANTE', 'MAYORISTA'
);

CREATE TYPE estado_comercio AS ENUM (
    'PENDIENTE', 'VERIFICADO', 'SUSPENDIDO', 'RECHAZADO'
);

CREATE TYPE estado_pedido AS ENUM (
    'BORRADOR', 'SOLICITADO', 'CONFIRMADO', 'EN_TRANSITO', 'ENTREGADO', 'CANCELADO'
);

CREATE TYPE tipo_evento_auditoria AS ENUM (
    'CREACION', 'LECTURA', 'ACTUALIZACION', 'ELIMINACION', 'LOGIN', 'LOGOUT', 'ERROR'
);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) UNIQUE NOT NULL,
    descripcion TEXT,
    permisos JSONB,
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_roles_updated_at BEFORE UPDATE ON roles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE usuarios (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nombre VARCHAR(100),
    apellido_paterno VARCHAR(100),
    apellido_materno VARCHAR(100),
    telefono VARCHAR(20),
    rol_id INTEGER REFERENCES roles(id),
    activo BOOLEAN DEFAULT true,
    email_verificado BOOLEAN DEFAULT false,
    ultimo_acceso TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_usuarios_updated_at BEFORE UPDATE ON usuarios FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE zonas_municipales (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    estado VARCHAR(100) NOT NULL,
    codigo_postal VARCHAR(10),
    latitud_centro DECIMAL(10,7),
    longitud_centro DECIMAL(10,7),
    radio_km DECIMAL(5,2),
    poligono GEOMETRY(POLYGON, 4326),
    activa BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_zonas_municipales_poligono ON zonas_municipales USING GIST (poligono);

CREATE TABLE comercios (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id),
    nombre_comercio VARCHAR(255) NOT NULL,
    tipo_comercio tipo_comercio NOT NULL,
    descripcion TEXT,
    direccion VARCHAR(255),
    colonia VARCHAR(100),
    municipio VARCHAR(100),
    estado VARCHAR(100),
    codigo_postal VARCHAR(10),
    latitud DECIMAL(10,7),
    longitud DECIMAL(10,7),
    geom GEOMETRY(POINT, 4326),
    telefono_comercio VARCHAR(20),
    horario_apertura TIME,
    horario_cierre TIME,
    dias_operacion VARCHAR(20)[],
    zona_id INTEGER REFERENCES zonas_municipales(id),
    estado_registro estado_comercio DEFAULT 'PENDIENTE',
    verificado_por UUID REFERENCES usuarios(id) NULL,
    fecha_verificacion TIMESTAMP,
    foto_url VARCHAR(255),
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_comercios_updated_at BEFORE UPDATE ON comercios FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE INDEX idx_comercios_geom ON comercios USING GIST (geom);

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
    categoria_id INTEGER REFERENCES categorias(id),
    unidad_medida VARCHAR(20) NOT NULL,
    codigo_barras VARCHAR(50),
    imagen_url VARCHAR(255),
    es_canasta_basica BOOLEAN DEFAULT false,
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(nombre, unidad_medida)
);
CREATE TRIGGER update_productos_maestros_updated_at BEFORE UPDATE ON productos_maestros FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE precios_comercio (
    id BIGSERIAL PRIMARY KEY,
    comercio_id UUID REFERENCES comercios(id) NOT NULL,
    producto_id INTEGER REFERENCES productos_maestros(id) NOT NULL,
    precio DECIMAL(10,2) NOT NULL CHECK (precio > 0),
    precio_anterior DECIMAL(10,2),
    fecha_registro TIMESTAMP DEFAULT NOW(),
    metodo_captura VARCHAR(20) DEFAULT 'MANUAL',
    estado_validacion VARCHAR(30) DEFAULT 'VALIDADO' CHECK (estado_validacion IN ('VALIDADO', 'PENDIENTE_VALIDACION')),
    usuario_registro_id UUID REFERENCES usuarios(id),
    notas TEXT,
    activo BOOLEAN DEFAULT true
);
CREATE INDEX idx_precios_comercio_producto ON precios_comercio (comercio_id, producto_id, fecha_registro DESC);
CREATE INDEX idx_precios_producto_fecha ON precios_comercio (producto_id, fecha_registro DESC);

CREATE TABLE proveedores (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id),
    nombre_empresa VARCHAR(255) NOT NULL,
    rfc VARCHAR(13),
    tipo_productos TEXT,
    zona_cobertura TEXT,
    telefono_contacto VARCHAR(20),
    email_contacto VARCHAR(255),
    direccion VARCHAR(255),
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_proveedores_updated_at BEFORE UPDATE ON proveedores FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE pedidos_abasto (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    comercio_id UUID REFERENCES comercios(id) NOT NULL,
    proveedor_id UUID REFERENCES proveedores(id) NOT NULL,
    estado estado_pedido DEFAULT 'BORRADOR',
    fecha_solicitud TIMESTAMP,
    fecha_confirmacion TIMESTAMP,
    fecha_entrega_estimada TIMESTAMP,
    fecha_entrega_real TIMESTAMP,
    subtotal DECIMAL(12,2),
    iva DECIMAL(12,2),
    total DECIMAL(12,2),
    notas TEXT,
    usuario_creacion_id UUID REFERENCES usuarios(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TRIGGER update_pedidos_abasto_updated_at BEFORE UPDATE ON pedidos_abasto FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE detalle_pedidos (
    id BIGSERIAL PRIMARY KEY,
    pedido_id UUID REFERENCES pedidos_abasto(id) ON DELETE CASCADE,
    producto_id INTEGER REFERENCES productos_maestros(id),
    cantidad DECIMAL(10,3) NOT NULL CHECK (cantidad > 0),
    unidad_medida VARCHAR(20),
    precio_unitario DECIMAL(10,2) NOT NULL CHECK (precio_unitario > 0),
    subtotal DECIMAL(12,2),
    notas TEXT
);

CREATE TABLE auditoria_eventos (
    id BIGSERIAL PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id),
    tipo_evento tipo_evento_auditoria NOT NULL,
    entidad VARCHAR(100),
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

CREATE OR REPLACE FUNCTION prevent_auditoria_modifications()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Los registros de auditoría son inmutables';
END;
$$ language 'plpgsql';

CREATE TRIGGER prevent_auditoria_update
BEFORE UPDATE ON auditoria_eventos
FOR EACH ROW EXECUTE FUNCTION prevent_auditoria_modifications();

CREATE TRIGGER prevent_auditoria_delete
BEFORE DELETE ON auditoria_eventos
FOR EACH ROW EXECUTE FUNCTION prevent_auditoria_modifications();

CREATE TABLE configuracion_sistema (
    id SERIAL PRIMARY KEY,
    clave VARCHAR(100) UNIQUE NOT NULL,
    valor TEXT,
    descripcion TEXT,
    tipo_dato VARCHAR(20),
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by UUID REFERENCES usuarios(id)
);
CREATE TRIGGER update_configuracion_sistema_updated_at BEFORE UPDATE ON configuracion_sistema FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
