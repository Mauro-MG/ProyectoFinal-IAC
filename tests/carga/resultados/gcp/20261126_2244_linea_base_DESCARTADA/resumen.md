# Resumen de la corrida `20261126_2244_linea_base`

```
fecha_local: 2026-11-26 22:44:47 -0600 (Central Standard Time (Mexico))
fecha_utc: 2026-11-27 04:44:47
escenario: linea_base
etapas (usuarios:segundos): 3:120
recuperacion: ninguna
incorporacion: 1 usuarios/s
prefijo de datos: gcp1126a
commit_scripts: 3a8cd6d (1 archivos de tests/carga/gcp sin commit)
sha256_scripts:
  51e53b140638bf9900721e808f7150a3138f39944abbb60454a6d7e7beafdc3a *comun.py
  3150ac656ed70b12ca05cab813d034679b9ddd470d84faf48bac90b1ce3c347a *locustfile_gcp.py
  3b77996ada278b3fa7efb4eb52adc8ef19d3d38c1645326d2e9f415a4075a0dc *muestreo_vm.sh
  963462ddea675b2700a96a7988dd3dc3c96caa93be465ff83a2bd111918fe448 *verificar.py
  9820fc41b5d4cf768e5b1412c919668929b818b7a456e6adbfa1b9cfee2a7934 *correr_gcp.sh
host: https://34.135.84.31 (HTTPS por NGINX; TLS verificado con certificado_gateway_gcp.crt)
certificado_publico: E3:82:2B:96:93:47:0E:94:51:6D:05:69:F8:8B:3B:37:F9:60:F0:92:3B:06:A9:3C:05:86:B1:76:0B:99:EC:31
certificado_servido: E3:82:2B:96:93:47:0E:94:51:6D:05:69:F8:8B:3B:37:F9:60:F0:92:3B:06:A9:3C:05:86:B1:76:0B:99:EC:31
proyecto/zona/vm: integracion-505802 / us-central1-c / integracion
tipo_maquina: e2-standard-4
generador: Windows-11-10.0.26200-SP0  16 CPU lgicas  31.9 GB  Python 3.12.9  Locust 2.32.2 · fuera de GCP, por internet público
limites: MAX_USUARIOS=150 DURACION_MAX_S=2400 TIMEOUT_S=30
paradas: errores>0.05 30s · p95_ok>3000ms 60s · sin respuestas 30s · mem_vm<1500MB · disco_vm<5GB · reinicio/OOM de contenedor · archivo PARAR
--- VM
commit_desplegado: 670ba4e
so: CentOS Stream 10 (Coughlan) · kernel 6.12.0-233.el10.x86_64
cpu: 4 vCPU · Intel(R) Xeon(R) CPU @ 2.20GHz
memoria_mb: total 15727 · disponible 9805
disco: 50G total · 40G libres
docker: 29.10.1
contenedores_en_ejecucion: 30
otros_proyectos_docker: 
otros_servicios_escuchando: 0.0.0.0:20202 [::1]:25 127.0.0.1:25 127.0.0.1:3000 127.0.0.1:5000 127.0.0.1:5001 127.0.0.1:5002 127.0.0.1:5003 127.0.0.1:5004 127.0.0.1:5005 127.0.0.1:5006 127.0.0.1:5432 127.0.0.1:6001 127.0.0.1:6379 127.0.0.1:8090 [::1]:5432 [::1]:6379 *:20201 
limite_gateway: limit_req_zone $binary_remote_addr zone=por_ip:10m rate=30r/s;
 limit_req zone=por_ip burst=60 nodelay;
limite_servicios: RATE_LIMIT_POR_MINUTO=120 (valor por omisión) por usuario y servicio
datos (usuarios comercios inventario ventas pedidos tamaño_bd): 169 129 747 5 29 22 MB
```

## Eventos de la guardia

- 22:45:15 etapa carga 3 usuarios durante 120 s
- 22:45:15 inicio · prefijo gcp1126a · etapas [(3, 120, False)] · recuperación [] · tasa 1.0/s
- 22:47:16 fin de la fase de carga: fin de las etapas
- 22:47:16 fin de la corrida

## Por etapa (ventanas de 10 s; se excluye la primera ventana de cada etapa)

| fase | usuarios | ventanas | pet/s | ok | 429 gateway | 429 servicio | 409 | 401/403 | 5xx | timeout+conexión | p50 ok (mediana) | p95 ok (mediana) | p95 ok (máx) | CPU VM prom/máx | mem. disp. VM mín (MB) | CPU generador máx |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| carga | 3 | 10 | 1.2 | 112 (96.6%) | 0 (0.0%) | 0 (0.0%) | 4 | 0 | 0 (0.0%) | 0 | 65.39099995279685 | 147.85714994650334 | 184.22229995485395 | 11 / 19 % | 9619.0 | 14.2 |

## Por endpoint (toda la corrida; latencias SOLO de respuestas exitosas)

| endpoint | total | ok | 429 gw | 429 srv | 409 | 401/403 | otros 4xx | 5xx | timeout | conexión | contrato | prom ok | p50 ok | p95 ok | p99 ok | máx ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GET analisis GET /analisis/agrupamientos [xml] | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59.6 | 56.327000027522445 | 67.69619998522103 | 67.69619998522103 | 67.7 |
| GET analisis GET /analisis/brechas [xml] | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 233.8 | 181.3240998890251 | 452.0411000121385 | 452.0411000121385 | 452.0 |
| GET analisis GET /analisis/zonas [xml] | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59.7 | 53.901500068604946 | 72.34049995895475 | 72.34049995895475 | 72.3 |
| GET busqueda GET /buscar | 26 | 26 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 72.4 | 76.26549992710352 | 94.82670004945248 | 123.44049999956042 | 123.4 |
| GET comercios GET /comercios | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 182.1 | 182.13460000697523 | 182.13460000697523 | 182.13460000697523 | 182.1 |
| GET demanda GET /demanda/estimacion [xml] | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69.8 | 73.21319996844977 | 76.82700001168996 | 76.82700001168996 | 76.8 |
| GET disponibilidad GET /disponibilidad | 11 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 62.2 | 57.71480000112206 | 91.1604999564588 | 91.1604999564588 | 91.2 |
| GET inventario GET /comercios/{id}/inventario | 16 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69.9 | 68.18639999255538 | 78.2368000363931 | 85.48769995104522 | 85.5 |
| GET notificaciones GET /notificaciones/contador | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 53.3 | 52.827600040473044 | 55.98120007198304 | 55.98120007198304 | 56.0 |
| GET pedidos GET /pedidos | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 111.6 | 59.37939998693764 | 163.72230008710176 | 163.72230008710176 | 163.7 |
| GET precios GET /precios/comparacion | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 66.0 | 65.3736999956891 | 67.48899992089719 | 67.48899992089719 | 67.5 |
| GET precios GET /precios/comparacion [xml] | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 71.4 | 65.20080007612705 | 92.25169999990612 | 92.25169999990612 | 92.3 |
| GET recomendaciones GET /recomendaciones/{id} | 5 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |  |  |  |  |  |
| GET reportes GET /reportes [xml] | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55.3 | 55.21380004938692 | 57.06839996855706 | 57.06839996855706 | 57.1 |
| GET ventas GET /ventas/resumen | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58.2 | 57.80279997270554 | 59.62569999974221 | 59.62569999974221 | 59.6 |
| GET web GET / | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 97.4 | 59.117999975569546 | 84.87159991636872 | 547.7934000082314 | 547.8 |
| GET web GET /disponibilidad | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 118.1 | 110.24229996837676 | 170.06719997152686 | 170.06719997152686 | 170.1 |
| POST ventas POST /ventas | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 121.8 | 111.6455999435857 | 153.19410001393408 | 153.19410001393408 | 153.2 |
| **TOTAL** | 139 | 134 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 85.0 | 67.39950005430728 | 175.66720000468194 | 452.0411000121385 | 547.8 |

## Agregado según Locust (mezcla éxitos y rechazos en los percentiles)

peticiones 139 · fallas 5 · promedio 85 ms · p50 67 · p95 180 · p99 450 · máx 548 ms · 1.16 pet/s

## Recursos de la VM (muestras cada ~5 s)

- CPU usada: promedio 11 %, máximo 32 % · steal máx 0 % · carga 1 min máx 0.9
- Memoria disponible: mínimo 9619 MB · disco libre mínimo 40 GB
- Alertas de reinicio/OOM de contenedores: ninguna
- Kernel: sin eventos OOM del kernel desde el inicio de la corrida

### Contenedores con más CPU (promedio y máximo; 100 % = 1 vCPU)

| contenedor | CPU prom % | CPU máx % | memoria (última muestra) |
|---|---|---|---|
| abastored-mongo | 9.6 | 94.4 | 353.6MiB / 15.36GiB |
| abastored-postgres | 1.7 | 9.3 | 175.8MiB / 15.36GiB |
| ms-inventario | 1.2 | 8.6 | 164.3MiB / 15.36GiB |
| ms-recomendaciones | 1.0 | 9.8 | 161.5MiB / 15.36GiB |
| abastored-redis | 1.0 | 7.2 | 19.25MiB / 15.36GiB |
| abastored-gateway | 1.0 | 9.8 | 12.88MiB / 15.36GiB |
| ms-documentos | 1.0 | 8.4 | 172.6MiB / 15.36GiB |
| ms-ventas | 0.9 | 8.2 | 163MiB / 15.36GiB |
| ms-notificaciones | 0.9 | 8.4 | 155.1MiB / 15.36GiB |
| ms-sincronizacion | 0.9 | 8.0 | 154.2MiB / 15.36GiB |
| ms-auditoria | 0.9 | 8.0 | 143.8MiB / 15.36GiB |
| ms-monitoreo | 0.9 | 7.9 | 161.1MiB / 15.36GiB |

