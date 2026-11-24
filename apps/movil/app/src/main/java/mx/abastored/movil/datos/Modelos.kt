package mx.abastored.movil.datos

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/*
 * Contratos JSON de los microservicios que usa la app (solo los campos que muestra).
 * Los nombres siguen el JSON (snake_case) con @SerialName; los campos que no se usan se ignoran.
 */

@Serializable
data class Usuario(
    val id: String,
    val email: String,
    val nombre: String,
    val apellido: String? = null,
    val rol: String,
    val permisos: List<String> = emptyList(),
)

@Serializable
data class Tokens(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String? = null,
    @SerialName("expires_in") val expiraEn: Long = 0,
    val usuario: Usuario? = null,
)

@Serializable
data class Paginacion(val pagina: Int = 1, val total: Int = 0, val paginas: Int = 0)

@Serializable
data class Comercio(
    val id: String,
    @SerialName("nombre_comercio") val nombre: String,
    val sector: String? = null,
    val municipio: String? = null,
    val zona: String? = null,
    @SerialName("estado_registro") val estadoRegistro: String? = null,
)

@Serializable
data class ListaComercios(val items: List<Comercio> = emptyList())

@Serializable
data class Renglon(
    val id: Int,
    @SerialName("comercio_id") val comercioId: String,
    @SerialName("producto_id") val productoId: Int,
    val producto: String,
    val categoria: String? = null,
    @SerialName("unidad_medida") val unidad: String = "pieza",
    val existencia: Double = 0.0,
    @SerialName("stock_minimo") val stockMinimo: Double = 0.0,
    @SerialName("stock_maximo") val stockMaximo: Double? = null,
    @SerialName("precio_venta") val precioVenta: Double? = null,
    val estado: String = "DISPONIBLE",
    @SerialName("cantidad_sugerida") val cantidadSugerida: Double = 0.0,
    val actualizado: String? = null,
)

@Serializable
data class ResumenInventario(
    val productos: Int = 0,
    val bajo: Int = 0,
    val agotado: Int = 0,
    @SerialName("valor_inventario") val valor: Double = 0.0,
)

@Serializable
data class Inventario(
    val resumen: ResumenInventario = ResumenInventario(),
    val renglones: List<Renglon> = emptyList(),
)

@Serializable
data class PartidaPedido(
    val producto: String,
    val cantidad: Double,
    @SerialName("precio_unitario") val precio: Double? = null,
    val subtotal: Double? = null,
)

@Serializable
data class Pedido(
    val id: String,
    val folio: String,
    val estado: String,
    @SerialName("estado_legible") val estadoLegible: String,
    val comercio: String? = null,
    val proveedor: String? = null,
    val subtotal: Double = 0.0,
    @SerialName("fecha_entrega_estimada") val entregaEstimada: String? = null,
    val partidas: List<PartidaPedido> = emptyList(),
    val acciones: List<String> = emptyList(),
)

@Serializable
data class ListaPedidos(val pedidos: List<Pedido> = emptyList())

@Serializable
data class Venta(val id: String, val folio: String, val total: Double)

@Serializable
data class CambioPrecio(
    @SerialName("estado_validacion") val estadoValidacion: String,
    @SerialName("promedio_zona_7_dias") val promedioZona: Double? = null,
)

// ---------------------------------------------------------------- sincronización (ms-sincronizacion)

@Serializable
data class OperacionLote(
    @SerialName("operacion_id") val operacionId: String,
    val tipo: String,
    val realizada: String,
    @SerialName("version_base") val versionBase: String? = null,
    val datos: JsonObject,
)

@Serializable
data class Lote(
    @SerialName("lote_id") val loteId: String,
    @SerialName("dispositivo_id") val dispositivoId: String,
    val plataforma: String = "android",
    @SerialName("version_app") val versionApp: String? = null,
    val operaciones: List<OperacionLote>,
)

@Serializable
data class ResultadoOperacion(
    @SerialName("operacion_id") val operacionId: String,
    val tipo: String,
    val estado: String,        // aplicada | duplicada | conflicto | rechazada | pendiente_reintento
    val mensaje: String? = null,
)

@Serializable
data class RespuestaLote(
    val aplicadas: Int = 0,
    val conflictos: Int = 0,
    val rechazadas: Int = 0,
    val pendientes: Int = 0,
    val resultados: List<ResultadoOperacion> = emptyList(),
)

// ---------------------------------------------------------------- errores (sobre estándar de todos los servicios)

@Serializable
data class DetalleError(val campo: String? = null, val mensaje: String? = null)

@Serializable
data class CuerpoError(
    val codigo: String = "error",
    val mensaje: String = "Error del servicio",
    val detalles: List<DetalleError> = emptyList(),
    @SerialName("correlation_id") val correlationId: String? = null,
)

@Serializable
data class SobreError(val error: CuerpoError)
