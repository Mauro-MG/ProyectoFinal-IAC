# Volumen, carga y rendimiento

**Fecha de las mediciones:** 25/11/2026. Todo se midió en el **entorno local**, y los resultados originales
están en `tests/carga/resultados/` (CSV, historial por segundo, HTML de Locust, muestras de `docker stats`
y planes `EXPLAIN`). No se corrió carga ni estrés contra Google Cloud: la VM es la instancia que se presenta
y comparte proyecto con otra práctica. Contra GCP se corrieron solo las pruebas funcionales
(`docs/evidencias/pruebas_gcp/`).

| Dato | Valor |
| :--- | :--- |
| Equipo | Windows 11 Pro, Docker Desktop: 16 CPU y 15.6 GB para contenedores |
| Sistema | 31 contenedores (24 servicios con 2 workers de gunicorn cada uno, web, gateway, monitor, PostgreSQL 16, MongoDB 7, Redis 7, emulador de GCS) |
| Commits | datos y planes: `d221929`; carga antes de optimizar: `dcb0892` sin la búsqueda nueva; después: `dcb0892`; recuperación final: `65fccba` |
| Generador de carga | Locust 2.32.2 en un contenedor de la misma máquina (compite por CPU con el sistema) |

## 1. Datos masivos

```bash
python scripts/datos_masivos.py generar --semilla 2026     # ~80 s
python scripts/datos_masivos.py contar
python scripts/datos_masivos.py limpiar
```

El generador es reproducible: dos cargas con la misma semilla dieron la misma huella MD5 de los comercios
y de las ventas. Los datos son coherentes con el dominio:

- comercios dentro del radio de las 6 zonas reales;
- 62 % informales, con precios algo más bajos;
- historial de precios, movimientos y ventas que respetan el inventario de cada comercio;
- pedidos con la distribución de estados de un proveedor real;
- bitácora en MongoDB con fechas recientes, porque la colección vence a los 30 días.

Todo queda marcado (`@masivo.abastored.test`, «MASIVO …», `masivo: true`) para poder borrarlo.

| Tabla o colección | Filas | Filas/s al insertar (COPY) |
| :--- | ---: | ---: |
| usuarios (4 000 comerciantes, 120 proveedores, 50 analistas/coordinadores/auditores) | 4 170 | 15 174 |
| comercios | 4 000 | 8 530 |
| inventario_comercio | 66 190 | 25 326 |
| precios_comercio (historial) | 198 570 | 16 112 |
| movimientos_inventario | 264 760 | 17 974 |
| ventas / detalle_ventas | 120 000 / 240 273 | 16 342 / 15 690 |
| pedidos_abasto / detalle_pedidos | 15 000 / 45 093 | 11 835 / 23 771 |
| MongoDB: bitacora_peticiones / demanda_busquedas / eventos_pedido | 300 000 / 50 000 / 15 000 | 46 143 / 45 981 / 31 086 |
| **Total** | **1 323 176** | |

La base PostgreSQL pasó de 26 MB a 283 MB. Salida original en
`tests/carga/resultados/20261125_1613_datos_masivos.txt`.

## 2. Planes de ejecución e índices

```bash
python tests/carga/medir_consultas.py antes_indices
python tests/carga/medir_consultas.py despues_indices
```

Se usan las consultas reales de los servicios con parámetros reales: el comercio con más ventas, el
proveedor con más pedidos y el arroz. Los `DELETE` corren dentro de `BEGIN … ROLLBACK` y miden solo la
revisión de llaves foráneas.

| Consulta | Origen | ms antes | ms después | ms FK antes | ms FK después |
| :--- | :--- | ---: | ---: | ---: | ---: |
| Más vendidos de un comercio | ms-ventas `GET /ventas/productos` | 30.1 | **1.0** | | |
| Reporte de ventas por día | ms-reportes | 26.0 | **0.8** | | |
| Inventario de un comercio | ms-inventario | 0.28 | 0.26 | | |
| Pedidos de un proveedor | ms-pedidos | 0.20 | 0.19 | | |
| Oferta por zona y producto | ms-analisis `/analisis/zonas` | 33.2 | 33.3 | | |
| Ventas por zona y producto | ms-analisis `/analisis/zonas` | 49.2 | 48.0 | | |
| Precio promedio por zona | ms-analisis | 37.1 | 34.9 | | |
| Disponibilidad pública de un producto | ms-disponibilidad | 5.1 | 4.6 | | |
| Borrar un pedido | revisión de `movimientos_inventario.pedido_id` | 24.6 | **3.2** | 24.2 | 2.9 |
| Borrar una venta | revisión de `detalle_ventas.venta_id` | 28.4 | **2.3** | 13.9 | 1.9 |

**Hallazgo.** PostgreSQL no indexa las llaves foráneas por sí solo, y había 51 sin índice. Con volumen,
las consultas de ventas por comercio recorrían las 240 000 partidas, y borrar pedidos revisaba los 265 000
movimientos por cada pedido. Limpiar los datos masivos tardó **más de 10 minutos** (se canceló) y, con los
índices, **117 s**. La corrección está en `db/postgres/08_indices_volumen.sql`: es idempotente, y el
instalador de la VM la aplica.

Las tres consultas de análisis recorren tablas completas porque agregan todo el sistema; un índice no las
cambia. Para eso está la caché de Redis (sección 3).

## 3. Caché de Redis en los análisis

```bash
python tests/carga/medir_cache.py 30
```

Para «sin caché» se sube `analisis:version` antes de cada petición, que es lo que hace la aplicación cuando
cambia un inventario. Así no se apaga Redis: la sesión, la revocación y los límites se siguen revisando en
las dos variantes. Fueron 30 peticiones de cada tipo, por el gateway HTTPS, con un analista.

| Endpoint | Con caché: promedio / p95 | Sin caché: promedio / p95 | Mejora |
| :--- | ---: | ---: | ---: |
| `GET /analisis/zonas` (índice de acceso por zona) | 6.5 / 7.4 ms | 42.4 / 44.7 ms | 6.5× |
| `GET /analisis/mapa` (4 000 puntos) | 49.8 / 58.5 ms | 255.2 / 268.5 ms | 5.1× |

Resultado: `tests/carga/resultados/20261125_1616_cache.json`.

## 4. Locust: carga, estrés y recuperación

```bash
docker exec -i ms-seguridad python - < tests/carga/emitir_sesiones.py > tests/carga/resultados/sesiones.json
bash tests/carga/correr.sh carga 100 10 5m
bash tests/carga/correr.sh estres 400 2 6m
bash tests/carga/recuperacion.sh
```

Escenarios (`tests/carga/locustfile.py`):

| Perfil | Peso | Qué hace | Formato |
| :--- | :---: | :--- | :---: |
| Comerciante (app Android) | 6 | inventario, avisos, resumen y más vendidos, recomendaciones, pedidos, **registrar venta** | JSON |
| Analista (app de escritorio) | 2 | cobertura, brechas, agrupamientos, comparación de precios, pronóstico, reportes | XML |
| Visitante público (web) | 3 | inicio, disponibilidad, búsqueda, disponibilidad por producto | HTML/JSON |
| Auditor | 1 | bitácora de auditoría y resumen | JSON |

Cada usuario virtual tiene su propia cuenta y sesión, emitida con el mismo código del login. El login se
limita a 10 por minuto por IP contra fuerza bruta, y lo prueba aparte `test_seguridad.py`.

Locust habla directo con los servicios dentro de la red interna, sin pasar por el gateway: el gateway
limita a 30 peticiones/s por IP, y todos los usuarios virtuales salen de una sola IP. Siguen activos el
JWT con su sesión en Redis, los permisos y el límite de 120 peticiones por minuto por usuario y servicio.

### Resultados

| Corrida | Peticiones | Peticiones/s | Promedio | p50 | p95 | p99 | Máx | Errores |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| Carga, 100 usuarios, 5 min, **antes** | 10 559 | 35.3 | 196 ms | 20 ms | 1 200 ms | 3 900 ms | 6.7 s | 356 × 429 |
| Carga, 100 usuarios, 5 min, **después** | 11 423 | 38.2 | 39 ms | 19 ms | 170 ms | 270 ms | 0.6 s | 651 × 429, 1 × 409 |
| Estrés, rampa a 400 usuarios, 6 min | 39 505 | 110 (150 sostenidas con 400) | 76 ms | 23 ms | 260 ms | 1 300 ms | 3.5 s | 4 499 × 429, 1 × 409 |

**No hubo ningún error 5xx en carga ni en estrés.** Los 429 son del límite por IP de los endpoints públicos
(`/disponibilidad` y `/buscar`, 120 por minuto por IP): todos los visitantes virtuales comparten la IP
del generador, así que es el control funcionando. Con visitantes reales, cada uno tendría su propia IP. El
409 es una regla de negocio: se intentó vender más de lo que había en existencia.

**Endpoint lento encontrado: la búsqueda unificada.** Tenía p50 de 2.7 s y máximo de 6.7 s con 100
usuarios. En el registro de consultas lentas de PostgreSQL (`log_min_duration_statement = 200 ms`, activado
solo durante la prueba) aparecieron solo sus dos consultas, de unos 500 ms cada una. La causa era una
subconsulta por comercio que recalculaba la relevancia de texto de todo su inventario, dos veces. Se
reescribió para calcularla una vez por producto, con **resultados idénticos en 16 búsquedas de referencia**.
Quedó con p50 de 120 ms y p95 de 140 ms.

| Endpoint (100 usuarios) | p50 antes → después | p95 antes → después |
| :--- | ---: | ---: |
| `busqueda GET /buscar` | 2 700 → 120 ms | 4 800 → 140 ms |
| `recomendaciones GET /recomendaciones/{id}` | 270 → 250 ms | 360 → 360 ms |
| `analisis GET /analisis/brechas` [XML] | 130 → 120 ms | 170 → 160 ms |
| `inventario GET /comercios/{id}/inventario` | 23 → 22 ms | 33 → 30 ms |
| `ventas POST /ventas` (escribe en 3 servicios) | 47 → 44 ms | 68 → 59 ms |

**Saturación con 400 usuarios.** El throughput creció parejo hasta unas 150 peticiones/s, sin errores de
servidor. El p50 se quedó en 22–28 ms, pero el p99 subió a 1–3 s. El recurso que se satura es PostgreSQL:
promedió 394 % de CPU, con un máximo de 729 % (unos 7 núcleos), según `docker_stats.csv`. El endpoint más
afectado fue `GET /recomendaciones/{id}`, con p95 de 2.6 s: es el siguiente candidato a optimizar, porque
calcula la recomendación en cada petición y no la guarda en caché.

### Recuperación bajo carga (100 usuarios)

`tests/carga/recuperacion.sh` detiene ms-inventario 30 s y, después, Redis 30 s, con la carga corriendo.

| Falla | Qué ve el cliente | Recuperación tras arrancar |
| :--- | :--- | :--- |
| ms-inventario detenido | ms-ventas responde `503 servicio_no_disponible: ms-inventario no respondió`; los demás servicios siguen | ~14 s (arranque del contenedor y de gunicorn) |
| Redis detenido, **antes** | `503 sesiones_no_disponibles` (no deja pasar sin verificar la sesión), pero cada petición esperaba: p95 de 20 s, 3 peticiones/s | ~12 s |
| Redis detenido, **después** | El mismo 503 en < 1 s: p95 de 1 s y 35 peticiones/s | ~10 s |

**Hallazgos y correcciones:**

1. **El nombre de un contenedor detenido tardaba hasta 11 s en fallar.** El DNS interno de Docker pregunta
   afuera, y el tiempo de conexión de 1 s no cubre esa fase. Se agregó `dns_opt: timeout:1, attempts:1`
   en `docker-compose.yml`.
2. **Con Redis caído, cada petición esperaba su propio tiempo de conexión en cada operación**: sesión,
   límite, contadores y bitácora. Se agregó un corte rápido al pool de Redis (`PoolConCorte` en
   `abasto_dominio/extensiones.py`, con prueba unitaria): después de una falla, durante 2 s se falla al
   instante.
3. **ms-busqueda respondía 500 con Redis caído**, porque el registro «best effort» en ms-demanda no
   capturaba `RedisError`. Ya está corregido.

La latencia que queda mientras ms-inventario está caído (p95 ~5 s) es del propio Locust, que resuelve sin
`dns_opt` el nombre del contenedor detenido. Las llamadas entre servicios ya fallan rápido.

## 5. Limitaciones

- Carga y estrés corrieron en local, en la misma máquina que el generador. Los números absolutos no se
  trasladan a la VM de GCP (4 vCPU y 16 GB, contra 16 CPU en local).
- El gateway quedó fuera de la carga por su límite por IP. Para medirlo haría falta generar carga desde
  varias IP.
- No se midió el consumo de memoria del lado de la base de datos con más volumen (por ejemplo, 10× los
  datos), ni la escalabilidad horizontal (más workers o réplicas por servicio).
