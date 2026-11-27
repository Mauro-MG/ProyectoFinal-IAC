# Resumen de la corrida `20261126_2252_linea_base`

```
fecha_local: 2026-11-26 22:52:19 -0600 (Central Standard Time (Mexico))
fecha_utc: 2026-11-27 04:52:19
escenario: linea_base
etapas (usuarios:segundos): 1:60,5:180
recuperacion: ninguna
incorporacion: 1 usuarios/s
prefijo de datos: gcp1126b
commit_scripts: 3a8cd6d (1 archivos de tests/carga/gcp sin commit)
sha256_scripts:
  51e53b140638bf9900721e808f7150a3138f39944abbb60454a6d7e7beafdc3a *comun.py
  3150ac656ed70b12ca05cab813d034679b9ddd470d84faf48bac90b1ce3c347a *locustfile_gcp.py
  3b77996ada278b3fa7efb4eb52adc8ef19d3d38c1645326d2e9f415a4075a0dc *muestreo_vm.sh
  b261e6ea232864bdaadc2dd33eea663e2b140916382b74d0c1fe45ab9f1739bf *verificar.py
  aee09cc3df99a92bda3eb3c46af64f60c549818fd8b9073c21d1109b16f1e0e8 *correr_gcp.sh
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
memoria_mb: total 15727 · disponible 9636
disco: 50G total · 39G libres
docker: 29.10.1
contenedores_en_ejecucion: 30
otros_proyectos_docker: 
otros_servicios_escuchando: 0.0.0.0:20202 [::1]:25 127.0.0.1:25 127.0.0.1:3000 127.0.0.1:5000 127.0.0.1:5001 127.0.0.1:5002 127.0.0.1:5003 127.0.0.1:5004 127.0.0.1:5005 127.0.0.1:5006 127.0.0.1:5432 127.0.0.1:6001 127.0.0.1:6379 127.0.0.1:8090 [::1]:5432 [::1]:6379 *:20201 
limite_gateway: limit_req_zone $binary_remote_addr zone=por_ip:10m rate=30r/s;
 limit_req zone=por_ip burst=60 nodelay;
limite_servicios: RATE_LIMIT_POR_MINUTO=120 (valor por omisión) por usuario y servicio
datos (usuarios comercios inventario ventas pedidos tamaño_bd): 304 219 1107 12 29 23 MB
```

## Eventos de la guardia

- 22:52:47 etapa carga 1 usuarios durante 60 s
- 22:52:47 inicio · prefijo gcp1126b · etapas [(1, 60, False), (5, 180, False)] · recuperación [] · tasa 1.0/s
- 22:53:48 etapa carga 5 usuarios durante 180 s
- 22:56:49 fin de la fase de carga: fin de las etapas
- 22:56:50 fin de la corrida

## Por etapa (ventanas de 10 s; se excluye la primera ventana de cada etapa)

| fase | usuarios | ventanas | pet/s | ok | 429 gateway | 429 servicio | 409 | 401/403 | 5xx | timeout+conexión | p50 ok (mediana) | p95 ok (mediana) | p95 ok (máx) | CPU VM prom/máx | mem. disp. VM mín (MB) | CPU generador máx |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| carga | 1 | 5 | 0.4 | 19 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 78 | 119 | 230 | 8 / 16 % | 9684 | 60 % |
| carga | 5 | 16 | 2.0 | 314 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 121 | 188 | 12 / 28 % | 9667 | 35 % |

## Por endpoint (toda la corrida; latencias SOLO de respuestas exitosas)

| endpoint | total | ok | 429 gw | 429 srv | 409 | 401/403 | otros 4xx | 5xx | timeout | conexión | contrato | prom ok | p50 ok | p95 ok | p99 ok | máx ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GET analisis GET /analisis/agrupamientos [xml] | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 57 | 56 | 58 | 58 | 58 |
| GET analisis GET /analisis/brechas [xml] | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 186 | 183 | 204 | 204 | 204 |
| GET analisis GET /analisis/zonas [xml] | 13 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 55 | 78 | 79 | 79 |
| GET busqueda GET /buscar | 21 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 76 | 80 | 94 | 99 | 99 |
| GET comercios GET /comercios | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 160 | 162 | 166 | 166 | 166 |
| GET demanda GET /demanda/estimacion [xml] | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 59 | 63 | 63 | 63 |
| GET disponibilidad GET /disponibilidad | 22 | 22 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 61 | 60 | 65 | 70 | 70 |
| GET inventario GET /comercios/{id}/inventario | 80 | 80 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 67 | 77 | 99 | 108 |
| GET notificaciones GET /notificaciones/contador | 68 | 68 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 51 | 51 | 54 | 55 | 68 |
| GET pedidos GET /pedidos | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 64 | 58 | 61 | 160 | 160 |
| GET precios GET /precios/comparacion | 17 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 68 | 66 | 78 | 78 | 78 |
| GET precios GET /precios/comparacion [xml] | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 77 | 66 | 161 | 161 | 161 |
| GET recomendaciones GET /recomendaciones/{id} | 21 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 154 | 145 | 200 | 230 | 230 |
| GET reportes GET /reportes [xml] | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 54 | 55 | 55 | 55 |
| GET ventas GET /ventas/resumen | 19 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 | 56 | 58 | 65 | 65 |
| GET web GET / | 26 | 26 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 70 | 62 | 85 | 177 | 177 |
| GET web GET /disponibilidad | 20 | 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 113 | 112 | 118 | 121 | 121 |
| POST ventas POST /ventas | 17 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 112 | 112 | 119 | 121 | 121 |
| **TOTAL** | 377 | 377 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 77 | 65 | 159 | 188 | 230 |

## Agregado según Locust (mezcla éxitos y rechazos en los percentiles)

peticiones 377 · fallas 0 · promedio 77 ms · p50 65 · p95 160 · p99 200 · máx 230 ms · 1.56 pet/s

## Recursos de la VM (muestras cada ~5 s)

- CPU usada: promedio 13 %, máximo 38 % · steal máx 0 % · carga 1 min máx 1.6
- Memoria disponible: mínimo 9574 MB · disco libre mínimo 39 GB
- Alertas de reinicio/OOM de contenedores: ninguna
- Kernel: sin eventos OOM del kernel desde el inicio de la corrida

### Contenedores con más CPU (promedio y máximo; 100 % = 1 vCPU)

| contenedor | CPU prom % | CPU máx % | memoria (última muestra) |
|---|---|---|---|
| abastored-mongo | 11.9 | 87.8 | 369MiB / 15.36GiB |
| abastored-postgres | 1.5 | 8.4 | 179.2MiB / 15.36GiB |
| ms-inventario | 1.5 | 8.5 | 164.7MiB / 15.36GiB |
| abastored-redis | 1.1 | 7.9 | 19.35MiB / 15.36GiB |
| ms-notificaciones | 0.9 | 8.2 | 155.2MiB / 15.36GiB |
| ms-monitoreo | 0.9 | 8.8 | 161.2MiB / 15.36GiB |
| ms-precios | 0.9 | 8.0 | 162.8MiB / 15.36GiB |
| ms-disponibilidad | 0.9 | 8.3 | 143.3MiB / 15.36GiB |
| ms-analisis | 0.8 | 8.6 | 150.7MiB / 15.36GiB |
| ms-seguridad | 0.8 | 8.1 | 155.8MiB / 15.36GiB |
| ms-ventas | 0.8 | 11.0 | 163.2MiB / 15.36GiB |
| ms-recomendaciones | 0.8 | 8.4 | 164.2MiB / 15.36GiB |

