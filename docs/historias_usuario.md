# Historias de Usuario

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal (AbastoRed - EQUIPO 01)

### Épica 1: Gestión de Precios e Inventario

**HU-001: Actualización Rápida de Precios (Informal)**
*   **Como** Comerciante Informal,
*   **Quiero** actualizar el precio de mis productos principales con pocos clics en mi móvil,
*   **Para** mantener informados a mis clientes y reflejar variaciones del mercado sin perder tiempo en la venta.
*   **Criterios de Aceptación:**
    *   *Dado* que el comerciante abre la app y selecciona la sección "Mis Precios",
    *   *Cuando* ingresa un nuevo valor numérico y presiona "Guardar",
    *   *Entonces* el sistema actualiza el registro localmente, y si hay conexión, lo sincroniza con el servidor.

**HU-002: Publicación de Inventario (Formal)**
*   **Como** Minorista Formal,
*   **Quiero** enlazar mi sistema de punto de venta (o cargar un CSV) a la plataforma,
*   **Para** que mis niveles de stock y precios se actualicen automáticamente.
*   **Criterios de Aceptación:**
    *   *Dado* que el minorista se encuentra en la sección de Inventario Web,
    *   *Cuando* sube un archivo CSV con formato válido,
    *   *Entonces* el MS de Inventario procesa las filas, actualiza PostgreSQL y actualiza la caché de Redis.

### Épica 2: Pedidos y Abastecimiento

**HU-003: Solicitud de Pedido a Mayorista**
*   **Como** Minorista Formal,
*   **Quiero** generar un pedido seleccionando productos del catálogo de un mayorista,
*   **Para** reabastecer mi tienda sin tener que trasladarme a la central de abastos.
*   **Criterios de Aceptación:**
    *   *Dado* que el carrito de compras tiene al menos un producto válido,
    *   *Cuando* se confirma el pedido,
    *   *Entonces* el sistema genera un ID de Orden, reserva el inventario y envía una notificación al Mayorista.

**HU-004: Gestión de Entregas**
*   **Como** Proveedor/Mayorista,
*   **Quiero** cambiar el estado de un pedido a "En camino" o "Entregado",
*   **Para** que el comprador conozca el estatus de su mercancía.
*   **Criterios de Aceptación:**
    *   *Dado* que el pedido está en estado "Aprobado",
    *   *Cuando* el Mayorista cambia el estado a "En camino",
    *   *Entonces* se notifica al Comerciante (push) y se registra el timestamp en la bitácora.

### Épica 3: Análisis y Geografía

**HU-005: Visualización de Desiertos Alimentarios**
*   **Como** Analista de Mercado,
*   **Quiero** visualizar un mapa de calor con el Índice de Acceso Alimentario,
*   **Para** identificar zonas críticas que requieren programas de abasto.
*   **Criterios de Aceptación:**
    *   *Dado* que el analista accede al Dashboard Geográfico,
    *   *Cuando* selecciona el filtro "Índice de Acceso",
    *   *Entonces* el mapa renderiza capas de colores basadas en cálculos geoespaciales desde el MS de Acceso Alimentario.

**HU-006: Delimitación de Tianguis**
*   **Como** Coordinador Municipal,
*   **Quiero** dibujar un polígono en un mapa interactivo para definir un nuevo mercado rodante,
*   **Para** validar que los comerciantes informales se registren solo en zonas permitidas.
*   **Criterios de Aceptación:**
    *   *Dado* que el coordinador usa la herramienta de dibujo poligonal,
    *   *Cuando* cierra el polígono y le asigna un nombre y días de operación,
    *   *Entonces* el polígono se guarda como geometría (GeoJSON/PostGIS) y queda activo.

**HU-007: Detección de Dispersión de Precios**
*   **Como** Analista de Mercado,
*   **Quiero** ver una gráfica de dispersión de precios del "Limón Persa" comparando el sector formal vs informal,
*   **Para** medir la competitividad en tiempo real.
*   **Criterios de Aceptación:**
    *   *Dado* que se selecciona un producto y rango de fechas,
    *   *Cuando* se ejecuta la consulta,
    *   *Entonces* se agrupan los datos por sector y se muestra la varianza y la media de los precios.

### Épica 4: Auditoría y Alertas

**HU-008: Alerta de Incremento Abrupto de Precio**
*   **Como** Administrador General,
*   **Quiero** recibir una alerta si un producto básico sube más de un 20% en menos de una semana en una zona,
*   **Para** investigar posibles casos de especulación.
*   **Criterios de Aceptación:**
    *   *Dado* que un usuario reporta un precio,
    *   *Cuando* el MS de Precios detecta que supera el umbral estadístico,
    *   *Entonces* se genera un evento de Alerta y se envía un correo a los Administradores.
