package mx.abastored.movil.ui.pantallas

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import androidx.activity.compose.rememberLauncherForActivityResult
import mx.abastored.movil.datos.Producto
import mx.abastored.movil.ui.AppViewModel
import mx.abastored.movil.ui.EstadoApp

/** Lector de códigos de barras y QR (ZXing, cámara del teléfono). La biblioteca pide el permiso de cámara. */
@Composable
fun rememberLector(prompt: String, formatos: Collection<String>, alLeer: (String) -> Unit) =
    rememberLauncherForActivityResult(ScanContract()) { r -> r.contents?.let(alLeer) }.let { lanzador ->
        {
            lanzador.launch(ScanOptions().setPrompt(prompt).setDesiredBarcodeFormats(formatos)
                .setBeepEnabled(true).setOrientationLocked(false))
        }
    }

/** Alta de un producto del catálogo maestro en el inventario del comercio (por nombre o escaneando el código). */
@Composable
fun DialogoAgregarProducto(estado: EstadoApp, vm: AppViewModel, cerrar: () -> Unit) {
    var texto by remember { mutableStateOf("") }
    var elegido by remember { mutableStateOf<Producto?>(null) }
    var existencia by remember { mutableStateOf("0") }
    var minimo by remember { mutableStateOf("1") }
    var precio by remember { mutableStateOf("") }
    val escanear = rememberLector("Apunta al código de barras del producto",
        listOf(ScanOptions.EAN_13, ScanOptions.EAN_8, ScanOptions.UPC_A, ScanOptions.UPC_E)) { vm.productoPorCodigo(it) }
    LaunchedEffect(estado.productoEscaneado) { estado.productoEscaneado?.let { elegido = it } }

    AlertDialog(
        onDismissRequest = cerrar,
        title = { Text("Agregar producto") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (elegido == null) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(texto, { texto = it; if (it.length >= 3) vm.buscarProductos(it) },
                            label = { Text("Buscar en el catálogo") }, singleLine = true, modifier = Modifier.weight(1f))
                    }
                    OutlinedButton(escanear) { Text("Escanear código de barras") }
                    LazyColumn(Modifier.heightIn(max = 240.dp)) {
                        items(estado.productosBusqueda, key = { it.id }) { p ->
                            Column(Modifier.fillMaxWidth().clickable { elegido = p }.padding(vertical = 6.dp)) {
                                Text(p.nombre)
                                Text("${p.categoria.orEmpty()} · ${p.unidad}", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                } else {
                    Text(elegido!!.nombre, fontWeight = FontWeight.SemiBold)
                    listOf(Triple("Existencia inicial", existencia) { v: String -> existencia = v },
                        Triple("Stock mínimo", minimo) { v: String -> minimo = v },
                        Triple("Precio de venta (opcional)", precio) { v: String -> precio = v }).forEach { (etiqueta, valor, cambiar) ->
                        OutlinedTextField(valor, cambiar, label = { Text(etiqueta) }, singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                    }
                }
            }
        },
        confirmButton = {
            val e = existencia.replace(',', '.').toDoubleOrNull()
            val m = minimo.replace(',', '.').toDoubleOrNull()
            val p = precio.replace(',', '.').toDoubleOrNull()
            TextButton({ vm.agregarProducto(elegido!!.id, e!!, m!!, p); cerrar() },
                enabled = elegido != null && e != null && e >= 0 && m != null && m >= 0 && (precio.isBlank() || (p != null && p > 0))) {
                Text("Agregar")
            }
        },
        dismissButton = { TextButton({ if (elegido != null) elegido = null else cerrar() }) { Text(if (elegido != null) "Atrás" else "Cancelar") } },
    )
}
