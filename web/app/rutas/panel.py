"""Panel principal: cada perfil ve los indicadores de su trabajo diario."""
from flask import render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from app import app
from app.extensions import db
from app.models import (AuditoriaEvento, CatalogoProveedor, Comercio, InventarioComercio, PedidoAbasto, Proveedor,
                        Usuario)
from app.servicios import analisis, notificaciones
from app.servicios.parametros import parametro

PEDIDOS_EN_CURSO = ('ENVIADO', 'ACEPTADO', 'EN_PREPARACION', 'ENVIADO_A_COMERCIO')


def _datos_comerciante():
    comercios = Comercio.query.filter_by(usuario_id=current_user.id, activo=True).order_by(Comercio.nombre_comercio).all()
    ids = [c.id for c in comercios]
    datos = {'comercios': comercios, 'faltantes': [], 'recomendaciones': []}
    if not comercios:
        return datos
    datos['productos'] = InventarioComercio.query.filter(InventarioComercio.comercio_id.in_(ids),
                                                          InventarioComercio.activo.is_(True)).count()
    for comercio in comercios:
        datos['faltantes'] += [{**f, 'comercio': comercio} for f in analisis.faltantes(comercio)]
    datos['recomendaciones'] = analisis.recomendaciones(comercios[0])[:4]
    datos['pedidos'] = (PedidoAbasto.query.filter(PedidoAbasto.comercio_id.in_(ids),
                                                  PedidoAbasto.estado.in_(('BORRADOR',) + PEDIDOS_EN_CURSO))
                        .order_by(PedidoAbasto.updated_at.desc()).all())
    return datos


def _datos_proveedor():
    proveedor = current_user.proveedor
    if not proveedor:
        return {'proveedor': None}
    pedidos = (PedidoAbasto.query.filter(PedidoAbasto.proveedor_id == proveedor.id,
                                         PedidoAbasto.estado.in_(PEDIDOS_EN_CURSO))
               .order_by(PedidoAbasto.fecha_envio).all())
    return {
        'proveedor': proveedor,
        'por_atender': [p for p in pedidos if p.estado == 'ENVIADO'],
        'en_proceso': [p for p in pedidos if p.estado != 'ENVIADO'],
        'ofertas': CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id, activo=True).count(),
        'sin_existencia': CatalogoProveedor.query.filter_by(proveedor_id=proveedor.id, activo=True)
                                                .filter(CatalogoProveedor.existencia_disponible <= 0).count(),
        'vendido_mes': db.session.query(func.coalesce(func.sum(PedidoAbasto.subtotal), 0))
                         .filter(PedidoAbasto.proveedor_id == proveedor.id, PedidoAbasto.estado == 'ENTREGADO',
                                 PedidoAbasto.fecha_entrega_real >= func.date_trunc('month', func.now()))
                         .scalar(),
    }


def _datos_admin():
    por_estado = dict(db.session.query(PedidoAbasto.estado, func.count(PedidoAbasto.id))
                      .group_by(PedidoAbasto.estado).all())
    destacados = Proveedor.query.filter_by(activo=True, plan='DESTACADO').count()
    return {
        'usuarios': Usuario.query.filter_by(activo=True).count(),
        'comercios_pendientes': Comercio.query.filter_by(activo=True, estado_registro='PENDIENTE').count(),
        'pedidos_por_estado': por_estado,
        'comisiones': db.session.query(func.coalesce(func.sum(PedidoAbasto.comision_plataforma), 0)).scalar(),
        'destacados': destacados,
        'ingreso_suscripciones': destacados * parametro('PRECIO_DESTACADO_MENSUAL'),
    }


@app.route('/panel')
@login_required
def panel():
    datos = {}
    if current_user.tiene_permiso('inventario.gestionar') and current_user.tiene_permiso('pedidos.crear'):
        datos['comerciante'] = _datos_comerciante()
    if current_user.tiene_permiso('pedidos.atender'):
        datos['proveedor'] = _datos_proveedor()
    if current_user.tiene_permiso('analisis.ver'):
        zonas = analisis.indicadores_zonas()
        datos['analisis'] = {'zonas': zonas[:3], 'total_zonas': len(zonas),
                             'criticas': sum(1 for z in zonas if z['clasificacion'] == 'Crítico')}
    if current_user.tiene_permiso('usuarios.gestionar'):
        datos['admin'] = _datos_admin()
    if current_user.tiene_permiso('auditoria.ver'):
        datos['auditoria'] = (AuditoriaEvento.query.order_by(AuditoriaEvento.created_at.desc()).limit(8).all())

    avisos = notificaciones.recientes(current_user.id)
    return render_template('panel.html', datos=datos, avisos=avisos)
