# Bitácora de participación e incidencias

**Fuente:** historial de git del repositorio (`git log`), al 25/11/2026, en la rama
`feature/entrega-final-completa`. Solo dice **lo que está en git**. El trabajo fuera del repositorio
(reuniones, diseño en papel, pruebas manuales, presentación oral, documentos editados en otra parte) no
aparece aquí: lo agrega cada integrante, con su evidencia.

## Cuentas de git y commits

| Cuenta de git | Commits | Fechas con commits | Dónde (carpetas con más archivos tocados) | Notas |
| :--- | ---: | :--- | :--- | :--- |
| Mauro-MG | 4 | 03/09 | `web/` (versión inicial), `db/`, `docs/` (requerimientos, reglas, plan) | Creó la primera versión del proyecto |
| Jose Moreno | 34 | 03/09 (25), 29/09, 12/10, 13/10 (6) | documentación del avance 1 (requerimientos, historias, datos, gestión), `apps/web`, documento técnico y presentación del avance 2 | |
| Betito016 | 39* | 28/09, 12/10, 14–15/11, 24–25/11 | microservicios, `libs/`, `apps/web`, `apps/movil`, `apps/escritorio`, `apps/infra`, `tests/` | *29 de esos commits dicen `Co-Authored-By: Claude` (hechos con asistencia de IA) |
| Humberto Vargas | 4 | 28/09, 12/10, 24/11 | — | Son las fusiones de los *pull requests* 1 a 4 en GitHub |

Para regenerar los números:

```bash
git log --format='%an' | sort | uniq -c
git log --author="<cuenta>" --format='%ad %s' --date=short
git log --author="<cuenta>" --format='%B' | grep -c "Co-Authored-By: Claude"
```

**A completar por el equipo (no se infiere de git):**

- Qué integrante corresponde a cada cuenta: la tabla no lo afirma.
- Las aportaciones de quien no tenga commits (en el historial no aparece ninguna cuenta a nombre de David López).
- El trabajo hecho fuera del repositorio.

## Incidencias de la etapa final (24–25/11/2026)

Son los defectos encontrados al validar la entrega final, con la prueba que los encontró y su corrección.

| # | Incidencia | Cómo se detectó | Corrección | Commit |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `ms-reportes` no estaba en el repositorio (`.gitignore` excluía `reportes/`) | construcción desde una descarga limpia | regla de `.gitignore` acotada | `c0fa41f` |
| 2 | La app Android cerraba la sesión cada vez que se reabría: comparaba un `token` que el servidor nunca devuelve | recorrido del APK en el emulador contra GCP | se compara `token_final`; revocar desde el web | `e8c4369`, `e58954e` |
| 3 | Gráficas vacías en 7 pantallas: `code.highcharts.com` respondía 403 | capturas del web | Highcharts con versión fija desde jsDelivr | `bdd08fe` |
| 4 | El respaldo diario no se habría generado: `.env` con CRLF en la VM | primer respaldo manual | el instalador normaliza el archivo y los scripts lo leen sin `\r` | `7fc2042` |
| 5 | La verificación al restaurar siempre fallaba: `SHA256SUMS` con rutas absolutas | simulacro de restauración | nombres relativos | `191e4bc` |
| 6 | 51 llaves foráneas sin índice; con volumen, limpiar datos tardaba más de 10 min | datos masivos y `EXPLAIN` | `08_indices_volumen.sql` | `dcb0892` |
| 7 | Búsqueda unificada de 2.7 s (p50) con 100 usuarios | Locust y registro de consultas lentas | relevancia calculada una vez por producto | `dcb0892` |
| 8 | Con Redis caído, cada petición esperaba hasta 20 s | `tests/carga/recuperacion.sh` | corte rápido del pool de Redis y DNS de 1 s | `65fccba` |
| 9 | ms-busqueda respondía 500 con Redis caído | misma prueba | `RedisError` capturado | `65fccba` |
| 10 | PostgreSQL o MongoDB caídos devolvían 500 en lugar de 503 | `test_fallas.py` | manejadores 503 con `Retry-After` | `6a0405c` |
| 11 | Venta descontada dos veces tras un timeout y un reintento | `test_fallas.py` (34 → 32 por 1 pieza) | `venta_id` determinista a partir de `id_cliente` | `6a0405c` |
| 12 | XML con un número en notación científica (`1.3e-05`) no válido para `xs:decimal` | validación XSD de la app de escritorio | formato decimal fijo | `01adb87` |

