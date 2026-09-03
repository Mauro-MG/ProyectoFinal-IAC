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

*   **Protección de datos en posesión de particulares:** Si AbastoRed es operada por una empresa o asociación privada, el tratamiento de datos deberá sujetarse a la Ley Federal de Protección de Datos Personales en Posesión de los Particulares. Esto implica realizar un tratamiento legítimo, controlado e informado, proporcionar un aviso de privacidad y proteger el derecho de las personas sobre sus datos [1].
*   **Protección de datos en instituciones públicas:** Si un municipio o dependencia pública opera la plataforma, deberá considerarse la Ley General de Protección de Datos Personales en Posesión de Sujetos Obligados [2].
*   **Minimización de datos:** Solo se capturará la información necesaria para los procesos de la plataforma.
*   **Control de acceso:** Cada perfil podrá consultar únicamente la información necesaria para sus responsabilidades.
*   **Ubicación geográfica:** La ubicación individual de comerciantes no deberá mostrarse públicamente sin una finalidad justificada y autorización correspondiente.
*   **Ética:** El sistema apoyará la generación de alertas y recomendaciones, pero las sanciones, validaciones de comerciantes y resolución de controversias permanecerán bajo responsabilidad humana.
*   **No discriminación:** Los datos no deberán utilizarse para perseguir, excluir o discriminar a comerciantes informales.

### 10. Beneficios Esperados

Los siguientes beneficios son resultados esperados que deberán medirse mediante indicadores durante las pruebas piloto; no representan porcentajes garantizados.

*   **Para comerciantes:** Reducción del tiempo utilizado para comparar opciones de abasto, mayor visibilidad de precios y mejores decisiones de surtido.
*   **Para mayoristas:** Mayor alcance hacia comercios formales e informales y mejor información para planear rutas de distribución.
*   **Para consumidores:** Mayor disponibilidad de información sobre precios y productos en su zona.
*   **Para instituciones públicas:** Información agregada para apoyar el monitoreo de precios, cobertura comercial y acceso alimentario.
*   **Para el proyecto:** Centralización de información que actualmente se encuentra dispersa en registros manuales, hojas de cálculo y sistemas aislados.

La FAO señala que los sistemas públicos de abastecimiento pueden contribuir a la estabilidad de la oferta, la difusión de información comercial y la reducción de fluctuaciones fuertes de precios [3].

### 11. Ejemplos del Mundo Real
*   **Registro de un Vendedor de Tianguis**: "Doña Mary", que vende fruta en el tianguis de los martes, abre la app en modo "baja cobertura", marca su ubicación GPS (que se asocia al polígono del tianguis aprobado), selecciona "Frutas de temporada" y actualiza los precios del plátano y la manzana.
*   **Comparación de Precios**: Un Analista de Mercado abre el dashboard y observa un mapa de calor que muestra que el kilogramo de huevo es un 12% más barato en el comercio informal de la Zona Norte comparado con los minisúpers formales de la misma área.

### 12. Referencias

[1] Cámara de Diputados del H. Congreso de la Unión. (2025). *Ley Federal de Protección de Datos Personales en Posesión de los Particulares*. https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf

[2] Cámara de Diputados del H. Congreso de la Unión. (2025). *Ley General de Protección de Datos Personales en Posesión de Sujetos Obligados*. https://www.diputados.gob.mx/LeyesBiblio/pdf/LGPDPPSO.pdf

[3] Organización de las Naciones Unidas para la Alimentación y la Agricultura. (s. f.). *Sistemas Públicos de Abastecimiento y Comercialización de Alimentos*. https://www.fao.org/in-action/redspaa/es
