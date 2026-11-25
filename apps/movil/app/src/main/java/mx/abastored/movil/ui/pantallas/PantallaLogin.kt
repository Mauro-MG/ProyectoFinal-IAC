package mx.abastored.movil.ui.pantallas

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
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import mx.abastored.movil.BuildConfig

/** Inicio de sesión o registro simplificado (ms-seguridad). El registro deja la sesión iniciada. */
@Composable
fun PantallaLogin(ocupado: Boolean, modifier: Modifier, entrar: (String, String) -> Unit,
                  registrarse: (String, String, String, String, String?, String) -> Unit) {
    var registro by rememberSaveable { mutableStateOf(false) }
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var nombre by rememberSaveable { mutableStateOf("") }
    var apellido by rememberSaveable { mutableStateOf("") }
    var telefono by rememberSaveable { mutableStateOf("") }
    var perfil by rememberSaveable { mutableStateOf("Comerciante Informal") }
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
    ) {
        Text("AbastoRed", style = MaterialTheme.typography.headlineLarge, color = MaterialTheme.colorScheme.primary)
        Text(if (registro) "Crea tu cuenta en un minuto." else
            "Tu inventario, tus ventas y tus pedidos de abasto, aunque no tengas señal.",
            style = MaterialTheme.typography.bodyMedium)
        if (registro) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("Comerciante Informal" to "Puesto o tianguis", "Minorista Formal" to "Tienda formal").forEach {
                    FilterChip(perfil == it.first, { perfil = it.first }, label = { Text(it.second) })
                }
            }
            OutlinedTextField(nombre, { nombre = it }, label = { Text("Nombre") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(apellido, { apellido = it }, label = { Text("Apellido") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(telefono, { telefono = it.filter(Char::isDigit).take(10) }, label = { Text("Teléfono (10 dígitos, opcional)") },
                singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone), modifier = Modifier.fillMaxWidth())
        }
        OutlinedTextField(email, { email = it }, label = { Text("Correo") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(password, { password = it }, label = { Text(if (registro) "Contraseña (mínimo 8)" else "Contraseña") },
            singleLine = true, visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth())
        if (registro) {
            val valido = nombre.length >= 2 && apellido.length >= 2 && email.contains('@') && password.length >= 8 &&
                (telefono.isEmpty() || telefono.length == 10)
            Button({ registrarse(nombre, apellido, email, password, telefono.ifBlank { null }, perfil) },
                enabled = !ocupado && valido, modifier = Modifier.fillMaxWidth()) { Text(if (ocupado) "Creando…" else "Crear cuenta") }
        } else {
            Button(onClick = { entrar(email, password) }, enabled = !ocupado && email.isNotBlank() && password.isNotBlank(),
                modifier = Modifier.fillMaxWidth()) { Text(if (ocupado) "Entrando…" else "Entrar") }
        }
        TextButton({ registro = !registro }) { Text(if (registro) "Ya tengo cuenta" else "Crear una cuenta nueva") }
        Text("Servidor: ${BuildConfig.GATEWAY_URL}", style = MaterialTheme.typography.labelSmall)
    }
}
