import 'dart:async';

import 'package:vistaar_mobile/shared/design/vistaar_typography.dart';

/// Runs once, wrapping every test in and under this directory (the
/// Flutter test framework's own convention for a file named exactly
/// this) — added 2026-09-08 alongside AppTheme's move to google_fonts
/// (Phase 2 design system).
///
/// `flutter test` has no reliable network access, and google_fonts
/// 6.3.3 has a rough edge when a font can't be loaded (no bundled
/// asset, fetching disallowed or unreachable): it creates an internal
/// derived Future — via `loadingFuture.then(...)` in its own
/// `google_fonts_base.dart`, verified directly against the installed
/// package source — that nothing awaits, so a failed load surfaces as
/// an uncaught async error attributed to whatever test happens to be
/// running at the time, not to whatever the test actually checks.
/// Confirmed directly: a real `flutter test` run here failed
/// intermittently on unrelated tests both with real network access
/// (one font fetch genuinely failed mid-suite) and with
/// `GoogleFonts.config.allowRuntimeFetching = false` (deterministic
/// "not bundled" failures instead). Neither is fixable from the
/// calling side — there is no supported way to stop google_fonts from
/// creating that unlistened Future once its font functions are called.
/// [VistaarTypography.useGoogleFonts] is this app's own seam instead:
/// off for the whole test run, every test gets a fully valid TextTheme
/// (same colors/weights, platform-default face) without ever calling
/// into google_fonts. The real app never sets this — only test code
/// does, here.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  VistaarTypography.useGoogleFonts = false;
  await testMain();
}
