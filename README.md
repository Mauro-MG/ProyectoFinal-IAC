# AbastoRed (Plataforma Híbrida para Comercio Formal e Informal)

Plataforma integral para la gestión y conexión entre comerciantes formales, informales y proveedores, facilitando el abasto, monitoreo de precios y logística.

## Alcance del Primer Parcial

Durante el primer parcial, AbastoRed se presenta como un producto mínimo funcional **cloud-enabled**. La versión actual incluye:

*   Aplicación web modular desarrollada con Flask.
*   Página pública, registro, inicio y cierre de sesión.
*   Autenticación mediante sesión web y JWT básico.
*   Roles y menús por perfil.
*   Catálogos funcionales de productos y comercios.
*   Registro y comparación de precios.
*   Persistencia real en PostgreSQL.
*   Auditoría básica.
*   Caché de precios y revocación de JWT mediante Redis.
*   Configuración inicial de MongoDB.
*   Ejecución local mediante Docker Compose.

Los microservicios, la aplicación móvil, la aplicación de escritorio, el monitoreo centralizado y la integración funcional completa con MongoDB se encuentran analizados y diseñados para etapas posteriores.

La versión actual se considera **cloud-enabled** porque puede desplegarse en infraestructura de nube mediante contenedores. La arquitectura objetivo evolucionará hacia un enfoque **cloud-native** utilizando microservicios, servicios administrados, monitoreo centralizado y posible orquestación mediante GKE.

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

- **Administrador General:** `admin@abastored.mx` — contraseña: `Admin123!`
- **Comerciante Informal:** `comerciante@test.mx` — contraseña: `Password123!`
- **Minorista Formal:** `minorista@test.mx` — contraseña: `Password123!`
- **Analista de Mercado:** `analista@test.mx` — contraseña: `Password123!`
- **Proveedor:** `proveedor@test.mx` — contraseña: `Password123!`
- **Coordinador Municipal:** `coordinador@test.mx` — contraseña: `Password123!`
- **Auditor:** `auditor@test.mx` — contraseña: `Password123!`

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
    └── ...                # Código fuente 
```

## Documentación

La carpeta `docs/` contiene:

*   `analisis_problema.md`: contexto, usuarios, procesos, riesgos y beneficios.
*   `matriz_perfiles_permisos.md`: actores, responsabilidades y autorizaciones.
*   `requerimientos.md`: requerimientos funcionales y no funcionales.
*   `historias_usuario.md`: historias y criterios de aceptación.
*   `reglas_negocio.md`: reglas aplicables a los procesos.
*   `casos_uso.md`: casos de uso principales.
*   `matriz_trazabilidad.md`: relación entre requerimientos, historias, reglas y pruebas.
*   `arquitectura.md`: diagramas y distribución de responsabilidades.
*   `diseno_datos.md`: diseño de PostgreSQL, MongoDB y Redis.
*   `casos_prueba.md`: validaciones actuales y pruebas futuras.
*   `gestion_proyecto.md`: ramas, tablero, incidencias y convenciones.
*   `plan_trabajo_semestre.md`: distribución del trabajo por parcial.
*   `prototipos_interfaces.md`: descripción de las interfaces.

## Development Guidelines

- **Nomenclatura:** Utilizar `snake_case` para variables y funciones en Python, `PascalCase` para Clases. En base de datos usar `snake_case` para tablas y columnas.
- **Idioma:** Comentarios, documentación y textos de cara al usuario deben estar en **Español**. Los identificadores en el código (nombres de variables, funciones, clases) pueden estar en **Inglés** por convención.
- **Formato:** Seguir las convenciones de PEP 8 para código Python.

## Branch Strategy

- `main`: Código estable de producción.
- `develop`: Rama de integración principal para desarrollo.
- `feature/*`: Para nuevas funcionalidades (ej. `feature/modulo-pagos`).
- `hotfix/*`: Para correcciones críticas en producción.

## Estado de Implementación

| Componente | Estado en el primer parcial |
| :--- | :--- |
| Aplicación web Flask | Implementado |
| PostgreSQL/PostGIS | Implementado |
| Redis | Implementación inicial |
| MongoDB | Inicialización y diseño; integración funcional futura |
| Docker Compose | Configuración inicial disponible |
| Microservicios | Diseñados para etapas posteriores |
| Aplicación móvil | Diseñada para etapas posteriores |
| Aplicación de escritorio | Diseñada para etapas posteriores |
| Compute Engine | Despliegue futuro |
| GKE | Uso futuro si el volumen lo justifica |
| Monitoreo centralizado | Diseñado para etapas posteriores |
| Pruebas automatizadas | Planeadas para etapas posteriores |
