package mx.abastored.movil.datos

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Cifrado de la sesión con una llave AES-256 que vive en el Android Keystore: la genera el propio
 * teléfono, nunca sale del almacén seguro (no se puede exportar) y se usa con AES/GCM (cifra y autentica).
 * Así los tokens guardados en DataStore no se pueden leer ni alterar copiando los archivos de la app.
 */
object Cifrado {
    private const val ALIAS = "abastored_sesion"
    private const val TRANSFORMACION = "AES/GCM/NoPadding"

    private fun llave(): SecretKey {
        val almacen = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (almacen.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build())
        }.generateKey()
    }

    fun cifrar(texto: String): String {
        val cifrador = Cipher.getInstance(TRANSFORMACION).apply { init(Cipher.ENCRYPT_MODE, llave()) }
        val datos = cifrador.iv + cifrador.doFinal(texto.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(datos, Base64.NO_WRAP)
    }

    /** null si el texto fue alterado o la llave ya no existe (p. ej. se restauró la app en otro teléfono). */
    fun descifrar(texto: String): String? = try {
        val datos = Base64.decode(texto, Base64.NO_WRAP)
        val cifrador = Cipher.getInstance(TRANSFORMACION).apply {
            init(Cipher.DECRYPT_MODE, llave(), GCMParameterSpec(128, datos, 0, 12))
        }
        String(cifrador.doFinal(datos, 12, datos.size - 12), Charsets.UTF_8)
    } catch (_: Exception) {
        null
    }
}
