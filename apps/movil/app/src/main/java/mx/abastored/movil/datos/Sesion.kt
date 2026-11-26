package mx.abastored.movil.datos

import android.content.Context
import android.util.Base64
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import java.security.SecureRandom
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.Json

private val Context.almacen by preferencesDataStore(name = "sesion")
private val TOKENS = stringPreferencesKey("tokens_cifrados")
private val DISPOSITIVO = stringPreferencesKey("dispositivo_cifrado")

/**
 * Sesión y token del dispositivo en el almacenamiento privado de la app (DataStore), CIFRADOS con la llave del
 * Android Keystore (ver Cifrado). La sesión sobrevive a cerrar la app; se borra al cerrar sesión, si el refresh
 * token ya no sirve o si el servidor revocó el dispositivo.
 */
class AlmacenSesion(private val contexto: Context) : AlmacenTokens {
    private val json = Json { ignoreUnknownKeys = true }
    @Volatile private var cache: Tokens? = null

    override suspend fun leer(): Tokens? = cache ?: contexto.almacen.data.first()[TOKENS]
        ?.let { Cifrado.descifrar(it) }?.let { json.decodeFromString<Tokens>(it) }?.also { cache = it }

    override suspend fun guardar(tokens: Tokens?) {
        cache = tokens
        contexto.almacen.edit {
            if (tokens == null) it.remove(TOKENS) else it[TOKENS] = Cifrado.cifrar(json.encodeToString(tokens))
        }
    }

    /**
     * Token del dispositivo: 256 bits aleatorios (SecureRandom), cifrados en el teléfono. Se registra en
     * ms-notificaciones (POST /dispositivos) ligado al usuario; el servidor puede revocarlo y la app lo comprueba.
     */
    suspend fun tokenDispositivo(): String {
        contexto.almacen.data.first()[DISPOSITIVO]?.let { Cifrado.descifrar(it) }?.let { return it }
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val token = "android-" + Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        contexto.almacen.edit { it[DISPOSITIVO] = Cifrado.cifrar(token) }
        return token
    }

    /** Identificador estable del teléfono para ms-sincronizacion (no es secreto: los primeros caracteres). */
    suspend fun dispositivoId(): String = tokenDispositivo().take(24)

    suspend fun olvidarDispositivo() = contexto.almacen.edit { it.remove(DISPOSITIVO) }
}
