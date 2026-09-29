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

**HU-008: Detección de Precio Atípico**

- **Como** Administrador General,
- **Quiero** identificar los precios que superen el 150% o sean menores al 10% del promedio regional de los últimos 7 días,
- **Para** revisar posibles errores de captura o variaciones anormales.

**Criterios de aceptación:**

- **Dado** que un usuario registra un precio,
- **Cuando** el sistema detecta que se encuentra fuera del umbral establecido,
- **Entonces** el precio se guarda como `PENDIENTE_VALIDACION` y queda disponible para revisión humana.
- **Y** en una etapa posterior, el MS de Alertas notificará a los administradores.

### Épica 5: Administración y recomendaciones
**HU-009: Administración del Catálogo Maestro**

- **Como** Administrador General,
- **Quiero** crear, consultar, editar y desactivar productos del catálogo maestro,
- **Para** mantener una referencia uniforme para precios, pedidos y análisis.

**Criterios de aceptación:**

- **Dado** que el administrador tiene una sesión válida,
- **Cuando** registra un producto con información válida,
- **Entonces** el producto se almacena en PostgreSQL.
- **Y** la creación queda registrada en la bitácora de auditoría.
- **Cuando** modifica o desactiva un producto,
- **Entonces** el cambio se guarda y también se registra en auditoría.

**HU-010: Recomendación de Surtido por Zona**

- **Como** Comerciante,
- **Quiero** recibir recomendaciones de productos con demanda no satisfecha en mi zona,
- **Para** decidir qué productos puedo incorporar a mi surtido.

**Criterios de aceptación:**

- **Dado** que el comercio reportó al menos cinco productos durante la última semana,
- **Cuando** solicita una recomendación,
- **Entonces** el futuro MS de Recomendaciones devuelve hasta cinco productos priorizados.
- **Y** la respuesta indica que se trata de una sugerencia y no de una decisión obligatoria.

**HU-011: Consulta de Auditoría**

- **Como** Auditor,
- **Quiero** consultar eventos por usuario, entidad y periodo,
- **Para** reconstruir los cambios realizados en el sistema.

**Criterios de aceptación:**

- **Dado** que el auditor tiene una sesión válida,
- **Cuando** accede al módulo de auditoría,
- **Entonces** puede consultar los eventos registrados y sus detalles.
- **Y** no dispone de operaciones para modificar o eliminar registros.
