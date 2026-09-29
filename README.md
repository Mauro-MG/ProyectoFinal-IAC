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

La documentación completa (análisis, requerimientos, arquitectura, datos, modelo de negocio y plan)
está en **`docs/AbastoRed_Equipo01_Documento_Tecnico.docx`**.

## Estructura del repositorio (monorepo)

```
.
├── web/              Sistema web empresarial (monolito Flask)              ← implementado
│   ├── app/
│   │   ├── __init__.py       crea la app y registra las rutas
│   │   ├── models/           modelos SQLAlchemy (un archivo por entidad)
│   │   ├── rutas/            vistas por proceso: inventario, pedidos, análisis...
│   │   ├── servicios/        reglas de negocio sin dependencia de Flask
│   │   ├── templates/        Jinja2
│   │   └── static/           CSS y JS propios (sin frameworks)
│   ├── tests/                prueba de integración del escenario completo
│   └── Dockerfile
├── microservicios/   12 servicios + monitoreo                             ← 2.º parcial
├── movil/            App Android (Kotlin), sólo JSON                        ← 3.er parcial
├── escritorio/       App PySide6, sólo XML                                  ← 3.er parcial
├── db/
│   ├── postgres/     01_schema.sql, 02_geo.sql (PostGIS), 03_seeds.sql
│   ├── mongo/        init.js (colecciones e índices)
│   └── redis/        redis.conf
├── infra/            despliegue en Google Cloud                            ← 4.º parcial
├── docs/             documento técnico (Word) y fuentes
└── docker-compose.yml
```

## Cómo levantarlo

Requisitos: Docker y Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

El sistema queda en `http://localhost:5000` y la verificación rápida es `curl http://localhost:5000/health`.

> Si ya habían levantado la versión del primer avance, borren el volumen de PostgreSQL para que se
> vuelvan a ejecutar los scripts de `db/postgres`: `docker compose down -v`.

### Sin Docker (desarrollo)

Con un PostgreSQL local (PostGIS es opcional; sin él se omite `02_geo.sql`):

```bash
psql -U abastored_admin -d abastored -f db/postgres/01_schema.sql
psql -U abastored_admin -d abastored -f db/postgres/03_seeds.sql
cd web
pip install -r requirements-dev.txt
POSTGRES_HOST=localhost python run.py
```

Redis y MongoDB son opcionales en desarrollo: si no responden, la caché de análisis y las
notificaciones se desactivan y el sistema sigue funcionando (la API JWT sí exige Redis).

### Pruebas

```bash
cd web
pytest -v
```

`tests/test_escenario_abasto.py` recorre el escenario completo de la sección siguiente contra la
base de datos configurada, además de reglas de pedido mínimo, existencia negativa y permisos.

## Usuarios de prueba

Contraseña `Password123!` (administrador: `Admin123!`).

| Perfil | Correo | Qué revisar |
| :--- | :--- | :--- |
| Administrador General | `admin@abastored.mx` | Usuarios, roles y permisos, parámetros, catálogos, comisiones |
| Comerciante Informal | `comerciante@test.mx` | Inventario del puesto 7 del tianguis Los Nogales (García Norte) |
| Minorista Formal | `minorista@test.mx` | Tres tiendas, pedidos entregados |
| Proveedor | `proveedor@test.mx` | Distribuidora Regia (plan Destacado), pedido por aceptar |
| Proveedor | `proveedor3@test.mx` | Bodega 14 del Mercado de Abastos (frutas y verduras) |
| Analista de Mercado | `analista@test.mx` | Comparación de precios, cobertura, brechas, reportes |
| Coordinador Municipal | `coordinador@test.mx` | Validación de comercios, cobertura por zona |
| Auditor | `auditor@test.mx` | Bitácora e historial de pedidos |

## Escenario de demostración

1. **Registro.** En `/registro` crear una cuenta de *Comerciante informal*.
2. **Comercio.** Registrar el comercio con ubicación dentro de García Norte
   (por ejemplo `25.8210, -100.5890`); la zona se asigna sola y queda *pendiente*.
3. **Catálogo del comercio.** Elegir del catálogo maestro los productos que vende.
4. **Existencias** y 5. **precios** en la misma pantalla (con mínimo y máximo).
6. **Disponibilidad pública.** Entrar como `coordinador@test.mx`, validar el comercio y consultar
   `/disponibilidad` sin sesión.
7. **Bajo inventario.** Con el comerciante, *Inventario → Por surtir*.
8. **Precios de proveedores.** *Comparar proveedores* muestra precio de mayoreo, venta mínima,
   existencia, pedido mínimo y tiempo de entrega.
9. **Brechas** (`analista@test.mx` → *Brechas de surtido*, zona García Norte) y
   10. **recomendaciones** (comerciante → *Recomendaciones*).
11. **Pedido.** Agregar productos y *Confirmar y enviar* (valida el pedido mínimo).
12. **El proveedor recibe** (`proveedor3@test.mx` → *Pedidos recibidos*) y 13. **acepta o rechaza**.
14. **Actualiza el estado:** en preparación → enviado.
15. **Recepción** por el comerciante y 16. **entrada automática al inventario**.
17. **Auditoría** (`auditor@test.mx`): cada cambio de estado con usuario, fecha e IP.

## Convenciones

- Python PEP 8; `snake_case` en funciones, variables, tablas y columnas; `PascalCase` en clases.
- Identificadores y textos en español, igual que el dominio del negocio.
- Rutas agrupadas por proceso en `web/app/rutas/`; nombre del endpoint = nombre de la función.
- Toda operación que cambia datos registra un evento de auditoría en la misma transacción.
- Bajas lógicas (`activo = false`); los registros de auditoría son inmutables.
- Claves de Redis con prefijo de dominio y TTL explícito (`jwt:blacklist:*`, `analisis:*`,
  `precio_promedio:*`, `recuperacion:*`).

## Ramas

- `main`: lo que se entrega.
- `develop`: integración.
- `feature/<componente>-<descripcion>`: por ejemplo `feature/web-pedidos`, `feature/ms-precios`.
- `hotfix/<descripcion>`: correcciones sobre `main`.

Cada *pull request* hacia `develop` requiere que `pytest` pase y la revisión de otro integrante.
