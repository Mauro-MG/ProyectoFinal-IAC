package mx.abastored.movil.ui.pantallas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import mx.abastored.movil.datos.Renglon
import mx.abastored.movil.datos.Repositorio
import mx.abastored.movil.ui.AppViewModel
import mx.abastored.movil.ui.Ambar
import mx.abastored.movil.ui.EstadoApp
import mx.abastored.movil.ui.Rojo
import mx.abastored.movil.ui.Verde

private enum class Accion(val titulo: String) { VENTA("Registrar venta"), ENTRADA("Registrar entrada"), PRECIO("Cambiar precio") }

@Composable
fun PantallaInventario(estado: EstadoApp, pendientes: Int, vm: AppViewModel) {
    var abierto by remember { mutableStateOf<Pair<Renglon, Accion>?>(null) }
    var filtro by remember { mutableStateOf<String?>(null) }
    val inventario = estado.inventario

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        if (estado.comercios.size > 1) SelectorComercio(estado, vm::elegirComercio)
        else estado.comercios.firstOrNull()?.let {
            Text(it.nombre, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(vertical = 8.dp))
        }
        if (inventario == null) {
            Text(if (estado.comercios.isEmpty() && !estado.ocupado) "Aún no tienes comercio registrado." else "Cargando…",
                modifier = Modifier.padding(16.dp))
            return@Column
        }
        if (inventario.deCopia) {
            val fecha = SimpleDateFormat("dd/MM HH:mm", Locale("es", "MX")).format(Date(inventario.fechaCopia ?: 0))
            Text("Sin conexión · copia guardada el $fecha. Puedes seguir capturando.", color = Ambar,
                style = MaterialTheme.typography.bodySmall)
        }
        val r = inventario.inventario.resumen
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 6.dp)) {
            FilterChip(filtro == null, { filtro = null }, label = { Text("Todos ${r.productos}") })
            FilterChip(filtro == "BAJO", { filtro = "BAJO" }, label = { Text("Bajos ${r.bajo}") })
            FilterChip(filtro == "AGOTADO", { filtro = "AGOTADO" }, label = { Text("Agotados ${r.agotado}") })
        }
        if (pendientes > 0) {
            AssistChip(onClick = vm::sincronizar, label = { Text("$pendientes capturas sin enviar · sincronizar") })
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxSize()) {
            items(inventario.inventario.renglones.filter { filtro == null || it.estado == filtro }, key = { it.id }) {
                TarjetaRenglon(it) { accion -> abierto = it to accion }
            }
        }
    }

    abierto?.let { (renglon, accion) ->
        DialogoCaptura(renglon, accion, cerrar = { abierto = null }) { cantidad, extra ->
            when (accion) {
                Accion.VENTA -> vm.venta(renglon, cantidad, extra ?: "EFECTIVO")
                Accion.ENTRADA -> vm.movimiento(renglon, "ENTRADA", cantidad, extra)
                Accion.PRECIO -> vm.precio(renglon, cantidad)
            }
            abierto = null
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SelectorComercio(estado: EstadoApp, elegir: (String) -> Unit) {
    var expandido by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expandido, { expandido = it }, Modifier.padding(vertical = 8.dp)) {
        OutlinedTextField(estado.comercios.firstOrNull { it.id == estado.comercioId }?.nombre.orEmpty(), {},
            readOnly = true, label = { Text("Comercio") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expandido) },
            modifier = Modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable).fillMaxWidth())
        ExposedDropdownMenu(expandido, { expandido = false }) {
            estado.comercios.forEach { c ->
                DropdownMenuItem(text = { Text(c.nombre) }, onClick = { expandido = false; elegir(c.id) })
            }
        }
    }
}

@Composable
private fun TarjetaRenglon(r: Renglon, accion: (Accion) -> Unit) {
    val color = when (r.estado) { "AGOTADO" -> Rojo; "BAJO" -> Ambar; else -> Verde }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(r.producto, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    Text("${r.categoria.orEmpty()} · mínimo ${Repositorio.formatoCantidad(r.stockMinimo)}",
                        style = MaterialTheme.typography.bodySmall)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("${Repositorio.formatoCantidad(r.existencia)} ${r.unidad}", color = color,
                        fontWeight = FontWeight.Bold)
                    Text(r.precioVenta?.let { "$%.2f".format(it) } ?: "sin precio",
                        style = MaterialTheme.typography.bodySmall)
                }
            }
            Row {
                TextButton({ accion(Accion.VENTA) }, enabled = r.existencia > 0) { Text("Vender") }
                TextButton({ accion(Accion.ENTRADA) }) { Text("Entrada") }
                Spacer(Modifier.weight(1f))
                TextButton({ accion(Accion.PRECIO) }) { Text("Precio") }
            }
        }
    }
}

@Composable
private fun DialogoCaptura(r: Renglon, accion: Accion, cerrar: () -> Unit, guardar: (Double, String?) -> Unit) {
    var valor by remember { mutableStateOf(if (accion == Accion.PRECIO) r.precioVenta?.toString().orEmpty() else "1") }
    var extra by remember { mutableStateOf(if (accion == Accion.VENTA) "EFECTIVO" else "") }
    val numero = valor.replace(',', '.').toDoubleOrNull()
    val valido = numero != null && numero > 0 && (accion != Accion.VENTA || numero <= r.existencia)
    AlertDialog(
        onDismissRequest = cerrar,
        title = { Text(accion.titulo) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(r.producto, fontWeight = FontWeight.SemiBold)
                OutlinedTextField(valor, { valor = it },
                    label = { Text(if (accion == Accion.PRECIO) "Precio de venta ($)" else "Cantidad (${r.unidad})") },
                    supportingText = {
                        if (accion == Accion.VENTA) Text("Hay ${Repositorio.formatoCantidad(r.existencia)} ${r.unidad}")
                    },
                    isError = valor.isNotEmpty() && !valido, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                when (accion) {
                    Accion.VENTA -> Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("EFECTIVO" to "Efectivo", "TARJETA" to "Tarjeta", "TRANSFERENCIA" to "Transf.").forEach {
                            FilterChip(extra == it.first, { extra = it.first }, label = { Text(it.second) })
                        }
                    }
                    Accion.ENTRADA -> OutlinedTextField(extra, { extra = it }, label = { Text("Motivo (opcional)") },
                        singleLine = true)
                    Accion.PRECIO -> Text("Si el precio se aleja mucho del promedio de tu zona, la coordinación lo revisa.",
                        style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = { TextButton({ guardar(numero!!, extra.ifBlank { null }) }, enabled = valido) { Text("Guardar") } },
        dismissButton = { TextButton(cerrar) { Text("Cancelar") } },
    )
}

