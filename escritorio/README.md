# Aplicación de escritorio

**Estado:** diseñada, se implementa en el tercer parcial.

Aplicación en Python con PySide6 para analistas, proveedores y coordinadores municipales.
Consume **únicamente XML** producido por los microservicios y valida cada respuesta contra
su esquema XSD.

## Funciones previstas

- Autenticación con JWT y validación de sesión en Redis (a través del microservicio).
- Administración de catálogos y validación de comercios.
- Comparación de precios y análisis de cobertura.
- Ejecución de recomendaciones y configuración de zonas.
- Importación de datos (CSV de precios o inventarios).
- Reportes, exportación de oportunidades de abasto e impresión.
- Registro local de actividades.
