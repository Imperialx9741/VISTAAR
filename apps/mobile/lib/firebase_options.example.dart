// CI-ONLY STUB — NOT the real FlutterFire CLI output.
//
// This file exists solely so `flutter analyze` (and any other static
// check that resolves `lib/main.dart`'s `import 'firebase_options.dart'`)
// has something to type-check against on a clean checkout, where the
// real `lib/firebase_options.dart` is intentionally absent — it's
// FlutterFire CLI output tied to the real "VISTAAR Production" Firebase
// project, gitignored on purpose (see apps/mobile/.gitignore, ADR-0052,
// and README.md §13 — the same never-in-git discipline this codebase
// applies to every other provider credential).
//
// Every value below is an obviously fake, non-functional placeholder —
// structurally shaped like a real FlutterFire-generated `FirebaseOptions`
// object (same class, same per-platform getters, same field set per
// platform) but incapable of authenticating against any real Firebase
// project. `flutter analyze` only needs these symbols to exist and
// type-check correctly; it never calls Firebase over the network, and
// nothing in CI (.github/workflows/ci.yml) ever calls
// `Firebase.initializeApp()` for real or builds an installable artifact.
//
// A real local developer still runs `flutterfire configure` to produce
// the actual `lib/firebase_options.dart` (gitignored, never committed) —
// this file is copied into that same path ONLY inside CI
// (.github/workflows/ci.yml's "Provide CI-only Firebase config stub"
// step), never checked out over a real local copy.
//
// ignore_for_file: type=lint
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

/// CI-only stand-in for [DefaultFirebaseOptions] — see file header.
class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for macos - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      case TargetPlatform.windows:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for windows - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      case TargetPlatform.linux:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for linux - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not supported for this platform.',
        );
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'ci-stub-fake-web-api-key',
    appId: '1:000000000000:web:0000000000000000000000',
    messagingSenderId: '000000000000',
    projectId: 'vistaar-ci-stub-placeholder',
    authDomain: 'vistaar-ci-stub-placeholder.firebaseapp.com',
    storageBucket: 'vistaar-ci-stub-placeholder.appspot.com',
    measurementId: 'G-0000000000',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'ci-stub-fake-android-api-key',
    appId: '1:000000000000:android:0000000000000000000000',
    messagingSenderId: '000000000000',
    projectId: 'vistaar-ci-stub-placeholder',
    storageBucket: 'vistaar-ci-stub-placeholder.appspot.com',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'ci-stub-fake-ios-api-key',
    appId: '1:000000000000:ios:0000000000000000000000',
    messagingSenderId: '000000000000',
    projectId: 'vistaar-ci-stub-placeholder',
    storageBucket: 'vistaar-ci-stub-placeholder.appspot.com',
    iosBundleId: 'com.vistaar.ci.stub.placeholder',
  );
}
