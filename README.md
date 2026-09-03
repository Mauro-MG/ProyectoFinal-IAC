# AbastoRed (Plataforma Híbrida para Comercio Formal e Informal)

Plataforma integral para la gestión y conexión entre comerciantes formales, informales y proveedores, facilitando el abasto, monitoreo de precios y logística.

## Tech Stack

- **Backend:** Python 3.11, Flask, Gunicorn
- **Bases de Datos:** 
  - PostgreSQL 16 + PostGIS (Datos relacionales, usuarios, comercios, catálogo, pedidos y geometrías)
  - MongoDB 7.0 (Datos no estructurados, telemetría, snapshots de precios)
  - Redis 7.2 (Caché, manejo de sesiones, colas)
- **Infraestructura:** Docker, Docker Compose

## Prerequisites

- Docker
- Docker Compose

## Quick Start

1. Clonar el repositorio.
2. Crear archivo `.env` a partir de `.env.example`:
   ```bash
   cp .env.example .env
   ```
3. Construir y levantar los contenedores:
   ```bash
   docker compose up --build
   ```

El sistema estará disponible en `http://localhost:5000`.

Verificación básica:

```bash
curl http://localhost:5000/health
```

## Demo técnica sugerida

1. Iniciar sesión como `admin@abastored.mx`.
2. Revisar el panel principal y el menú por perfil.
3. Crear, editar y desactivar un producto desde `Productos`.
4. Crear, editar y desactivar un comercio desde `Comercios`.
5. Registrar un precio desde `Precios > Registrar Precio`.
6. Consultar la comparación de precios por producto, zona y sector.
7. Revisar el registro en `Auditoría`.
8. Solicitar un JWT para API:
   ```bash
   curl -X POST http://localhost:5000/api/auth/token \
     -H "Content-Type: application/json" \
     -d "{\"email\":\"admin@abastored.mx\",\"password\":\"Admin123!\"}"
   ```
9. Consultar un endpoint protegido con `Authorization: Bearer <token>`:
   ```bash
   curl http://localhost:5000/api/precios/resumen \
     -H "Authorization: Bearer <token>"
   ```

## Default Credentials

La base de datos se inicializa con los siguientes usuarios de prueba (la contraseña para todos es `Password123!`, excepto para el admin que es `Admin123!`):

- **Administrador:** admin@abastored.mx
- **Comerciante:** comerciante@test.mx
- **Minorista:** minorista@test.mx
- **Analista:** analista@test.mx

## Project Structure

```
abasto_red/
├── docker-compose.yml     # Orquestación de servicios
├── .env.example           # Variables de entorno
├── .gitignore
├── .dockerignore
├── README.md              # Documentación
├── db/
│   ├── postgres/          # Scripts SQL (Esquema y Datos Semilla)
│   ├── mongo/             # Scripts de inicialización MongoDB
│   └── redis/             # Configuración de Redis
└── web/                   # Aplicación Flask
    ├── Dockerfile         # Dockerfile de la aplicación
    ├── requirements.txt   # Dependencias de Python
    └── ...                # Código fuente (app.py, modelos, rutas, etc.)
```

## Development Guidelines

- **Nomenclatura:** Utilizar `snake_case` para variables y funciones en Python, `PascalCase` para Clases. En base de datos usar `snake_case` para tablas y columnas.
- **Idioma:** Comentarios, documentación y textos de cara al usuario deben estar en **Español**. Los identificadores en el código (nombres de variables, funciones, clases) pueden estar en **Inglés** por convención.
- **Formato:** Seguir las convenciones de PEP 8 para código Python.

## Branch Strategy

- `main`: Código estable de producción.
- `develop`: Rama de integración principal para desarrollo.
- `feature/*`: Para nuevas funcionalidades (ej. `feature/modulo-pagos`).
- `hotfix/*`: Para correcciones críticas en producción.
