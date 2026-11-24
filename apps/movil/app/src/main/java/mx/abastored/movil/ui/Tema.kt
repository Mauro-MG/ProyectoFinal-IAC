package mx.abastored.movil.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Verde = Color(0xFF2F6B4F)
val Ambar = Color(0xFFB7791F)
val Rojo = Color(0xFFB3261E)

private val Claro = lightColorScheme(primary = Verde, secondary = Color(0xFF4F7A65), tertiary = Ambar)
private val Oscuro = darkColorScheme(primary = Color(0xFF8CCBA9), secondary = Color(0xFFA5C9B6), tertiary = Color(0xFFE8B86A))

@Composable
fun TemaAbastoRed(contenido: @Composable () -> Unit) =
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Oscuro else Claro, content = contenido)
