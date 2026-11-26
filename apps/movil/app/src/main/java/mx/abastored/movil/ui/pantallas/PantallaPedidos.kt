package mx.abastored.movil.ui.pantallas

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.journeyapps.barcodescanner.ScanOptions
import mx.abastored.movil.datos.Pedido
import mx.abastored.movil.datos.Repositorio
import mx.abastored.movil.ui.AppViewModel
import mx.abastored.movil.ui.EstadoApp

private val ETIQUETAS = mapOf("enviar" to "Enviar al proveedor", "cancelar" to "Cancelar",
    "recibir" to "Confirmar que llegó", "aceptar" to "Aceptar", "preparar" to "Preparar", "despachar" to "Despachar")

@Composable
fun PantallaPedidos(estado: EstadoApp, vm: AppViewModel) {
    LaunchedEffect(Unit) { if (estado.pedidos.isEmpty()) vm.refrescarPedidos() }
    if (estado.pedidos.isEmpty() && !estado.ocupado) {
        Text("No tienes pedidos de abasto. Los haces desde el sistema web con el proveedor que te convenga; aquí "
            + "les das seguimiento y confirmas cuando llegan.", Modifier.padding(16.dp))
    }
    LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(estado.pedidos, key = { it.id }) { p ->
            Card(Modifier.fillMaxWidth().clickable { vm.abrirPedido(p.id) }) {
                Column(Modifier.padding(12.dp)) {
                    Row {
                        Text(p.folio, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        Text(p.estadoLegible, color = MaterialTheme.colorScheme.primary)
                    }
                    Text(p.proveedor.orEmpty(), style = MaterialTheme.typography.bodyMedium)
                    Text("$%.2f".format(p.subtotal) + (p.entregaEstimada?.let { " · entrega estimada $it" } ?: ""),
                        style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
    estado.pedidoAbierto?.let { DetallePedido(it, vm, estado.usuario?.let { u -> "${u.nombre} ${u.apellido.orEmpty()}".trim() } ?: "Comercio") }
}

@Composable
private fun DetallePedido(p: Pedido, vm: AppViewModel, recibe: String) {
    // QR del repartidor (ms-entregas): ABASTORED:ENTREGA:<id>:<código>
    val escanearQr = rememberLector("Escanea el código QR que muestra el repartidor", listOf(ScanOptions.QR_CODE)) {
        vm.confirmarEntregaConQr(p, it, recibe)
    }
    AlertDialog(
        onDismissRequest = { vm.abrirPedido(null) },
        title = { Text("${p.folio} · ${p.estadoLegible}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(p.proveedor.orEmpty(), fontWeight = FontWeight.SemiBold)
                p.partidas.forEach {
                    Row {
                        Text("${Repositorio.formatoCantidad(it.cantidad)} × ${it.producto}", Modifier.weight(1f))
                        Text("$%.2f".format(it.subtotal ?: 0.0))
                    }
                }
                HorizontalDivider()
                Text("Total: $%.2f".format(p.subtotal), fontWeight = FontWeight.Bold)
                if ("recibir" in p.acciones) {
                    Text("Al confirmar, las cantidades se suman a tu inventario.", style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            Row {
                if (p.estado == "ENVIADO_A_COMERCIO") TextButton(escanearQr) { Text("Recibir con QR") }
                p.acciones.filter { it in ETIQUETAS }.forEach { a ->
                    TextButton({ vm.accionPedido(p, a) }) { Text(ETIQUETAS.getValue(a)) }
                }
            }
        },
        dismissButton = { TextButton({ vm.abrirPedido(null) }) { Text("Cerrar") } },
    )
}
