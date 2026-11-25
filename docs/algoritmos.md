# Algoritmos de AbastoRed

Este documento cubre los tres algoritmos que se agregaron para la entrega final. Los análisis que ya
existían se resumen al final.

## 1. Agrupamiento geográfico de comercios (DBSCAN)

- **Código:** `libs/abasto_dominio/abasto_dominio/servicios/agrupamiento.py`.
- **API:** `GET /ms/analisis/api/v1/analisis/agrupamientos`, en JSON o XML.
- **Pruebas:** `tests/unitarias/test_agrupamiento.py` (8 pruebas).

### Problema

Encontrar dónde se concentran los puntos de venta (tianguis, corredores, mercados) y qué comercios
están aislados, sin decir de antemano cuántos grupos hay. Con eso, la coordinación puede ver por
concentración:

- la mezcla de comercio formal e informal;
- si un producto de la canasta está disponible o falta, lo que señala una oportunidad de abasto
  focalizada.

### Por qué DBSCAN y no K-medias

| Criterio | K-medias | DBSCAN |
| :--- | :--- | :--- |
| Número de grupos | Hay que fijarlo | Sale de la densidad |
| Forma de los grupos | Esférica y de tamaño parecido | Libre: corredores alargados, tianguis |
| Comercios aislados | Los obliga a entrar en algún grupo | Los marca como ruido |
| Distancia | Euclidiana (en grados, deforma) | Cualquiera: aquí haversine, en metros |

### Entradas, salidas y variables

| | Nombre | Descripción |
| :--- | :--- | :--- |
| Entrada | `puntos` | `(id, latitud, longitud)` de los comercios activos; por omisión, solo los verificados |
| Parámetro | `radio_m` (ε) | Distancia máxima en metros para que dos comercios sean vecinos (25 a 5000; 400 por omisión) |
| Parámetro | `minimo` (MinPts) | Vecinos, incluido el propio, para que un comercio sea núcleo (1 a 100; 4 por omisión) |
| Filtro | `municipio`, `sector`, `solo_verificados` | Subconjunto de comercios |
| Filtro | `producto_id` | Calcula la cobertura de ese producto en cada grupo |
| Salida | `grupos[]` | Por grupo: tamaño, centro, radio, distancia media al centro, núcleos, formales e informales, municipio principal, cobertura del producto y una lectura en texto |
| Salida | `aislados[]`, `porcentaje_ruido` | Comercios que no forman parte de ninguna concentración |
| Salida | `excluidos` | Comercios con coordenadas ausentes o fuera de rango |
| Salida | `tiempo_ms` | Tiempo de cálculo medido |

### Pseudocódigo

```
para cada punto p no visitado:
    N ← vecinos(p, ε)                       # rejilla + haversine
    si |N| < MinPts: p ← ruido; continuar
    C ← nuevo grupo; p ∈ C; cola ← N \ {p}
    mientras cola no vacía:
        q ← sacar(cola)
        si q es ruido: q ∈ C (borde); continuar
        si q ya tiene grupo: continuar
        q ∈ C; Nq ← vecinos(q, ε)
        si |Nq| ≥ MinPts: cola ← cola ∪ (Nq sin grupo)
```

`vecinos(p, ε)` no recorre todos los puntos. Los comercios se reparten en una rejilla de celdas de ε
metros, así que los vecinos de `p` solo pueden estar en las 3×3 celdas que lo rodean. Dentro de
esas celdas se calcula la distancia haversine exacta.

### Complejidad

| Caso | Tiempo | Memoria |
| :--- | :--- | :--- |
| Típico (k vecinos candidatos por punto, k ≪ n) | O(n·k) | O(n) |
| Peor (todos dentro de un mismo ε) | O(n²) | O(n) |

### Restricciones y casos límite

Todos están cubiertos por las pruebas:

- Coordenadas nulas, de texto, fuera de rango o (0, 0): se excluyen y se reportan.
- Sin puntos: cero grupos y 0 % de ruido.
- `minimo = 1`: cada punto es núcleo y no hay ruido.
- Comercios en la misma coordenada: distancia 0, forman un solo grupo.
- Todos dispersos: cero grupos.
- `radio_m ≤ 0` o `minimo < 1`: error de validación.
- Un punto borde alcanzable desde dos grupos queda en el primero que lo alcanza. Es una propiedad
  conocida de DBSCAN y no cambia los núcleos.

### Pruebas y métricas

- **Corrección de la rejilla.** En tres conjuntos aleatorios de 460 puntos, las etiquetas son
  idénticas a las de un DBSCAN de fuerza bruta O(n²) con la misma definición. Esto demuestra que la
  rejilla no pierde vecinos.
- **Caso con respuesta conocida.**
  - Datos: dos concentraciones sintéticas de 15 y 12 comercios, más 3 comercios aislados.
  - Resultado: el algoritmo encuentra exactamente 2 grupos y 3 de ruido.
  - El centro del primer grupo queda a menos de 120 m del centro real.
- **Métricas que regresa:** número de grupos, porcentaje de ruido, radio y distancia media por grupo,
  y cobertura del producto por grupo.

### Tiempo de ejecución medido

- **Equipo:** AMD Ryzen (Family 23 Model 113), Python 3.12.9.
- **Datos:** sintéticos sobre el área metropolitana de Monterrey (33 × 44 km). El 30 % de los
  comercios se concentra en 40 corredores.
- **Parámetros:** ε = 250 m, MinPts = 6.
- **Medición:** el mejor de 3 corridas.

| Comercios | Grupos | Ruido | Tiempo |
| ---: | ---: | ---: | ---: |
| 1 000 | 40 | 69.3 % | 0.008 s |
| 5 000 | 35 | 69.0 % | 0.098 s |
| 20 000 | 297 | 57.5 % | 1.21 s |
| 50 000 | 1 144 | 9.4 % | 7.07 s |
| 100 000 | 1 | 0.1 % | 26.8 s |

Con 100 000 comercios repartidos uniformemente, cada círculo de 250 m tiene en promedio unos
13 comercios. Así, todo queda conectado en un solo grupo y el algoritmo se acerca a su peor caso.
Esto indica que ε debe bajar cuando sube la densidad. Con los datos reales del sistema, el cálculo
tarda menos de 1 ms.

### Limitaciones

- ε y MinPts los elige el analista. Un ε grande en zonas densas une todo (ver la tabla anterior).
- Una sola densidad para toda el área metropolitana. Variantes como HDBSCAN o OPTICS manejan
  densidades distintas, pero no se implementaron.
- La rejilla usa el factor de grados por metro de la latitud de cada punto. Es exacto para
  Monterrey, pero no para zonas cercanas a los polos.

## 2. Pronóstico de demanda con evaluación fuera de muestra

- **Código:** `libs/abasto_dominio/abasto_dominio/servicios/pronostico.py`.
- **API:** `GET /ms/demanda/api/v1/demanda/estimacion`.
- **Pruebas:** `tests/unitarias/test_pronostico.py`.

### Modelo

```
unidades(t) = max(a + b·t, 0) · índice[día_semana(t)]
índice[d]   = promedio de unidades del día d / promedio general
```

`a` y `b` se ajustan por mínimos cuadrados. Ajustar es O(n) y pronosticar h días es O(h).

### Evaluación

Antes, el sistema reportaba el error medio absoluto sobre la misma historia con que ajustaba el
modelo (error de entrenamiento). Ese error subestima el error real. Ahora la respuesta incluye
`evaluacion`, que mide el modelo con datos que no vio:

1. Se separan los últimos `dias_prueba` días: entre 7 y 28, y 1/4 de la serie.
2. Se ajusta el modelo solo con los días anteriores.
3. Se pronostican los días de prueba y se comparan con lo que se vendió.
4. Se reportan el MAE y el WAPE (error absoluto ponderado, en %).
5. Se compara contra un pronóstico ingenuo estacional, que repite lo vendido el mismo día de la
   semana anterior al corte. Un modelo que no mejora al ingenuo no aporta.

El rango `minimo`/`maximo` del pronóstico usa el MAE de esta evaluación. Con menos de 3 semanas de
historia no hay evaluación y se usa el error de entrenamiento.

Una de las pruebas cambia los días de prueba y comprueba que las predicciones para esos días no
cambian, lo que demuestra que el modelo no vio esos datos. Otra comprueba, con datos sintéticos de
tendencia y estacionalidad conocidas, que el modelo supera al ingenuo.

### Ejemplo real (base de desarrollo, 24 de noviembre de 2026)

Arroz blanco 1 kg, con 84 días de historia:

| Medida | Valor |
| :--- | ---: |
| Error de entrenamiento | 2.17 unidades |
| MAE fuera de muestra | 11.14 unidades |
| WAPE fuera de muestra | 135 % |
| Mejora contra el ingenuo | −5.3 % (no lo supera) |

**Causa:** la base se cargó el 15 de noviembre y desde entonces casi no hay ventas, así que los
últimos 21 días no se parecen a la historia.

Este ejemplo muestra por qué no debe presentarse el error de entrenamiento como precisión futura.

### Limitaciones

- La tendencia es lineal.
- Solo hay estacionalidad semanal; no hay mensual, de días festivos ni de quincena.
- No tiene variables externas como el precio o las promociones.

## 3. Comparación estadística de precios formal contra informal

- **Código:** `libs/abasto_dominio/abasto_dominio/servicios/estadistica.py`.
- **API:** `resumen[]` de `GET /ms/precios/api/v1/precios/comparacion`.
- **Pruebas:** `tests/unitarias/test_estadistica.py`.

**Pregunta:** la diferencia de precio entre el comercio formal y el informal, ¿es real o puede ser
azar?

**Prueba:** Mann-Whitney U de dos colas.
- Usa los **precios individuales** validados del periodo, no los promedios.
- Es no paramétrica: no supone normalidad, porque los precios tienen sesgo y valores atípicos.
- Usa la aproximación normal con corrección por empates y por continuidad.

**Salidas por producto:**

| Campo | Significado |
| :--- | :--- |
| `n_formal`, `n_informal` | Número de precios de cada sector |
| `mediana_formal`, `mediana_informal` | Mediana de cada sector |
| `p_valor` | Probabilidad de ver una diferencia así por azar |
| `diferencia_significativa` | `true` si p < 0.05 |
| `efecto` | Correlación biserial por rangos, de −1 a 1. Negativo: lo informal es más barato |

**Validación:** los p-valores y la U coinciden con `scipy.stats.mannwhitneyu` en los casos de
prueba.

**Restricción:** con menos de 5 precios en algún sector no se calcula el p-valor y se explica en
`nota_prueba`.

**Ejemplo real (base de desarrollo):** arroz blanco 1 kg.

| Medida | Valor |
| :--- | :--- |
| Precios formales | 33, con mediana de $33.50 |
| Precios informales | 21, con mediana de $26.00 |
| p-valor | < 10⁻⁶ |
| Efecto | −0.93 |

Lo informal es claramente más barato.

**Complejidad:** O(n log n), por el ordenamiento para asignar rangos.

## Análisis que ya existían

- **Brechas de surtido:** `servicios/analisis.py`. La cobertura es la proporción de comercios de la
  zona con existencia. El déficit son los puntos de venta que requiere la población menos los que
  tienen existencia. El nivel (ALTA, MEDIA o BAJA) depende de umbrales configurables.
- **Índice de acceso y ranking de zonas:** cobertura promedio de la canasta básica por zona.
- **Recomendación de surtido (regla RN-003):** ms-recomendaciones.
  - **Cuándo se recomienda un producto:** el comercio no lo vende, la cobertura de la zona está bajo
    el umbral, hay demanda y algún proveedor que entrega en la zona lo tiene.
  - **Puntaje:**
    `(100 − cobertura) + 20 si es de canasta básica + ventas/5 (máx. 20) + 5 por proveedor (máx. 15)
    + 2 por búsqueda no satisfecha en ms-demanda (máx. 20)`.
  - **Prioridad:** alta si el puntaje es 110 o más, media si es 80 o más.
  - Cada recomendación explica los factores que sumaron puntos. El margen estimado se muestra, pero no
    suma al puntaje.
- **Geoespacial:** PostGIS (ST_Contains para asignar la zona, buffers por radio) y mapas de calor
  en el web.
