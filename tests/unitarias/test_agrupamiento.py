"""DBSCAN geográfico (libs/abasto_dominio/servicios/agrupamiento.py)."""
import math
import random
import time

import pytest

from abasto_dominio.servicios.agrupamiento import RUIDO, agrupar, dbscan, haversine_m, validar_puntos

MTY = (25.6866, -100.3161)


def _alrededor(centro, n, radio_m, semilla, prefijo):
    azar = random.Random(semilla)
    puntos = []
    for i in range(n):
        d, ang = azar.uniform(0, radio_m), azar.uniform(0, 2 * math.pi)
        dlat = d * math.cos(ang) / 111_320
        dlon = d * math.sin(ang) / (111_320 * math.cos(math.radians(centro[0])))
        puntos.append((f'{prefijo}{i}', centro[0] + dlat, centro[1] + dlon))
    return puntos


def _dbscan_ingenuo(puntos, radio_m, minimo):
    """Misma definición de DBSCAN pero comparando cada par (O(n²)): referencia para la versión con rejilla."""
    n = len(puntos)

    def vecinos(i):
        return [j for j in range(n) if haversine_m(puntos[i][1], puntos[i][2], puntos[j][1], puntos[j][2]) <= radio_m]
    etiquetas, grupo = [None] * n, -1
    for i in range(n):
        if etiquetas[i] is not None:
            continue
        v = vecinos(i)
        if len(v) < minimo:
            etiquetas[i] = RUIDO
            continue
        grupo += 1
        etiquetas[i] = grupo
        cola, vistos = [j for j in v if j != i], set(v)
        while cola:
            j = cola.pop()
            if etiquetas[j] == RUIDO:
                etiquetas[j] = grupo
            if etiquetas[j] is not None:
                continue
            etiquetas[j] = grupo
            vj = vecinos(j)
            if len(vj) >= minimo:
                for k in vj:
                    if k not in vistos and (etiquetas[k] is None or etiquetas[k] == RUIDO):
                        vistos.add(k)
                        cola.append(k)
    return etiquetas


def test_haversine_contra_distancia_conocida():
    # Macroplaza de Monterrey a la UDEM (San Pedro): ~8.3 km en línea recta
    assert 8000 < haversine_m(25.6697, -100.3099, 25.6614, -100.4210) < 11500
    assert haversine_m(*MTY, *MTY) == 0


def test_encuentra_dos_concentraciones_y_aisla_el_ruido():
    tianguis = _alrededor(MTY, 15, 120, 1, 't')
    corredor = _alrededor((25.7400, -100.2600), 12, 150, 2, 'c')       # ~7.5 km al noreste
    aislados = [('a1', 25.60, -100.40), ('a2', 25.80, -100.20), ('a3', 25.65, -100.10)]
    r = agrupar(tianguis + corredor + aislados, radio_m=300, minimo=4)
    assert len(r['grupos']) == 2
    assert sorted(g['tamano'] for g in r['grupos']) == [12, 15]
    assert set(r['ruido']) == {'a1', 'a2', 'a3'}
    assert r['porcentaje_ruido'] == round(3 * 100 / 30, 2)
    grupo_tianguis = next(g for g in r['grupos'] if 't0' in g['ids'])
    assert haversine_m(grupo_tianguis['centro_latitud'], grupo_tianguis['centro_longitud'], *MTY) < 120
    assert grupo_tianguis['radio_m'] <= 120 + 1


@pytest.mark.parametrize('semilla', [3, 7, 11])
def test_la_rejilla_da_exactamente_lo_mismo_que_la_fuerza_bruta(semilla):
    azar = random.Random(semilla)
    puntos = [(i, 25.55 + azar.random() * 0.25, -100.45 + azar.random() * 0.35) for i in range(400)]
    puntos += _alrededor(MTY, 60, 200, semilla, 'g')
    etiquetas, _ = dbscan(puntos, 500, 5)
    assert etiquetas == _dbscan_ingenuo(puntos, 500, 5)


def test_casos_limite():
    vacio = agrupar([], radio_m=300, minimo=3)
    assert vacio['grupos'] == [] and vacio['ruido'] == [] and vacio['porcentaje_ruido'] == 0.0
    # Un solo punto y MinPts = 1: es núcleo de su propio grupo, sin ruido
    assert len(agrupar([('x', *MTY)], radio_m=10, minimo=1)['grupos']) == 1
    # Comercios en la misma coordenada (mismo mercado): distancia 0, un grupo
    repetidos = [(f'm{i}', *MTY) for i in range(5)]
    r = agrupar(repetidos, radio_m=1, minimo=5)
    assert len(r['grupos']) == 1 and r['grupos'][0]['radio_m'] == 0
    # Todos dispersos: cero grupos
    dispersos = [(i, 25.5 + i * 0.05, -100.3) for i in range(6)]
    assert agrupar(dispersos, radio_m=200, minimo=2)['grupos'] == []
    with pytest.raises(ValueError):
        dbscan(repetidos, 0, 3)
    with pytest.raises(ValueError):
        dbscan(repetidos, 100, 0)


def test_coordenadas_invalidas_se_excluyen_y_se_reportan():
    validos, excluidos = validar_puntos([('ok', *MTY), ('nula', None, -100.3), ('rango', 95, -100.3),
                                         ('texto', 'abc', 'x'), ('isla_nula', 0, 0)])
    assert [v[0] for v in validos] == ['ok']
    assert set(excluidos) == {'nula', 'rango', 'texto', 'isla_nula'}


def test_escala_a_miles_de_comercios():
    """20 000 comercios en el área metropolitana: con la rejilla termina en segundos (O(n·k))."""
    azar = random.Random(42)
    puntos = [(i, 25.55 + azar.random() * 0.30, -100.50 + azar.random() * 0.40) for i in range(20_000)]
    inicio = time.perf_counter()
    r = agrupar(puntos, radio_m=250, minimo=6)
    segundos = time.perf_counter() - inicio
    assert r['validos'] == 20_000
    assert segundos < 30, f'tardó {segundos:.1f} s'
