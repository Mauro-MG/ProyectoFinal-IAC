import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("com.google.devtools.ksp")
}

// Dirección del gateway HTTPS. Con el emulador y «adb reverse tcp:8443 tcp:443», https://localhost:8443 llega al
// gateway de la computadora y coincide con el nombre del certificado. Se cambia con -PgatewayUrl=https://...
val gatewayUrl = (project.findProperty("gatewayUrl") as String?) ?: "https://localhost:8443"

// El certificado autofirmado del gateway (infra/certs, fuera de git) se copia a los recursos: la app confía
// SOLO en él (y en las autoridades del sistema), no acepta cualquier certificado.
// -PcertificadoGateway=ruta.crt para otro servidor (p. ej. apps/infra/gcp/certificado_gateway_gcp.crt)
val certificadoGateway = (project.findProperty("certificadoGateway") as String?) ?: "../../infra/certs/abastored.crt"
val copiarCertificado by tasks.registering(Copy::class) {
    from(rootProject.file(certificadoGateway))
    into(layout.projectDirectory.dir("src/main/res/raw"))
    rename { "abastored_gateway.crt" }
}
tasks.named("preBuild") { dependsOn(copiarCertificado) }

android {
    namespace = "mx.abastored.movil"
    compileSdk = 36

    defaultConfig {
        applicationId = "mx.abastored.movil"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.3.0"
        buildConfigField("String", "GATEWAY_URL", "\"$gatewayUrl\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // Firma de distribución: llave propia del equipo, FUERA de git (firma/abastored.jks y firma/firma.properties, ver
    // README). Sin esos archivos el APK de release se genera sin firmar.
    val firma = rootProject.file("firma/firma.properties")
    signingConfigs {
        if (firma.exists()) create("equipo") {
            val datos = Properties().apply { firma.inputStream().use { load(it) } }
            storeFile = rootProject.file("firma/abastored.jks")
            storePassword = datos.getProperty("storePassword")
            keyAlias = datos.getProperty("keyAlias")
            keyPassword = datos.getProperty("keyPassword")
        }
    }
    buildTypes {
        release {
            if (firma.exists()) signingConfig = signingConfigs.getByName("equipo")
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions { unitTests.isReturnDefaultValues = true }
}

kotlin { jvmToolchain(17) }

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.09.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.2")
    implementation("androidx.core:core-ktx:1.16.0")

    // HTTP y JSON: la app solo habla JSON con los microservicios por el gateway
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    // Sin conexión: operaciones pendientes y última copia del inventario en SQLite (Room)
    implementation("androidx.room:room-runtime:2.7.2")
    implementation("androidx.room:room-ktx:2.7.2")
    ksp("androidx.room:room-compiler:2.7.2")

    // Sesión (tokens) en DataStore, privada de la app
    implementation("androidx.datastore:datastore-preferences:1.1.7")

    // Lector de códigos de barras y QR con la cámara (ZXing, sin servicios de Google)
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    // Revisión periódica de avisos de negocio en segundo plano
    implementation("androidx.work:work-runtime-ktx:2.10.3")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
}
