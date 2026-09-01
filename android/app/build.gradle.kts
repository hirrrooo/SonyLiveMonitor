plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val releaseStoreFile = System.getenv("ANDROID_KEYSTORE_FILE")
val releaseStorePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
val releaseKeyAlias = System.getenv("ANDROID_KEY_ALIAS")
val releaseKeyPassword = System.getenv("ANDROID_KEY_PASSWORD")
val hasReleaseSigning = listOf(
    releaseStoreFile,
    releaseStorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { !it.isNullOrBlank() }

val appVersionCode = providers.gradleProperty("versionCode")
    .orNull?.toIntOrNull() ?: 11
val appVersionName = providers.gradleProperty("versionName")
    .orNull ?: "0.11"

android {
    namespace = "com.otoniel.sonylivemonitor"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.otoniel.sonylivemonitor"
        minSdk = 24
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersionName
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = file(releaseStoreFile!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

}

dependencies {
    implementation("androidx.exifinterface:exifinterface:1.4.2")
    implementation("com.github.ernestp.AndroidUSBCamera:libausbc:3.6.0")
    implementation("com.github.ernestp.AndroidUSBCamera:libuvc:3.6.0")
    testImplementation("junit:junit:4.13.2")
}

tasks.withType<Test>().configureEach {
    listOf("arwSample", "arwOutput").forEach { name ->
        System.getProperty(name)?.let { systemProperty(name, it) }
    }
}
