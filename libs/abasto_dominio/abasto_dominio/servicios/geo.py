"""Cálculos geográficos simples sobre latitud/longitud."""
import math

RADIO_TIERRA_KM = 6371.0


def distancia_km(lat1, lon1, lat2, lon2):
    """Distancia en línea recta (fórmula de Haversine)."""
    lat1, lon1, lat2, lon2 = map(lambda v: math.radians(float(v)), (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RADIO_TIERRA_KM * math.asin(math.sqrt(a))


def zona_para_punto(lat, lon, zonas):
    """
    Zona cuyo buffer (radio_km alrededor del centro) contiene el punto.
    Si el punto cae en varias, gana la de centro más cercano; si no cae en
    ninguna, regresa None para que el usuario la elija.
    """
    candidatas = []
    for zona in zonas:
        d = distancia_km(lat, lon, zona.latitud_centro, zona.longitud_centro)
        if d <= float(zona.radio_km):
            candidatas.append((d, zona))
    return min(candidatas, key=lambda par: par[0])[1] if candidatas else None


def area_km2(radio_km):
    return math.pi * float(radio_km) ** 2
