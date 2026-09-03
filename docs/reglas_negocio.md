# Reglas de Negocio

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal (AbastoRed - EQUIPO 01)

| ID Regla | Nombre de la Regla | Descripción y Lógica | Componente(s) Afectado(s) |
| :--- | :--- | :--- | :--- |
| **RN-001** | **Umbral Máximo de Variación de Precio** | Un precio reportado no puede ser guardado directamente si excede el 150% o es menor al 10% del precio promedio regional de los últimos 7 días. Debe ser marcado como "Pendiente de Validación" para evitar ruido estadístico (fat-finger errors). | MS de Precios, Base de Datos |
| **RN-002** | **Tolerancia Geográfica para Tianguis** | El sistema permitirá hacer "check-in" a un Comerciante Informal solo si su GPS se ubica dentro del polígono registrado del tianguis, con un margen de tolerancia de **50 metros** (buffer geoespacial) para compensar imprecisión del GPS móvil. | MS Geográfico, App Móvil |
| **RN-003** | **Surtido Mínimo para Recomendaciones** | Para que el MS de Recomendaciones procese sugerencias de un comercio, dicho comercio debe haber reportado al menos **5 productos** en la última semana, para perfilar correctamente su giro. | MS de Recomendaciones |
| **RN-004** | **Montos Mínimos de Pedido a Mayoristas** | Los Proveedores/Mayoristas pueden configurar un "Monto Mínimo de Compra" (ej. $1000 MXN). El sistema debe impedir la finalización de un pedido (checkout) si el subtotal es inferior a este monto. | MS de Pedidos, Carrito de Compras |
| **RN-005** | **Restricción de Operación (Offline a Online)** | Los datos capturados en modo offline (App Móvil) solo son válidos para sincronizarse si la antigüedad del registro (timestamp local) no supera las **48 horas**. Después de este tiempo, los datos de precio se consideran obsoletos y se descartan. | App Móvil, API Gateway |
| **RN-006** | **Inmutabilidad de Registros de Auditoría** | Bajo ninguna circunstancia (ni siquiera por un Administrador General), se pueden modificar o eliminar los registros almacenados en el log del MS de Reportes/Auditoría. (Aplicación de Append-Only). | MS de Reportes, MongoDB/Log |
| **RN-007** | **Caducidad de Sesiones JWT** | Los tokens JWT para aplicaciones móviles tendrán un TTL (Time To Live) de **7 días** (para facilitar el uso), mientras que las sesiones en Web y Desktop para Analistas y Administradores expirarán a las **8 horas** de inactividad. | Auth, API Gateway |
| **RN-008** | **Fórmula de Índice de Acceso Alimentario (IAA)** | El IAA = (Densidad de Puntos de Venta de Alimentos Frescos por $KM^2$) / (Densidad Poblacional). Si IAA < Umbral Mínimo (definido por municipio), la zona se cataloga como "Desierto Alimentario" (Rojo en mapa). | MS Acceso Alimentario |
