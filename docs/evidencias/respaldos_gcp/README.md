# Respaldo y simulacro de restauración en Google Cloud

- **Fecha:** 2026-11-25
- **Dónde:** VM `integracion`, bucket `gs://abastored-archivos-integracion-505802/respaldos/`
- **Respaldo automático:** cron diario a las 03:30 UTC (`/etc/cron.d/abastored-respaldo`). Los objetos vencen a los 60 días.

## Comandos (en la VM)

```bash
sudo /usr/local/bin/abastored-respaldar
sudo bash /opt/abastored/actual/apps/infra/gcp/probar_restauracion.sh <respaldo>   # no toca los datos en uso
sudo bash /opt/abastored/actual/apps/infra/gcp/restaurar.sh <respaldo>             # restauración real (pide confirmar)
```

El simulacro hace cuatro cosas:

1. Descarga el respaldo y verifica el SHA-256.
2. Restaura PostgreSQL en la base `restauracion_prueba`, y MongoDB con los nombres cambiados a `restauracion_prueba`.
3. Compara el conteo de cada tabla y colección contra las bases en uso.
4. Borra las copias.

Las bases del sistema no se detienen.

## Resultado (respaldo `20261125T213911Z`, 1.1 MB)

```
postgres.dump: OK
mongo.archive.gz: OK
PostgreSQL: 44 restauradas, 44 con el mismo conteo que hoy, 0 creadas después del respaldo
MongoDB: 26 restauradas, 26 con el mismo conteo que hoy, 0 creadas después del respaldo
```

## Defectos encontrados con este simulacro y corregidos

1. **El `.env` de la VM tenía fin de línea CRLF.** `respaldar.sh` fallaba al leerlo, así que el respaldo diario no se habría generado. Ahora el instalador lo normaliza y los scripts lo leen sin `\r` (commit `7fc2042`).
2. **`SHA256SUMS` guardaba la ruta absoluta de la carpeta temporal.** La verificación de `restaurar.sh` fallaba siempre. Ahora guarda nombres relativos, y los scripts de restauración aceptan también los respaldos con el formato anterior.
3. **`sudo abastored-respaldar` no se encontraba.** En CentOS, `sudo` no busca en `/usr/local/bin`, así que se documenta la ruta completa. El cron ya la usaba.

## No probado

La restauración real con `restaurar.sh`, que reemplaza los datos en uso, no se ejecutó sobre el despliegue. El simulacro valida el mismo respaldo y los mismos comandos `pg_restore` y `mongorestore`, pero sobre bases aparte.
