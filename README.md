# AbastoRed — Plataforma híbrida para comercio formal e informal

**Proyecto 14 · Equipo 01 · Integración de Aplicaciones · Universidad de Monterrey**

| Integrante | Matrícula |
| :--- | :--- |
| José Humberto Moreno | 596055 |
| David López | 600390 |
| Mauro Montelongo | 595821 |
| Humberto Vargas | 604775 |

AbastoRed integra tianguis, puestos de mercado, tiendas de barrio y proveedores mayoristas del área
metropolitana de Monterrey. El comerciante lleva su inventario, ve qué se le está acabando, compara
precios de mayoreo y hace su pedido de abasto; el proveedor recibe y atiende pedidos; el municipio
y los analistas ven la cobertura por zona, las brechas de surtido y el índice de acceso a la
canasta básica.

La documentación completa (análisis, requerimientos, arquitectura, datos, fichas de los
microservicios, contratos, pruebas y plan) está en **`docs/AbastoRed_Equipo01_Documento_Tecnico.docx`**.

## Estructura del repositorio (monorepo)

```
.
├── apps/
│   ├── web/              Sistema web empresarial (Flask, sin blueprints)     ← avance 1, ampliado en el 2
│   ├── microservicios/   24 servicios Flask, uno por contenedor (8101–8124)   ← avance 2 y entrega final
│   ├── movil/            App Android (Kotlin), sólo JSON                       ← avance 3
│   ├── escritorio/       App PySide6, sólo XML                                 ← avance 3
│   └── infra/            Despliegue en Google Cloud                            ← avance 4
├── libs/
│   ├── abasto_dominio/   Modelos y reglas de negocio (los usan el web y los servicios)
│   └── abasto_api/       Base común de los servicios: rutas, JWT, JSON/XML, XSD, errores, Swagger
├── db/                   postgres/ (esquema y datos), mongo/init.js, redis/redis.conf
├── tests/
│   ├── unitarias/        sin Docker (fakeredis)
│   ├── integracion/      contra el sistema levantado
│   └── evidencias/       generar.py: 5 casos por endpoint, reporte HTML y colección Postman
├── docs/                 documento técnico, diagramas, evidencias/, postman/
└── docker-compose.yml
```

## Cómo levantarlo

Requisitos: Docker y Docker Compose (y Python 3.11+ sólo para generar los secretos).

```bash
python scripts/preparar_entorno.py   # una vez: crea .env y los secretos aleatorios en secrets/
docker compose up -d --build
docker compose ps                    # los 29 contenedores deben quedar "healthy"
```

El sistema tiene **una sola entrada**: el gateway HTTPS (nginx). Ningún otro contenedor publica puertos;
las bases de datos están en una red interna de Docker sin acceso desde fuera.

| Componente | Dirección |
| :--- | :--- |
| Sistema web | https://localhost/ |
| Swagger de cada microservicio | https://localhost/ms/seguridad/docs · …/ms/ventas/docs · etc. (los 24 en `apps/microservicios/README.md`) |
| API de un microservicio | https://localhost/ms/<servicio>/api/v1/… |

El certificado es autofirmado y se genera al primer arranque en `infra/certs/` (fuera de git). Para que el
navegador no muestre la advertencia, se puede confiar en él una vez (Windows, sin permisos de administrador):

```bash
certutil -user -addstore Root infra\certs\abastored.crt
```

| Archivo | Para qué |
| :--- | :--- |
| `.env` | Configuración sin secretos (copia de `.env.example`). `ENTORNO=produccion` hace que el arranque falle si falta un secreto o es de ejemplo. |
| `secrets/*.txt` | Contraseñas y llaves; Docker las monta en `/run/secrets` sólo en los contenedores que las usan. Nunca van a git. |
| `docker-compose.dev.yml` | Sólo desarrollo: publica web, servicios y bases en `127.0.0.1` (`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`). |

Cada servicio publica `/health`, `/openapi.json`, `/docs` (Swagger) y `/xsd` (contrato XML). Qué servicio es
dueño de cada tabla y cómo se coordinan las operaciones que cruzan servicios: `docs/propiedad_de_datos.md`.
Para detener: `docker compose stop` (conserva datos) o `docker compose down -v` (borra los volúmenes
y vuelve a cargar los scripts de `db/`).

## Pruebas y evidencias

Dos formas de correr **todas** las pruebas, con el sistema levantado:

```bash
docker compose --profile pruebas run --rm pruebas   # sin instalar nada: corre dentro de un contenedor
python scripts/ejecutar_pruebas.py                  # en el equipo: crea .venv e instala lo necesario
```

Ambas generan un reporte con fecha, ambiente (sistema, versiones, commit, estado de los contenedores), comando y el
resultado de cada prueba clasificado como **aprobada, fallida, error, omitida** (faltó algo del ambiente) o
**no aplica** (no tiene sentido en ese ambiente; p. ej. las que detienen contenedores no aplican dentro de un
contenedor). La última corrida completa queda en `docs/pruebas/` (`reporte.html`, `resultados.json`, `junit.xml`,
`salida.txt`); `--solo unitarias` corre sólo las que no necesitan Docker.

```bash
python tests/evidencias/generar.py   # 5 casos por endpoint: docs/evidencias/ y la colección de Postman
```

- El reporte de evidencias marca cada caso como **aprobado** (obtuvo el código HTTP esperado), **fallido**,
  **omitido** o **no aplica** con su motivo (p. ej. una operación pública no tiene caso de acceso no autorizado).
- `tests/integracion/test_proceso_abasto.py` recorre el proceso de abasto completo pasando sólo por los
  microservicios (stock bajo → aviso → pedido en XML → proveedor → recepción → inventario → historial).
- `tests/integracion/test_servicios_nuevos.py` prueba los flujos que cruzan servicios de la entrega final: venta con
  saga sobre el inventario y su traza en ms-auditoria, lote offline con duplicados y conflicto, entrega con QR,
  cotización consolidada hasta pedido, documentos con validación del tipo real, búsqueda y demanda, reportes e
  importación con errores por fila.
- La colección de Postman (`docs/postman/AbastoRed_Avance2.postman_collection.json`) se ejecuta empezando
  por la carpeta «00 · Sesiones». Como el certificado es autofirmado, en Postman se agrega
  `infra/certs/abastored.crt` en *Settings → Certificates → CA certificates*.

## Usuarios de prueba

Contraseña `Password123!` (administrador: `Admin123!`).

| Perfil | Correo | Qué revisar |
| :--- | :--- | :--- |
| Administrador General | `admin@abastored.mx` | Usuarios, roles, sesiones abiertas, estado de los servicios |
| Comerciante Informal | `comerciante@test.mx` | Inventario del puesto 7 del tianguis Los Nogales, fotos del comercio |
| Minorista Formal | `minorista@test.mx` | Tres tiendas, importación de inventario por CSV |
| Proveedor | `proveedor@test.mx` | Distribuidora Regia (plan Destacado), equipo de operadores |
| Operador de Proveedor | `operador@test.mx` | Atiende los pedidos de la Distribuidora Regia |
| Proveedor | `proveedor3@test.mx` | Bodega 14 del Mercado de Abastos (plan Básico) |
| Analista de Mercado | `analista@test.mx` | Comparación de precios, cobertura, brechas, desempeño de proveedores |
| Coordinador Municipal | `coordinador@test.mx` | Validación de comercios, revisión de precios atípicos |
| Auditor | `auditor@test.mx` | Bitácora e historial de pedidos |

## Escenario de demostración

1. **Registro.** En `/registro` crear una cuenta de *Comerciante informal*.
2. **Comercio.** Registrar el comercio con ubicación dentro de García Norte
   (por ejemplo `25.8210, -100.5890`); la zona se asigna sola y queda *pendiente*. Subir la foto de la fachada.
3. **Catálogo del comercio.** Elegir del catálogo maestro los productos que vende.
4. **Existencias** y 5. **precios** en la misma pantalla (con mínimo y máximo).
6. **Disponibilidad pública.** Entrar como `coordinador@test.mx`, validar el comercio y consultar
   `/disponibilidad` sin sesión.
7. **Bajo inventario.** Registrar una venta que deje un producto bajo el mínimo: llega un aviso a la campana.
8. **Precios de proveedores.** *Comparar proveedores* muestra precio de mayoreo, venta mínima,
   existencia, pedido mínimo y tiempo de entrega.
9. **Brechas** (`analista@test.mx` → *Brechas de surtido*, zona García Norte) y
   10. **recomendaciones** (comerciante → *Recomendaciones*).
11. **Pedido.** Agregar productos y *Confirmar y enviar* (valida el pedido mínimo).
12. **El proveedor recibe** el aviso y 13. **acepta o rechaza** (también lo puede hacer su operador).
14. **Actualiza el estado:** en preparación → enviado.
15. **Recepción** por el comerciante y 16. **entrada automática al inventario**.
17. **Auditoría** (`auditor@test.mx`) y **rastreo** (`admin@abastored.mx` → *Estado de los servicios*).

## Convenciones

- Python PEP 8; `snake_case` en funciones, variables, tablas y columnas; `PascalCase` en clases.
- Identificadores y textos en español, igual que el dominio del negocio.
- Web: rutas agrupadas por proceso en `apps/web/app/rutas/`; nombre del endpoint = nombre de la función.
- Servicios: una ruta = `@srv.ruta(...)` con permisos, modelo de entrada y elemento raíz XML; los XSD se
  regeneran con `python -m abasto_api.contratos apps/microservicios/<servicio>`.
- Toda operación que cambia datos registra un evento de auditoría en la misma transacción.
- Bajas lógicas (`activo = false`); los registros de auditoría son inmutables.
- Claves de Redis con prefijo de dominio y TTL explícito (`sesion:*`, `jwt:revocado:*`, `rate:*`,
  `analisis:v*`, `bloqueo:*`, `notif:no_leidas:*`); la lista completa está en el documento técnico.

## Ramas

- `main`: lo que se entrega.
- `develop`: integración.
- `feature/<componente>-<descripcion>`: por ejemplo `feature/web-pedidos`, `feature/microservicios`.
- `hotfix/<descripcion>`: correcciones sobre `main`.

Cada *pull request* hacia `develop` requiere que las pruebas pasen y la revisión de otro integrante.
