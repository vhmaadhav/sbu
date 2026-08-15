plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

/**
 * The phone talks to the backend over the LAN, so the APK needs the build machine's
 * current address. That address is handed out by DHCP and changes between sessions,
 * so hardcoding it silently ships a build that points at nothing — the app then just
 * reports "BACKEND OFFLINE". Detect it at build time instead.
 *
 * Override with -PSTUDY_BUDDY_API_URL=... when the backend runs somewhere else.
 * Uses providers.exec so the configuration cache stays valid.
 */
fun defaultApiBaseUrl(): String {
    val detected = providers.exec {
        // en0/en1 cover Wi-Fi on macOS; the hostname -I branch covers Linux.
        commandLine(
            "sh", "-c",
            "ipconfig getifaddr en0 || ipconfig getifaddr en1 || hostname -I 2>/dev/null | awk '{print \$1}'",
        )
        isIgnoreExitValue = true
    }.standardOutput.asText.map { it.trim() }.getOrElse("")

    return if (detected.isNotEmpty()) {
        "http://$detected:8010"
    } else {
        // Detection failed (no LAN, unusual interface layout). Fall back to the
        // emulator's alias for the host loopback rather than a stale literal IP.
        logger.warn("STUDY_BUDDY: could not detect a LAN IP; defaulting to the emulator host alias.")
        "http://10.0.2.2:8010"
    }
}

android {
    namespace = "com.example.mobile"
    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.example.mobile"
        minSdk = 35
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        buildConfigField(
            "String",
            "API_BASE_URL",
            "\"${providers.gradleProperty("STUDY_BUDDY_API_URL").orElse(defaultApiBaseUrl()).get().trimEnd('/')}\"",
        )

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
