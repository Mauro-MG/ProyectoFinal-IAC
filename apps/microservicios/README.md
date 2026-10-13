# Microservicios

Ocho aplicaciones Flask independientes, cada una en su propio contenedor (gunicorn, puerto 8000
dentro de la red; publicado en 8101–8108). Comparten dos bibliotecas del repositorio:

- `libs/abasto_dominio`: modelos SQLAlchemy y reglas de negocio (las mismas que usa el web).
- `libs/abasto_api`: la clase `Servicio`, que da a todos el mismo comportamiento: `/api/v1`, JWT con
  sesión en Redis y permisos por ruta, validación con Pydantic, JSON o XML según `Accept` (o
  `?formato=xml`), XSD, errores estandarizados, límite de peticiones, `X-Correlation-ID`, bitácora en
  MongoDB, `/health/*`, OpenAPI 3.1 y Swagger UI.

| Servicio | Puerto | Responsabilidad |
| :--- | :--- | :--- |
| `seguridad/` | 8101 | Login, refresh, logout, usuarios, roles, sesiones, auditoría, actividad |
| `comercios/` | 8102 | Comercios, validación municipal, zonas, fotos y evidencias (GridFS) |
| `catalogo/` | 8103 | Catálogo maestro, proveedores, ofertas, catálogo mayorista |
| `inventario/` | 8104 | Existencias, movimientos, faltantes, importación CSV, disponibilidad pública |
| `precios/` | 8105 | Precio al consumidor, revisión de atípicos, comparación, snapshots |
| `pedidos/` | 8106 | Pedidos, partidas, estados, historial, desempeño de proveedores |
| `analisis/` | 8107 | Cobertura, índice de acceso, brechas, recomendaciones, evolución |
| `notificaciones/` | 8108 | Avisos internos, contador de no leídas, lote para otros servicios |

## Estructura de cada servicio

```
<servicio>/
├── app.py          # srv = Servicio(...); rutas con @srv.ruta('/...', 'GET', permisos=[...], ...)
├── esquemas.py     # modelos de entrada, consulta y salida + CONTRATOS_XML (raíz -> modelo)
├── xsd/<servicio>.xsd   # generado de esquemas.py (no se edita a mano)
└── Dockerfile      # se construye desde la raíz del repositorio (instala libs/)
```

## Tareas comunes

```bash
# Regenerar los XSD después de cambiar un esquema (hay una prueba que verifica que estén al día)
python -m abasto_api.contratos apps/microservicios/pedidos

# Reconstruir y reiniciar un servicio
docker compose up -d --build ms-pedidos

# Ver su bitácora (una línea JSON por petición)
docker compose logs -f ms-pedidos

# Token de servicio para probar POST /notificaciones/lote
docker exec ms-pedidos python -c "from app import app; from abasto_dominio.sesiones import token_servicio; app.app_context().push(); print(token_servicio('prueba', ['notificaciones.crear']))"
```

Las fichas técnicas de cada servicio (13 elementos), los contratos y las claves de Redis están en el
documento técnico (capítulos 13 a 17); la evidencia de cada endpoint en `docs/evidencias/`.
