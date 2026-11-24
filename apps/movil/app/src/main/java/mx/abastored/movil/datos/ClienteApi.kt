package mx.abastored.movil.datos

import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** Error con el sobre estándar de los servicios ({"error": {...}}) o sin conexión (status 0). */
class ErrorApi(val status: Int, val codigo: String, override val message: String,
               val correlationId: String? = null) : Exception(message) {
    val sinConexion get() = status == 0 || status == 502 || status == 503 || status == 504
}

/** Dónde guarda la app su sesión (DataStore en el teléfono, memoria en las pruebas). */
interface AlmacenTokens {
    suspend fun leer(): Tokens?
    suspend fun guardar(tokens: Tokens?)
}

/**
 * Cliente JSON de los microservicios por el gateway HTTPS (https://<gateway>/ms/<servicio>/api/v1/...).
 *
 * - Cada petición lleva el JWT del usuario y su X-Correlation-ID.
 * - Si un servicio responde 401 (token vencido o revocado), se renueva una sola vez con el refresh token
 *   (POST /auth/renovar en ms-seguridad) y se repite la petición. Si tampoco se puede, la sesión se cierra.
 * - Sin red, o con el servicio caído, lanza ErrorApi con sinConexion = true: el repositorio decide si guarda
 *   la operación para sincronizarla después.
 */
class ClienteApi(
    private val gateway: String,
    private val almacen: AlmacenTokens,
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).build(),
) {
    val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private val tipoJson = "application/json; charset=utf-8".toMediaType()
    var alCerrarSesion: (() -> Unit)? = null

    suspend fun peticion(servicio: String, metodo: String, ruta: String, cuerpo: String? = null,
                         autenticado: Boolean = true, reintentar: Boolean = true): String =
        withContext(Dispatchers.IO) {
            val tokens = if (autenticado) almacen.leer() else null
            val solicitud = Request.Builder()
                .url("${gateway.trimEnd('/')}/ms/$servicio/api/v1$ruta")
                .header("Accept", "application/json")
                .header("X-Correlation-ID", "android-${UUID.randomUUID().toString().take(20)}")
                .apply { tokens?.let { header("Authorization", "Bearer ${it.accessToken}") } }
                .method(metodo, cuerpo?.toRequestBody(tipoJson)
                    ?: if (metodo == "POST" || metodo == "PUT" || metodo == "PATCH") "".toRequestBody(tipoJson) else null)
                .build()
            val respuesta = try {
                http.newCall(solicitud).execute()
            } catch (e: IOException) {
                throw ErrorApi(0, "sin_conexion", "Sin conexión con el servidor.")
            }
            respuesta.use {
                val texto = it.body?.string().orEmpty()
                when {
                    it.isSuccessful -> texto
                    it.code == 401 && autenticado && reintentar && renovar() ->
                        peticion(servicio, metodo, ruta, cuerpo, autenticado, reintentar = false)
                    else -> {
                        if (it.code == 401 && autenticado) {
                            almacen.guardar(null)
                            alCerrarSesion?.invoke()
                        }
                        throw error(it.code, texto)
                    }
                }
            }
        }

    private fun error(status: Int, texto: String): ErrorApi = try {
        val e = json.decodeFromString<SobreError>(texto).error
        val detalles = e.detalles.joinToString("") { d -> "\n· ${d.campo.orEmpty()}: ${d.mensaje.orEmpty()}" }
        ErrorApi(status, e.codigo, e.mensaje + detalles, e.correlationId)
    } catch (_: Exception) {
        ErrorApi(status, "error_http", "El servidor respondió $status.")
    }

    private suspend fun renovar(): Boolean {
        val refresh = almacen.leer()?.refreshToken ?: return false
        return try {
            val cuerpo = buildJsonObject { put("refresh_token", refresh) }.toString()
            val texto = peticion("seguridad", "POST", "/auth/renovar", cuerpo, autenticado = false, reintentar = false)
            val nuevos = json.decodeFromString<Tokens>(texto)
            almacen.guardar(nuevos.copy(usuario = nuevos.usuario ?: almacen.leer()?.usuario))
            true
        } catch (_: ErrorApi) {
            false
        }
    }

    suspend inline fun <reified T> get(servicio: String, ruta: String): T =
        json.decodeFromString(peticion(servicio, "GET", ruta))

    suspend inline fun <reified E, reified T> enviar(servicio: String, metodo: String, ruta: String, cuerpo: E): T =
        json.decodeFromString(peticion(servicio, metodo, ruta, json.encodeToString(cuerpo)))
}
