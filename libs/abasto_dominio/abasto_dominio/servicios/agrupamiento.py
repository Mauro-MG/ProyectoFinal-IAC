"""
Agrupamiento geográfico de comercios: DBSCAN con distancia haversine e índice de rejilla.

Problema
    Encontrar dónde se concentran los puntos de venta (tianguis, corredores comerciales, mercados)
    y qué comercios están aislados, sin fijar de antemano cuántos grupos hay. Con eso se ve, por
    grupo, la mezcla formal/informal y si un producto está disponible en la concentración o falta.

Por qué DBSCAN
    K-medias exige saber k y hace grupos esféricos de tamaño parecido; los corredores y tianguis son
    alargados y de densidad muy distinta, y K-medias obliga a meter a los comercios aislados en algún
    grupo. DBSCAN encuentra grupos de forma libre a partir de la densidad y marca el «ruido».

Entradas
    puntos: lista de (id, latitud, longitud) en grados WGS84.
    radio_m (ε): distancia máxima en metros para considerar vecinos a dos comercios.
    minimo (MinPts): vecinos (incluido el propio) para que un comercio sea núcleo de un grupo.

Salidas
    etiquetas: {id: número de grupo (0, 1, ...) o -1 si es ruido}, y por grupo: tamaño, centroide,
    radio (distancia máxima al centroide), núcleos y bordes.

Complejidad
    Una búsqueda de vecinos ingenua es O(n) por punto (O(n²) en total). Aquí los puntos se ubican en
    una rejilla de celdas de ε metros: los vecinos de un punto solo pueden estar en las 3×3 celdas
    que lo rodean, así que cada búsqueda revisa k puntos cercanos (k << n) y el total es O(n·k).
    El peor caso (todos los comercios en una misma manzana) sigue siendo O(n²). Memoria O(n).

Restricciones y casos límite
    - Coordenadas fuera de rango o ausentes: se excluyen y se reportan.
    - Sin puntos o ningún núcleo: cero grupos, todo es ruido.
    - minimo = 1: cada punto es núcleo (no hay ruido).
    - Puntos repetidos en la misma coordenada: distancia 0, son vecinos entre sí.
    - Un punto «borde» alcanzable desde dos grupos queda en el primero que lo alcanza (propiedad
      conocida de DBSCAN; no cambia los núcleos).
    - La rejilla usa grados por metro a la latitud de cada punto; en Monterrey (≈25.7°N) el error
      de la aproximación es despreciable a escala de cientos de metros.
"""
import math
import time

RADIO_TIERRA_M = 6_371_008.8
RUIDO = -1


def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia sobre la esfera en metros."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(min(1.0, math.sqrt(a)))


class _Rejilla:
    """Celdas de aproximadamente radio_m × radio_m para buscar vecinos sin recorrer todos los puntos."""

    def __init__(self, puntos, radio_m):
        self.radio = radio_m
        self.paso_lat = radio_m / 111_320.0
        self.celdas = {}
        for i, (_, lat, lon) in enumerate(puntos):
            self.celdas.setdefault(self._celda(lat, lon), []).append(i)
        self.puntos = puntos

    def _celda(self, lat, lon):
        paso_lon = self.radio / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
        return int(math.floor(lat / self.paso_lat)), int(math.floor(lon / paso_lon))

    def vecinos(self, i):
        _, lat, lon = self.puntos[i]
        ci, cj = self._celda(lat, lon)
        encontrados = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for j in self.celdas.get((ci + di, cj + dj), ()):
                    _, lat2, lon2 = self.puntos[j]
                    if haversine_m(lat, lon, lat2, lon2) <= self.radio:
                        encontrados.append(j)
        return encontrados


def validar_puntos(puntos):
    """Separa los puntos válidos de los que tienen coordenadas ausentes o fuera de rango."""
    validos, excluidos = [], []
    for p in puntos:
        ident, lat, lon = p
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            excluidos.append(ident)
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
            validos.append((ident, lat, lon))
        else:
            excluidos.append(ident)
    return validos, excluidos


def dbscan(puntos, radio_m, minimo):
    """
    Pseudocódigo:
        para cada punto p no visitado:
            marcar p visitado; N = vecinos(p, ε)
            si |N| < MinPts: p es ruido (por ahora)
            si no: nuevo grupo C; agregar p a C; cola = N
                mientras la cola no esté vacía:
                    q = siguiente; si q era ruido: q pasa a C (borde)
                    si q no visitado: visitarlo; Nq = vecinos(q, ε)
                        si |Nq| >= MinPts: agregar Nq a la cola (q es núcleo)
                    si q no tiene grupo: q pasa a C
    Regresa (etiquetas por índice, conjunto de índices núcleo).
    """
    if radio_m <= 0 or minimo < 1:
        raise ValueError('radio_m debe ser mayor a 0 y minimo al menos 1.')
    n = len(puntos)
    etiquetas = [None] * n
    nucleos = set()
    rejilla = _Rejilla(puntos, radio_m)
    grupo = -1
    for i in range(n):
        if etiquetas[i] is not None:
            continue
        vecinos = rejilla.vecinos(i)
        if len(vecinos) < minimo:
            etiquetas[i] = RUIDO
            continue
        grupo += 1
        etiquetas[i] = grupo
        nucleos.add(i)
        cola = [j for j in vecinos if j != i]
        visitados_en_cola = set(cola)
        while cola:
            j = cola.pop()
            if etiquetas[j] == RUIDO:
                etiquetas[j] = grupo            # era ruido: queda como borde del grupo
            if etiquetas[j] is not None:
                continue
            etiquetas[j] = grupo
            vecinos_j = rejilla.vecinos(j)
            if len(vecinos_j) >= minimo:
                nucleos.add(j)
                for k in vecinos_j:
                    if k not in visitados_en_cola and (etiquetas[k] is None or etiquetas[k] == RUIDO):
                        visitados_en_cola.add(k)
                        cola.append(k)
    return etiquetas, nucleos


def agrupar(puntos, radio_m=400, minimo=4):
    """Corre DBSCAN y resume cada grupo. `puntos`: (id, latitud, longitud). Mide su propio tiempo."""
    inicio = time.perf_counter()
    validos, excluidos = validar_puntos(puntos)
    etiquetas, nucleos = dbscan(validos, radio_m, minimo) if validos else ([], set())
    grupos = {}
    for i, etiqueta in enumerate(etiquetas):
        if etiqueta != RUIDO:
            grupos.setdefault(etiqueta, []).append(i)
    resumen = []
    for etiqueta, indices in sorted(grupos.items()):
        lat_c = sum(validos[i][1] for i in indices) / len(indices)
        lon_c = sum(validos[i][2] for i in indices) / len(indices)
        distancias = [haversine_m(lat_c, lon_c, validos[i][1], validos[i][2]) for i in indices]
        resumen.append({'grupo': etiqueta, 'tamano': len(indices), 'centro_latitud': round(lat_c, 6),
                        'centro_longitud': round(lon_c, 6), 'radio_m': round(max(distancias), 1),
                        'distancia_media_m': round(sum(distancias) / len(distancias), 1),
                        'nucleos': sum(1 for i in indices if i in nucleos),
                        'ids': [validos[i][0] for i in indices]})
    ruido = [validos[i][0] for i, e in enumerate(etiquetas) if e == RUIDO]
    return {
        'parametros': {'radio_m': radio_m, 'minimo': minimo},
        'puntos': len(puntos), 'validos': len(validos), 'excluidos': excluidos,
        'grupos': resumen, 'ruido': ruido,
        'porcentaje_ruido': round(len(ruido) * 100 / len(validos), 2) if validos else 0.0,
        'etiquetas': {validos[i][0]: e for i, e in enumerate(etiquetas)},
        'tiempo_ms': round((time.perf_counter() - inicio) * 1000, 2),
    }
