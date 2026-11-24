package mx.abastored.movil.datos

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import java.util.UUID
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.Json

private val Context.almacen by preferencesDataStore(name = "sesion")
private val TOKENS = stringPreferencesKey("tokens")
private val DISPOSITIVO = stringPreferencesKey("dispositivo_id")

/**
 * Tokens en el almacenamiento privado de la app (DataStore): solo esta app puede leerlos. La sesión sobrevive a
 * cerrar la app; se borra al cerrar sesión o si el refresh token ya no sirve.
 */
class AlmacenSesion(private val contexto: Context) : AlmacenTokens {
    private val json = Json { ignoreUnknownKeys = true }
    @Volatile private var cache: Tokens? = null

    override suspend fun leer(): Tokens? = cache ?: contexto.almacen.data.first()[TOKENS]
        ?.let { json.decodeFromString<Tokens>(it) }?.also { cache = it }

    override suspend fun guardar(tokens: Tokens?) {
        cache = tokens
        contexto.almacen.edit { if (tokens == null) it.remove(TOKENS) else it[TOKENS] = json.encodeToString(tokens) }
    }

    /** Identificador estable del teléfono para ms-sincronizacion (control de duplicados por dispositivo). */
    suspend fun dispositivoId(): String = contexto.almacen.data.first()[DISPOSITIVO]
        ?: "android-${UUID.randomUUID()}".also { id -> contexto.almacen.edit { it[DISPOSITIVO] = id } }
}
