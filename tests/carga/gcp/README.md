# Carga, estrés y recuperación contra el despliegue en Google Cloud

Estas pruebas miden el sistema **desplegado**. Todas las peticiones entran por la URL pública HTTPS y pasan por
NGINX. Los resultados locales (`tests/carga/locustfile.py` y `docs/rendimiento.md`) no se tocan: allá la carga va
directo a los contenedores y no pasa por el gateway. El análisis está en
[docs/rendimiento_gcp.md](../../../docs/rendimiento_gcp.md).

| Archivo | Qué hace |
| :--- | :--- |
| `config.ejemplo.env` | Plantilla sin secretos: proyecto, zona, VM, URL pública, certificado público, límites y umbrales. Se copia como `config.env`, que no se versiona |
| `preparar_cuentas_vm.py` | Corre dentro de `ms-seguridad`. Crea las cuentas de la corrida (`<prefijo>-com001@carga.abastored.test`…) con una contraseña aleatoria que no se guarda y emite sus tokens con el mismo código del login |
| `preparar_datos.py` | Usa la API pública. Cada comerciante da de alta su comercio, dentro de una zona, con 4 productos de 100 000 unidades y precio |
| `locustfile_gcp.py` | Los cuatro perfiles de siempre por HTTPS. Clasifica cada respuesta, guarda las latencias de los éxitos, aplica la forma por etapas, la guardia de parada y la fase de recuperación |
| `muestreo_vm.sh` | Corre en la VM y solo lee. Cada ~5 s registra CPU, memoria y disco de la VM y `docker stats`; cada ~30 s, los reinicios y OOM de cada contenedor |
| `verificar.py` | Comprobación funcional y una escritura controlada (venta idempotente). Con `--consistencia`, revisa el inventario y las ventas de todos los datos del prefijo |
| `resumen.py` | Genera `resumen.md` de cada corrida a partir de los CSV originales |
| `correr_gcp.sh` | Orquesta todo: `preparar`, `verificar`, `correr` y `limpiar` |

## Requisitos

- `gcloud` con sesión iniciada en una cuenta que pueda entrar por SSH a la VM a través de IAP. Los scripts no
  crean ni redimensionan recursos.
- Python con `locust==2.32.2` y `requests`, la misma versión que se usó en local:

  ```bash
  python -m venv .venv-carga && .venv-carga/Scripts/python -m pip install locust==2.32.2 requests
  ```

- `bash` (Git Bash en Windows) y `openssl`.
- `config.env` con los datos de **tu** VM. En `LOCUST_PY` va la ruta al Python del paso anterior.

## Pasos (los mismos que se ejecutaron el 26/11/2026)

```bash
cp tests/carga/gcp/config.ejemplo.env tests/carga/gcp/config.env      # y llénalo
P=gcp$(date +%m%d)a                                                    # prefijo NUEVO en cada corrida

bash tests/carga/gcp/correr_gcp.sh preparar  $P                         # cuentas, comercios e inventario (~2 min)
bash tests/carga/gcp/correr_gcp.sh verificar $P verificacion_inicial --muestras 3 --consistencia
bash tests/carga/gcp/correr_gcp.sh correr    $P linea_base "1:60,5:180" "" 1
bash tests/carga/gcp/correr_gcp.sh correr    $P carga "10:180,25:180,50:180" "" 2
bash tests/carga/gcp/correr_gcp.sh correr    $P estres_recuperacion "75:180,100:240,125?:180" "5:300" 2
bash tests/carga/gcp/correr_gcp.sh verificar $P verificacion_final --muestras 5 --consistencia
bash tests/carga/gcp/correr_gcp.sh limpiar   $P                         # revoca sesiones y desactiva las cuentas
```

Formato de las etapas: `usuarios:segundos`. Una etapa marcada con `?` solo se ejecuta si la anterior fue sana:
menos de 1 % de 5xx, timeouts o errores de conexión, p95 de los éxitos por debajo de la mitad del umbral y CPU de
la VM por debajo de 75 %. La recuperación (`"5:300"`) empieza al terminar las etapas o en cuanto se dispara una
condición de parada.

Cada corrida queda en `tests/carga/resultados/gcp/<AAAAMMDD_HHMM>_<escenario>/`:

| Archivo | Contenido |
| :--- | :--- |
| `ambiente.txt` | Fecha y zona horaria, commit de los scripts y su sha256, commit desplegado, VM (tipo, SO, CPU, memoria, disco), huella del certificado, generador, límites activos, condiciones de parada y tamaño de los datos |
| `reporte.html`, `locust_stats.csv`, `locust_stats_history.csv`, `locust_failures.csv`, `locust_exceptions.csv` | Salida original de Locust |
| `resultados_por_categoria.csv` | Por endpoint: ok, 429 del gateway, 429 del servicio, 409, 401/403, otros 4xx, 5xx, timeout, conexión y contrato, con latencias **solo de éxitos** |
| `linea_tiempo.csv` | Cada 10 s: usuarios, peticiones por categoría, p50/p95/p99 de éxitos, CPU y memoria de la VM, CPU del generador y estado de los 24 servicios |
| `muestras_vm.csv`, `estado_antes.txt`, `estado_despues.txt`, `oom_kernel.txt` | Recursos de la VM y de los contenedores, reinicios, OOM |
| `eventos_guardia.csv`, `ventas_enviadas.csv`, `cuentas.json` | Etapas, paradas, cada venta enviada con su `id_cliente`, y si alguna cuenta tuvo que reutilizarse |
| `resumen.md` | Tablas generadas de lo anterior |

Los tokens quedan solo en `tests/carga/resultados/gcp/privado/`, que no se versiona. `limpiar` borra ese archivo.

## Condiciones de parada (guardia)

Se revisan cada 5 s. Al dispararse una, la carga pasa a la fase de recuperación; si no hay recuperación, termina.

| Condición | Valor por omisión |
| :--- | :--- |
| 5xx + timeouts + errores de conexión sobre el total, sostenido 30 s | > 5 % |
| p95 de las respuestas **exitosas**, sostenido 60 s | > 3 000 ms |
| Sin ninguna respuesta | 30 s |
| Memoria disponible en la VM | < 1 500 MB |
| Disco libre en la VM | < 5 GB |
| Un contenedor se reinicia o queda OOMKilled | cualquiera |
| Parada manual | crear el archivo `PARAR` en la carpeta de la corrida |
| Concurrencia máxima / duración máxima de cada corrida | 150 usuarios / 2 400 s |

## Qué no hacen estos scripts

- No detienen ni reinician Redis, las bases ni los microservicios. La recuperación que se mide es tras
  **sobrecarga**, no tras una caída. Las caídas deliberadas se prueban solo en local (`tests/carga/recuperacion.sh`
  y `tests/integracion/test_fallas.py`).
- No desactivan la autenticación, los permisos ni los límites, y no usan `verify=False`. Tampoco alteran
  `X-Forwarded-For`.
- No miden el login: las sesiones se emiten antes, porque `POST /auth/login` admite 10 intentos por minuto y por IP.
- No miden el renderizado del web, de Android ni del escritorio: Locust solo reproduce sus peticiones.

## Prueba complementaria de backend (propuesta, no ejecutada)

El gateway admite **30 peticiones/s por IP** (ráfaga de 60). Un generador con una sola IP choca con ese límite
antes de saturar la VM. Para encontrar la capacidad de los servicios habría dos caminos:

1. Varios generadores con IP distintas, por ejemplo laptops del equipo en redes diferentes. Así se mide de verdad
   a través del gateway.
2. Correr `tests/carga/locustfile.py` dentro de la red de Docker de la VM, sin pasar por NGINX. Compite por la CPU
   con el sistema y **no** es rendimiento por HTTPS; habría que reportarlo aparte.

Ninguna de las dos se ejecutó.
