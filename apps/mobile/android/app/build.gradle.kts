import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    // START: FlutterFire Configuration
    id("com.google.gms.google-services")
    // END: FlutterFire Configuration
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Android production signing (docs/16-mobile/android-release-signing.md,
// ADR-0064, 2026-09-03). key.properties is gitignored (android/
// .gitignore already covers it, plus **/*.keystore and **/*.jks) — it
// holds the real store/key passwords and the real keystore's absolute
// path, never committed. Loaded conditionally, not required: a
// checkout without key.properties (any other developer, CI without the
// real file) must still be able to run `flutter build` — see the
// signingConfig fallback in the `release` buildType below for what
// happens when it's absent.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
val hasRealSigningConfig = keystorePropertiesFile.exists()
if (hasRealSigningConfig) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "com.vistaar.vistaar_mobile"
    // flutter.compileSdkVersion currently resolves to 36 (Flutter
    // 3.47.0's own bundled default), but flutter_secure_storage 11.x
    // (pre-existing dependency, unrelated to the Contacts picker) now
    // requires compiling against 37 — discovered only once a real debug
    // APK was actually built, since flutter analyze/flutter test never
    // exercise the native Android Gradle build at all. Overriding here
    // (Gradle's own recommended fix) only raises the compile-time API
    // surface available; minSdk/targetSdk below are untouched, so this
    // doesn't change which devices the app installs on or its runtime
    // behavior.
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.vistaar.vistaar_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasRealSigningConfig) {
            create("release") {
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Real production signing (android-release-signing.md,
            // ADR-0064) when key.properties exists (the real, gitignored
            // file — see that doc for where the actual keystore lives);
            // falls back to the debug key otherwise, so `flutter build
            // --release`/`flutter run --release` still work for anyone
            // without the real signing credentials (any other developer,
            // CI without the real file) — same fallback Flutter's own
            // default template scaffolds, just made conditional instead
            // of hardcoded.
            signingConfig = if (hasRealSigningConfig) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
