"""
Prueba de integración del escenario completo pedido en la retroalimentación
del primer avance (registro -> inventario -> disponibilidad -> brechas ->
recomendación -> pedido -> proveedor -> recepción -> inventario -> auditoría).

Requiere una base PostgreSQL con 01_schema.sql y 03_seeds.sql cargados.
Crea un usuario y un comercio nuevos en cada ejecución, así que se puede
correr varias veces sobre la misma base.

    cd apps/web
    pytest -v tests/test_escenario_abasto.py
"""
import re
import uuid
from decimal import Decimal

import pytest
from flask import g

from app import app as flask_app
from app.extensions import db
from app.models import (AuditoriaEvento, Comercio, InventarioComercio, PedidoAbasto, ProductoMaestro, Proveedor,
                        Usuario)

CLAVE = 'Password123!'


@pytest.fixture(scope='module')
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    # El contexto de aplicación queda abierto para consultar la BD desde la prueba;
    # como las peticiones lo reutilizan, se borra el usuario que Flask-Login guarda en g.
    @flask_app.teardown_request
    def olvidar_usuario(_):
        g.pop('_login_user', None)

    with flask_app.app_context():
        yield flask_app


@pytest.fixture
def cliente(app):
    return app.test_client()


def entrar(cliente, email, password=CLAVE):
    cliente.get('/logout')
    respuesta = cliente.post('/login', data={'email': email, 'password': password})
    assert respuesta.status_code == 302, f'No pudo iniciar sesión {email}'


def producto(nombre):
    return ProductoMaestro.query.filter_by(nombre=nombre).one()


def test_escenario_completo(cliente):
    email = f'prueba.{uuid.uuid4().hex[:8]}@test.mx'
    tomate = producto('Tomate saladette')
    leche = producto('Leche entera 1 L')
    bodega = Proveedor.query.filter_by(nombre_empresa='Bodega 14 - Mercado de Abastos Estrella').one()

    # 1. Un usuario se registra
    r = cliente.post('/registro', data={'perfil': 'Comerciante Informal', 'nombre': 'Prueba',
                                        'apellido_paterno': 'Escenario', 'email': email,
                                        'password': CLAVE, 'confirmar': CLAVE})
    assert r.status_code == 302 and '/comercios/nuevo' in r.location

    # 2. Registra su comercio (coordenadas dentro de García Norte; la zona se asigna sola)
    r = cliente.post('/comercios/nuevo', data={
        'nombre_comercio': 'Puesto de prueba', 'tipo_comercio': 'INFORMAL_TIANGUIS',
        'direccion': 'Tianguis Los Nogales, pasillo F', 'municipio': 'García', 'estado': 'Nuevo León',
        'zona_id': 0, 'latitud': '25.8210', 'longitud': '-100.5890'})
    assert r.status_code == 302
    comercio = Comercio.query.join(Usuario, Comercio.usuario_id == Usuario.id).filter(Usuario.email == email).one()
    assert comercio.zona.nombre == 'García Norte'
    assert comercio.estado_registro == 'PENDIENTE'

    # 3-5. Selecciona productos del catálogo maestro con existencia y precio
    r = cliente.post(f'/inventario/{comercio.id}/agregar', data={
        'producto_id': [tomate.id],
        f'existencia_{tomate.id}': '3', f'minimo_{tomate.id}': '10',
        f'maximo_{tomate.id}': '40', f'precio_{tomate.id}': '25.50'})
    assert r.status_code == 302
    renglon = InventarioComercio.query.filter_by(comercio_id=comercio.id, producto_id=tomate.id).one()
    assert renglon.existencia == 3 and renglon.estado == 'BAJO'

    # 6. El público consulta disponibilidad (tras la validación municipal)
    entrar(cliente, 'coordinador@test.mx')
    assert cliente.post(f'/comercios/{comercio.id}/validar', data={'estado': 'VERIFICADO'}).status_code == 302
    cliente.get('/logout')
    r = cliente.get('/disponibilidad?q=Tomate&zona_id=%d' % comercio.zona_id)
    assert 'Puesto de prueba' in r.get_data(as_text=True)

    # 7. El comerciante detecta bajo inventario
    entrar(cliente, email)
    r = cliente.get('/inventario')
    assert 'Por surtir' in r.get_data(as_text=True)

    # 8. Consulta precios de proveedores
    r = cliente.get(f'/proveedores/buscar?producto_id={tomate.id}&comercio_id={comercio.id}')
    assert bodega.nombre_empresa in r.get_data(as_text=True)

    # 9-10. Brechas y recomendaciones: leche tiene baja cobertura en García Norte
    r = cliente.get(f'/recomendaciones?comercio_id={comercio.id}')
    assert leche.nombre in r.get_data(as_text=True)

    # 11. Crea el pedido de abasto y lo envía
    r = cliente.post('/pedidos/nuevo', data={'comercio_id': comercio.id, 'proveedor_id': bodega.id,
                                             'producto_id': tomate.id, 'cantidad': '40'})
    assert r.status_code == 302
    pedido = PedidoAbasto.query.filter_by(comercio_id=comercio.id).one()
    assert pedido.estado == 'BORRADOR'
    cliente.post(f'/pedidos/{pedido.id}/accion/enviar')
    db.session.refresh(pedido)
    assert pedido.estado == 'ENVIADO', 'El pedido debió enviarse (¿no alcanzó el pedido mínimo?)'

    # 12-14. El proveedor lo recibe, lo acepta y actualiza el estado
    entrar(cliente, 'proveedor3@test.mx')
    assert pedido.folio_legible in cliente.get('/pedidos').get_data(as_text=True)
    for accion, estado in (('aceptar', 'ACEPTADO'), ('preparar', 'EN_PREPARACION'),
                           ('despachar', 'ENVIADO_A_COMERCIO')):
        cliente.post(f'/pedidos/{pedido.id}/accion/{accion}')
        db.session.refresh(pedido)
        assert pedido.estado == estado

    # 15-16. El comerciante confirma la recepción y su inventario aumenta
    entrar(cliente, email)
    cliente.post(f'/pedidos/{pedido.id}/accion/recibir')
    db.session.refresh(pedido)
    db.session.refresh(renglon)
    assert pedido.estado == 'ENTREGADO'
    assert renglon.existencia == Decimal('43')
    assert pedido.comision_plataforma > 0

    # 17. Todo quedó en auditoría
    cambios = AuditoriaEvento.query.filter_by(entidad='PedidoAbasto', entidad_id=str(pedido.id),
                                              tipo_evento='CAMBIO_ESTADO').count()
    assert cambios == 5
    assert [h.estado_nuevo for h in pedido.historial] == [
        'BORRADOR', 'ENVIADO', 'ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO', 'ENTREGADO']


def test_no_se_envia_pedido_bajo_minimo(cliente):
    """RN-004: un pedido que no alcanza el mínimo del proveedor se queda en borrador."""
    entrar(cliente, 'comerciante@test.mx')
    comercio = Comercio.query.filter_by(nombre_comercio='Tianguis Los Nogales - Puesto 7').one()
    distribuidora = Proveedor.query.filter_by(nombre_empresa='Distribuidora Regia de Abarrotes').one()
    arroz = producto('Arroz blanco 1 kg')
    # Cancelar borradores de corridas anteriores para empezar desde cero
    for previo in PedidoAbasto.query.filter_by(comercio_id=comercio.id, proveedor_id=distribuidora.id,
                                               estado='BORRADOR'):
        cliente.post(f'/pedidos/{previo.id}/accion/cancelar')
    cliente.post('/pedidos/nuevo', data={'comercio_id': comercio.id, 'proveedor_id': distribuidora.id,
                                         'producto_id': arroz.id, 'cantidad': '12'})
    pedido = PedidoAbasto.query.filter_by(comercio_id=comercio.id, proveedor_id=distribuidora.id,
                                          estado='BORRADOR').one()
    r = cliente.post(f'/pedidos/{pedido.id}/accion/enviar', follow_redirects=True)
    assert re.search('pedido mínimo', r.get_data(as_text=True))
    db.session.refresh(pedido)
    assert pedido.estado == 'BORRADOR'


def test_salida_mayor_a_existencia_se_rechaza(cliente):
    """RN-009: la existencia nunca queda negativa."""
    entrar(cliente, 'comerciante@test.mx')
    comercio = Comercio.query.filter_by(nombre_comercio='Tianguis Los Nogales - Puesto 7').one()
    renglon = InventarioComercio.query.filter_by(comercio_id=comercio.id,
                                                 producto_id=producto('Papa blanca').id).one()
    antes = renglon.existencia
    cliente.post(f'/inventario/item/{renglon.id}/movimiento',
                 data={'tipo': 'SALIDA', 'cantidad': str(antes + 100), 'motivo': 'Venta'})
    db.session.refresh(renglon)
    assert renglon.existencia == antes


def test_permisos_por_rol(cliente):
    entrar(cliente, 'comerciante@test.mx')
    assert cliente.get('/auditoria').status_code == 403
    assert cliente.get('/admin/usuarios').status_code == 403
    entrar(cliente, 'auditor@test.mx')
    assert cliente.get('/auditoria').status_code == 200
    assert cliente.get('/inventario').status_code == 403
    entrar(cliente, 'analista@test.mx')
    assert cliente.get('/analisis/brechas').status_code == 200
    assert cliente.get('/pedidos/nuevo').status_code in (403, 405)


@pytest.mark.parametrize('ruta', ['/', '/disponibilidad', '/puntos-de-venta', '/acerca', '/login', '/registro',
                                  '/health'])
def test_paginas_publicas(cliente, ruta):
    assert cliente.get(ruta).status_code == 200
