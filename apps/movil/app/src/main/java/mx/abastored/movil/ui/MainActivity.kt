package mx.abastored.movil.ui

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import mx.abastored.movil.AbastoApp
import mx.abastored.movil.datos.AvisosWorker
import mx.abastored.movil.ui.pantallas.DialogoAgregarProducto
import mx.abastored.movil.ui.pantallas.PantallaAbasto
import mx.abastored.movil.ui.pantallas.PantallaAvisos
import mx.abastored.movil.ui.pantallas.PantallaInventario
import mx.abastored.movil.ui.pantallas.PantallaLogin
import mx.abastored.movil.ui.pantallas.PantallaPedidos
import mx.abastored.movil.ui.pantallas.PantallaPendientes
import mx.abastored.movil.ui.pantallas.PantallaPerfil

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val repo = (application as AbastoApp).repositorio
        setContent {
            TemaAbastoRed {
                val vm: AppViewModel = viewModel(factory = viewModelFactory { initializer { AppViewModel(repo, applicationContext) } })
                App(vm)
            }
        }
    }
}

private data class Seccion(val titulo: String, val icono: ImageVector)

private val SECCIONES = listOf(
    Seccion("Inventario", Icons.Filled.Inventory2),
    Seccion("Abasto", Icons.Filled.Storefront),
    Seccion("Pedidos", Icons.Filled.LocalShipping),
    Seccion("Avisos", Icons.Filled.Notifications),
    Seccion("Perfil", Icons.Filled.Person),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App(vm: AppViewModel) {
    val estado by vm.estado.collectAsStateWithLifecycle()
    val pendientes by vm.pendientes.collectAsStateWithLifecycle()
    val avisos = remember { SnackbarHostState() }
    var seccion by rememberSaveable { mutableIntStateOf(0) }
    var verPendientes by rememberSaveable { mutableStateOf(false) }
    var agregando by remember { mutableStateOf(false) }
    val permisoAvisos = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }

    LaunchedEffect(estado.mensaje) {
        estado.mensaje?.let {
            avisos.showSnackbar(it)
            vm.avisar(null)
        }
    }
    // Con sesión: revisión periódica de avisos en segundo plano (WorkManager) y permiso de notificaciones
    LaunchedEffect(estado.usuario?.id) {
        if (estado.usuario != null) {
            AvisosWorker.programar(vm.contexto)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) permisoAvisos.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else AvisosWorker.cancelar(vm.contexto)
    }

    when {
        estado.cargandoSesion -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        estado.usuario == null -> Scaffold(snackbarHost = { SnackbarHost(avisos) }) { relleno ->
            PantallaLogin(estado.ocupado, Modifier.padding(relleno), vm::iniciarSesion, vm::registrarse)
        }
        else -> Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(if (verPendientes) "Capturas sin enviar" else SECCIONES[seccion].titulo) },
                    navigationIcon = {
                        if (verPendientes) IconButton({ verPendientes = false }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Regresar")
                        }
                    })
            },
            floatingActionButton = {
                if (seccion == 0 && !verPendientes && estado.comercioId != null) {
                    FloatingActionButton({ agregando = true }) { Icon(Icons.Filled.Add, contentDescription = "Agregar producto") }
                }
            },
            bottomBar = {
                NavigationBar {
                    SECCIONES.forEachIndexed { i, s ->
                        NavigationBarItem(
                            selected = seccion == i && !verPendientes,
                            onClick = { seccion = i; verPendientes = false; if (i == 2) vm.refrescarPedidos() },
                            label = { Text(s.titulo) },
                            icon = {
                                val numero = when (i) { 3 -> estado.noLeidas; 0 -> pendientes.size; else -> 0 }
                                if (numero > 0) BadgedBox(badge = { Badge { Text("$numero") } }) {
                                    Icon(s.icono, contentDescription = s.titulo)
                                } else Icon(s.icono, contentDescription = s.titulo)
                            })
                    }
                }
            },
            snackbarHost = { SnackbarHost(avisos) },
        ) { relleno ->
            Box(Modifier.padding(relleno)) {
                if (verPendientes) PantallaPendientes(pendientes, vm)
                else when (seccion) {
                    0 -> PantallaInventario(estado, pendientes.size, vm)
                    1 -> PantallaAbasto(estado, vm)
                    2 -> PantallaPedidos(estado, vm)
                    3 -> PantallaAvisos(estado, vm)
                    else -> PantallaPerfil(estado, pendientes.size, vm) { verPendientes = true }
                }
                if (estado.ocupado) LinearProgressIndicator(Modifier.align(Alignment.TopCenter))
            }
        }
    }
    if (agregando) DialogoAgregarProducto(estado, vm) { agregando = false }
}
