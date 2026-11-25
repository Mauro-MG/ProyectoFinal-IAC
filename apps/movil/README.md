# Aplicación móvil Android

Aplicación en Kotlin con Jetpack Compose para pequeños comerciantes, formales e informales. Cumple tres
reglas:

- **Solo usa JSON** y entra a los microservicios por el gateway HTTPS.
- **No se conecta a las bases de datos** ni comparte la sesión del sistema web.
- **Sigue funcionando sin señal.**

## Qué hace

| Pantalla | Qué hace | Servicios |
| :--- | :--- | :--- |
| Inicio de sesión y registro | Entrar o crear cuenta en un minuto (puesto/tianguis o tienda formal); JWT y refresh token cifrados en el teléfono | ms-seguridad `POST /auth/login`, `POST /auth/registro`; renueva con `POST /auth/renovar` al recibir un 401 |
| Agregar producto | Búsqueda en el catálogo maestro o **escaneo del código de barras** con la cámara; existencia, mínimo y precio iniciales | ms-catalogo, ms-inventario |
| Inventario | Productos del comercio con existencia, mínimo, precio y estado (disponible, bajo, agotado) | ms-comercios, ms-inventario |
| Vender | Venta rápida con método de pago; descuenta el inventario | ms-ventas `POST /ventas` (con `id_cliente`, no se duplica) |
| Entrada | Mercancía que llegó | ms-inventario `POST /inventario/{id}/movimientos` |
| Precio | Cambio de precio; avisa si quedó en revisión por ser atípico | ms-precios `PUT /inventario/{id}/precio` |
| Abasto | Productos recomendados para el comercio (faltan en la zona y se demandan), proveedores con oferta y envío del pedido | ms-recomendaciones, ms-proveedores, ms-pedidos |
| Pedidos | Seguimiento de los pedidos de abasto; la recepción se confirma **escaneando el QR del repartidor**, y suma la mercancía al inventario | ms-pedidos, ms-entregas |
| Avisos | Notificaciones del negocio (pedido aceptado, stock bajo, precio en revisión...) y, con la app cerrada, aviso en la barra del teléfono cada 15 min (WorkManager, sin Firebase) | ms-notificaciones |
| Perfil | Registro del comercio con la **ubicación del teléfono** (asigna la zona), foto del local con la cámara, cambio de contraseña y cierre de sesión | ms-seguridad, ms-comercios, ms-geolocalizacion, ms-documentos |
| Pendientes | Lo capturado sin conexión, con su estado: por enviar, conflicto o rechazada | ms-sincronizacion `POST /lotes` |

### Sin conexión

Si no hay señal o el servidor no responde, la app sigue funcionando:

- **Inventario.** Muestra la última copia guardada en el teléfono (Room/SQLite).
- **Capturas.** La venta, la entrada y el cambio de precio se guardan en el teléfono con un UUID.
- **Sincronización.** Al pulsar «Sincronizar», se manda todo en un lote a ms-sincronizacion, que lo
  aplica en el servicio dueño en el orden en que se capturó. Si el lote se reenvía, el UUID evita que
  algo se aplique dos veces.
- **Conflictos de precio.** El cambio de precio lleva `version_base`, la fecha del dato que vio el
  teléfono. Si el servidor lo cambió después, la operación queda como *conflicto* para que el usuario
  la revise.
- **RN-005.** Una captura con más de 48 horas ya no se envía y queda marcada para revisión.

### Seguridad

- Solo HTTPS (`cleartextTrafficPermitted="false"`).
- La app confía en las autoridades del sistema y en el certificado del gateway del proyecto, que el
  build copia de `infra/certs/abastored.crt`. No acepta cualquier certificado.
- Los tokens se guardan cifrados (AES-GCM con una llave del Android Keystore, que no sale del
  teléfono). Si no se pueden renovar, la sesión se cierra.
- **Dispositivo registrado.** Al iniciar sesión, la app registra el teléfono en ms-notificaciones con un
  token aleatorio de 256 bits. El servidor solo muestra sus últimos 8 caracteres. Desde el web
  (Notificaciones > Dispositivos) el usuario puede revocarlo: la próxima vez que se abra, la app lo
  detecta y cierra la sesión. Al cerrar sesión, la app lo da de baja.

## Compilar y probar

Requisitos:
- Android Studio, o su JDK (`jbr`) más el Android SDK 36.
- El sistema levantado al menos una vez, para que exista el certificado en `infra/certs/`.

```bash
cd apps/movil
./gradlew assembleDebug testDebugUnitTest
```

El APK queda en `app/build/outputs/apk/debug/app-debug.apk`.

### En el emulador

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb reverse tcp:8443 tcp:443
```

Con `adb reverse`, `https://localhost:8443` dentro del emulador llega al gateway de la computadora, y el
nombre coincide con el del certificado. Para otra dirección, compila con
`./gradlew assembleDebug -PgatewayUrl=https://<host>`. El certificado debe incluir ese nombre.

### Contra el despliegue en Google Cloud (APK de release firmado)

```bash
./gradlew assembleRelease -PgatewayUrl=https://34.135.84.31     -PcertificadoGateway=../../apps/infra/gcp/certificado_gateway_gcp.crt
```

El APK firmado queda en `app/build/outputs/apk/release/app-release.apk`. La firma usa la llave del
equipo, que **no está en git**: `firma/abastored.jks` y `firma/firma.properties` (con `storePassword`,
`keyAlias` y `keyPassword`). Para crear una nueva:

```bash
keytool -genkeypair -v -keystore firma/abastored.jks -alias abastored -keyalg RSA -keysize 3072 -validity 10000
```

Sin esos archivos, el APK de release sale sin firmar. Comprobar la firma:
`apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk`.
El recorrido completo contra GCP está en `docs/evidencias/movil_gcp/`.

Usuarios de prueba: `comerciante@test.mx` o `minorista@test.mx`, con la contraseña `Password123!`.

## Cómo está hecha

```
app/src/main/java/mx/abastored/movil/
├── datos/
│   ├── ClienteApi.kt     # OkHttp + kotlinx.serialization; JWT, renovación, X-Correlation-ID, errores
│   ├── Modelos.kt        # contratos JSON que usa la app
│   ├── Repositorio.kt    # en línea o a la cola sin conexión; sincronización por lotes
│   ├── Sesion.kt         # tokens (cifrados) y token del dispositivo en DataStore
│   ├── Cifrado.kt        # AES-GCM con llave del Android Keystore
│   ├── AvisosWorker.kt   # avisos en segundo plano (WorkManager)
│   └── local/BaseLocal.kt  # Room: operaciones pendientes y copia del inventario
└── ui/                   # Compose: inicio de sesión, inventario, abasto, pedidos, avisos, perfil, pendientes
```

`app/src/test/.../ClienteApiTest.kt` prueba el cliente contra un servidor simulado (MockWebServer):

- la ruta por el gateway y el token;
- la renovación del token tras un 401;
- el cierre de sesión si no se puede renovar;
- los mensajes de error del contrato;
- la detección de «sin conexión».
