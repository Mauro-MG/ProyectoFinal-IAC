-- =====================================================================
-- AbastoRed - Equipo 01
-- Extensión geoespacial (PostGIS)
--
-- Las coordenadas se capturan como latitud/longitud en 01_schema.sql.
-- Aquí se agregan las geometrías, se mantienen sincronizadas por trigger
-- y se indexan con GIST para el futuro servicio geográfico.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

ALTER TABLE zonas_municipales ADD COLUMN area GEOMETRY(POLYGON, 4326);
ALTER TABLE comercios ADD COLUMN geom GEOMETRY(POINT, 4326);
ALTER TABLE proveedores ADD COLUMN geom GEOMETRY(POINT, 4326);

CREATE INDEX idx_zonas_area ON zonas_municipales USING GIST (area);
CREATE INDEX idx_comercios_geom ON comercios USING GIST (geom);
CREATE INDEX idx_proveedores_geom ON proveedores USING GIST (geom);

-- Punto a partir de latitud/longitud
CREATE OR REPLACE FUNCTION sincronizar_geom_punto()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.latitud IS NOT NULL AND NEW.longitud IS NOT NULL THEN
        NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitud, NEW.latitud), 4326);
    ELSE
        NEW.geom := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Área de la zona = buffer de radio_km alrededor del centro.
-- Se calcula sobre geography para que el radio quede en metros reales.
CREATE OR REPLACE FUNCTION sincronizar_area_zona()
RETURNS TRIGGER AS $$
BEGIN
    NEW.area := ST_Buffer(
        ST_SetSRID(ST_MakePoint(NEW.longitud_centro, NEW.latitud_centro), 4326)::geography,
        NEW.radio_km * 1000
    )::geometry;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_comercios_geom BEFORE INSERT OR UPDATE OF latitud, longitud ON comercios
    FOR EACH ROW EXECUTE FUNCTION sincronizar_geom_punto();
CREATE TRIGGER trg_proveedores_geom BEFORE INSERT OR UPDATE OF latitud, longitud ON proveedores
    FOR EACH ROW EXECUTE FUNCTION sincronizar_geom_punto();
CREATE TRIGGER trg_zonas_area BEFORE INSERT OR UPDATE OF latitud_centro, longitud_centro, radio_km ON zonas_municipales
    FOR EACH ROW EXECUTE FUNCTION sincronizar_area_zona();

-- Vista de control para el coordinador: comercios cuya ubicación cae fuera
-- del área de la zona que tienen asignada (posible error de captura).
CREATE VIEW v_comercios_fuera_de_zona AS
SELECT c.id, c.nombre_comercio, z.nombre AS zona,
       ROUND(ST_Distance(c.geom::geography, ST_Centroid(z.area)::geography)) AS distancia_centro_m
FROM comercios c
JOIN zonas_municipales z ON z.id = c.zona_id
WHERE c.geom IS NOT NULL AND NOT ST_Contains(z.area, c.geom);
