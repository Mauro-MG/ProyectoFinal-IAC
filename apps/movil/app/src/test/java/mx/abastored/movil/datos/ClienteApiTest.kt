package mx.abastored.movil.datos

import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

private class AlmacenMemoria(var tokens: Tokens?) : AlmacenTokens {
    override suspend fun leer() = tokens
    override suspend fun guardar(tokens: Tokens?) { this.tokens = tokens }
}

class ClienteApiTest {
    private lateinit var servidor: MockWebServer
    private lateinit var almacen: AlmacenMemoria
    private lateinit var api: ClienteApi

    @Before
    fun preparar() {
        servidor = MockWebServer().apply { start() }
        almacen = AlmacenMemoria(Tokens("viejo", "refresh-1"))
        api = ClienteApi(servidor.url("/").toString(), almacen)
    }

    @After
    fun terminar() = servidor.shutdown()

    @Test
    fun usaLaRutaDelGatewayYElTokenDelUsuario() = runTest {
        servidor.enqueue(MockResponse().setBody("""{"items":[{"id":"c1","nombre_comercio":"Puesto 7"}]}"""))
        val lista = api.get<ListaComercios>("comercios", "/comercios")
        val peticion = servidor.takeRequest()
        assertEquals("/ms/comercios/api/v1/comercios", peticion.path)
        assertEquals("Bearer viejo", peticion.getHeader("Authorization"))
        assertTrue(peticion.getHeader("X-Correlation-ID")!!.startsWith("android-"))
        assertEquals("Puesto 7", lista.items.single().nombre)
    }

    @Test
    fun un401RenuevaElTokenUnaVezYRepiteLaPeticion() = runTest {
        servidor.enqueue(MockResponse().setResponseCode(401).setBody(error("token_expirado", "El token expiró")))
        servidor.enqueue(MockResponse().setBody("""{"access_token":"nuevo","refresh_token":"refresh-2"}"""))
        servidor.enqueue(MockResponse().setBody("""{"pedidos":[]}"""))

        api.get<ListaPedidos>("pedidos", "/pedidos")

        servidor.takeRequest()
        val renovar = servidor.takeRequest()
        assertEquals("/ms/seguridad/api/v1/auth/renovar", renovar.path)
        assertTrue(renovar.body.readUtf8().contains("refresh-1"))
        assertEquals("Bearer nuevo", servidor.takeRequest().getHeader("Authorization"))
        assertEquals("refresh-2", almacen.tokens?.refreshToken)
    }

    @Test
    fun siNoSePuedeRenovarSeCierraLaSesion() = runTest {
        var cerrada = false
        api.alCerrarSesion = { cerrada = true }
        servidor.enqueue(MockResponse().setResponseCode(401).setBody(error("token_revocado", "Sesión cerrada")))
        servidor.enqueue(MockResponse().setResponseCode(401).setBody(error("refresh_invalido", "Inválido")))
        servidor.enqueue(MockResponse().setResponseCode(401).setBody(error("token_revocado", "Sesión cerrada")))
        try {
            api.get<ListaPedidos>("pedidos", "/pedidos")
            fail("debía fallar")
        } catch (e: ErrorApi) {
            assertEquals(401, e.status)
        }
        assertNull(almacen.tokens)
        assertTrue(cerrada)
    }

    @Test
    fun losErroresTraenElMensajeDelServicio() = runTest {
        servidor.enqueue(MockResponse().setResponseCode(409).setBody(
            error("existencia_insuficiente", "No hay suficiente arroz", """[{"campo":"cantidad","mensaje":"máximo 3"}]""")))
        try {
            api.peticion("ventas", "POST", "/ventas", "{}")
            fail("debía fallar")
        } catch (e: ErrorApi) {
            assertEquals("existencia_insuficiente", e.codigo)
            assertTrue(e.message.contains("No hay suficiente arroz") && e.message.contains("máximo 3"))
            assertTrue(!e.sinConexion)
        }
    }

    @Test
    fun sinServidorEsSinConexion() = runTest {
        servidor.shutdown()
        try {
            api.peticion("ventas", "POST", "/ventas", "{}")
            fail("debía fallar")
        } catch (e: ErrorApi) {
            assertTrue(e.sinConexion)
        }
    }

    private fun error(codigo: String, mensaje: String, detalles: String = "[]") =
        """{"error":{"codigo":"$codigo","mensaje":"$mensaje","detalles":$detalles,"status":0,"correlation_id":"x"}}"""
}
