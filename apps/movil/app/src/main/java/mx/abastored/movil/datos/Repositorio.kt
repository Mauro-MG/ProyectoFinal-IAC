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
        // Baja del dispositivo y revocación del token en el servidor; después se borra la sesión local
        try { api.peticion("notificaciones", "DELETE", "/dispositivos/${sesion.tokenDispositivo()}") } catch (_: ErrorApi) { }
        try { api.peticion("seguridad", "POST", "/auth/logout") } catch (_: ErrorApi) { }
        sesion.guardar(null)
        sesion.olvidarDispositivo()
    }

    /** Registro simplificado (ms-seguridad POST /auth/registro): la cuenta queda con sesión iniciada. */
    suspend fun registrarse(nombre: String, apellido: String, email: String, password: String, telefono: String?,
                            perfil: String): Usuario {
        val cuerpo = buildJsonObject {
            put("nombre", nombre); put("apellido_paterno", apellido); put("email", email); put("password", password)
            put("telefono", telefono); put("perfil", perfil); put("origen", "movil")
        }
        val tokens = json.decodeFromString<Tokens>(
            api.peticion("seguridad", "POST", "/auth/registro", cuerpo.toString(), autenticado = false))
        sesion.guardar(tokens)
        return tokens.usuario!!
    }

    // ------------------------------------------------------------ dispositivo
    /**
     * Registra este teléfono en ms-notificaciones con su token aleatorio cifrado (POST /dispositivos). Al abrir la app
     * con sesión guardada, `dispositivoVigente` comprueba que el servidor lo siga teniendo: si se revocó (desde el web
     * o por un administrador), la app cierra la sesión. No basta con tener el token guardado en el teléfono.
     */
    suspend fun registrarDispositivo(nombre: String) {
        api.peticion("notificaciones", "POST", "/dispositivos", buildJsonObject {
            put("token", sesion.tokenDispositivo()); put("plataforma", "android"); put("nombre", nombre)
        }.toString())
    }

    suspend fun dispositivoVigente(): Boolean {
        val token = sesion.tokenDispositivo()
        return api.get<ListaDispositivos>("notificaciones", "/dispositivos").dispositivos.any { it.token == token }
    }

    // ------------------------------------------------------------ perfil y comercio
    suspend fun perfil(): Perfil = api.get("seguridad", "/usuarios/me")

    suspend fun cambiarPassword(actual: String, nueva: String) {
        api.peticion("seguridad", "PUT", "/usuarios/me/password",
            buildJsonObject { put("password_actual", actual); put("password_nueva", nueva) }.toString())
    }

    /** Alta del comercio con la ubicación del teléfono; ms-comercios asigna la zona por coordenadas (RN-016). */
    suspend fun registrarComercio(nombre: String, tipo: String, direccion: String, municipio: String,
                                  latitud: Double?, longitud: Double?): Comercio =
        json.decodeFromString(api.peticion("comercios", "POST", "/comercios", buildJsonObject {
            put("nombre_comercio", nombre); put("tipo_comercio", tipo); put("direccion", direccion)
            put("municipio", municipio); put("estado", "Nuevo León")
            latitud?.let { put("latitud", "%.6f".format(java.util.Locale.US, it)) }
            longitud?.let { put("longitud", "%.6f".format(java.util.Locale.US, it)) }
        }.toString()))

    /** Foto del comercio: el archivo va a ms-documentos (bucket) y ms-comercios la fija como foto principal. */
    suspend fun subirFotoComercio(comercioId: String, jpeg: ByteArray): String {
        val documento = json.decodeFromString<Documento>(api.subir("documentos", "/documentos",
            mapOf("categoria" to "foto_comercio", "entidad" to "comercio", "entidad_id" to comercioId,
                  "descripcion" to "Foto tomada con la app"), "fachada.jpg", "image/jpeg", jpeg))
        api.peticion("comercios", "PUT", "/comercios/$comercioId/foto",
            buildJsonObject { put("documento_id", documento.id) }.toString())
        return documento.id
    }

    // ------------------------------------------------------------ catálogo y alta de productos
    suspend fun buscarProductos(texto: String): List<Producto> =
        api.get<ListaProductos>("catalogo", "/productos?por_pagina=50&texto=${java.net.URLEncoder.encode(texto, "UTF-8")}")
            .productos

    /** Producto por código de barras (lector de la cámara). null si no está en el catálogo. */
    suspend fun productoPorCodigo(codigo: String): Producto? = try {
        api.get("catalogo", "/productos/codigo/${java.net.URLEncoder.encode(codigo, "UTF-8")}")
    } catch (e: ErrorApi) {
        if (e.status == 404) null else throw e
    }

    suspend fun agregarProducto(comercioId: String, productoId: Int, existencia: Double, minimo: Double,
                                precio: Double?): Renglon =
        json.decodeFromString(api.peticion("inventario", "POST", "/comercios/$comercioId/inventario", buildJsonObject {
            put("producto_id", productoId); put("existencia", existencia); put("stock_minimo", minimo)
            precio?.let { put("precio_venta", it) }
        }.toString()))

    // ------------------------------------------------------------ abasto
    suspend fun recomendaciones(comercioId: String): ListaRecomendaciones =
        api.get("recomendaciones", "/recomendaciones/$comercioId")

    suspend fun responderRecomendacion(comercioId: String, productoId: Int, respuesta: String) {
        api.peticion("recomendaciones", "POST", "/recomendaciones/$comercioId/respuestas", buildJsonObject {
            put("producto_id", productoId); put("respuesta", respuesta)
        }.toString())
    }

    suspend fun proveedoresSugeridos(comercioId: String): List<ProveedorSugerido> =
        api.get<ListaProveedores>("proveedores", "/comercios/$comercioId/proveedores-sugeridos").proveedores

    suspend fun ofertas(productoId: Int, zonaId: Int?): List<Oferta> =
        api.get<ListaOfertas>("proveedores", "/ofertas?producto_id=$productoId" + (zonaId?.let { "&zona_id=$it" } ?: ""))
            .ofertas.filter { it.cubreZona }

    /** Solicitud de abasto: abre (o reutiliza) el borrador con el proveedor, agrega la partida y lo envía. */
    suspend fun solicitarAbasto(comercioId: String, oferta: Oferta, cantidad: Double, enviar: Boolean): Pedido {
        val borrador = json.decodeFromString<Pedido>(api.peticion("pedidos", "POST", "/pedidos", buildJsonObject {
            put("comercio_id", comercioId); put("proveedor_id", oferta.proveedorId)
            putJsonArray("partidas") { addJsonObject { put("producto_id", oferta.productoId); put("cantidad", cantidad) } }
        }.toString()))
        return if (enviar) accionPedido(borrador.id, "enviar") else borrador
    }

    // ------------------------------------------------------------ notificaciones y entregas
    suspend fun notificaciones(): ListaNotificaciones =
        api.get("notificaciones", "/notificaciones?por_pagina=50")

    suspend fun noLeidas(): Int = api.get<Contador>("notificaciones", "/notificaciones/contador").noLeidas

    suspend fun marcarLeida(id: String) {
        api.peticion("notificaciones", "PATCH", "/notificaciones/$id", buildJsonObject { put("leida", true) }.toString())
    }

    suspend fun entregaDePedido(pedidoId: String): Entrega? = try {
        api.get("entregas", "/pedidos/$pedidoId/entrega")
    } catch (e: ErrorApi) {
        if (e.status == 404) null else throw e
    }

    /** Confirma la recepción con el código del QR que muestra el repartidor (ms-entregas valida el código). */
    suspend fun confirmarEntrega(entregaId: String, codigo: String, recibidoPor: String) {
        api.peticion("entregas", "POST", "/entregas/$entregaId/confirmacion", buildJsonObject {
            put("codigo", codigo); put("recibido_por", recibidoPor)
        }.toString())
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

