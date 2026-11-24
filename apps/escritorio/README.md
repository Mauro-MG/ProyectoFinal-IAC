# Aplicación de escritorio

Aplicación en Python 3.12 y PySide6 para la coordinación municipal, los analistas de mercado y los
proveedores. Cumple dos reglas:

- **No se conecta a ninguna base de datos.** Todo pasa por el gateway HTTPS hacia los microservicios.
- **Solo usa XML.** Cada petición se valida contra el XSD del servicio antes de enviarse, y cada
  respuesta al llegar, incluidas las de error.

## Cómo correrla

Con el sistema levantado (`docker compose up -d` en la raíz del repositorio):

```bash
cd apps/escritorio
pip install -r requirements.txt
python -m abastored_escritorio
```

Variables opcionales:

| Variable | Valor por omisión | Uso |
| :--- | :--- | :--- |
| `ABASTORED_GATEWAY` | `https://localhost` | Dirección del gateway |
| `ABASTORED_CA` | `infra/certs/abastored.crt` | Certificado del gateway en el que se confía |
| `ABASTORED_CARPETA` | `~/AbastoRed` | Bitácora local y reportes descargados |

Usuarios de prueba: `coordinador@test.mx`, `analista@test.mx` y `proveedor@test.mx`, todos con la
contraseña `Password123!`.

## Módulos

Cada usuario ve solo los módulos que permite su rol, según los permisos de su token.

| Módulo | Quién lo ve | Servicios |
| :--- | :--- | :--- |
| Validación de comercios | coordinación (`comercios.validar`) | ms-comercios `GET /comercios`, `PATCH /comercios/{id}/validacion` |
| Verificación de proveedores | coordinación (`proveedores.verificar`) | ms-proveedores `PATCH /proveedores/{id}/verificacion` |
| Pedidos recibidos | proveedor (`pedidos.atender`) | ms-pedidos: detalle, partidas y acciones (aceptar, preparar, despachar, rechazar) |
| Precios | `precios.consultar` | ms-precios `/precios/comparacion` (formal, informal y mayoreo); revisión de precios atípicos |
| Cobertura y brechas | `analisis.ver` | ms-analisis `/analisis/brechas`; exportación a CSV registrada en ms-auditoria (`POST /eventos`) |
| Importar archivos | `integraciones.ejecutar`, `proveedor.catalogo` | ms-integraciones: plantilla, simulación e importación con errores por fila |
| Reportes | `reportes.ver`, `pedidos.atender` | ms-reportes: genera el PDF, Excel, CSV o JSON, lo descarga y lo abre |
| Mi actividad | todos | Bitácora local (SQLite); con `auditoria.ver`, la traza en ms-auditoria `GET /trazas/{id}` |

## Cómo está hecha

```
abastored_escritorio/
├── contratos.py      # lee el XSD de cada servicio: valida, convierte tipos y reconoce listas
├── cliente.py        # HTTP por el gateway: JWT, renovación con refresh token, X-Correlation-ID, errores
├── bitacora.py       # registro local de actividades (SQLite)
├── configuracion.py
└── ui/               # una pantalla por módulo; las consultas corren en segundo plano
```

- **Contratos.** No hay modelos escritos a mano. `contratos.py` descarga `GET /ms/<servicio>/xsd` y, con
  el tipo de cada elemento, sabe:
  - qué elementos son listas, aunque lleguen con un solo elemento o vacías;
  - a qué tipo se convierte cada valor (`xs:decimal` → `Decimal`, `xs:dateTime` → `datetime`, …).
- **Sesión.** Si un servicio responde 401 porque el token venció, el cliente lo renueva con
  `POST /auth/renovar` y repite la petición.
- **Folio de cada operación.** Cada petición lleva un `X-Correlation-ID` que empieza con `escritorio-`.
  La bitácora local lo guarda, y con ese folio se busca la operación en ms-auditoria.

## Pruebas

Están en la suite del proyecto (`python scripts/ejecutar_pruebas.py`):

- **`tests/unitarias/test_contratos_escritorio.py`:** la conversión guiada por el XSD (listas de un
  elemento y vacías, tipos y peticiones inválidas).
- **`tests/integracion/test_app_escritorio.py`:** pruebas contra el sistema real:
  - login en XML y errores del contrato;
  - validar un comercio;
  - generar un reporte PDF;
  - importar en simulación;
  - renovar el token vencido;
  - abrir la ventana de cada rol sin mostrarla (Qt offscreen) y comprobar que todos sus módulos cargan
    sin errores.

`python capturar.py <correo> <contraseña>` recorre los módulos de un usuario y guarda una captura de
cada uno en `capturas/`. Para correrlo sin ventanas, define `QT_QPA_PLATFORM=offscreen` y
`QT_QPA_FONTDIR=C:/Windows/Fonts`.
