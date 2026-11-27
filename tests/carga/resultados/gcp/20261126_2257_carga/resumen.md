# Resumen de la corrida `20261126_2257_carga`

```
fecha_local: 2026-11-26 22:57:32 -0600 (Central Standard Time (Mexico))
fecha_utc: 2026-11-27 04:57:32
escenario: carga
etapas (usuarios:segundos): 10:180,25:180,50:180
recuperacion: ninguna
incorporacion: 2 usuarios/s
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
memoria_mb: total 15727 · disponible 9674
disco: 50G total · 39G libres
docker: 29.10.1
contenedores_en_ejecucion: 30
otros_proyectos_docker: 
otros_servicios_escuchando: 0.0.0.0:20202 [::1]:25 127.0.0.1:25 127.0.0.1:3000 127.0.0.1:5000 127.0.0.1:5001 127.0.0.1:5002 127.0.0.1:5003 127.0.0.1:5004 127.0.0.1:5005 127.0.0.1:5006 127.0.0.1:5432 127.0.0.1:6001 127.0.0.1:6379 127.0.0.1:8090 [::1]:5432 [::1]:6379 *:20201 
limite_gateway: limit_req_zone $binary_remote_addr zone=por_ip:10m rate=30r/s;
 limit_req zone=por_ip burst=60 nodelay;
limite_servicios: RATE_LIMIT_POR_MINUTO=120 (valor por omisión) por usuario y servicio
datos (usuarios comercios inventario ventas pedidos tamaño_bd): 304 219 1107 29 29 23 MB
```

## Eventos de la guardia

- 22:57:59 etapa carga 10 usuarios durante 180 s
- 22:57:59 inicio · prefijo gcp1126b · etapas [(10, 180, False), (25, 180, False), (50, 180, False)] · recuperación [] · tasa 2.0/s
- 23:01:00 etapa carga 25 usuarios durante 180 s
- 23:04:01 etapa carga 50 usuarios durante 180 s
- 23:07:01 fin de la fase de carga: fin de las etapas
- 23:07:01 fin de la corrida

## Por etapa (ventanas de 10 s; se excluye la primera ventana de cada etapa)

| fase | usuarios | ventanas | pet/s | ok | 429 gateway | 429 servicio | 409 | 401/403 | 5xx | timeout+conexión | p50 ok (mediana) | p95 ok (mediana) | p95 ok (máx) | CPU VM prom/máx | mem. disp. VM mín (MB) | CPU generador máx |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| carga | 10 | 16 | 3.7 | 589 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 64 | 150 | 180 | 14 / 41 % | 9539 | 20 % |
| carga | 14 | 1 | 3.8 | 38 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 72 | 183 | 183 | 10 / 10 % | 9671 | 36 % |
| carga | 25 | 16 | 9.5 | 1521 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 155 | 180 | 15 / 34 % | 9482 | 18 % |
| carga | 31 | 1 | 10.2 | 102 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 0 (0.0%) | 0 | 67 | 160 | 160 | 16 / 16 % | 9633 | 11 % |
| carga | 50 | 16 | 19.0 | 2961 (97.6%) | 0 (0.0%) | 74 (2.4%) | 0 | 0 | 0 (0.0%) | 0 | 65 | 156 | 164 | 24 / 39 % | 9495 | 31 % |

## Por endpoint (toda la corrida; latencias SOLO de respuestas exitosas)

| endpoint | total | ok | 429 gw | 429 srv | 409 | 401/403 | otros 4xx | 5xx | timeout | conexión | contrato | prom ok | p50 ok | p95 ok | p99 ok | máx ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GET analisis GET /analisis/agrupamientos [xml] | 55 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 | 55 | 59 | 66 | 78 |
| GET analisis GET /analisis/brechas [xml] | 124 | 124 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 184 | 181 | 208 | 268 | 284 |
| GET analisis GET /analisis/zonas [xml] | 165 | 165 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 55 | 79 | 143 | 151 |
| GET auditoria GET /eventos | 161 | 161 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 159 | 157 | 170 | 230 | 245 |
| GET auditoria GET /resumen | 97 | 97 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 67 | 81 | 98 | 160 |
| GET auditoria GET /trazas/{correlation_id} | 79 | 79 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | 54 | 57 | 58 | 62 |
| GET busqueda GET /buscar | 382 | 382 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 75 | 78 | 92 | 103 | 194 |
| GET comercios GET /comercios | 25 | 25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 157 | 156 | 172 | 184 | 184 |
| GET demanda GET /demanda/estimacion [xml] | 69 | 69 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 | 58 | 64 | 65 | 65 |
| GET disponibilidad GET /disponibilidad | 430 | 354 | 0 | 76 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 61 | 59 | 67 | 106 | 164 |
| GET inventario GET /comercios/{id}/inventario | 1009 | 1009 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 67 | 77 | 87 | 203 |
| GET notificaciones GET /notificaciones/contador | 739 | 739 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 51 | 51 | 54 | 60 | 133 |
| GET pedidos GET /pedidos | 270 | 270 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 58 | 57 | 63 | 66 | 68 |
| GET precios GET /precios/comparacion | 243 | 243 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 67 | 65 | 78 | 98 | 167 |
| GET precios GET /precios/comparacion [xml] | 125 | 125 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 71 | 67 | 79 | 166 | 172 |
| GET recomendaciones GET /recomendaciones/{id} | 243 | 243 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 155 | 149 | 192 | 243 | 310 |
| GET reportes GET /reportes [xml] | 67 | 67 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 53 | 53 | 58 | 62 | 68 |
| GET ventas GET /ventas/resumen | 261 | 261 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 | 55 | 61 | 66 | 112 |
| GET web GET / | 579 | 579 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 66 | 61 | 82 | 101 | 184 |
| GET web GET /disponibilidad | 404 | 404 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 112 | 110 | 120 | 181 | 191 |
| POST ventas POST /ventas | 234 | 234 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 115 | 113 | 135 | 145 | 187 |
| **TOTAL** | 5761 | 5685 | 0 | 76 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 78 | 65 | 158 | 185 | 310 |

## Agregado según Locust (mezcla éxitos y rechazos en los percentiles)

peticiones 5757 · fallas 76 · promedio 78 ms · p50 65 · p95 160 · p99 190 · máx 310 ms · 10.64 pet/s

## Recursos de la VM (muestras cada ~5 s)

- CPU usada: promedio 18 %, máximo 41 % · steal máx 0 % · carga 1 min máx 1.5
- Memoria disponible: mínimo 9482 MB · disco libre mínimo 39 GB
- Alertas de reinicio/OOM de contenedores: ninguna
- Kernel: sin eventos OOM del kernel desde el inicio de la corrida

### Contenedores con más CPU (promedio y máximo; 100 % = 1 vCPU)

| contenedor | CPU prom % | CPU máx % | memoria (última muestra) |
|---|---|---|---|
| abastored-mongo | 12.3 | 105.5 | 385.1MiB / 15.36GiB |
| abastored-postgres | 6.9 | 19.9 | 180MiB / 15.36GiB |
| ms-inventario | 4.1 | 17.3 | 165.2MiB / 15.36GiB |
| abastored-web | 2.8 | 12.6 | 233.3MiB / 15.36GiB |
| ms-recomendaciones | 2.7 | 21.4 | 166.8MiB / 15.36GiB |
| ms-ventas | 1.9 | 11.3 | 166.6MiB / 15.36GiB |
| ms-precios | 1.7 | 9.4 | 163.1MiB / 15.36GiB |
| abastored-redis | 1.4 | 7.9 | 21.14MiB / 15.36GiB |
| ms-busqueda | 1.4 | 9.2 | 158.8MiB / 15.36GiB |
| ms-analisis | 1.4 | 10.3 | 152.1MiB / 15.36GiB |
| abastored-gateway | 1.3 | 12.4 | 13.35MiB / 15.36GiB |
| ms-monitoreo | 1.2 | 8.4 | 162.7MiB / 15.36GiB |

