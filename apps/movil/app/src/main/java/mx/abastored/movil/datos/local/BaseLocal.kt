package mx.abastored.movil.datos.local

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/**
 * Operación hecha sin conexión, esperando a sincronizarse con ms-sincronizacion.
 * `id` es el operacion_id (UUID generado en el teléfono): si el lote se reenvía, el servidor la reconoce
 * como duplicada y no la aplica dos veces.
 */
@Entity(tableName = "operaciones_pendientes")
data class OperacionPendiente(
    @PrimaryKey val id: String,
    val tipo: String,             // venta | movimiento_inventario | precio
    val descripcion: String,      // para mostrarla en la pantalla de pendientes
    val realizada: String,        // ISO-8601 con zona
    val versionBase: String?,     // updated_at del renglón que vio el teléfono (conflictos de precio)
    val datosJson: String,
    val estado: String = "pendiente",   // pendiente | conflicto | rechazada
    val mensaje: String? = null,
)

/** Última copia del inventario de cada comercio, para consultarlo sin conexión. */
@Entity(tableName = "inventario_copia")
data class CopiaInventario(@PrimaryKey val comercioId: String, val json: String, val fecha: Long)

@Dao
interface OperacionesDao {
    @Query("SELECT * FROM operaciones_pendientes ORDER BY realizada")
    fun observar(): Flow<List<OperacionPendiente>>

    @Query("SELECT * FROM operaciones_pendientes WHERE estado = 'pendiente' ORDER BY realizada")
    suspend fun porEnviar(): List<OperacionPendiente>

    @Insert
    suspend fun agregar(operacion: OperacionPendiente)

    @Query("DELETE FROM operaciones_pendientes WHERE id IN (:ids)")
    suspend fun quitar(ids: List<String>)

    @Query("UPDATE operaciones_pendientes SET estado = :estado, mensaje = :mensaje WHERE id = :id")
    suspend fun marcar(id: String, estado: String, mensaje: String?)

    @Query("DELETE FROM operaciones_pendientes WHERE estado != 'pendiente'")
    suspend fun limpiarRevisadas()
}

@Dao
interface CopiasDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun guardar(copia: CopiaInventario)

    @Query("SELECT * FROM inventario_copia WHERE comercioId = :comercioId")
    suspend fun leer(comercioId: String): CopiaInventario?
}

@Database(entities = [OperacionPendiente::class, CopiaInventario::class], version = 1, exportSchema = false)
abstract class BaseLocal : RoomDatabase() {
    abstract fun operaciones(): OperacionesDao
    abstract fun copias(): CopiasDao

    companion object {
        fun crear(contexto: Context) =
            Room.databaseBuilder(contexto, BaseLocal::class.java, "abastored.db").build()
    }
}
