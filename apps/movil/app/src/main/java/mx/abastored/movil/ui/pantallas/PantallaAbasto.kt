package mx.abastored.movil.ui.pantallas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import mx.abastored.movil.datos.Oferta
import mx.abastored.movil.datos.Repositorio
import mx.abastored.movil.ui.Ambar
import mx.abastored.movil.ui.AppViewModel
import mx.abastored.movil.ui.EstadoApp
import mx.abastored.movil.ui.Rojo
import mx.abastored.movil.ui.Verde

/** Qué surtir (ms-recomendaciones, con su explicación), quién te lo vende (ms-proveedores) y la solicitud de abasto. */
@Composable
fun PantallaAbasto(estado: EstadoApp, vm: AppViewModel) {
    LaunchedEffect(estado.comercioId) { vm.cargarAbasto() }
    LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            Text("Recomendado para tu comercio", style = MaterialTheme.typography.titleMedium)
            Text("Productos que faltan en tu zona y que tus clientes buscan. Toca uno para ver quién te lo surte.",
                style = MaterialTheme.typography.bodySmall)
        }
        if (estado.recomendaciones.isEmpty() && !estado.ocupado) {
            item { Text("Por ahora no hay recomendaciones para tu zona.", Modifier.padding(8.dp)) }
        }
        items(estado.recomendaciones, key = { "r${it.productoId}" }) { r ->
            val color = when (r.prioridad) { "alta" -> Rojo; "media" -> Ambar; else -> Verde }
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row {
                        Text(r.producto, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        Text("Prioridad ${r.prioridad}", color = color, style = MaterialTheme.typography.labelMedium)
                    }
                    r.explicacion.take(3).forEach { Text("· ${it.detalle}", style = MaterialTheme.typography.bodySmall) }
                    Row {
                        TextButton({ vm.verOfertas(r.productoId, r.producto) }) { Text("Ver proveedores") }
                        TextButton({ vm.responder(r.productoId, "descartada") }) { Text("No me interesa") }
                    }
                }
            }
        }
        item {
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("Proveedores que entregan en tu zona", style = MaterialTheme.typography.titleMedium)
        }
        items(estado.proveedores, key = { "p${it.id}" }) { p ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(p.nombre, fontWeight = FontWeight.SemiBold)
                    Text("Pedido mínimo $%.0f · entrega en %d día(s)".format(p.pedidoMinimo, p.diasEntrega),
                        style = MaterialTheme.typography.bodySmall)
                    p.condiciones?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
    }
    if (estado.ofertasDe != null) DialogoOfertas(estado, vm)
}

@Composable
private fun DialogoOfertas(estado: EstadoApp, vm: AppViewModel) {
    var elegida by remember { mutableStateOf<Oferta?>(null) }
    var cantidad by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = vm::cerrarOfertas,
        title = { Text(estado.ofertasDe.orEmpty()) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (estado.ofertas.isEmpty()) Text("Ningún proveedor que entregue en tu zona lo tiene disponible.")
                estado.ofertas.forEach { o ->
                    AssistChip(onClick = { elegida = o; cantidad = Repositorio.formatoCantidad(o.minima) },
                        label = { Text("${o.proveedor}: $%.2f · mín. %s".format(o.precio, Repositorio.formatoCantidad(o.minima))) })
                }
                elegida?.let { o ->
                    val numero = cantidad.replace(',', '.').toDoubleOrNull()
                    OutlinedTextField(cantidad, { cantidad = it }, label = { Text("Cantidad (${o.unidad})") },
                        isError = numero == null || numero < o.minima || numero > o.existencia, singleLine = true,
                        supportingText = { Text("Mínimo ${Repositorio.formatoCantidad(o.minima)}; disponibles " +
                                                "${Repositorio.formatoCantidad(o.existencia)}. Pedido mínimo del proveedor $%.0f".format(o.pedidoMinimo)) },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                }
            }
        },
        confirmButton = {
            val o = elegida
            val numero = cantidad.replace(',', '.').toDoubleOrNull()
            val valido = o != null && numero != null && numero >= o.minima && numero <= o.existencia
            Row {
                TextButton({ vm.solicitarAbasto(o!!, numero!!, enviar = false) }, enabled = valido) { Text("Agregar a borrador") }
                TextButton({ vm.solicitarAbasto(o!!, numero!!, enviar = true) }, enabled = valido) { Text("Enviar pedido") }
            }
        },
        dismissButton = { TextButton(vm::cerrarOfertas) { Text("Cerrar") } },
    )
}
