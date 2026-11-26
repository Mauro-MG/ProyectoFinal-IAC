"""
Pruebas estadísticas para comparar precios entre el comercio formal y el informal.

Mann-Whitney U (dos colas, aproximación normal con corrección por empates y por continuidad):
¿los precios de un grupo tienden a ser mayores que los del otro? No supone normalidad (los precios
suelen estar sesgados y con atípicos), solo muestras independientes.

    U1 = R1 − n1(n1+1)/2,  U = min(U1, n1·n2 − U1)
    z  = (|U1 − n1·n2/2| − 0.5) / σ,   σ² = n1·n2/12 · ((n+1) − Σ(t³−t)/(n(n−1)))
    p  = erfc(|z| / √2)
    efecto (correlación biserial por rangos) r = 1 − 2U1'/(n1·n2), con U1' = U de la muestra 1

Con n1 o n2 < 5 la aproximación normal no es confiable: se reporta sin p-valor.
Complejidad O(n log n) por el ordenamiento.
"""
import math


def rangos(valores):
    """Rangos promedio (1..n) con empates; regresa (rangos, suma de t³−t de los empates)."""
    orden = sorted(range(len(valores)), key=lambda i: valores[i])
    resultado = [0.0] * len(valores)
    empates = 0.0
    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and valores[orden[j + 1]] == valores[orden[i]]:
            j += 1
        promedio = (i + j) / 2 + 1
        for k in range(i, j + 1):
            resultado[orden[k]] = promedio
        t = j - i + 1
        empates += t ** 3 - t
        i = j + 1
    return resultado, empates


def mediana(valores):
    v = sorted(valores)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def mann_whitney(a, b, alfa=0.05):
    """Compara la muestra a (p. ej. informal) contra b (formal)."""
    n1, n2 = len(a), len(b)
    resultado = {'n1': n1, 'n2': n2, 'mediana1': mediana(a), 'mediana2': mediana(b), 'u': None, 'z': None,
                 'p_valor': None, 'significativa': None, 'efecto': None,
                 'nota': None}
    if n1 < 5 or n2 < 5:
        resultado['nota'] = 'Menos de 5 precios en algún sector: no hay suficientes datos para la prueba.'
        return resultado
    todos = list(a) + list(b)
    r, empates = rangos(todos)
    n = n1 + n2
    u1 = sum(r[:n1]) - n1 * (n1 + 1) / 2
    u = min(u1, n1 * n2 - u1)
    varianza = n1 * n2 / 12 * ((n + 1) - empates / (n * (n - 1)))
    if varianza <= 0:
        resultado.update(u=u, p_valor=1.0, significativa=False, efecto=0.0,
                         nota='Todos los precios son iguales.')
        return resultado
    z = (abs(u1 - n1 * n2 / 2) - 0.5) / math.sqrt(varianza)
    p = math.erfc(max(z, 0) / math.sqrt(2))
    efecto = 1 - 2 * (n1 * n2 - u1) / (n1 * n2)     # > 0: la muestra a tiende a ser mayor
    # 6 cifras significativas: un p muy pequeño se reporta como tal (p. ej. 3.2e-12), nunca como 0
    resultado.update(u=round(u, 2), z=round(z, 3), p_valor=float(f'{min(p, 1.0):.6g}'), significativa=p < alfa,
                     efecto=round(efecto, 3))
    return resultado
