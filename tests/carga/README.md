# Pruebas de carga y volumen

Solo para el entorno **local**. Los resultados y su análisis están en [docs/rendimiento.md](../../docs/rendimiento.md).

Las pruebas contra el despliegue en Google Cloud (por HTTPS y a través de NGINX) están aparte, en
[gcp/](gcp/README.md), y sus resultados en [docs/rendimiento_gcp.md](../../docs/rendimiento_gcp.md).

| Archivo | Para qué |
| :--- | :--- |
| `../../scripts/datos_masivos.py` | Genera, cuenta o borra ~1.3 M filas coherentes, con semilla reproducible |
| `emitir_sesiones.py` | Sesiones de los usuarios virtuales, con el mismo código del login (se corre en ms-seguridad) |
| `locustfile.py` | Escenarios: comerciante (JSON), analista (XML), visitante público y auditor |
| `correr.sh` | Corre un escenario y guarda CSV, historial, HTML, `docker stats` y el ambiente |
| `recuperacion.sh` | Carga con ms-inventario y Redis detenidos a la mitad |
| `medir_consultas.py` | `EXPLAIN (ANALYZE, BUFFERS)` de las consultas reales de los servicios |
| `medir_cache.py` | Análisis con y sin la caché de Redis |

```bash
python scripts/datos_masivos.py generar
docker exec -i ms-seguridad python - < tests/carga/emitir_sesiones.py > tests/carga/resultados/sesiones.json
bash tests/carga/correr.sh carga 100 10 5m
python scripts/datos_masivos.py limpiar        # al terminar
```

`resultados/sesiones.json` contiene tokens de prueba y **no se versiona**.
