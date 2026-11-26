# Página del proyecto en Ubiquitous

Ubiquitous (`ubiquitous.udem.edu`) es el servidor de páginas personales de la UDEM. Solo sirve archivos
estáticos y se publica por SSH, solo desde la red de la universidad o con la VPN. No ejecuta Docker,
así que **el sistema corre en Google Cloud** (`https://34.135.84.31`). En Ubiquitous queda la página
del proyecto, dentro del portafolio del curso:

- `proyecto-final-abastored/`: la página, con capturas reales y diagramas. Usa el CSS del portafolio
  (`../assets/css/styles.css`).
- `tarjeta_portafolio.html`: la tarjeta que se agrega en la portada del portafolio.
- `publicar.ps1`: copia la carpeta por `scp` y pide la contraseña en la terminal. La contraseña no se
  guarda en ningún archivo.

```powershell
powershell -ExecutionPolicy Bypass -File apps\ubiquitous\publicar.ps1
```

Antes de publicar, el equipo completa la sección **Equipo**: aportaciones, conclusiones y uso de IA,
marcadas como pendientes en el HTML.

Estado: **preparada, no publicada.** Desde el equipo donde se preparó no había conexión SSH a
Ubiquitous (fuera de la red UDEM). El portafolio sí responde por HTTPS.
