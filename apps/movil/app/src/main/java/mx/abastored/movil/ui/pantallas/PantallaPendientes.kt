package mx.abastored.movil.ui.pantallas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import mx.abastored.movil.datos.local.OperacionPendiente
import mx.abastored.movil.ui.AppViewModel
import mx.abastored.movil.ui.Ambar
import mx.abastored.movil.ui.Rojo

@Composable
fun PantallaPendientes(pendientes: List<OperacionPendiente>, vm: AppViewModel) {
    Column(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Lo que capturaste sin conexión. Al sincronizar, ms-sincronizacion lo aplica en el orden en que lo "
            + "hiciste y no repite lo que ya se había aplicado.", style = MaterialTheme.typography.bodySmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(vm::sincronizar, enabled = pendientes.any { it.estado == "pendiente" }) { Text("Sincronizar ahora") }
            if (pendientes.any { it.estado != "pendiente" }) {
                OutlinedButton(vm::descartarRevisadas) { Text("Quitar revisadas") }
            }
        }
        if (pendientes.isEmpty()) Text("Todo está enviado.", Modifier.padding(top = 16.dp))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(pendientes, key = { it.id }) { op ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text(op.descripcion, style = MaterialTheme.typography.titleSmall)
                        Text("Capturada ${op.realizada.take(16).replace('T', ' ')}", style = MaterialTheme.typography.bodySmall)
                        when (op.estado) {
                            "conflicto" -> Text("Conflicto: ${op.mensaje.orEmpty()}", color = Ambar)
                            "rechazada" -> Text("No se aplicó: ${op.mensaje.orEmpty()}", color = Rojo)
                            else -> Text("Por enviar", color = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        }
    }
}
