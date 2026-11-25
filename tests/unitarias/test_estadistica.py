"""Mann-Whitney U para comparar precios formal vs informal. Valores de referencia calculados con
scipy.stats.mannwhitneyu(alternative='two-sided', method='asymptotic', use_continuity=True)."""
import pytest

from abasto_dominio.servicios.estadistica import mann_whitney, mediana, rangos


@pytest.mark.parametrize('a, b, p, u', [
    ([29.5, 30, 28, 31, 29, 30.5, 28.5], [33, 34, 32.5, 33.5, 35, 34, 33], 0.002117, 0.0),
    ([20, 21, 22, 23, 24, 25], [20, 21, 22, 23, 24, 25], 1.0, 18.0),
    ([10, 12, 12, 14, 15, 15, 16, 18], [11, 12, 13, 13, 15, 17, 19, 19, 20], 0.410524, 27.0),
])
def test_coincide_con_scipy(a, b, p, u):
    r = mann_whitney(a, b)
    assert r['p_valor'] == pytest.approx(p, rel=1e-3) and r['u'] == u


def test_direccion_del_efecto_y_significancia():
    informal = [28, 29, 29.5, 30, 28.5, 29, 30.5]
    formal = [33, 34, 32.5, 33.5, 35, 34, 33]
    r = mann_whitney(informal, formal)
    assert r['significativa'] and r['efecto'] == -1.0            # informal siempre más barato
    assert r['mediana1'] == 29 and r['mediana2'] == 33.5


def test_pocos_datos_y_empates_totales():
    assert mann_whitney([1, 2, 3], [4, 5, 6, 7, 8])['p_valor'] is None
    iguales = mann_whitney([10] * 6, [10] * 6)
    assert iguales['p_valor'] == 1.0 and not iguales['significativa']


def test_rangos_con_empates():
    r, empates = rangos([10, 20, 20, 30])
    assert r == [1, 2.5, 2.5, 4] and empates == 6
    assert mediana([3, 1, 2]) == 2 and mediana([4, 1, 3, 2]) == 2.5 and mediana([]) is None
