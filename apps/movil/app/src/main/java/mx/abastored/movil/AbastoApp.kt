package mx.abastored.movil

import android.app.Application
import mx.abastored.movil.datos.AlmacenSesion
import mx.abastored.movil.datos.ClienteApi
import mx.abastored.movil.datos.Repositorio
import mx.abastored.movil.datos.local.BaseLocal

/** Crea una sola vez el cliente HTTP, la sesión y la base local que comparten las pantallas. */
class AbastoApp : Application() {
    lateinit var repositorio: Repositorio
        private set

    override fun onCreate() {
        super.onCreate()
        val sesion = AlmacenSesion(this)
        repositorio = Repositorio(ClienteApi(BuildConfig.GATEWAY_URL, sesion), sesion, BaseLocal.crear(this))
    }
}
