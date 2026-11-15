from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida

TipoOperacion = Literal['movimiento_inventario', 'venta', 'precio', 'limites_inventario', 'pedido_borrador',
                        'busqueda']
EstadoOperacion = Literal['aplicada', 'duplicada', 'conflicto', 'rechazada', 'pendiente_reintento']
Politica = Literal['servidor_gana', 'cliente_gana', 'rechazar']


class Partida(BaseEntrada):
    producto_id: int = Field(ge=1)
    cantidad: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    precio_unitario: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)


class DatosOperacion(BaseEntrada):
    """Campos según el tipo de operación (los que no aplican se omiten)."""
    comercio_id: str | None = None
    inventario_id: int | None = Field(None, ge=1)
    producto_id: int | None = Field(None, ge=1)
    proveedor_id: str | None = None
    tipo_movimiento: Literal['ENTRADA', 'SALIDA', 'AJUSTE'] | None = None
    cantidad: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    motivo: str | None = Field(None, max_length=255)
    precio: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    stock_minimo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    stock_maximo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    metodo_pago: Literal['EFECTIVO', 'TARJETA', 'TRANSFERENCIA', 'FIADO', 'OTRO'] | None = None
    partidas: list[Partida] | None = Field(None, max_length=100)
    texto: str | None = Field(None, max_length=120)
    resultados: int | None = Field(None, ge=0)
    zona_id: int | None = Field(None, ge=1)


class Operacion(BaseEntrada):
    operacion_id: str = Field(min_length=8, max_length=64, description='UUID generado en el dispositivo')
    tipo: TipoOperacion
    realizada: datetime = Field(description='Cuándo se hizo en el dispositivo (sin conexión)')
    version_base: datetime | None = Field(None, description='updated_at del dato que el dispositivo tenía al editarlo')
    datos: DatosOperacion


class LoteEntrada(BaseEntrada):
    lote_id: str = Field(min_length=8, max_length=64, description='UUID del lote generado en el dispositivo')
    dispositivo_id: str = Field(min_length=4, max_length=64)
    plataforma: Literal['android', 'escritorio']
    version_app: str | None = Field(None, max_length=20)
    politica_conflictos: Politica | None = Field(None, description='Por omisión SINCRONIZACION_POLITICA_CONFLICTO')
    operaciones: list[Operacion] = Field(min_length=1, max_length=1000)


class LotesConsulta(BaseConsulta):
    dispositivo_id: str | None = None
    limite: int = Field(20, ge=1, le=100)


class ReintentoEntrada(BaseEntrada):
    operaciones: list[str] | None = Field(None, description='operacion_id a reintentar; por omisión, todas las pendientes')


# ---------------------------------------------------------------- salidas
class ResultadoOperacion(Salida):
    operacion_id: str
    tipo: str
    estado: EstadoOperacion
    mensaje: str | None = None
    servicio: str | None = None
    id_servidor: str | None = Field(None, description='id del registro creado o afectado en el servidor')
    version_servidor: datetime | None = None
    intentos: int


class LoteSalida(Salida):
    lote_id: str
    dispositivo_id: str
    plataforma: str
    recibido: datetime
    terminado: datetime | None = None
    politica_conflictos: Politica
    total: int
    aplicadas: int
    duplicadas: int
    conflictos: int
    rechazadas: int
    pendientes: int
    resultados: list[ResultadoOperacion]


class LotesSalida(Salida):
    total: int
    lotes: list[LoteSalida]


class EstadoSalida(Salida):
    servidor: datetime
    max_operaciones: int
    politica_conflictos: Politica
    tipos: list[str]


CONTRATOS_XML = {
    'lote_entrada': LoteEntrada, 'reintento_entrada': ReintentoEntrada,
    'lote': LoteSalida, 'lotes': LotesSalida, 'estado': EstadoSalida,
}
