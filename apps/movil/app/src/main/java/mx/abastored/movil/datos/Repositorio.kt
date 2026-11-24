package mx.abastored.movil.datos

import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import mx.abastored.movil.BuildConfig
import mx.abastored.movil.datos.local.BaseLocal
import mx.abastored.movil.datos.local.CopiaInventario
import mx.abastored.movil.datos.local.OperacionPendiente

/** Resultado de una captura: se aplicó en el servidor o quedó guardada en el teléfono para sincronizar. */
sealed interface Captura {
    data class Enviada(val mensaje: String) : Captura
    data class Guardada(val mensaje: String) : Captura
}

data class InventarioLocal(val inventario: Inventario, val deCopia: Boolean, val fechaCopia: Long? = null)

/**
 * Acceso a los datos de la app. Cada operación va al microservicio dueño:
 *   ms-seguridad (sesión) · ms-comercios · ms-inventario · ms-ventas · ms-precios · ms-pedidos · ms-sincronizacion.
 *
 * Sin conexión, la venta, la entrada/salida y el cambio de precio se guardan en Room con un UUID y se mandan
 * después en un lote a ms-sincronizacion, que las aplica en el servicio dueño sin duplicarlas.
 * RN-005: una captura de más de 48 horas ya no se envía (se marca para que el usuario la revise).
 */
class Repositorio(
    val api: ClienteApi,
    private val sesion: AlmacenSesion,
    private val base: BaseLocal,
) {
    private val json get() = api.json
    val pendientes = base.operaciones().observar()

    suspend fun usuario(): Usuario? = sesion.leer()?.usuario

    // ------------------------------------------------------------ sesión
    suspend fun iniciarSesion(email: String, password: String): Usuario {
        val cuerpo = buildJsonObject { put("email", email); put("password", password); put("origen", "movil") }
        val tokens = json.decodeFromString<Tokens>(
            api.peticion("seguridad", "POST", "/auth/login", cuerpo.toString(), autenticado = false))
        sesion.guardar(tokens)
        return tokens.usuario!!
    }

    suspend fun cerrarSesion() {
        try { api.peticion("seguridad", "POST", "/auth/logout") } catch (_: ErrorApi) { }
        sesion.guardar(null)
    }

    // ------------------------------------------------------------ consultas
    suspend fun comercios(): List<Comercio> = api.get<ListaComercios>("comercios", "/comercios").items

    suspend fun inventario(comercioId: String): InventarioLocal = try {
        val texto = api.peticion("inventario", "GET", "/comercios/$comercioId/inventario?por_pagina=200")
        base.copias().guardar(CopiaInventario(comercioId, texto, System.currentTimeMillis()))
        InventarioLocal(json.decodeFromString(texto), deCopia = false)
    } catch (e: ErrorApi) {
        val copia = base.copias().leer(comercioId)
        if (!e.sinConexion || copia == null) throw e
        InventarioLocal(json.decodeFromString(copia.json), deCopia = true, fechaCopia = copia.fecha)
    }

    suspend fun pedidos(): List<Pedido> = api.get<ListaPedidos>("pedidos", "/pedidos?por_pagina=50").pedidos

    suspend fun pedido(id: String): Pedido = api.get("pedidos", "/pedidos/$id")

    suspend fun accionPedido(id: String, accion: String): Pedido =
        json.decodeFromString(api.peticion("pedidos", "POST", "/pedidos/$id/acciones/$accion", "{}"))

    // ------------------------------------------------------------ capturas (en línea o sin conexión)
    suspend fun venta(renglon: Renglon, cantidad: Double, metodoPago: String): Captura {
        val id = UUID.randomUUID().toString()
        val cuerpo = buildJsonObject {
            put("comercio_id", renglon.comercioId); put("origen", "android"); put("id_cliente", id)
            put("metodo_pago", metodoPago)
            putJsonArray("partidas") { addJsonObject { put("inventario_id", renglon.id); put("cantidad", cantidad) } }
        }
        return enLineaOGuardar(
            enLinea = {
                val venta = json.decodeFromString<Venta>(api.peticion("ventas", "POST", "/ventas", cuerpo.toString()))
                "Venta ${venta.folio} registrada por $${"%.2f".format(venta.total)}."
            },
            operacion = OperacionPendiente(
                id = id, tipo = "venta", realizada = ahora(), versionBase = null,
                descripcion = "Venta: ${formatoCantidad(cantidad)} ${renglon.unidad} de ${renglon.producto}",
                datosJson = buildJsonObject {
                    put("comercio_id", renglon.comercioId); put("metodo_pago", metodoPago)
                    putJsonArray("partidas") {
                        addJsonObject { put("producto_id", renglon.productoId); put("cantidad", cantidad) }
                    }
                }.toString()))
    }

    suspend fun movimiento(renglon: Renglon, tipo: String, cantidad: Double, motivo: String?): Captura {
        val id = UUID.randomUUID().toString()
        val cuerpo = buildJsonObject {
            put("tipo", tipo); put("cantidad", cantidad); put("motivo", motivo); put("referencia", "android:$id")
        }
        return enLineaOGuardar(
            enLinea = {
                api.peticion("inventario", "POST", "/inventario/${renglon.id}/movimientos", cuerpo.toString())
                "${if (tipo == "ENTRADA") "Entrada" else "Salida"} de ${formatoCantidad(cantidad)} registrada."
            },
            operacion = OperacionPendiente(
                id = id, tipo = "movimiento_inventario", realizada = ahora(), versionBase = null,
                descripcion = "${tipo.lowercase().replaceFirstChar { it.uppercase() }}: " +
                    "${formatoCantidad(cantidad)} ${renglon.unidad} de ${renglon.producto}",
                datosJson = buildJsonObject {
                    put("inventario_id", renglon.id); put("tipo_movimiento", tipo); put("cantidad", cantidad)
                    put("motivo", motivo ?: "Capturado sin conexión")
                }.toString()))
    }

    suspend fun precio(renglon: Renglon, precio: Double): Captura {
        val cuerpo = buildJsonObject { put("precio", precio); put("metodo_captura", "MOVIL") }
        return enLineaOGuardar(
            enLinea = {
                val cambio = json.decodeFromString<CambioPrecio>(
                    api.peticion("precios", "PUT", "/inventario/${renglon.id}/precio", cuerpo.toString()))
                if (cambio.estadoValidacion == "PENDIENTE_VALIDACION")
                    "Precio guardado, pero quedó en revisión: está muy lejos del promedio de tu zona."
                else "Precio actualizado a $${"%.2f".format(precio)}."
            },
            // version_base: cuándo vio el teléfono el renglón. Si el servidor lo cambió después, hay conflicto.
            operacion = OperacionPendiente(
                id = UUID.randomUUID().toString(), tipo = "precio", realizada = ahora(),
                versionBase = renglon.actualizado,
                descripcion = "Precio de ${renglon.producto}: $${"%.2f".format(precio)}",
                datosJson = buildJsonObject { put("inventario_id", renglon.id); put("precio", precio) }.toString()))
    }

    private suspend fun enLineaOGuardar(enLinea: suspend () -> String, operacion: OperacionPendiente): Captura =
        try {
            Captura.Enviada(enLinea())
        } catch (e: ErrorApi) {
            if (!e.sinConexion) throw e
            base.operaciones().agregar(operacion)
            Captura.Guardada("Sin conexión: se guardó en el teléfono y se enviará al sincronizar.")
        }

    // ------------------------------------------------------------ sincronización
    @Serializable
    data class Sincronizacion(val enviadas: Int, val aplicadas: Int, val conRevision: Int, val pendientes: Int)

    suspend fun sincronizar(): Sincronizacion {
        val porEnviar = base.operaciones().porEnviar()
        val limite = OffsetDateTime.now().minus(Duration.ofHours(48))
        val (vencidas, vigentes) = porEnviar.partition { OffsetDateTime.parse(it.realizada).isBefore(limite) }
        vencidas.forEach {
            base.operaciones().marcar(it.id, "rechazada", "Tiene más de 48 horas; ya no se envía (RN-005).")
        }
        if (vigentes.isEmpty()) return Sincronizacion(0, 0, vencidas.size, 0)

        val lote = Lote(
            loteId = UUID.randomUUID().toString(), dispositivoId = sesion.dispositivoId(),
            versionApp = BuildConfig.VERSION_NAME,
            operaciones = vigentes.map {
                OperacionLote(it.id, it.tipo, it.realizada, it.versionBase,
                    json.decodeFromString<JsonObject>(it.datosJson))
            })
        val respuesta = json.decodeFromString<RespuestaLote>(
            api.peticion("sincronizacion", "POST", "/lotes", json.encodeToString(lote)))
        val terminadas = mutableListOf<String>()
        var revision = vencidas.size
        for (r in respuesta.resultados) {
            when (r.estado) {
                "aplicada", "duplicada" -> terminadas += r.operacionId
                "conflicto", "rechazada" -> {
                    revision++
                    base.operaciones().marcar(r.operacionId, r.estado, r.mensaje)
                }
                // pendiente_reintento: el servicio dueño no respondió; se queda para el siguiente intento
            }
        }
        if (terminadas.isNotEmpty()) base.operaciones().quitar(terminadas)
        return Sincronizacion(vigentes.size, terminadas.size, revision, respuesta.pendientes)
    }

    suspend fun descartarRevisadas() = base.operaciones().limpiarRevisadas()

    companion object {
        fun ahora(): String = OffsetDateTime.now().toString()
        fun formatoCantidad(c: Double) = if (c % 1.0 == 0.0) c.toLong().toString() else "%.2f".format(c)
    }
}

