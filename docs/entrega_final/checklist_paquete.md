# Checklist del paquete de la entrega final

**Estado al 25/11/2026.** Este checklist **no** significa que la entrega académica se haya hecho. Cada
integrante hace además su **entrega individual**.

- [x] Preparado y verificado.
- [ ] Falta, o lo hace una persona del equipo.

## Código y ejecución

- [x] Código en la rama `feature/entrega-final-completa`. Se construye desde una descarga limpia
  (`docs/evidencias/descarga_limpia/`).
- [ ] **Push de la rama, pull request y merge a `main`.** Lo hace el equipo: no se publicó nada sin
  autorización.
- [x] Scripts de inicialización: `scripts/preparar_entorno.py`, `db/postgres/*.sql`, `db/mongo/init.js`.
- [x] Contenedores: `docker-compose.yml` (local) y `docker-compose.gcp.yml` (nube).
- [x] Swagger de los 24 servicios (`/ms/<servicio>/docs`) y contratos XSD (`/xsd`).
- [x] Colección de Postman: `docs/postman/` (es del avance 2; revisar si hace falta regenerarla con
  `tests/evidencias/generar.py`).
- [x] Ningún secreto en el repositorio: `.env`, `secrets/`, llaves de firma y llave del certificado están
  fuera de git. Los tokens JWT que aparecen en las evidencias del avance 2 vencieron el 15/11.

## Instalables

- [x] APK de release firmado, compilado para GCP: se genera con `apps/movil/README.md`.
- [ ] **Subir el APK** donde lo pida el profesor (no se versiona; pesa 13 MB).
- [x] Instalador `AbastoRed-1.1.0-win64.msi` para GCP, probado en un entorno limpio
  (`docs/evidencias/instalador_escritorio/`).
- [ ] **Subir el MSI** (46 MB, no se versiona).
- [ ] Prueba manual del MSI en otra computadora con Windows recién instalado.
- [ ] Prueba de la app en un teléfono físico (solo se probó en el emulador).

## Despliegues

- [x] Google Cloud: `https://34.135.84.31`, verificado con 185 pruebas, bucket real, respaldo y restauración.
- [ ] **Ubiquitous:** la página está lista en `apps/ubiquitous/`. Falta:
  - completar la sección «Equipo» con aportaciones, conclusiones y uso de IA;
  - publicarla con `publicar.ps1` desde la red UDEM o VPN;
  - agregar la tarjeta al portafolio.
- [ ] Decidir qué hacer con las reglas de firewall heredadas de la otra práctica (`apps/infra/README.md`,
  «Pendientes y riesgos»).
- [ ] Apagar la VM cuando ya no se use (unos US$0.13 por hora).

## Documentación y presentación

- [ ] **Documento técnico actualizado.** La guía con lo que cambió y su evidencia está en
  `docs/entrega_final/actualizacion_documento_tecnico.md`; la redacción es del equipo.
- [ ] **Presentación final actualizada** (misma guía, sección «Presentación»).
- [x] Manuales técnicos y de instalación: README principal, `apps/infra/README.md`, `apps/movil/README.md`,
  `apps/escritorio/README.md` y `apps/ubiquitous/README.md`.
- [ ] Manual de usuario: no existe un documento aparte; el «Escenario de demostración» del README y el
  guion de la demo sirven de base.
- [x] Algoritmos: `docs/algoritmos.md`.
- [x] Rendimiento y carga: `docs/rendimiento.md`, con resultados originales en `tests/carga/resultados/`.
- [x] Matriz de requisitos con su evidencia: `docs/entrega_final/matriz_requisitos.md`.

## Evidencias

- [x] Suite completa local y contra GCP: `docs/pruebas/` y `docs/evidencias/pruebas_gcp/`.
- [x] Tres procesos completos: `docs/evidencias/procesos/`.
- [x] Recorrido de Android contra GCP: `docs/evidencias/movil_gcp/`.
- [x] Respaldos: `docs/evidencias/respaldos_gcp/`.
- [ ] **Video** de la demostración (guion en `docs/entrega_final/guion_demo.md`).

## Equipo

- [ ] Bitácora de participación: la base con datos de git está en `bitacora_participacion.md`. Cada
  integrante confirma qué cuenta es la suya y agrega lo que hizo fuera de git.
- [ ] Reflexión individual de cada integrante (preguntas guía en `plantillas_reflexion.md`).
- [ ] Entrega individual de cada integrante en la plataforma del curso.
