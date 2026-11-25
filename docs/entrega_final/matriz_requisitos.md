# Matriz de requisitos de la entrega final

**Fecha:** 25/11/2026. **Rama:** `feature/entrega-final-completa` (sin push).

Estados:

- **Cumplido:** implementado y verificado con la evidencia indicada.
- **Parcial:** implementado, pero falta una verificación o una parte.
- **Pendiente (equipo):** requiere acción o acceso de una persona del equipo.
- **No hecho:** no se hizo.

## 1. Construcción y bloqueo de ms-reportes

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| ms-reportes en el repositorio (lo excluía `.gitignore`) | Cumplido | commit `c0fa41f` |
| Construcción desde una descarga limpia, con secretos y certificados por el procedimiento documentado | Cumplido | `docs/evidencias/descarga_limpia/` |

## 2. Despliegue en GCP y Ubiquitous

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Infraestructura reproducible: aprovisionar, instalar, desplegar, actualizar, revertir | Cumplido | `apps/infra/gcp/*.sh`, `apps/infra/README.md` |
| Firewall: solo puertos públicos necesarios; bases privadas | Parcial | Reglas propias: 80/443 y 22 solo por IAP; solo el gateway publica puertos. **Riesgo:** dos reglas de otra práctica abren el 22 a todo internet (solo con llave) y el 8080 (nada escucha). Ver `apps/infra/README.md` |
| HTTPS, credenciales protegidas, logs, persistencia | Cumplido | certificado con SAN, secretos 700 en la VM, rotación de logs, volúmenes |
| Respaldo y restauración documentados y probados | Cumplido | `docs/evidencias/respaldos_gcp/` (44/44 tablas, 26/26 colecciones) |
| Distribución de componentes y justificación de bases en contenedores | Cumplido | `apps/infra/README.md`, `docs/diagramas/despliegue_gcp.png` |
| Desplegado y validado en GCP | Cumplido | `https://34.135.84.31`; `docs/evidencias/pruebas_gcp/` (182 aprobadas) |
| Despliegue en Ubiquitous | **Pendiente (equipo)** | Ubiquitous solo sirve páginas estáticas: el sistema no puede correr ahí. La página del proyecto está lista en `apps/ubiquitous/`, pero no hubo conexión SSH desde fuera de la red UDEM. La publica el usuario con su contraseña (`publicar.ps1`) |

## 3. Cloud Storage y URL firmadas

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Fotos, documentos, evidencias, CSV y reportes en GCS; metadatos en la base | Cumplido | `libs/abasto_dominio/.../archivos.py`, `test_almacenamiento.py` |
| Migración no destructiva desde GridFS | Cumplido | `POST /documentos/migracion`, prueba de migración |
| URL firmadas temporales, bucket privado, autorización por recurso | Cumplido | firma V4 con suplantación de cuenta, sin llaves descargadas |
| Validación del contenido real, del tamaño y del nombre | Cumplido | `test_acceso_denegado_inexistente_e_invalido` |
| Pruebas: autorizado, denegado, caducidad, inexistente, inválido y caída | Cumplido | caducidad real en `storage.googleapis.com` (`PRUEBAS_GCS_REAL=1`); la caída se prueba con el emulador local |

## 4. Android

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Registro simplificado, perfil, alta de productos, cámara, ubicación, códigos de barras y QR, proveedores, recomendaciones, pedido de abasto y avisos | Cumplido | `docs/evidencias/movil_gcp/` (recorrido del APK contra GCP) |
| Token cifrado (Keystore), renovación, registro y revocación del dispositivo | Cumplido | se corrigió que la app cerraba la sesión al reabrirse (`e8c4369`, `e58954e`) |
| Sin conexión, idempotencia y conflictos | Cumplido | se conservaron (Room + ms-sincronizacion); `test_lote_offline_con_duplicados_y_conflicto` |
| APK instalable firmado y compilación reproducible | Cumplido | `apps/movil/README.md`; la llave está fuera de git |
| Prueba en un dispositivo físico | **No hecho** | Solo en el emulador. El escaneo con la cámara no se probó con códigos reales |

## 5. Escritorio

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Catálogos, recomendaciones, zonas y permisos por rol | Cumplido | `apps/escritorio/`, `test_app_escritorio.py` |
| Exportación de oportunidades e impresión | Cumplido | pestaña Oportunidades (CSV y PDF), impresión con auditoría |
| Solo XML validado con XSD, también en los errores | Cumplido | se encontró y corrigió un número no válido para `xs:decimal` |
| Instalador para Windows probado en un entorno limpio | Parcial | MSI para GCP con diagnóstico correcto en un entorno sin Python. Falta la prueba manual en otra computadora |

## 6. Salud y monitoreo

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| `/health/live`, `/ready`, `/database`, `/redis`, `/mongodb` y `/storage`; estados degradado y caído | Cumplido | `test_monitoreo.py`, `test_seguridad.py::test_health_es_publico...` |
| Verificaciones automáticas periódicas con historial | Cumplido | `monitor-verificador` (30 s, parámetro), `verificaciones_salud` con TTL |
| Panel: estado, latencia, último error y dependencia responsable | Cumplido | web → *Estado de los servicios* (`apps/ubiquitous/.../web_monitoreo.png`) |
| El monitor informa aunque caiga su propia dependencia | Cumplido | `test_el_monitor_informa_aunque_caiga_su_mongodb`, `test_sin_redis_ni_mongodb...` |

## 7. Locust, volumen y rendimiento

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Escenarios web/API, móvil JSON, escritorio XML y administración, con autenticación | Cumplido | `tests/carga/locustfile.py` |
| Carga, estrés y recuperación en un entorno controlado; RPS, p95/p99, errores y saturación | Cumplido | `docs/rendimiento.md` §4 (solo local; no se cargó la VM de GCP) |
| Datos masivos reproducibles (miles de usuarios y comercios, cientos de miles de eventos) | Cumplido | `scripts/datos_masivos.py`: 1.32 M filas, misma huella con la misma semilla |
| Planes de ejecución, índices, caché con y sin Redis | Cumplido | `docs/rendimiento.md` §2–3 |
| Resultados originales con fecha, commit y ambiente | Cumplido | `tests/carga/resultados/` |

## 8. Algoritmos

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Agrupamiento geográfico con parámetros, ruido y visualización | Cumplido | DBSCAN (haversine + índice de rejilla), web *Concentraciones comerciales* |
| Pronóstico evaluado con datos no usados al ajustar | Cumplido | evaluación fuera de muestra contra un modelo base |
| Comparación estadística | Cumplido | Mann-Whitney, validado contra scipy |
| Documentación: problema, complejidad, pseudocódigo, pruebas, métricas y tiempos | Cumplido | `docs/algoritmos.md`, `tests/unitarias/test_agrupamiento.py`, `test_pronostico.py`, `test_estadistica.py` |

## 9. Pruebas y procesos completos

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Suite actualizada en la entrega actual (no el reporte del 15/11) | Cumplido | `docs/pruebas/` (corrida completa de este commit; ver el resumen abajo) |
| Caída y recuperación: servicio, Redis, MongoDB, PostgreSQL y almacenamiento | Cumplido | `test_fallas.py`, `test_resiliencia.py`, `test_almacenamiento.py`, `tests/carga/recuperacion.sh` |
| Timeout, archivo inexistente, token revocado, sin permisos y sobrecarga | Cumplido | `test_fallas.py` (timeout con reintento), `test_almacenamiento.py`, `test_seguridad.py` (revocación, 403, 429) |
| Respuesta inválida de una dependencia | Parcial | El cliente de escritorio rechaza respuestas que no cumplen el XSD. No hay una prueba que inyecte una respuesta malformada entre servicios |
| Tres procesos completos con evidencia | Cumplido | `docs/evidencias/procesos/` (local y GCP) |
| Usabilidad | **No hecho** | No se hicieron pruebas con usuarios |

## 10. Verificación del web y los servicios

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Sin regresiones en lo ya implementado | Cumplido | suite completa local y en GCP |
| Sitio público y privado, sesión, roles, catálogos, transacciones, reportes con Highcharts, auditoría, archivos, avisos y configuración | Cumplido | `test_web_por_apis.py`, capturas; se corrigieron las gráficas vacías (`bdd08fe`) |
| Siete perfiles | Cumplido | cuentas de prueba del README; `test_seguridad.py` |
| Seguridad: JWT de acceso y renovación, revocación, permisos por recurso, límites, validación y errores seguros | Cumplido | `test_seguridad.py`; el gateway no permite falsificar `X-Forwarded-For` |

## 11. Documentación y entregables

| Requisito | Estado | Evidencia |
| :--- | :--- | :--- |
| Documento técnico actualizado | **Pendiente (equipo)** | Guía con cada cambio y su evidencia: `actualizacion_documento_tecnico.md`. El `.docx` no se modificó |
| Presentación final alineada con el código | **Pendiente (equipo)** | misma guía, sección «Presentación» |
| Guion y recorrido de la demo | Cumplido | `guion_demo.md`; procesos reproducibles |
| Video | **Pendiente (equipo)** | grabación con el guion |
| Bitácora de participación e incidencias con datos reales | Parcial | `bitacora_participacion.md` (datos de git). Cada integrante confirma su cuenta y agrega el trabajo fuera de git |
| Plantillas de reflexión | Cumplido | `plantillas_reflexion.md` (preguntas, sin respuestas) |
| Checklist del paquete | Cumplido | `checklist_paquete.md` |

## Resumen de pruebas

| Corrida | Commit | Resultado | Dónde |
| :--- | :--- | :--- | :--- |
| Suite completa local (unitarias + integración), `python scripts/ejecutar_pruebas.py` | `c7fb9bc`, sin cambios pendientes | **342 aprobadas**, 0 fallidas, 1 no aplica: la caducidad en el bucket real, que solo corre en GCP. Tardó 6 min 48 s | `docs/pruebas/` |
| Integración contra GCP (`PRUEBAS_GCS_REAL=1`) | ver `docs/evidencias/pruebas_gcp/` | 182 aprobadas, 15 omitidas (detienen contenedores o requieren el secreto local) | `docs/evidencias/pruebas_gcp/` |
| Tres procesos completos | `c7fb9bc` | 3/3 en local y 3/3 en GCP | `docs/evidencias/procesos/` |
| Carga, estrés y recuperación | `dcb0892` y `65fccba` | Sin 5xx en carga ni estrés. Con Redis caído: p95 de 1 s y 503 claro | `docs/rendimiento.md` |
