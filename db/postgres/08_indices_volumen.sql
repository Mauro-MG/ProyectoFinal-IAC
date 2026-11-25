-- =============================================================================
-- Índices para llaves foráneas en tablas de alto volumen (entrega final).
-- Idempotente: se puede aplicar sobre una base existente.
--
-- Encontrados con los datos masivos (scripts/datos_masivos.py, ~1.3 M filas) y medidos con
-- tests/carga/medir_consultas.py (antes/después en docs/rendimiento.md):
--   - detalle_ventas.venta_id: las consultas de ventas por comercio (más vendidos, reporte por día)
--     recorrían toda la tabla; y cada venta borrada revisaba la tabla completa.
--   - movimientos_inventario.pedido_id: cada pedido borrado (o cancelado en cascada) revisaba los
--     movimientos completos: 24 ms por pedido con 265 000 movimientos.
-- PostgreSQL no crea índices para las llaves foráneas automáticamente. Las demás FK sin índice son de
-- tablas pequeñas o columnas que casi no se borran (usuario que registró, verificado_por).
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_detalle_ventas_venta        ON detalle_ventas (venta_id);
CREATE INDEX IF NOT EXISTS idx_detalle_ventas_inventario   ON detalle_ventas (inventario_id);
CREATE INDEX IF NOT EXISTS idx_devoluciones_venta          ON devoluciones (venta_id);
CREATE INDEX IF NOT EXISTS idx_detalle_devoluciones_detalle ON detalle_devoluciones (detalle_venta_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_pedido          ON movimientos_inventario (pedido_id) WHERE pedido_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entregas_comercio           ON entregas (comercio_id);
CREATE INDEX IF NOT EXISTS idx_partidas_orden_orden        ON partidas_orden (orden_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_compra_comercio     ON ordenes_compra (comercio_id);
ANALYZE detalle_ventas, movimientos_inventario;
