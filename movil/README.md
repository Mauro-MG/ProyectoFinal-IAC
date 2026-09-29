# Aplicación móvil Android

**Estado:** diseñada, se implementa en el tercer parcial.

Aplicación en Kotlin para pequeños comerciantes. Consume **únicamente JSON** de los microservicios;
no se conecta a PostgreSQL, MongoDB ni Redis y no comparte la sesión del sistema web.

## Funciones previstas

- Inicio de sesión con JWT y renovación segura del token.
- Registro simplificado del comercio (con geolocalización del teléfono).
- Alta de productos desde el catálogo maestro, lectura de código de barras y foto del producto.
- Actualización rápida de precio y registro de ventas/entradas.
- Solicitud de abasto a proveedores y seguimiento del pedido.
- Consulta de recomendaciones y proveedores.
- Trabajo sin conexión con Room (SQLite) y sincronización diferida por lotes (RN-005: se descartan
  capturas de más de 48 horas).

Los endpoints que usará ya tienen equivalente en el monolito (`/api/inventario`,
`/api/disponibilidad`, `/api/auth/token`) y se moverán a los microservicios.
