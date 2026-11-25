package mx.abastored.movil.ui.pantallas

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import mx.abastored.movil.ui.AppViewModel
import mx.abastored.movil.ui.EstadoApp

/** Notificaciones de negocio (ms-notificaciones): pedidos, stock bajo, precios en revisión, validación del comercio. */
@Composable
fun PantallaAvisos(estado: EstadoApp, vm: AppViewModel) {
    LaunchedEffect(Unit) { vm.cargarNotificaciones() }
    LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item { Text("${estado.noLeidas} sin leer · toca un aviso para marcarlo como leído",
                    style = MaterialTheme.typography.bodySmall) }
        if (estado.notificaciones.isEmpty() && !estado.ocupado) item { Text("No tienes avisos.") }
        items(estado.notificaciones, key = { it.id }) { n ->
            Card(Modifier.fillMaxWidth().clickable(enabled = !n.leida) { vm.marcarLeida(n) },
                colors = if (n.leida) CardDefaults.cardColors() else
                    CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                Column(Modifier.padding(12.dp)) {
                    Text(n.titulo, fontWeight = if (n.leida) FontWeight.Normal else FontWeight.SemiBold)
                    Text(n.mensaje, style = MaterialTheme.typography.bodySmall)
                    Text("${n.tipo.replace('_', ' ')} · ${n.creada?.take(16)?.replace('T', ' ').orEmpty()}",
                        style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}
