-- =============================================================================
-- AbastoRed - un usuario de PostgreSQL por microservicio (propiedad de datos)
--
-- Cada servicio entra con su propio usuario:
--   * SELECT en todas las tablas: la lectura compartida está permitida y
--     documentada en docs/propiedad_de_datos.md;
--   * INSERT, UPDATE y DELETE solo en las tablas de las que es dueño;
--   * INSERT en auditoria_eventos, en la misma transacción de su operación.
-- El sistema web (abastored_web) solo lee: todo cambio lo manda a la API del dueño.
--
-- Si un servicio intenta escribir en una tabla ajena, PostgreSQL lo rechaza con
-- «permission denied». Las pruebas lo comprueban (test_propiedad_datos.py).
--
-- Los usuarios se crean sin contraseña (NOLOGIN). 06_contrasenas.sh les pone la
-- de su archivo en secrets/ y les permite entrar. El superusuario solo se usa
-- para crear el esquema, cargar los datos iniciales y en estos scripts.
-- =============================================================================

CREATE TEMP TABLE propiedad (rol TEXT, tabla TEXT);

INSERT INTO propiedad (rol, tabla) VALUES
    ('ms_seguridad',       'usuarios'),
    ('ms_seguridad',       'roles'),
    ('ms_comercios',       'comercios'),
    ('ms_comercios',       'responsables_comercio'),
    ('ms_catalogo',        'productos_maestros'),
    ('ms_catalogo',        'categorias'),
    ('ms_catalogo',        'marcas'),
    ('ms_catalogo',        'unidades_medida'),
    ('ms_catalogo',        'variantes_producto'),
    ('ms_catalogo',        'equivalencias_producto'),
    ('ms_inventario',      'inventario_comercio'),
    ('ms_inventario',      'movimientos_inventario'),
    ('ms_inventario',      'reservas_inventario'),
    ('ms_inventario',      'transferencias_inventario'),
    ('ms_precios',         'precios_comercio'),
    ('ms_precios',         'promociones'),
    ('ms_pedidos',         'pedidos_abasto'),
    ('ms_pedidos',         'detalle_pedidos'),
    ('ms_pedidos',         'historial_pedido'),
    ('ms_proveedores',     'proveedores'),
    ('ms_proveedores',     'proveedor_zonas'),
    ('ms_proveedores',     'catalogo_proveedor'),
    ('ms_proveedores',     'precios_mayoreo'),
    ('ms_proveedores',     'evaluaciones_proveedor'),
    ('ms_proveedores',     'salidas_catalogo'),
    ('ms_abastecimiento',  'solicitudes_cotizacion'),
    ('ms_abastecimiento',  'necesidades_solicitud'),
    ('ms_abastecimiento',  'cotizaciones'),
    ('ms_abastecimiento',  'partidas_cotizacion'),
    ('ms_abastecimiento',  'ordenes_compra'),
    ('ms_abastecimiento',  'partidas_orden'),
    ('ms_geolocalizacion', 'zonas_municipales'),
    ('ms_geolocalizacion', 'colonias'),
    ('ms_ventas',          'ventas'),
    ('ms_ventas',          'detalle_ventas'),
    ('ms_ventas',          'devoluciones'),
    ('ms_ventas',          'detalle_devoluciones'),
    ('ms_entregas',        'entregas'),
    ('ms_entregas',        'eventos_entrega'),
    ('ms_entregas',        'incidencias_entrega'),
    ('ms_configuracion',   'configuracion_sistema'),
    ('ms_configuracion',   'catalogos_administrativos');

DO $$
DECLARE
    -- Los 24 servicios (libs/abasto_dominio/abasto_dominio/registro_servicios.py). Los que no aparecen en
    -- la tabla «propiedad» solo leen PostgreSQL: sus datos propios están en MongoDB o Redis.
    servicios TEXT[] := ARRAY['seguridad', 'comercios', 'catalogo', 'inventario', 'precios', 'pedidos', 'analisis',
                              'notificaciones', 'proveedores', 'abastecimiento', 'disponibilidad', 'geolocalizacion',
                              'sincronizacion', 'documentos', 'reportes', 'recomendaciones', 'demanda', 'ventas',
                              'entregas', 'auditoria', 'integraciones', 'configuracion', 'monitoreo', 'busqueda'];
    s TEXT;
    p RECORD;
    secuencia TEXT;
BEGIN
    FOREACH s IN ARRAY servicios || ARRAY['web'] LOOP
        EXECUTE format('CREATE ROLE %I NOLOGIN', CASE WHEN s = 'web' THEN 'abastored_web' ELSE 'ms_' || s END);
    END LOOP;

    -- Lectura para todos (servicios y web)
    FOREACH s IN ARRAY servicios || ARRAY['web'] LOOP
        s := CASE WHEN s = 'web' THEN 'abastored_web' ELSE 'ms_' || s END;
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), s);
        EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', s);
        EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', s);
    END LOOP;

    -- Auditoría: los servicios solo insertan (un trigger impide UPDATE y DELETE, ver 01_schema.sql)
    FOREACH s IN ARRAY servicios LOOP
        EXECUTE format('GRANT INSERT ON auditoria_eventos TO %I', 'ms_' || s);
        secuencia := pg_get_serial_sequence('auditoria_eventos', 'id');
        IF secuencia IS NOT NULL THEN
            EXECUTE format('GRANT USAGE ON SEQUENCE %s TO %I', secuencia, 'ms_' || s);
        END IF;
    END LOOP;

    -- Escritura solo en las tablas propias (y en sus secuencias, para los id seriales)
    FOR p IN SELECT rol, tabla FROM propiedad LOOP
        EXECUTE format('GRANT INSERT, UPDATE, DELETE ON %I TO %I', p.tabla, p.rol);
        FOR secuencia IN
            SELECT pg_get_serial_sequence(p.tabla, a.attname)
            FROM pg_attribute a
            WHERE a.attrelid = p.tabla::regclass AND a.attnum > 0 AND NOT a.attisdropped
              AND pg_get_serial_sequence(p.tabla, a.attname) IS NOT NULL
        LOOP
            EXECUTE format('GRANT USAGE ON SEQUENCE %s TO %I', secuencia, p.rol);
        END LOOP;
    END LOOP;
END $$;

-- Excepción documentada (docs/propiedad_de_datos.md): ms-precios fija el precio vigente del renglón de
-- inventario. Solo esa columna; existencia, mínimos y estado siguen siendo de ms-inventario.
GRANT UPDATE (precio_venta) ON inventario_comercio TO ms_precios;

-- Consulta rápida de quién puede escribir qué:
--   SELECT grantee, table_name, string_agg(privilege_type, ', ')
--   FROM information_schema.role_table_grants
--   WHERE privilege_type <> 'SELECT' AND grantee LIKE 'ms\_%' GROUP BY 1, 2 ORDER BY 1, 2;
