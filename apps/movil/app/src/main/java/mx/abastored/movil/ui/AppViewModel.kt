package mx.abastored.movil.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import mx.abastored.movil.datos.Captura
import mx.abastored.movil.datos.Comercio
import mx.abastored.movil.datos.ErrorApi
import mx.abastored.movil.datos.InventarioLocal
import mx.abastored.movil.datos.Pedido
import mx.abastored.movil.datos.Renglon
import mx.abastored.movil.datos.Repositorio
import mx.abastored.movil.datos.Usuario
import mx.abastored.movil.datos.local.OperacionPendiente

data class EstadoApp(
    val cargandoSesion: Boolean = true,
    val usuario: Usuario? = null,
    val ocupado: Boolean = false,
    val comercios: List<Comercio> = emptyList(),
    val comercioId: String? = null,
    val inventario: InventarioLocal? = null,
    val pedidos: List<Pedido> = emptyList(),
    val pedidoAbierto: Pedido? = null,
    val mensaje: String? = null,
)

class AppViewModel(private val repo: Repositorio) : ViewModel() {
    private val _estado = MutableStateFlow(EstadoApp())
    val estado: StateFlow<EstadoApp> = _estado.asStateFlow()
    val pendientes: StateFlow<List<OperacionPendiente>> =
        repo.pendientes.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        repo.api.alCerrarSesion = { _estado.update { EstadoApp(cargandoSesion = false, mensaje = "Tu sesión terminó; vuelve a entrar.") } }
        viewModelScope.launch {
            val usuario = repo.usuario()
            _estado.update { it.copy(cargandoSesion = false, usuario = usuario) }
            if (usuario != null) cargarInicio()
        }
    }

    private fun ejecutar(bloque: suspend () -> Unit) = viewModelScope.launch {
        _estado.update { it.copy(ocupado = true) }
        try {
            bloque()
        } catch (e: ErrorApi) {
            avisar(e.message)
        } finally {
            _estado.update { it.copy(ocupado = false) }
        }
    }

    fun avisar(mensaje: String?) = _estado.update { it.copy(mensaje = mensaje) }

    // ------------------------------------------------------------ sesión
    fun iniciarSesion(email: String, password: String) = ejecutar {
        val usuario = repo.iniciarSesion(email.trim().lowercase(), password)
        _estado.update { it.copy(usuario = usuario) }
        cargarInicio()
    }

    fun cerrarSesion() = ejecutar {
        repo.cerrarSesion()
        _estado.update { EstadoApp(cargandoSesion = false) }
    }

    private suspend fun cargarInicio() {
        try {
            val comercios = repo.comercios()
            _estado.update { it.copy(comercios = comercios, comercioId = it.comercioId ?: comercios.firstOrNull()?.id) }
        } catch (e: ErrorApi) {
            avisar(if (e.sinConexion) "Sin conexión: se muestra la última copia guardada." else e.message)
        }
        _estado.value.comercioId?.let { cargarInventarioDe(it) }
    }

    // ------------------------------------------------------------ inventario
    fun elegirComercio(id: String) {
        _estado.update { it.copy(comercioId = id) }
        refrescarInventario()
    }

    fun refrescarInventario() = ejecutar { _estado.value.comercioId?.let { cargarInventarioDe(it) } }

    private suspend fun cargarInventarioDe(comercioId: String) {
        try {
            val inventario = repo.inventario(comercioId)
            _estado.update { it.copy(inventario = inventario) }
        } catch (e: ErrorApi) {
            avisar(e.message)
        }
    }

    fun venta(renglon: Renglon, cantidad: Double, metodoPago: String) =
        capturar { repo.venta(renglon, cantidad, metodoPago) }

    fun movimiento(renglon: Renglon, tipo: String, cantidad: Double, motivo: String?) =
        capturar { repo.movimiento(renglon, tipo, cantidad, motivo) }

    fun precio(renglon: Renglon, precio: Double) = capturar { repo.precio(renglon, precio) }

    private fun capturar(accion: suspend () -> Captura) = ejecutar {
        when (val resultado = accion()) {
            is Captura.Enviada -> {
                avisar(resultado.mensaje)
                _estado.value.comercioId?.let { cargarInventarioDe(it) }
            }
            is Captura.Guardada -> avisar(resultado.mensaje)
        }
    }

    // ------------------------------------------------------------ pedidos
    fun refrescarPedidos() = ejecutar { _estado.update { it.copy(pedidos = repo.pedidos()) } }

    fun abrirPedido(id: String?) = if (id == null) _estado.update { it.copy(pedidoAbierto = null) }
    else ejecutar { _estado.update { it.copy(pedidoAbierto = repo.pedido(id)) } }

    fun accionPedido(pedido: Pedido, accion: String) = ejecutar {
        val actualizado = repo.accionPedido(pedido.id, accion)
        _estado.update { it.copy(pedidoAbierto = actualizado) }
        avisar("Pedido ${actualizado.folio}: ${actualizado.estadoLegible.lowercase()}.")
        _estado.update { it.copy(pedidos = repo.pedidos()) }
        if (accion == "recibir") _estado.value.comercioId?.let { cargarInventarioDe(it) }
    }

    // ------------------------------------------------------------ sincronización
    fun sincronizar() = ejecutar {
        val r = repo.sincronizar()
        avisar(when {
            r.enviadas == 0 && r.conRevision == 0 -> "No hay capturas por enviar."
            else -> "Se enviaron ${r.enviadas}: ${r.aplicadas} aplicadas" +
                (if (r.conRevision > 0) ", ${r.conRevision} para revisar" else "") +
                (if (r.pendientes > 0) ", ${r.pendientes} se reintentarán" else "") + "."
        })
        _estado.value.comercioId?.let { cargarInventarioDe(it) }
    }

    fun descartarRevisadas() = ejecutar { repo.descartarRevisadas() }
}
