"""Reglas de negocio de la biblioteca de dominio que no necesitan base de datos."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from abasto_dominio.servicios import ReglaNegocioError
from abasto_dominio.servicios.bloqueos import bloqueo
from abasto_dominio.servicios.geo import distancia_km, zona_para_punto
from abasto_dominio.servicios.importaciones import _numero
from abasto_dominio.servicios.pedidos import TRANSICIONES, acciones_disponibles


# ---------------------------------------------------------------- pedidos (RN-010)

def actores():
    empresa = SimpleNamespace(id=uuid4())
    comerciante = SimpleNamespace(id=uuid4(), proveedor_vinculado=None)
    dueno = SimpleNamespace(id=uuid4(), proveedor_vinculado=empresa)
    operador = SimpleNamespace(id=uuid4(), proveedor_vinculado=empresa)
    ajeno = SimpleNamespace(id=uuid4(), proveedor_vinculado=SimpleNamespace(id=uuid4()))
    return empresa, comerciante, dueno, operador, ajeno


def pedido(estado, comerciante, empresa):
    return SimpleNamespace(estado=estado, comercio=SimpleNamespace(usuario_id=comerciante.id), proveedor_id=empresa.id)


@pytest.mark.parametrize('estado, comercio, proveedor', [
    ('BORRADOR', ['enviar', 'cancelar'], []),
    ('ENVIADO', ['cancelar'], ['aceptar', 'rechazar']),
    ('ACEPTADO', [], ['preparar']),
    ('EN_PREPARACION', [], ['despachar']),
    ('ENVIADO_A_COMERCIO', ['recibir'], []),
    ('ENTREGADO', [], []),
    ('CANCELADO', [], []),
])
def test_acciones_por_estado_y_lado(estado, comercio, proveedor):
    empresa, comerciante, dueno, operador, ajeno = actores()
    p = pedido(estado, comerciante, empresa)
    assert acciones_disponibles(p, comerciante) == comercio
    assert acciones_disponibles(p, dueno) == proveedor
    assert acciones_disponibles(p, operador) == proveedor  # el operador atiende igual que el dueño
    assert acciones_disponibles(p, ajeno) == []             # otro proveedor no puede tocarlo


def test_flujo_feliz_recorre_todos_los_estados():
    estado = 'BORRADOR'
    for accion in ('enviar', 'aceptar', 'preparar', 'despachar', 'recibir'):
        origenes, destino, _ = TRANSICIONES[accion]
        assert estado in origenes
        estado = destino
    assert estado == 'ENTREGADO'


# ---------------------------------------------------------------- importación CSV

@pytest.mark.parametrize('texto, esperado', [
    ('12', Decimal('12')), (' 3.50 ', Decimal('3.50')), ('$1,250.00', Decimal('1250.00')), ('', None), (None, None),
])
def test_numero_acepta_formatos_de_excel(texto, esperado):
    assert _numero(texto, 'precio') == esperado


@pytest.mark.parametrize('texto, mensaje', [('-4', 'negativo'), ('doce', 'no es un número')])
def test_numero_rechaza_valores_invalidos(texto, mensaje):
    with pytest.raises(ReglaNegocioError, match=mensaje):
        _numero(texto, 'existencia')


def test_numero_obligatorio():
    with pytest.raises(ReglaNegocioError, match='Falta existencia'):
        _numero('  ', 'existencia', obligatorio=True)


# ---------------------------------------------------------------- geografía

def test_distancia_monterrey_san_nicolas():
    # Macroplaza -> centro de San Nicolás de los Garza: ~8 km en línea recta
    assert 6 < distancia_km(25.6694, -100.3097, 25.7417, -100.3022) < 10


def test_zona_para_punto_elige_el_centro_mas_cercano():
    norte = SimpleNamespace(nombre='Norte', latitud_centro=25.75, longitud_centro=-100.30, radio_km=5)
    centro = SimpleNamespace(nombre='Centro', latitud_centro=25.67, longitud_centro=-100.31, radio_km=10)
    assert zona_para_punto(25.745, -100.30, [centro, norte]).nombre == 'Norte'  # cae en ambas
    assert zona_para_punto(25.66, -100.31, [centro, norte]).nombre == 'Centro'
    assert zona_para_punto(26.50, -99.00, [centro, norte]) is None


# ---------------------------------------------------------------- bloqueo distribuido (Redis)

def test_bloqueo_impide_la_segunda_ejecucion(redis_falso):
    with bloqueo('importacion:c1', ttl_segundos=30):
        assert redis_falso.exists('bloqueo:importacion:c1')
        assert 0 < redis_falso.ttl('bloqueo:importacion:c1') <= 30
        with pytest.raises(ReglaNegocioError, match='ya se está ejecutando'):
            with bloqueo('importacion:c1'):
                pass
    assert not redis_falso.exists('bloqueo:importacion:c1')  # se libera al terminar


def test_bloqueo_se_libera_aunque_falle_la_operacion(redis_falso):
    with pytest.raises(RuntimeError):
        with bloqueo('pedido:p1'):
            raise RuntimeError('falla a la mitad')
    with bloqueo('pedido:p1'):
        pass


def test_bloqueo_ajeno_no_se_borra(redis_falso):
    """Si el bloqueo expiró y otro proceso lo tomó, el primero no debe liberarlo."""
    with bloqueo('pedido:p2', ttl_segundos=30):
        redis_falso.set('bloqueo:pedido:p2', 'token-de-otro-proceso')
    assert redis_falso.get('bloqueo:pedido:p2') == 'token-de-otro-proceso'
