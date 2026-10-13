"""Filtros de Jinja y variables disponibles en todas las plantillas."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import request, url_for

from app import app
from abasto_dominio.modelos.comercio import TIPOS_COMERCIO
from abasto_dominio.modelos.pedido import ESTADOS_PEDIDO

# Clase CSS de la etiqueta según el estado
COLOR_ESTADO = {
    'DISPONIBLE': 'ok', 'BAJO': 'alerta', 'AGOTADO': 'critico',
    'VERIFICADO': 'ok', 'PENDIENTE': 'alerta', 'RECHAZADO': 'critico', 'SUSPENDIDO': 'neutro',
    'BORRADOR': 'neutro', 'ENVIADO': 'info', 'ACEPTADO': 'info', 'EN_PREPARACION': 'info',
    'ENVIADO_A_COMERCIO': 'alerta', 'ENTREGADO': 'ok', 'CANCELADO': 'neutro',
    'ALTA': 'critico', 'MEDIA': 'alerta', 'BAJA': 'info', 'SIN_BRECHA': 'ok',
    'PENDIENTE_VALIDACION': 'alerta', 'VALIDADO': 'ok',
}


@app.template_filter('moneda')
def moneda(valor):
    if valor is None:
        return '—'
    return f'${valor:,.2f}'


@app.template_filter('cantidad')
def cantidad(valor):
    """12.00 -> 12, 2.50 -> 2.5"""
    if valor is None:
        return '—'
    if isinstance(valor, Decimal):
        valor = valor.normalize()
        return f'{valor:f}'
    return f'{valor:g}'


HORA_MONTERREY = timezone(timedelta(hours=-6))  # sin horario de verano desde 2022


@app.template_filter('fecha')
def fecha(valor, con_hora=True):
    """
    Acepta datetime o texto ISO 8601 (lo que regresan los microservicios en
    JSON). Las fechas con zona (MongoDB guarda en UTC) se muestran en hora local.
    """
    if not valor:
        return '—'
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace('Z', '+00:00'))
        except ValueError:
            return valor
    if getattr(valor, 'tzinfo', None):  # date no tiene zona; datetime de MongoDB sí
        valor = valor.astimezone(HORA_MONTERREY)
    return valor.strftime('%d/%m/%Y %H:%M' if con_hora else '%d/%m/%Y')


@app.template_filter('porcentaje')
def porcentaje(valor):
    return '—' if valor is None else f'{valor:.1f} %'


def url_pagina(numero):
    """Misma URL con los filtros actuales, cambiando sólo la página."""
    argumentos = request.args.to_dict()
    argumentos['page'] = numero
    return url_for(request.endpoint, **(request.view_args or {}), **argumentos)


# Globales (y no context_processor) para que también las vean las macros importadas
app.jinja_env.globals.update(
    url_pagina=url_pagina,
    COLOR_ESTADO=COLOR_ESTADO,
    ESTADOS_PEDIDO=ESTADOS_PEDIDO,
    TIPOS_COMERCIO=TIPOS_COMERCIO,
)
