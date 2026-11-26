# Construcción desde una descarga limpia

**Fecha:** 24 de noviembre de 2026.
**Commit probado:** `5dd8916`, de la rama `feature/entrega-final-completa`.
**Equipo:** Windows 11, Docker 29.8.1 (16 CPU, 16 GB), Python 3.12 de python.org.

## Procedimiento seguido

Solo el procedimiento documentado en el README, sobre un clon nuevo que no reutiliza archivos
ignorados, secretos, certificados ni imágenes:

```bash
git clone <repo> abastored-limpio && cd abastored-limpio
python scripts/preparar_entorno.py      # creó .env y 30 secretos nuevos
docker compose build --no-cache         # 26 imágenes: 24 servicios, web y gateway
docker compose up -d                    # 29 contenedores; los 29 quedaron "healthy"
python scripts/ejecutar_pruebas.py      # crea su propio .venv e instala dependencias
```

## Resultado

| Paso | Resultado |
| :--- | :--- |
| Construcción | 26 imágenes construidas sin errores (`construccion_imagenes.txt`) |
| Arranque | 29 de 29 contenedores sanos |
| Pruebas | **294 aprobadas y 1 fallida** de 295 (`pruebas_reporte.html`, `pruebas_salida.txt`) |

## Problemas encontrados y corregidos

1. **ms-reportes no estaba en GitHub.** La regla `reportes/` del `.gitignore` excluía también
   `apps/microservicios/reportes`. Se acotó a `/reportes/` (commit `c0fa41f`). Por eso este clon ya
   incluye los 24 servicios.
2. **`gradlew` podía quedar con fin de línea CRLF** en Windows. Se fijó a LF en `.gitattributes`
   (commit `5dd8916`).
3. **El runner de pruebas fallaba con el Python de MSYS2.** Ese Python crea el entorno virtual en
   `bin/python.exe` y el runner no lo buscaba ahí. Se corrigió `scripts/ejecutar_pruebas.py`.
4. **Una prueba dependía del orden en que se corren.**
   - `test_los_servicios_se_conectan_con_su_propio_usuario` suponía que ms-ventas ya tenía abierta
     una conexión a PostgreSQL.
   - En el clon limpio ninguna prueba anterior había usado ms-ventas, así que falló.
   - Se corrigió: la prueba hace una consulta real a ms-ventas y verifica que responda 200.
   - Es la única falla de esta corrida, y fue un defecto de la prueba, no del sistema.
