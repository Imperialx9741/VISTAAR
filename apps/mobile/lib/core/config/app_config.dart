/// App-wide configuration.
///
/// [apiBaseUrl] points at the FastAPI backend (apps/backend,
/// core/config.py's default `127.0.0.1:8000`). Override at build/run time
/// with `--dart-define=API_BASE_URL=http://<host>:<port>` — the default
/// below only works for a desktop/web/iOS-simulator target talking to a
/// backend on the same machine. An Android emulator cannot reach the host
/// machine via `127.0.0.1` (it has its own loopback) — use
/// `http://10.0.2.2:8000` instead, e.g.:
///
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
///
/// [mapTilerApiKey] is MapTiler Cloud's API key (owner decision,
/// 2026-08-29 — see docs/16-mobile/mobile-app-implementation-plan.md
/// §6.4). Never hardcoded here and never committed to git — supplied at
/// build/run time the same way [apiBaseUrl] is, conventionally via
/// `--dart-define-from-file=dart_define.json` (a git-ignored local file,
/// see `dart_define.example.json` for the shape and the README for the
/// full setup). Empty string is a real, supported value — every screen
/// that reads it must treat "no key configured" as "maps disabled," the
/// same "wired, real credential arrives later" pattern this codebase's
/// backend follows for every other provider integration (e.g. MSG91,
/// Sentry).
class AppConfig {
  const AppConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static const String mapTilerApiKey = String.fromEnvironment(
    'MAPTILER_API_KEY',
  );

  /// Whether a real key was actually supplied — screens that need a map
  /// check this rather than comparing [mapTilerApiKey] to `''` directly,
  /// so the "no key" check reads as intent, not a magic-string comparison.
  static bool get hasMapTilerApiKey => mapTilerApiKey.isNotEmpty;

  /// Sentry Flutter's project DSN (2026-09-08, owner decision — a
  /// separate Sentry project per app, `vistaar-3j` org, so mobile
  /// crashes don't mix into the backend's own error feed). Same
  /// "wired, real credential arrives later" pattern as [mapTilerApiKey]
  /// above — `SentryFlutter.init` treats an empty/missing DSN as its
  /// own documented disabled state (verified against the backend's
  /// identical `sentry_sdk.init(dsn="")` behavior, ADR-0053), so no
  /// separate `hasSentryDsn`-style branch is needed anywhere this is
  /// read; `main.dart` passes it straight through.
  static const String sentryDsn = String.fromEnvironment('SENTRY_DSN');
}
