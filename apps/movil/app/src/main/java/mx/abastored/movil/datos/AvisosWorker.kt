package mx.abastored.movil.datos

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit
import mx.abastored.movil.AbastoApp
import mx.abastored.movil.R
import mx.abastored.movil.ui.MainActivity

/**
 * Avisos de negocio en la barra del teléfono aunque la app esté cerrada: cada 15 minutos (mínimo de Android), con
 * red, pregunta a ms-notificaciones cuántos avisos sin leer hay. Si hay más que la última vez, muestra el más
 * reciente (pedido aceptado, stock bajo, precio en revisión, comercio validado...). También intenta enviar las
 * capturas que quedaron sin conexión.
 *
 * No usa Firebase: el proyecto no depende de servicios de Google. El costo es que el aviso puede tardar hasta 15 min.
 */
class AvisosWorker(contexto: Context, parametros: WorkerParameters) : CoroutineWorker(contexto, parametros) {

    override suspend fun doWork(): Result {
        val repo = (applicationContext as AbastoApp).repositorio
        if (repo.usuario() == null) return Result.success()
        return try {
            try { repo.sincronizar() } catch (_: ErrorApi) { }
            val preferencias = applicationContext.getSharedPreferences("avisos", Context.MODE_PRIVATE)
            val antes = preferencias.getInt("no_leidas", 0)
            val lista = repo.notificaciones()
            if (lista.noLeidas > antes) {
                lista.notificaciones.firstOrNull { !it.leida }?.let { mostrar(it.titulo, it.mensaje, lista.noLeidas) }
            }
            preferencias.edit().putInt("no_leidas", lista.noLeidas).apply()
            Result.success()
        } catch (e: ErrorApi) {
            if (e.sinConexion) Result.retry() else Result.success()
        }
    }

    private fun mostrar(titulo: String, mensaje: String, total: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(applicationContext, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED) return
        val gestor = applicationContext.getSystemService(NotificationManager::class.java)
        gestor.createNotificationChannel(NotificationChannel(CANAL, "Avisos de negocio", NotificationManager.IMPORTANCE_DEFAULT))
        val abrir = PendingIntent.getActivity(applicationContext, 0, Intent(applicationContext, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE)
        val aviso = NotificationCompat.Builder(applicationContext, CANAL)
            .setSmallIcon(R.drawable.ic_abastored)
            .setContentTitle(titulo)
            .setContentText(mensaje)
            .setSubText("$total sin leer")
            .setContentIntent(abrir)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(applicationContext).notify(1, aviso)
    }

    companion object {
        private const val CANAL = "avisos_negocio"
        private const val NOMBRE = "avisos_abastored"

        fun programar(contexto: Context) {
            val trabajo = PeriodicWorkRequestBuilder<AvisosWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(contexto).enqueueUniquePeriodicWork(NOMBRE, ExistingPeriodicWorkPolicy.KEEP, trabajo)
        }

        fun cancelar(contexto: Context) = WorkManager.getInstance(contexto).cancelUniqueWork(NOMBRE)
    }
}
