# Análisis del Problema de Negocio

## Proyecto 14: Plataforma Híbrida para Comercio Formal e Informal (AbastoRed - EQUIPO 01)

### 1. Contexto y Antecedentes
En México y gran parte de América Latina, el abastecimiento de alimentos y bienes básicos se realiza a través de un ecosistema mixto donde coexisten el comercio formal (tiendas de abarrotes, minisúpers, supermercados) y el comercio informal (tianguis, mercados sobre ruedas, puestos semifijos, vendedores ambulantes). Este ecosistema presenta grandes asimetrías de información, problemas de logística y volatilidad de precios. Adicionalmente, existen "desiertos alimentarios" en zonas urbanas marginadas y periurbanas, donde el acceso a productos frescos y a precios razonables es limitado. El comercio informal, aunque fundamental para el abasto popular, opera desconectado de sistemas de información centralizados, lo que dificulta su integración en cadenas de suministro eficientes y limita su crecimiento.

### 2. Organizaciones Involucradas
*   **Municipios / Ayuntamientos**: Responsables de la regulación, asignación de espacios públicos y ordenamiento territorial de tianguis y mercados.
*   **PROFECO (Procuraduría Federal del Consumidor)**: Entidad gubernamental interesada en monitorear la evolución de precios y evitar abusos.
*   **Mercados Públicos y Centrales de Abastos**: Centros logísticos de acopio y distribución mayorista que abastecen a la mayoría de los comerciantes minoristas, formales e informales.
*   **Asociaciones de Comerciantes y Uniones de Tianguistas**: Agrupaciones que organizan a los vendedores informales y negocian con autoridades.

### 3. Usuarios Principales y Puntos de Dolor (Pain Points)
*   **Comerciante Informal**: 
    *   *Puntos de dolor*: Dificultad para comparar precios de mayoristas sin trasladarse; falta de historial crediticio o formalidad que le impide acceder a mejores condiciones comerciales; merma de productos perecederos por sobreestimación de demanda.
*   **Minorista Formal (Tienda de Abarrotes)**:
    *   *Puntos de dolor*: Competencia de precios con cadenas de conveniencia y tianguis; altos costos operativos para mantener inventarios óptimos; fallas en la cadena de suministro por retrasos de proveedores.
*   **Proveedor/Mayorista**:
    *   *Puntos de dolor*: Dificultad para llegar a comerciantes informales de forma eficiente; costos de logística elevados al entregar en zonas de difícil acceso o tianguis itinerantes; falta de predictibilidad en la demanda.
*   **Coordinador Municipal**:
    *   *Puntos de dolor*: Falta de datos fiables sobre la ubicación exacta y el giro de los puestos informales; dificultad para validar permisos en campo.
*   **Analista de Mercado**:
    *   *Puntos de dolor*: Recolección manual de precios; falta de datos agregados en tiempo real sobre dispersión de precios entre sector formal e informal.

### 4. Procesos Actuales y sus Problemas
1.  **Abastecimiento del Comerciante**: El vendedor (formal o informal) acude físicamente a la Central de Abastos en la madrugada, basando sus compras en la intuición o en precios del momento, incurriendo en gastos de transporte y tiempos muertos.
2.  **Fijación de Precios**: Se realiza empíricamente, observando a la competencia cercana, lo que genera alta dispersión de precios en zonas aledañas.
3.  **Registro y Control (Municipal)**: Los inspectores realizan recorridos físicos con libretas o Excel, generando información desactualizada, propensa a corrupción y difícil de analizar espacialmente.

### 5. Información que Debe Capturarse
*   **Datos del Comerciante**: Tipo (formal/informal), giro, ubicación geográfica (fija o itinerante/polígonos), días de operación.
*   **Catálogos y Precios**: Lista de productos básicos, precios de compra y venta, disponibilidad.
*   **Pedidos y Logística**: Órdenes de suministro hacia mayoristas, historial de entregas.
*   **Auditoría y Monitoreo**: Cambios de precios, validaciones de inspectores, registros de sesiones.

### 6. Decisiones que el Sistema Debe Soportar
*   **Mayoristas**: Dónde y cuándo enviar rutas de distribución para consolidar entregas a tianguis y comercios cercanos.
*   **Comerciantes**: A qué mayorista comprar basándose en el mejor precio y costo de entrega; qué productos añadir a su surtido según la demanda de la zona.
*   **Analistas/Gobierno**: Dónde implementar programas sociales o incentivos para reducir desiertos alimentarios; detección de anomalías inflacionarias regionales.

### 7. Actividades Automatizables vs. Juicio Humano
*   **Automatizable**: Comparación de precios, cálculo del Índice de Acceso Alimentario mediante geoprocesamiento, alertas de variación atípica de precios, recomendaciones de surtido basadas en el perfil del comercio.
*   **Juicio Humano**: Validación física en sitio de un puesto informal por parte del coordinador municipal; resolución de disputas sobre pedidos no entregados; interpretación cualitativa de las alertas económicas.

### 8. Riesgos de Negocio
*   **Adopción Tecnológica**: Resistencia al uso de la app por parte de comerciantes informales por temor a fiscalización (SAT) o por falta de alfabetización digital.
*   **Conectividad**: Fallas en la captura de datos en tianguis con baja cobertura de red (requiere funcionamiento offline).
*   **Calidad de Datos**: Captura intencionalmente errónea de precios para despistar a la competencia.

### 9. Restricciones Legales, Éticas y de Privacidad
*   **LFPDPPP (Ley Federal de Protección de Datos Personales en Posesión de los Particulares)**: Los datos personales de los comerciantes, especialmente de los informales, deben ser anonimizados y protegidos para evitar usos punitivos.
*   **NOM-076-SCFI-2012**: Requerimientos de sistemas de información comercial.
*   **Ética**: Evitar que el sistema se convierta en una herramienta de cacería fiscal para el comercio de subsistencia. Fomentar la inclusión.

### 10. Beneficios Esperados
*   **Para Comerciantes**: Reducción de costos de abastecimiento en un 15-20% y mejora en competitividad.
*   **Para Mayoristas**: Incremento del 25% en cobertura de clientes de canal tradicional y optimización de rutas.
*   **Para el Consumidor Final**: Menor volatilidad de precios y mayor disponibilidad de productos en sus barrios.

### 11. Ejemplos del Mundo Real
*   **Registro de un Vendedor de Tianguis**: "Doña Mary", que vende fruta en el tianguis de los martes, abre la app en modo "baja cobertura", marca su ubicación GPS (que se asocia al polígono del tianguis aprobado), selecciona "Frutas de temporada" y actualiza los precios del plátano y la manzana.
*   **Comparación de Precios**: Un Analista de Mercado abre el dashboard y observa un mapa de calor que muestra que el kilogramo de huevo es un 12% más barato en el comercio informal de la Zona Norte comparado con los minisúpers formales de la misma área.
