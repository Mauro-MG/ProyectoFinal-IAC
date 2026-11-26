# Guion de la demostración y del video

**Estado:** guion y pasos listos. **La grabación está pendiente:** la hace el equipo con el sistema real.

- **Duración objetivo:** 12–15 minutos.
- **Orden:** el mismo que pide la entrega: problema, arquitectura, web, Android, escritorio, APIs/Swagger, nube,
  almacenamiento, monitoreo, algoritmo, carga e integración.
- **Reparto:** cada bloque tiene un responsable sugerido. Ajústenlo para que cada integrante presente lo
  que trabajó.

## Antes de grabar (15 min)

1. **Encender la VM de GCP**, si estaba apagada, y comprobar que todo esté sano:
   ```bash
   gcloud compute instances start integracion --zone us-central1-c --project integracion-505802
   ```
   Luego abrir `https://34.135.84.31/` y aceptar la advertencia del certificado autofirmado.
   En *Estado de los servicios* deben aparecer 24 de 24 en línea.
2. **Teléfono o emulador** con el APK de release, compilado para `https://34.135.84.31`
   (`apps/movil/README.md`).
3. **Escritorio:** instalar `AbastoRed-1.1.0-win64.msi`, el construido con `--gateway https://34.135.84.31`
   (ver `docs/evidencias/instalador_escritorio/`).
4. **Sesiones abiertas en pestañas distintas.** Las cuentas de prueba están en el README principal:
   - comerciante (`minorista@test.mx`);
   - proveedor (`proveedor@test.mx`);
   - coordinador;
   - analista;
   - auditor;
   - administrador.
5. **Para el bloque de carga:** dejar abierto `tests/carga/resultados/20261125_1626_carga_post_optimizacion/reporte.html`.
   La carga no se corre en vivo contra la nube.

## Guion

| Min | Bloque | Qué se muestra | Qué se dice (idea, en sus palabras) | Responsable |
| :--- | :--- | :--- | :--- | :--- |
| 0:00 | Problema | Inicio público: acceso a la canasta básica por zona | Tianguis y tiendas sin sistemas. Qué resuelve AbastoRed para comerciantes, proveedores y municipio | |
| 1:00 | Arquitectura | `docs/diagramas/microservicios_24.png` y `despliegue_gcp.png` | 24 servicios dueños de sus datos, gateway HTTPS, JSON y XML, sesión en Redis | |
| 2:30 | Web | Comerciante: inventario, precio atípico en revisión, pedido. Proveedor: acepta | El web escribe solo por las APIs; la auditoría muestra qué servicio cambió cada dato | |
| 4:00 | Android | Registro, comercio con ubicación, agregar producto escaneando el código de barras, Abasto → pedido, recibir con QR, sin conexión → sincronizar | JSON, sin conexión, token cifrado y dispositivo revocable desde el web | |
| 6:00 | Escritorio | Coordinador valida un comercio. Analista: cobertura, oportunidades, exportar a PDF, imprimir | Solo XML, validado con XSD, también en los errores; instalador MSI | |
| 7:30 | APIs / Swagger | `https://34.135.84.31/ms/pedidos/docs`: probar un endpoint en JSON y en XML | Contratos, versión `/api/v1`, errores uniformes, límite de peticiones | |
| 8:30 | Nube | VM, firewall (80/443 e IAP), `desplegar.sh`, respaldo diario y simulacro de restauración | Despliegue reproducible con `git archive`; las bases van en contenedores (y por qué) | |
| 9:30 | Almacenamiento | Subir la foto de un comercio, abrirla y mostrar que la URL es de `storage.googleapis.com` y caduca | Bucket privado, URL firmadas V4 sin llaves descargadas | |
| 10:30 | Monitoreo | *Estado de los servicios*: historial de 24 h. Detener un servicio en local → degradado o caído | Verificación automática cada 30 s; liveness contra readiness | |
| 11:30 | Algoritmo | *Concentraciones comerciales* (DBSCAN) y el pronóstico con su evaluación fuera de muestra | Qué resuelve, parámetros, complejidad, cómo se evaluó (`docs/algoritmos.md`) | |
| 12:30 | Carga | Reporte de Locust: antes y después; búsqueda de 2.7 s a 120 ms | Datos masivos (1.3 M filas), índices, caché y recuperación con Redis caído (`docs/rendimiento.md`) | |
| 13:30 | Integración | Un `correlation_id` del proceso de abasto en `GET /trazas/{id}` | Un pedido toca 6 servicios y queda rastreado de punta a punta | |
| 14:30 | Cierre | Lo que falta y lo que aprendieron | Limitaciones reales (ver la matriz de requisitos) | |

## Recorrido reproducible (sin video)

Los tres procesos completos se pueden repetir con:

```bash
PROCESOS_EVIDENCIA=1 PRUEBAS_HOST=https://34.135.84.31 PRUEBAS_CA=apps/infra/gcp/certificado_gateway_gcp.crt \
    python -m pytest tests/integracion/test_procesos_completos.py -q
```

La corrida deja cada paso, con su `correlation_id`, en `docs/evidencias/procesos/`.

## Al terminar

- Apagar la VM si no se va a usar. Cuesta unos US$0.13 por hora encendida:
  ```bash
  gcloud compute instances stop integracion --zone us-central1-c --project integracion-505802
  ```
- Subir el video a donde lo pida el profesor y poner el enlace en el checklist del paquete.
