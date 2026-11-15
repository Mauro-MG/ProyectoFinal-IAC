from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from abasto_api import BaseConsulta, BaseEntrada
from abasto_api.modelos_comunes import Salida

Destino = Literal['catalogo_proveedor', 'inventario', 'precios']
Formato = Literal['csv', 'json', 'xml']


# ------------------------------------------------ filas (contrato de cada destino, se valida fila por fila)
class _Producto(BaseEntrada):
    producto_id: int | None = Field(None, ge=1)
    codigo_barras: str | None = Field(None, pattern=r'^\d{8,14}$')
    producto: str | None = Field(None, max_length=200, description='Nombre exacto en el catálogo maestro')

    @model_validator(mode='after')
    def _identificado(self):
        if not (self.producto_id or self.codigo_barras or self.producto):
            raise ValueError('cada fila necesita producto_id, codigo_barras o producto')
        return self


class FilaCatalogo(_Producto):
    precio_mayoreo: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    cantidad_minima: Decimal = Field(1, gt=0, max_digits=10, decimal_places=2)
    existencia_disponible: Decimal = Field(0, ge=0, max_digits=12, decimal_places=2)


class FilaInventario(_Producto):
    existencia: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    stock_minimo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    stock_maximo: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    precio_venta: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)


class FilaPrecio(_Producto):
    precio: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class ImportacionCatalogo(BaseEntrada):
    """Documento XML de importación del catálogo mayorista."""
    filas: list[FilaCatalogo] = Field(min_length=1, max_length=2000)


class ImportacionInventario(BaseEntrada):
    filas: list[FilaInventario] = Field(min_length=1, max_length=2000)


class ImportacionPrecios(BaseEntrada):
    filas: list[FilaPrecio] = Field(min_length=1, max_length=2000)


class ConectorEntrada(BaseEntrada):
    nombre: str = Field(min_length=3, max_length=80)
    destino: Destino
    formato: Formato
    separador: Literal[',', ';', '|', '\t'] = ','
    mapeo: dict[str, str] = Field(default_factory=dict,
                                  description='campo_destino -> columna del archivo del proveedor, p. ej. {"precio_mayoreo": "PRECIO"}')
    valores_fijos: dict[str, str] = Field(default_factory=dict, description='campo_destino -> valor para todas las filas')
    descripcion: str | None = Field(None, max_length=300)


class ImportacionesConsulta(BaseConsulta):
    limite: int = Field(20, ge=1, le=100)


class ExportacionConsulta(BaseConsulta):
    archivo: Formato = Field('csv', description='Formato del archivo exportado (csv, json o xml)')
    comercio_id: str | None = Field(None, description='Para exportar el inventario o los precios de un comercio')


# ---------------------------------------------------------------- salidas
class ErrorFila(Salida):
    fila: int
    campo: str | None = None
    error: str


class LoteSalida(Salida):
    id: str
    destino: Destino
    formato: Formato
    archivo: str
    conector: str | None = None
    simulacion: bool
    fecha: datetime
    filas: int
    validas: int
    aplicadas: int
    creadas: int
    actualizadas: int
    con_error: int
    errores: list[ErrorFila]


class LotesSalida(Salida):
    total: int
    lotes: list[LoteSalida]


class ConectorSalida(Salida):
    id: str
    nombre: str
    destino: Destino
    formato: Formato
    separador: str
    mapeo: dict
    valores_fijos: dict
    descripcion: str | None = None
    creado: datetime


class ConectoresSalida(Salida):
    conectores: list[ConectorSalida]


CONTRATOS_XML = {
    'importacion_catalogo': ImportacionCatalogo, 'importacion_inventario': ImportacionInventario,
    'importacion_precios': ImportacionPrecios, 'conector_entrada': ConectorEntrada,
    'lote': LoteSalida, 'lotes': LotesSalida, 'conector': ConectorSalida, 'conectores': ConectoresSalida,
}
