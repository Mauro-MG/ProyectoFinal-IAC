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
│   ├── microservicios/   8 servicios Flask, uno por contenedor                ← avance 2
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

Requisitos: Docker y Docker Compose.

```bash
cp .env.example .env          # en Windows: copy .env.example .env
docker compose up -d --build
docker compose ps             # los 12 contenedores deben quedar "healthy"
```

| Componente | Dirección |
| :--- | :--- |
| Sistema web | http://localhost:5000 |
| ms-seguridad · comercios · catalogo · inventario | http://localhost:8101/docs · 8102 · 8103 · 8104 |
| ms-precios · pedidos · analisis · notificaciones | http://localhost:8105/docs · 8106 · 8107 · 8108 |
| PostgreSQL · MongoDB · Redis | 5432 · 27017 · 6379 |

Cada servicio publica `/health`, `/openapi.json`, `/docs` (Swagger) y `/xsd` (contrato XML).
Para detener: `docker compose stop` (conserva datos) o `docker compose down -v` (borra los volúmenes
y vuelve a cargar los scripts de `db/`).

Después de cambiar algo en `libs/` hay que reconstruir los servicios (`docker compose up -d --build`),
porque sus imágenes copian las bibliotecas; el web monta `apps/web` y `libs` como volumen.

## Pruebas y evidencias

```bash
python -m venv .venv
.venv\Scripts\activate                       # Linux/macOS: source .venv/bin/activate
pip install -e libs/abasto_dominio -e libs/abasto_api -r tests/requirements.txt

pytest tests/unitarias -v                    # no necesita Docker
pytest tests/integracion -v                  # con el sistema levantado
python tests/evidencias/generar.py           # docs/evidencias/*.html y docs/postman/*.json
```

- `tests/integracion/test_proceso_abasto.py` recorre el proceso de abasto completo pasando sólo por los
  microservicios (stock bajo → aviso → pedido en XML → proveedor → recepción → inventario → historial).
- `tests/integracion/test_resiliencia.py` detiene contenedores con el CLI de Docker.
- La colección de Postman (`docs/postman/AbastoRed_Avance2.postman_collection.json`) se ejecuta empezando
  por la carpeta «00 · Sesiones», que guarda los tokens en variables.
- La prueba original del web sigue en `apps/web/tests` (`docker exec abastored-web python -m pytest tests`
  después de `pip install pytest` en el contenedor).

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
