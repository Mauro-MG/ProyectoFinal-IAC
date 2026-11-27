# Resumen de la corrida `20261126_2312_estres_recuperacion`

```
fecha_local: 2026-11-26 23:12:58 -0600 (Central Standard Time (Mexico))
fecha_utc: 2026-11-27 05:12:58
escenario: estres_recuperacion
etapas (usuarios:segundos): 75:180,100:240,125?:180
recuperacion: 5:300
incorporacion: 2 usuarios/s
prefijo de datos: gcp1126b
commit_scripts: 3a8cd6d (1 archivos de tests/carga/gcp sin commit)
sha256_scripts:
  51e53b140638bf9900721e808f7150a3138f39944abbb60454a6d7e7beafdc3a *comun.py
  3150ac656ed70b12ca05cab813d034679b9ddd470d84faf48bac90b1ce3c347a *locustfile_gcp.py
  3b77996ada278b3fa7efb4eb52adc8ef19d3d38c1645326d2e9f415a4075a0dc *muestreo_vm.sh
  b261e6ea232864bdaadc2dd33eea663e2b140916382b74d0c1fe45ab9f1739bf *verificar.py
  0ae05e608cb51ea49a5dac305e8c3533108674810068462af410cdd8c458d563 *correr_gcp.sh
host: https://34.135.84.31 (HTTPS por NGINX; TLS verificado con certificado_gateway_gcp.crt)
certificado_publico: E3:82:2B:96:93:47:0E:94:51:6D:05:69:F8:8B:3B:37:F9:60:F0:92:3B:06:A9:3C:05:86:B1:76:0B:99:EC:31
certificado_servido: E3:82:2B:96:93:47:0E:94:51:6D:05:69:F8:8B:3B:37:F9:60:F0:92:3B:06:A9:3C:05:86:B1:76:0B:99:EC:31
proyecto/zona/vm: integracion-505802 / us-central1-c / integracion
tipo_maquina: e2-standard-4
generador: Windows-11-10.0.26200-SP0 · 16 CPU lógicas · 31.9 GB · Python 3.12.9 · Locust 2.32.2 · fuera de GCP, por internet público
limites: MAX_USUARIOS=150 DURACION_MAX_S=2400 TIMEOUT_S=30
paradas: errores>0.05 30s · p95_ok>3000ms 60s · sin respuestas 30s · mem_vm<1500MB · disco_vm<5GB · reinicio/OOM de contenedor · archivo PARAR
--- VM
commit_desplegado: 670ba4e
so: CentOS Stream 10 (Coughlan) · kernel 6.12.0-233.el10.x86_64
cpu: 4 vCPU · Intel(R) Xeon(R) CPU @ 2.20GHz
memoria_mb: total 15727 · disponible 9612
disco: 50G total · 39G libres
docker: 29.10.1
contenedores_en_ejecucion: 30
otros_proyectos_docker: 
otros_servicios_escuchando: 0.0.0.0:20202 [::1]:25 127.0.0.1:25 127.0.0.1:3000 127.0.0.1:5000 127.0.0.1:5001 127.0.0.1:5002 127.0.0.1:5003 127.0.0.1:5004 127.0.0.1:5005 127.0.0.1:5006 127.0.0.1:5432 127.0.0.1:6001 127.0.0.1:6379 127.0.0.1:8090 [::1]:5432 [::1]:6379 *:20201 
limite_gateway: limit_req_zone $binary_remote_addr zone=por_ip:10m rate=30r/s;
 limit_req zone=por_ip burst=60 nodelay;
limite_servicios: RATE_LIMIT_POR_MINUTO=120 (valor por omisión) por usuario y servicio
datos (usuarios comercios inventario ventas pedidos tamaño_bd): 304 219 1107 263 29 24 MB
```

## Eventos de la guardia

- 23:13:26 etapa carga 75 usuarios durante 180 s
- 23:13:26 inicio · prefijo gcp1126b · etapas [(75, 180, False), (100, 240, False), (125, 180, True)] · recuperación [(5, 300, False)] · tasa 2.0/s
- 23:16:26 etapa carga 100 usuarios durante 240 s
- 23:20:27 etapa carga 125 usuarios durante 180 s
- 23:23:27 fin de la fase de carga: fin de las etapas
- 23:23:27 etapa recuperacion 5 usuarios durante 300 s
- 23:28:28 fin de la corrida

## Por etapa (ventanas de 10 s; se excluye la primera ventana de cada etapa)

| fase | usuarios | ventanas | pet/s | ok | 429 gateway | 429 servicio | 409 | 401/403 | 5xx | timeout+conexión | p50 ok (mediana) | p95 ok (mediana) | p95 ok (máx) | CPU VM prom/máx | mem. disp. VM mín (MB) | CPU generador máx |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| carga | 20 | 1 | 5.8 | 58 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 64 | 180 | 180 | 6 / 6 % | 9586 | 11 % |
| carga | 42 | 1 | 13.5 | 135 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 166 | 166 | 26 / 26 % | 9595 | 13 % |
| carga | 62 | 1 | 20.7 | 207 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 64 | 163 | 163 | 23 / 23 % | 9560 | 15 % |
| carga | 75 | 13 | 28.3 | 3585 (97.4%) | 0 (0.0%) | 97 (2.6%) | 0 | 0 | 0 (0.0%) | 0 | 64 | 156 | 173 | 27 / 44 % | 9460 | 23 % |
| carga | 79 | 1 | 28.7 | 272 (94.8%) | 0 (0.0%) | 15 (5.2%) | 0 | 0 | 0 (0.0%) | 0 | 67 | 159 | 159 | 30 / 30 % | 9591 | 6 % |
| carga | 99 | 1 | 36.0 | 326 (90.6%) | 10 (2.8%) | 24 (6.7%) | 0 | 0 | 0 (0.0%) | 0 | 67 | 167 | 167 | 30 / 30 % | 9583 | 5 % |
| carga | 100 | 21 | 38.1 | 6037 (75.5%) | 1690 (21.1%) | 267 (3.3%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 157 | 172 | 29 / 55 % | 9448 | 52 % |
| carga | 108 | 1 | 40.2 | 296 (73.6%) | 101 (25.1%) | 5 (1.2%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 159 | 159 | 35 / 35 % | 9595 | 18 % |
| carga | 125 | 16 | 47.0 | 4623 (61.5%) | 2722 (36.2%) | 172 (2.3%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 157 | 311 | 29 / 44 % | 9437 | 52 % |
| recuperacion | 95 | 1 | 43.2 | 298 (69.0%) | 132 (30.6%) | 2 (0.5%) | 0 | 0 | 0 (0.0%) | 0 | 67 | 157 | 157 | 51 / 51 % | 9559 | 12 % |
| recuperacion | 75 | 1 | 32.1 | 270 (84.1%) | 30 (9.3%) | 21 (6.5%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 156 | 156 | 26 / 26 % | 9510 | 10 % |
| recuperacion | 55 | 1 | 25.1 | 227 (90.4%) | 0 (0.0%) | 24 (9.6%) | 0 | 0 | 0 (0.0%) | 0 | 66 | 167 | 167 | 31 / 31 % | 9542 | 12 % |
| recuperacion | 35 | 1 | 16.8 | 148 (88.1%) | 0 (0.0%) | 20 (11.9%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 162 | 162 | 26 / 26 % | 9555 | 7 % |
| recuperacion | 15 | 1 | 9.5 | 95 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 64 | 172 | 172 | 23 / 23 % | 9549 | 8 % |
| recuperacion | 5 | 24 | 1.9 | 452 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 63 | 124 | 178 | 13 / 42 % | 9526 | 15 % |

## Por endpoint (toda la corrida; latencias SOLO de respuestas exitosas)

| endpoint | total | ok | 429 gw | 429 srv | 409 | 401/403 | otros 4xx | 5xx | timeout | conexión | contrato | prom ok | p50 ok | p95 ok | p99 ok | máx ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GET analisis GET /analisis/agrupamientos [xml] | 272 | 221 | 51 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 | 55 | 60 | 94 | 155 |
| GET analisis GET /analisis/brechas [xml] | 502 | 394 | 108 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 184 | 179 | 208 | 260 | 292 |
| GET analisis GET /analisis/zonas [xml] | 762 | 579 | 183 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 55 | 77 | 110 | 160 |
| GET auditoria GET /eventos | 697 | 558 | 139 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 160 | 156 | 178 | 221 | 466 |
| GET auditoria GET /resumen | 334 | 281 | 53 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 75 | 70 | 98 | 163 | 239 |
| GET auditoria GET /trazas/{correlation_id} | 327 | 252 | 75 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 53 | 60 | 68 | 89 |
| GET busqueda GET /buscar | 1708 | 1265 | 379 | 64 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 77 | 78 | 100 | 145 | 440 |
| GET comercios GET /comercios | 63 | 57 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 155 | 154 | 162 | 164 | 178 |
| GET demanda GET /demanda/estimacion [xml] | 270 | 202 | 68 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 58 | 69 | 107 | 164 |
| GET disponibilidad GET /disponibilidad | 1686 | 679 | 386 | 621 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 59 | 68 | 81 | 155 |
| GET inventario GET /comercios/{id}/inventario | 4061 | 3213 | 848 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 67 | 80 | 99 | 366 |
| GET notificaciones GET /notificaciones/contador | 3046 | 2398 | 648 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 52 | 51 | 56 | 66 | 324 |
| GET pedidos GET /pedidos | 1028 | 815 | 213 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 | 57 | 66 | 74 | 97 |
| GET precios GET /precios/comparacion | 1037 | 825 | 212 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 68 | 65 | 79 | 105 | 386 |
| GET precios GET /precios/comparacion [xml] | 522 | 406 | 116 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 70 | 66 | 81 | 167 | 352 |
| GET recomendaciones GET /recomendaciones/{id} | 1022 | 813 | 209 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 158 | 150 | 207 | 234 | 458 |
| GET reportes GET /reportes [xml] | 261 | 216 | 45 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 53 | 57 | 144 | 155 |
| GET ventas GET /ventas/resumen | 1039 | 838 | 201 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 | 55 | 62 | 74 | 271 |
| GET web GET / | 2507 | 1995 | 512 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 65 | 61 | 83 | 102 | 350 |
| GET web GET /disponibilidad | 1648 | 1308 | 340 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 113 | 111 | 126 | 170 | 412 |
| POST ventas POST /ventas | 963 | 764 | 199 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 116 | 110 | 143 | 185 | 397 |
| **TOTAL** | 23755 | 18079 | 4991 | 685 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 79 | 65 | 160 | 192 | 466 |

## Agregado según Locust (mezcla éxitos y rechazos en los percentiles)

peticiones 23754 · fallas 5676 · promedio 72 ms · p50 59 · p95 150 · p99 190 · máx 466 ms · 26.36 pet/s

## Recursos de la VM (muestras cada ~5 s)

- CPU usada: promedio 23 %, máximo 62 % · steal máx 0 % · carga 1 min máx 3.2
- Memoria disponible: mínimo 9420 MB · disco libre mínimo 39 GB
- Alertas de reinicio/OOM de contenedores: ninguna
- Kernel: sin eventos OOM del kernel desde el inicio de la corrida

### Contenedores con más CPU (promedio y máximo; 100 % = 1 vCPU)

| contenedor | CPU prom % | CPU máx % | memoria (última muestra) |
|---|---|---|---|
| abastored-mongo | 14.1 | 103.0 | 429.9MiB / 15.36GiB |
| abastored-postgres | 12.7 | 33.8 | 181.5MiB / 15.36GiB |
| ms-inventario | 6.7 | 17.7 | 168.5MiB / 15.36GiB |
| ms-recomendaciones | 5.0 | 42.5 | 167.3MiB / 15.36GiB |
| abastored-web | 4.7 | 19.4 | 234MiB / 15.36GiB |
| ms-ventas | 3.3 | 14.2 | 166.9MiB / 15.36GiB |
| ms-analisis | 2.4 | 14.5 | 152.4MiB / 15.36GiB |
| ms-precios | 2.1 | 12.6 | 167MiB / 15.36GiB |
| ms-busqueda | 2.0 | 12.1 | 160.8MiB / 15.36GiB |
| abastored-gateway | 1.9 | 13.9 | 13.91MiB / 15.36GiB |
| ms-notificaciones | 1.8 | 10.8 | 159.5MiB / 15.36GiB |
| abastored-redis | 1.8 | 9.6 | 20.64MiB / 15.36GiB |

