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
import mx.abastored.movil.datos.Notificacion
import mx.abastored.movil.datos.Oferta
import mx.abastored.movil.datos.Perfil
import mx.abastored.movil.datos.Producto
import mx.abastored.movil.datos.ProveedorSugerido
import mx.abastored.movil.datos.Recomendacion
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
    // Entrega final
    val perfil: Perfil? = null,
    val productosBusqueda: List<Producto> = emptyList(),
    val productoEscaneado: Producto? = null,
    val recomendaciones: List<Recomendacion> = emptyList(),
    val proveedores: List<ProveedorSugerido> = emptyList(),
    val ofertas: List<Oferta> = emptyList(),
    val ofertasDe: String? = null,
    val notificaciones: List<Notificacion> = emptyList(),
    val noLeidas: Int = 0,
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
            if (usuario != null) {
                // ¿El servidor sigue reconociendo este teléfono? Si se dio de baja desde el web, se cierra la sesión.
                try {
                    if (!repo.dispositivoVigente()) {
                        repo.cerrarSesion()
                        _estado.update { EstadoApp(cargandoSesion = false,
                            mensaje = "Este teléfono fue dado de baja desde tu cuenta. Vuelve a iniciar sesión.") }
                        return@launch
                    }
                } catch (_: ErrorApi) { /* sin conexión: se sigue con la copia local */ }
                cargarInicio()
            }
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
        registrarDispositivo()
        cargarInicio()
    }

    fun registrarse(nombre: String, apellido: String, email: String, password: String, telefono: String?,
                    perfil: String) = ejecutar {
        val usuario = repo.registrarse(nombre.trim(), apellido.trim(), email.trim().lowercase(), password,
            telefono?.trim()?.ifBlank { null }, perfil)
        _estado.update { it.copy(usuario = usuario) }
        registrarDispositivo()
        cargarInicio()
        avisar("Cuenta creada. Registra tu comercio para empezar.")
    }

    private suspend fun registrarDispositivo() {
        try {
            repo.registrarDispositivo("${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}")
        } catch (_: ErrorApi) { }
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

    // ------------------------------------------------------------ perfil y comercio
    fun cargarPerfil() = ejecutar { _estado.update { it.copy(perfil = repo.perfil()) } }

    fun cambiarPassword(actual: String, nueva: String) = ejecutar {
        repo.cambiarPassword(actual, nueva)
        avisar("Contraseña actualizada. Se cerraron tus otras sesiones.")
    }

    fun registrarComercio(nombre: String, tipo: String, direccion: String, municipio: String,
                          latitud: Double?, longitud: Double?) = ejecutar {
        val comercio = repo.registrarComercio(nombre.trim(), tipo, direccion.trim(), municipio.trim(), latitud, longitud)
        _estado.update { it.copy(comercios = it.comercios + comercio, comercioId = comercio.id) }
        avisar("Comercio registrado${comercio.zona?.let { z -> " en la zona $z" } ?: ""}. Queda pendiente de validación.")
        cargarInventarioDe(comercio.id)
    }

    fun subirFoto(jpeg: ByteArray) = ejecutar {
        val comercio = _estado.value.comercioId ?: return@ejecutar
        repo.subirFotoComercio(comercio, jpeg)
        avisar("Foto guardada en el almacenamiento del sistema.")
    }

    // ------------------------------------------------------------ alta de productos
    fun buscarProductos(texto: String) = ejecutar {
        _estado.update { it.copy(productosBusqueda = repo.buscarProductos(texto)) }
    }

    fun productoPorCodigo(codigo: String) = ejecutar {
        val producto = repo.productoPorCodigo(codigo)
        if (producto == null) avisar("El código $codigo no está en el catálogo. Búscalo por nombre.")
        _estado.update { it.copy(productoEscaneado = producto) }
    }

    fun agregarProducto(productoId: Int, existencia: Double, minimo: Double, precio: Double?) = ejecutar {
        val comercio = _estado.value.comercioId ?: return@ejecutar
        val renglon = repo.agregarProducto(comercio, productoId, existencia, minimo, precio)
        avisar("${renglon.producto} agregado a tu inventario.")
        _estado.update { it.copy(productoEscaneado = null, productosBusqueda = emptyList()) }
        cargarInventarioDe(comercio)
    }

    // ------------------------------------------------------------ abasto
    fun cargarAbasto() = ejecutar {
        val comercio = _estado.value.comercioId ?: return@ejecutar
        val recomendaciones = repo.recomendaciones(comercio).recomendaciones
        val proveedores = repo.proveedoresSugeridos(comercio)
        _estado.update { it.copy(recomendaciones = recomendaciones, proveedores = proveedores) }
    }

    private fun zonaDelComercio(): Int? = _estado.value.comercios.firstOrNull { it.id == _estado.value.comercioId }?.zonaId

    fun verOfertas(productoId: Int, producto: String) = ejecutar {
        _estado.update { it.copy(ofertas = repo.ofertas(productoId, zonaDelComercio()), ofertasDe = producto) }
    }

    fun cerrarOfertas() = _estado.update { it.copy(ofertas = emptyList(), ofertasDe = null) }

    fun responder(productoId: Int, respuesta: String) = ejecutar {
        val comercio = _estado.value.comercioId ?: return@ejecutar
        repo.responderRecomendacion(comercio, productoId, respuesta)
        _estado.update { e -> e.copy(recomendaciones = e.recomendaciones.filter { it.productoId != productoId }) }
    }

    fun solicitarAbasto(oferta: Oferta, cantidad: Double, enviar: Boolean) = ejecutar {
        val comercio = _estado.value.comercioId ?: return@ejecutar
        val pedido = repo.solicitarAbasto(comercio, oferta, cantidad, enviar)
        _estado.update { it.copy(ofertas = emptyList(), ofertasDe = null, pedidos = repo.pedidos()) }
        avisar(if (enviar) "Pedido ${pedido.folio} enviado a ${oferta.proveedor}."
               else "Producto agregado al pedido ${pedido.folio} (borrador).")
    }

    // ------------------------------------------------------------ notificaciones y entregas
    fun cargarNotificaciones() = ejecutar {
        val lista = repo.notificaciones()
        _estado.update { it.copy(notificaciones = lista.notificaciones, noLeidas = lista.noLeidas) }
    }

    fun marcarLeida(n: Notificacion) = ejecutar {
        repo.marcarLeida(n.id)
        _estado.update { e -> e.copy(notificaciones = e.notificaciones.map { if (it.id == n.id) it.copy(leida = true) else it },
                                     noLeidas = (e.noLeidas - 1).coerceAtLeast(0)) }
    }

    /** Contenido del QR que muestra el repartidor: ABASTORED:ENTREGA:<entrega_id>:<código>. ms-entregas valida el
     *  código (con límite de intentos) y, al confirmarse, ms-pedidos recibe el pedido y ms-inventario suma la mercancía. */
    fun confirmarEntregaConQr(pedido: Pedido, contenido: String, recibidoPor: String) = ejecutar {
        val partes = contenido.trim().split(":")
        val (entregaId, codigo) = if (partes.size == 4 && partes[0] == "ABASTORED" && partes[1] == "ENTREGA") {
            partes[2] to partes[3]
        } else {
            val entrega = repo.entregaDePedido(pedido.id)
            if (entrega == null) {
                avisar("Este pedido no tiene una entrega programada con QR.")
                return@ejecutar
            }
            entrega.id to contenido.trim()
        }
        repo.confirmarEntrega(entregaId, codigo, recibidoPor.trim())
        _estado.update { it.copy(pedidoAbierto = repo.pedido(pedido.id), pedidos = repo.pedidos()) }
        avisar("Entrega confirmada con el código QR. La mercancía se sumó a tu inventario.")
        _estado.value.comercioId?.let { cargarInventarioDe(it) }
    }
}
