"""Corte rápido del pool de Redis (extensiones.PoolConCorte): con Redis inalcanzable no se reintenta en cada llamada."""
import time

import pytest
import redis

from abasto_dominio.extensiones import PoolConCorte


def cliente():
    # Puerto 1 en la máquina local: la conexión se rechaza de inmediato, sin depender de la red
    return redis.Redis(connection_pool=PoolConCorte.from_url('redis://127.0.0.1:1/0', socket_connect_timeout=1))


def test_tras_una_falla_las_siguientes_llamadas_cortan_sin_conectar():
    r = cliente()
    with pytest.raises(redis.exceptions.RedisError):     # ConnectionError o TimeoutError según el sistema
        r.get('x')
    inicio = time.perf_counter()
    for _ in range(50):
        with pytest.raises(redis.exceptions.ConnectionError, match='se reintentará'):
            r.get('x')
    assert time.perf_counter() - inicio < 0.1          # 50 llamadas sin intentar conectar


def test_pasada_la_espera_vuelve_a_intentar():
    r = cliente()
    with pytest.raises(redis.exceptions.RedisError):
        r.get('x')
    r.connection_pool.abierto_hasta = time.monotonic() - 1     # simula que pasaron los 2 s
    with pytest.raises(redis.exceptions.RedisError) as error:
        r.get('x')
    assert 'se reintentará' not in str(error.value)            # fue un intento real de conexión
