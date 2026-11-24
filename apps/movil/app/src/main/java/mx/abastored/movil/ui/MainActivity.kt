package mx.abastored.movil.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.CloudSync
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
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
import mx.abastored.movil.ui.pantallas.PantallaInventario
import mx.abastored.movil.ui.pantallas.PantallaLogin
import mx.abastored.movil.ui.pantallas.PantallaPedidos
import mx.abastored.movil.ui.pantallas.PantallaPendientes

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val repo = (application as AbastoApp).repositorio
        setContent {
            TemaAbastoRed {
                val vm: AppViewModel = viewModel(factory = viewModelFactory { initializer { AppViewModel(repo) } })
                App(vm)
            }
        }
    }
}

private data class Seccion(val titulo: String, val icono: ImageVector)

private val SECCIONES = listOf(
    Seccion("Inventario", Icons.Filled.Inventory2),
    Seccion("Pedidos", Icons.Filled.LocalShipping),
    Seccion("Pendientes", Icons.Filled.CloudSync),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App(vm: AppViewModel) {
    val estado by vm.estado.collectAsStateWithLifecycle()
    val pendientes by vm.pendientes.collectAsStateWithLifecycle()
    val avisos = remember { SnackbarHostState() }
    var seccion by rememberSaveable { mutableIntStateOf(0) }

    LaunchedEffect(estado.mensaje) {
        estado.mensaje?.let {
            avisos.showSnackbar(it)
            vm.avisar(null)
        }
    }

    when {
        estado.cargandoSesion -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        estado.usuario == null -> Scaffold(snackbarHost = { SnackbarHost(avisos) }) { relleno ->
            PantallaLogin(estado.ocupado, Modifier.padding(relleno), vm::iniciarSesion)
        }
        else -> Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(SECCIONES[seccion].titulo) },
                    actions = {
                        IconButton(onClick = vm::cerrarSesion) {
                            Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = "Cerrar sesión")
                        }
                    })
            },
            bottomBar = {
                NavigationBar {
                    SECCIONES.forEachIndexed { i, s ->
                        NavigationBarItem(
                            selected = seccion == i,
                            onClick = { seccion = i; if (i == 1) vm.refrescarPedidos() },
                            label = { Text(s.titulo) },
                            icon = {
                                if (i == 2 && pendientes.isNotEmpty()) {
                                    BadgedBox(badge = { Badge { Text("${pendientes.size}") } }) {
                                        Icon(s.icono, contentDescription = s.titulo)
                                    }
                                } else Icon(s.icono, contentDescription = s.titulo)
                            })
                    }
                }
            },
            snackbarHost = { SnackbarHost(avisos) },
        ) { relleno ->
            Box(Modifier.padding(relleno)) {
                when (seccion) {
                    0 -> PantallaInventario(estado, pendientes.size, vm)
                    1 -> PantallaPedidos(estado, vm)
                    else -> PantallaPendientes(pendientes, vm)
                }
                if (estado.ocupado) LinearProgressIndicator(Modifier.align(Alignment.TopCenter))
            }
        }
    }
}
