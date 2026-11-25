package mx.abastored.movil.ui.pantallas

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.location.Location
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.ByteArrayOutputStream
import java.io.File
import mx.abastored.movil.ui.AppViewModel
import mx.abastored.movil.ui.EstadoApp

private val TIPOS = listOf("INFORMAL_TIANGUIS" to "Tianguis", "INFORMAL_FIJO" to "Puesto fijo",
    "INFORMAL_AMBULANTE" to "Ambulante", "FORMAL_ABARROTES" to "Abarrotes", "FORMAL_MINISUPER" to "Minisúper")

@Composable
fun PantallaPerfil(estado: EstadoApp, pendientes: Int, vm: AppViewModel, verPendientes: () -> Unit) {
    LaunchedEffect(Unit) { vm.cargarPerfil() }
    val contexto = LocalContext.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        estado.perfil?.let { p ->
            Text("${p.nombre} ${p.apellido.orEmpty()}", style = MaterialTheme.typography.titleLarge)
            Text("${p.email} · ${p.rol}", style = MaterialTheme.typography.bodyMedium)
        }
        if (estado.comercios.isEmpty()) RegistroComercio(vm) else FotoComercio(estado, vm, contexto)
        OutlinedButton(verPendientes, Modifier.fillMaxWidth()) {
            Text(if (pendientes > 0) "$pendientes capturas sin enviar" else "Capturas sin conexión")
        }
        CambioPassword(vm)
        HorizontalDivider()
        Text("Este teléfono está registrado en tu cuenta. Si lo pierdes, dalo de baja desde el sistema web y la app " +
             "cerrará la sesión al abrirse.", style = MaterialTheme.typography.bodySmall)
        Button(vm::cerrarSesion, Modifier.fillMaxWidth()) { Text("Cerrar sesión y dar de baja este teléfono") }
    }
}

@Composable
private fun FotoComercio(estado: EstadoApp, vm: AppViewModel, contexto: Context) {
    val comercio = estado.comercios.firstOrNull { it.id == estado.comercioId } ?: return
    val archivo = remember { File(contexto.cacheDir, "fotos/fachada.jpg").apply { parentFile?.mkdirs() } }
    val uri = remember { FileProvider.getUriForFile(contexto, "${contexto.packageName}.archivos", archivo) }
    val tomar = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) vm.subirFoto(comprimir(archivo)) else vm.avisar("No se tomó la foto.")
    }
    val permiso = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { concedido ->
        if (concedido) tomar.launch(uri) else vm.avisar("Sin permiso de cámara no se puede tomar la foto.")
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(comercio.nombre, fontWeight = FontWeight.SemiBold)
            Text("${comercio.zona ?: "Sin zona"} · ${comercio.estadoRegistro?.lowercase() ?: ""}",
                style = MaterialTheme.typography.bodySmall)
            OutlinedButton({
                if (ContextCompat.checkSelfPermission(contexto, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
                    tomar.launch(uri) else permiso.launch(Manifest.permission.CAMERA)
            }) { Text("Tomar foto de la fachada") }
        }
    }
}

/** JPEG de máximo 1600 px y calidad 80: suficiente para la ficha y ligero para datos móviles. */
private fun comprimir(archivo: File): ByteArray {
    val original = BitmapFactory.decodeFile(archivo.path)
    val escala = minOf(1f, 1600f / maxOf(original.width, original.height))
    val imagen = if (escala < 1f) Bitmap.createScaledBitmap(original, (original.width * escala).toInt(),
        (original.height * escala).toInt(), true) else original
    return ByteArrayOutputStream().also { imagen.compress(Bitmap.CompressFormat.JPEG, 80, it) }.toByteArray()
}

@Composable
private fun RegistroComercio(vm: AppViewModel) {
    val contexto = LocalContext.current
    var nombre by rememberSaveable { mutableStateOf("") }
    var direccion by rememberSaveable { mutableStateOf("") }
    var municipio by rememberSaveable { mutableStateOf("") }
    var tipo by rememberSaveable { mutableStateOf(TIPOS.first().first) }
    var ubicacion by remember { mutableStateOf<Location?>(null) }
    val pedirUbicacion = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { concedido ->
        if (concedido) ubicacionActual(contexto) { ubicacion = it; if (it == null) vm.avisar("No se pudo obtener la ubicación.") }
        else vm.avisar("Sin permiso de ubicación: la coordinación asignará tu zona al validar.")
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Registra tu comercio", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(nombre, { nombre = it }, label = { Text("Nombre del comercio") }, singleLine = true,
                modifier = Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TIPOS.take(3).forEach { (clave, texto) -> FilterChip(tipo == clave, { tipo = clave }, label = { Text(texto) }) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TIPOS.drop(3).forEach { (clave, texto) -> FilterChip(tipo == clave, { tipo = clave }, label = { Text(texto) }) }
            }
            OutlinedTextField(direccion, { direccion = it }, label = { Text("Dirección o referencia") },
                modifier = Modifier.fillMaxWidth())
            OutlinedTextField(municipio, { municipio = it }, label = { Text("Municipio") }, singleLine = true,
                modifier = Modifier.fillMaxWidth())
            OutlinedButton({
                if (ContextCompat.checkSelfPermission(contexto, Manifest.permission.ACCESS_FINE_LOCATION) ==
                    PackageManager.PERMISSION_GRANTED) ubicacionActual(contexto) { ubicacion = it }
                else pedirUbicacion.launch(Manifest.permission.ACCESS_FINE_LOCATION)
            }) { Text(ubicacion?.let { "Ubicación: %.5f, %.5f".format(it.latitude, it.longitude) } ?: "Usar mi ubicación") }
            Button({ vm.registrarComercio(nombre, tipo, direccion, municipio, ubicacion?.latitude, ubicacion?.longitude) },
                enabled = nombre.length >= 3 && direccion.length >= 3 && municipio.length >= 2,
                modifier = Modifier.fillMaxWidth()) { Text("Registrar comercio") }
        }
    }
}

/** Ubicación del GPS o de la red, sin servicios de Google (LocationManager del sistema). */
@SuppressLint("MissingPermission")
private fun ubicacionActual(contexto: Context, alTerminar: (Location?) -> Unit) {
    val gestor = contexto.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    val proveedor = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        .firstOrNull { gestor.isProviderEnabled(it) }
    if (proveedor == null) {
        alTerminar(null)
        return
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        gestor.getCurrentLocation(proveedor, null, ContextCompat.getMainExecutor(contexto)) { alTerminar(it) }
    } else {
        alTerminar(gestor.getLastKnownLocation(proveedor))
    }
}

@Composable
private fun CambioPassword(vm: AppViewModel) {
    var actual by remember { mutableStateOf("") }
    var nueva by remember { mutableStateOf("") }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Cambiar contraseña", fontWeight = FontWeight.SemiBold)
            OutlinedTextField(actual, { actual = it }, label = { Text("Actual") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth())
            OutlinedTextField(nueva, { nueva = it }, label = { Text("Nueva (mínimo 8)") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth())
            OutlinedButton({ vm.cambiarPassword(actual, nueva); actual = ""; nueva = "" },
                enabled = actual.isNotEmpty() && nueva.length >= 8) { Text("Guardar") }
        }
    }
}

@Suppress("unused")
private fun Uri.vacia() = this == Uri.EMPTY
