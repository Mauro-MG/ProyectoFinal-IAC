"""
Pronóstico de demanda diaria: regresión lineal (mínimos cuadrados) con índice por día de la semana,
y su evaluación honesta con datos que el modelo no vio.

    unidades(t) = max(a + b·t, 0) · índice[día_semana(t)]
    índice[d]   = promedio de las unidades del día d / promedio general

El error del ajuste sobre la misma historia (error de entrenamiento) subestima el error real. Por eso
`evaluar` separa los últimos días como prueba, ajusta solo con los anteriores, pronostica los de prueba
y compara con lo que pasó, y con un pronóstico ingenuo estacional (mismo día de la semana anterior),
que es el mínimo que un modelo debe mejorar.
Complejidad: O(n) para ajustar y O(h) para pronosticar h días.
"""
from datetime import timedelta


def ajustar(dias, valores):
    """dias: fechas consecutivas; valores: unidades por día. Regresa el modelo como diccionario."""
    n = len(valores)
    if n == 0:
        raise ValueError('No hay historia para ajustar.')
    media_x, media_y = (n - 1) / 2, sum(valores) / n
    var_x = sum((x - media_x) ** 2 for x in range(n))
    pendiente = sum((x - media_x) * (y - media_y) for x, y in enumerate(valores)) / var_x if var_x else 0.0
    ordenada = media_y - pendiente * media_x
    por_dia = {}
    for d, v in zip(dias, valores):
        por_dia.setdefault(d.weekday(), []).append(v)
    indice = {k: (sum(v) / len(v)) / media_y if media_y else 1.0 for k, v in por_dia.items()}
    modelo = {'ordenada': ordenada, 'pendiente': pendiente, 'indice': indice, 'inicio': dias[0], 'n': n,
              'media': media_y}
    ajuste = [predecir(modelo, d) for d in dias]
    modelo['error_entrenamiento'] = sum(abs(a - y) for a, y in zip(ajuste, valores)) / n
    return modelo


def predecir(modelo, fecha):
    t = (fecha - modelo['inicio']).days
    return max(modelo['ordenada'] + modelo['pendiente'] * t, 0) * modelo['indice'].get(fecha.weekday(), 1.0)


def pronosticar(modelo, ultimo_dia, horizonte):
    return [(ultimo_dia + timedelta(days=p), predecir(modelo, ultimo_dia + timedelta(days=p)))
            for p in range(1, horizonte + 1)]


def _metricas(reales, estimados):
    total = sum(reales)
    mae = sum(abs(r - e) for r, e in zip(reales, estimados)) / len(reales)
    wape = sum(abs(r - e) for r, e in zip(reales, estimados)) * 100 / total if total else None
    return mae, wape


def evaluar(dias, valores, dias_prueba=None):
    """Validación fuera de muestra (holdout temporal). Requiere al menos 3 semanas de historia."""
    n = len(valores)
    dias_prueba = dias_prueba or max(7, min(28, n // 4))
    if n - dias_prueba < 14:
        return None
    modelo = ajustar(dias[:-dias_prueba], valores[:-dias_prueba])
    reales = valores[-dias_prueba:]
    estimados = [predecir(modelo, d) for d in dias[-dias_prueba:]]
    # Ingenuo estacional: cada día de prueba repite lo vendido el mismo día de la semana anterior al corte
    ultima_semana = valores[-dias_prueba - 7:-dias_prueba]
    ingenuo = [ultima_semana[i % 7] for i in range(dias_prueba)]
    mae, wape = _metricas(reales, estimados)
    mae_ingenuo, wape_ingenuo = _metricas(reales, ingenuo)
    return {'dias_entrenamiento': n - dias_prueba, 'dias_prueba': dias_prueba,
            'mae': round(mae, 3), 'wape_pct': round(wape, 2) if wape is not None else None,
            'mae_ingenuo': round(mae_ingenuo, 3),
            'wape_ingenuo_pct': round(wape_ingenuo, 2) if wape_ingenuo is not None else None,
            'mejora_vs_ingenuo_pct': round((mae_ingenuo - mae) * 100 / mae_ingenuo, 1) if mae_ingenuo else None,
            'error_entrenamiento': round(modelo['error_entrenamiento'], 3)}
