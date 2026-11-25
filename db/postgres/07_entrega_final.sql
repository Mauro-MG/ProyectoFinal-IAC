-- =============================================================================
-- AbastoRed - cambios de la entrega final (idempotente)
--
-- Se ejecuta solo al crear la base (docker-entrypoint-initdb.d). Para una base que
-- ya existe se aplica a mano, sin perder datos:
--   docker compose exec -T abastored-postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/07_entrega_final.sql'
-- =============================================================================

-- Monitoreo: periodo de la verificación automática (contenedor monitor-verificador)
INSERT INTO configuracion_sistema (clave, valor, descripcion, tipo_dato, categoria, publico, valor_minimo, valor_maximo)
VALUES ('MONITOREO_INTERVALO_SEGUNDOS', '30', 'Cada cuántos segundos se verifica automáticamente la salud de los servicios',
        'int', 'MONITOREO', false, 10, 3600)
ON CONFLICT (clave) DO NOTHING;
