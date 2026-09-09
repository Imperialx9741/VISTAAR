import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// VISTAAR's own type pairing (Phase 2 design system, 2026-09-08) —
/// replaces the platform default font, which every screen inherited
/// silently and which reads as generic/unbranded on both Android and
/// iOS. Two faces, each doing one job:
///  - "Sora" — geometric, confident, slightly technical — carries
///    headings, fares, and anything meant to be read at a glance
///    (screen titles, the fare figure, the "Book" CTA).
///  - "Manrope" — warm, humanist, highly legible at small sizes —
///    carries body text, labels, and form fields, where long-session
///    readability matters more than personality.
/// Both are open-source (Google Fonts, OFL-licensed) and fetched via
/// `google_fonts`, which caches them on-device after first load — no
/// font files shipped in the repo, no extra `pubspec.yaml` asset
/// wiring.
class VistaarTypography {
  const VistaarTypography._();

  /// Test-only escape hatch. `flutter test` has no reliable network
  /// access and this app ships no bundled .ttf (the runtime fetch is
  /// deliberate — see pubspec.yaml's own comment on the `google_fonts`
  /// dependency), so `GoogleFonts.config.allowRuntimeFetching = false`
  /// (test/flutter_test_config.dart) makes every font "load" fail by
  /// design. That's fine for the *style itself* (google_fonts always
  /// returns a usable [TextStyle] with a system-font fallback
  /// immediately, synchronously) but google_fonts 6.3.3 also creates a
  /// second, internal derived Future via `loadingFuture.then(...)`
  /// (`google_fonts_base.dart` — verified directly against the
  /// installed package source, not assumed) that nothing awaits; when
  /// the load fails, that Future rejects with no listener, which
  /// `flutter_test` reports as an uncaught async error attributed to
  /// whatever test happens to be running — unrelated to anything the
  /// test is actually checking. There is no supported way to prevent
  /// google_fonts from creating that Future once its `.sora()`/
  /// `.manrope()` functions are called at all, so test/
  /// flutter_test_config.dart flips this to false for the whole test
  /// run, and this class skips the google_fonts call paths entirely —
  /// same colors/weights/sizes, platform-default face instead of
  /// Sora/Manrope. Only ever set outside app code, in tests.
  static bool useGoogleFonts = true;

  static TextTheme textTheme(TextTheme base, {required Color displayColor, required Color bodyColor}) {
    final display = base.apply(displayColor: displayColor, bodyColor: displayColor);
    final body = base.apply(displayColor: bodyColor, bodyColor: bodyColor);

    if (!useGoogleFonts) {
      return display.copyWith(
        bodyLarge: body.bodyLarge,
        bodyMedium: body.bodyMedium,
        bodySmall: body.bodySmall,
        labelLarge: body.labelLarge?.copyWith(fontWeight: FontWeight.w600),
        labelMedium: body.labelMedium?.copyWith(fontWeight: FontWeight.w600),
        labelSmall: body.labelSmall?.copyWith(fontWeight: FontWeight.w600),
      );
    }

    return GoogleFonts.soraTextTheme(display).copyWith(
      bodyLarge: GoogleFonts.manrope(textStyle: body.bodyLarge),
      bodyMedium: GoogleFonts.manrope(textStyle: body.bodyMedium),
      bodySmall: GoogleFonts.manrope(textStyle: body.bodySmall),
      labelLarge: GoogleFonts.manrope(textStyle: body.labelLarge, fontWeight: FontWeight.w600),
      labelMedium: GoogleFonts.manrope(textStyle: body.labelMedium, fontWeight: FontWeight.w600),
      labelSmall: GoogleFonts.manrope(textStyle: body.labelSmall, fontWeight: FontWeight.w600),
    );
  }
}
