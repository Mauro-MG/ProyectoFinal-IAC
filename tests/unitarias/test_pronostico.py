"""Pronóstico de demanda y su evaluación fuera de muestra (libs/abasto_dominio/servicios/pronostico.py)."""
import random
from datetime import date, timedelta

import pytest

from abasto_dominio.servicios import pronostico

FACTOR = {0: 0.8, 1: 0.9, 2: 1.0, 3: 1.0, 4: 1.2, 5: 1.5, 6: 0.6}   # lunes .. domingo


def _serie(dias=84, base=20.0, tendencia=0.15, ruido=1.5, semilla=1):
    azar = random.Random(semilla)
    inicio = date(2026, 6, 1)
    fechas = [inicio + timedelta(days=i) for i in range(dias)]
    valores = [max(0.0, (base + tendencia * i) * FACTOR[f.weekday()] + azar.gauss(0, ruido))
               for i, f in enumerate(fechas)]
    return fechas, valores


def test_recupera_tendencia_y_estacionalidad():
    fechas, valores = _serie(ruido=0.0)
    modelo = pronostico.ajustar(fechas, valores)
    assert modelo['pendiente'] > 0
    assert modelo['indice'][5] > modelo['indice'][6]            # sábado vende más que domingo
    assert modelo['error_entrenamiento'] < 2.5


def test_evaluacion_fuera_de_muestra_supera_al_ingenuo():
    fechas, valores = _serie(tendencia=0.25, ruido=1.0)
    r = pronostico.evaluar(fechas, valores)
    assert r['dias_prueba'] == 21 and r['dias_entrenamiento'] == 63
    assert r['mae'] < r['mae_ingenuo'] and r['mejora_vs_ingenuo_pct'] > 0
    assert r['wape_pct'] < 15


def test_no_hay_fuga_de_datos_de_prueba():
    """Cambiar los días de prueba no cambia lo que el modelo predijo para ellos: solo vio el entrenamiento."""
    fechas, valores = _serie()
    alterados = valores[:-21] + [v * 10 for v in valores[-21:]]
    modelo = pronostico.ajustar(fechas[:-21], valores[:-21])
    modelo_alterado = pronostico.ajustar(fechas[:-21], alterados[:-21])
    assert [pronostico.predecir(modelo, d) for d in fechas[-21:]] == \
        [pronostico.predecir(modelo_alterado, d) for d in fechas[-21:]]
    assert pronostico.evaluar(fechas, alterados)['mae'] > pronostico.evaluar(fechas, valores)['mae']


def test_historia_corta_y_casos_limite():
    fechas, valores = _serie(dias=20)
    assert pronostico.evaluar(fechas, valores) is None          # menos de 3 semanas: sin evaluación
    ceros = [0.0] * 30
    modelo = pronostico.ajustar(_serie(dias=30)[0], ceros)
    assert pronostico.pronosticar(modelo, date(2026, 7, 1), 3)[0][1] == 0
    with pytest.raises(ValueError):
        pronostico.ajustar([], [])
    # Nunca pronostica unidades negativas aunque la tendencia baje
    fechas, valores = _serie(dias=60, base=10, tendencia=-0.5, ruido=0)
    modelo = pronostico.ajustar(fechas, valores)
    assert all(v >= 0 for _, v in pronostico.pronosticar(modelo, fechas[-1], 30))
