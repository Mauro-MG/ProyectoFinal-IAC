# Guía para actualizar el documento técnico y la presentación

**Archivos:**

- `docs/AbastoRed_Equipo01_Documento_Tecnico.docx`: 21 capítulos. La última edición es del avance 2
  (12/10/2026).
- `docs/AbastoRed_Avance2_Final.pptx`: 17 diapositivas, del 13/10/2026.

Estos archivos **no se modificaron**. El equipo los redacta con sus palabras. Esta guía señala qué dice hoy
cada parte que ya no coincide con el sistema final, el dato correcto y dónde está la evidencia. Así no queda
ninguna tecnología planeada descrita como implementada, ni al revés.

## Documento técnico: afirmaciones que ya no son ciertas

| Capítulo (párrafo aprox.) | Dice hoy | Lo correcto en la entrega final | Evidencia |
| :--- | :--- | :--- | :--- |
| 3. Modelo de negocio | «VM e2-medium, Cloud SQL chico, Memorystore básico, Storage» | VM **e2-standard-4**; PostgreSQL, MongoDB y Redis **en contenedores** en la misma VM (sin Cloud SQL ni Memorystore); Cloud Storage real. Costo aproximado: US$0.13/h encendida | `apps/infra/README.md` (justificación) |
| 5. Requerimientos | «Doce servicios independientes…» y «Compute Engine con VPC, firewall y **Secret Manager**» | **24 microservicios**. Secretos en archivos de la VM con permisos 700, no en Secret Manager. Red: firewall con etiqueta, 80/443 públicos y 22 solo por IAP | `docs/diagramas/microservicios_24.png`, `apps/infra/gcp/` |
| 5. Requerimientos | «Health checks y monitoreo (segundo parcial), despliegue en GCP (cuarto parcial)» | Hecho: `/health/live`, `/ready`, `/database`, `/redis`, `/mongodb` y `/storage`; verificación automática cada 30 s con historial; desplegado en GCP | `docs/evidencias/pruebas_gcp/`, `tests/integracion/test_monitoreo.py` |
| 2 y 5 | «App móvil… (tercer parcial)» | Hecha: Android en Kotlin con Compose y APK de release firmado | `apps/movil/README.md`, `docs/evidencias/movil_gcp/` |
| 7. Arquitectura (diagrama de despliegue) | Balanceador HTTPS, Memorystore, Secret Manager, Cloud Logging | Despliegue **real**: sin balanceador (una VM; gateway nginx con TLS), logs con rotación en la VM y bitácora en MongoDB | `docs/diagramas/despliegue_gcp.png` (reemplaza `despliegue.png`) |
| 9. Algoritmos | Regresión con estacionalidad, recomendaciones y geoespacial | Agregar **DBSCAN** (concentraciones comerciales), **evaluación del pronóstico fuera de muestra** contra un modelo base y **Mann-Whitney** para comparar precios formal/informal | `docs/algoritmos.md` |
| 12–14. Segundo avance y fichas | «Ocho microservicios» | Son 24, con puertos 8101–8124. Las fichas de los 16 nuevos se pueden generar del registro (`abasto_dominio/registro_servicios.py`) y de cada `/openapi.json` | `apps/microservicios/README.md` |
| 14 (ms-comercios, ms-inventario) y 17 (MongoDB) | «Archivos en **GridFS**», «CSV en GridFS» | Archivos en **Cloud Storage**: bucket privado, URL firmadas V4 y suplantación de cuenta sin llaves. Los metadatos quedan en MongoDB (`archivos_metadatos`) y GridFS solo como origen de la migración no destructiva | `docs/propiedad_de_datos.md`, `tests/integracion/test_almacenamiento.py` |
| 19. Docker Compose | Una red `abastored-network` y puertos 8101–8108 publicados | Dos redes internas (`publica`, `datos`). **Solo el gateway publica puertos** (80/443). 31 contenedores, con `dns_opt` y el monitor | `docker-compose.yml`, `test_seguridad.py::test_solo_el_gateway_esta_expuesto` |
| 20. Pruebas | Resultados del avance 2 | Resultados actuales: suite completa local, suite contra GCP, carga y estrés con Locust, fallas y recuperación, tres procesos completos | `docs/pruebas/`, `docs/evidencias/`, `docs/rendimiento.md` |
| 21. Plan de trabajo | Lo planeado para el cierre | Lo hecho y lo pendiente real | `docs/entrega_final/matriz_requisitos.md` |

## Documento técnico: capítulos nuevos que pide la entrega final

| Capítulo sugerido | Contenido (los datos ya están medidos) | Fuente |
| :--- | :--- | :--- |
| Aplicación móvil | Pantallas, sin conexión, cifrado del token con Keystore, dispositivo revocable, cámara, ubicación, escáner, avisos con WorkManager, firma | `apps/movil/README.md`, `docs/evidencias/movil_gcp/` |
| Aplicación de escritorio | Solo XML validado con XSD, módulos por rol, exportación e impresión, instalador MSI | `apps/escritorio/README.md`, `docs/evidencias/instalador_escritorio/` |
| Infraestructura en GCP | VM, firewall, bucket, IAM sin llaves, despliegue y reversión, respaldos y restauración | `apps/infra/README.md`, `docs/evidencias/respaldos_gcp/` |
| Almacenamiento y URL firmadas | Flujo de subida, metadatos, autorización por recurso, caducidad real | `docs/evidencias/pruebas_gcp/` |
| Monitoreo | Liveness y readiness, estados degradado y caído, historial, panel | `tests/integracion/test_monitoreo.py`, captura `web_monitoreo.png` |
| Volumen y rendimiento | Datos masivos, `EXPLAIN` antes y después, caché, Locust, recuperación | `docs/rendimiento.md` |
| Fallas y recuperación | PostgreSQL, MongoDB, Redis y un servicio caídos; timeout con reintento | `tests/integracion/test_fallas.py`, `docs/rendimiento.md` §4 |
| Procesos de punta a punta | Los 3 procesos con `correlation_id` | `docs/evidencias/procesos/` |
| Manual de instalación y despliegue | Local, GCP, APK, MSI | README principal, `apps/*/README.md` |
| Limitaciones y trabajo futuro | Ver la sección «Pendientes» de la matriz | `docs/entrega_final/matriz_requisitos.md` |

## Presentación (`AbastoRed_Avance2_Final.pptx`)

| Diapositiva | Dice hoy | Cambiar a |
| :--- | :--- | :--- |
| 1 | «Avance 2 · Microservicios, integración y pruebas» | Entrega final |
| 5 | «Del monolito a 8 microservicios», 87 operaciones | 24 microservicios y **258 operaciones** (suma de los 24 `/openapi.json` el 25/11/2026) |
| 6 | Diagrama de arquitectura del avance 2 | `docs/diagramas/microservicios_24.png` |
| 7 | «¿Por qué estos 8 servicios?»; ms-comercios con «fotos (GridFS)» | Los 24 agrupados por dominio; fotos en Cloud Storage |
| 10 | Puertos 8101–8108, 5432, 27017 y 6379 publicados; una red | Solo el gateway publica (80/443); redes `publica` y `datos` |
| 11, 14, 15 | «Fotos y evidencias en GridFS», «GridFS: fotos, evidencias y CSV» | Cloud Storage con URL firmadas; metadatos en MongoDB |
| 17 | «Siguiente avance: app móvil y de escritorio» | Ya están hechas: agregar diapositivas de Android, escritorio, GCP, monitoreo, rendimiento y los 3 procesos |
| Nuevas | — | Despliegue real (`despliegue_gcp.png`), resultados de carga (tabla de `docs/rendimiento.md`), incidencias encontradas (`bitacora_participacion.md`) y limitaciones |
