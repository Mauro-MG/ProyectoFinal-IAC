# Recorrido de la app Android contra Google Cloud

- **Fecha:** 2026-11-25
- **Commit desplegado:** `e58954e` en la VM `integracion` (https://34.135.84.31)
- **APK:** release firmado (`app-release.apk`, 13.3 MB), compilado con `-PgatewayUrl=https://34.135.84.31 -PcertificadoGateway=../../apps/infra/gcp/certificado_gateway_gcp.crt`
- **Dispositivo:** emulador Pixel 5 (API 36, x86_64), ubicación simulada en Monterrey centro

Lo maneja `scripts/recorrido_movil_gcp.py` con adb (`scripts/emulador.py`); la salida está en [recorrido.txt](recorrido.txt).

| Paso | Qué se comprobó | Resultado | Captura |
|---|---|---|---|
| 1 | Registro simplificado desde la app (ms-seguridad) | OK | movil_10_registro.png |
| 2 | Alta del comercio con la ubicación del teléfono; ms-geolocalización asigna la zona «Monterrey Centro» | OK | movil_11_comercio_ubicacion.png |
| 3 | Alta de producto desde el catálogo maestro con existencia y precio | OK | movil_12_inventario.png |
| 4 | Recomendaciones de abasto, ofertas del proveedor y pedido enviado (20 kg; con 5 kg el proveedor lo rechaza por pedido mínimo de $350) | OK | movil_13_abasto.png, movil_14_ofertas.png |
| 5 | Avisos y perfil | OK (0 avisos para la cuenta nueva) | movil_15_avisos.png, movil_16_perfil.png |
| 5b | Reabrir la app sin revocar: la sesión se mantiene | OK | — |
| 6 | Revocar el dispositivo en el servidor (por `token_final`, igual que el web en Notificaciones > Dispositivos): al reabrir, la app vuelve al inicio de sesión | OK | movil_17_revocado.png |

## Defecto encontrado y corregido en este recorrido

La lista de dispositivos de ms-notificaciones solo devuelve los últimos 8 caracteres del token (`token_final`), pero la app comparaba el campo `token`, que siempre llegaba vacío. Con eso, cualquier reapertura de la app habría cerrado la sesión. Se corrigió en los commits `e8c4369` (servidor y web) y `e58954e` (app); las pruebas `test_dispositivo_se_revoca_con_el_final_del_token` y `test_revocar_dispositivo_desde_el_web_lo_hace_ms_notificaciones` lo cubren.

## Qué no cubre

- No se probó en un teléfono físico.
- El escaneo de código de barras y de QR se probó solo a nivel de compilación: el emulador no tiene cámara con códigos reales.
- Las notificaciones de WorkManager tardan hasta 15 minutos y no se esperaron en este recorrido.
