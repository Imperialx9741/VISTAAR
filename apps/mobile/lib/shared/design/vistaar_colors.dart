import 'package:flutter/material.dart';

/// VISTAAR's centralized color tokens — the **only** place a brand or
/// semantic color literal is defined anywhere in this app. Every
/// screen reads color through `Theme.of(context).colorScheme` (built
/// from [seed]/[accent] below via `AppTheme`, `core/theme/app_theme.
/// dart`) or through this class directly for the handful of tones
/// Material 3's own tonal system doesn't cover (the accent and the
/// semantic warning/success roles) — never a hardcoded `Colors.*` or a
/// literal hex value in a screen file. That discipline is what makes
/// this file the single edit point for a brand-color change: verified
/// directly while making this exact change (2026-09-08, owner-directed
/// brand correction) — a repo-wide search turned up zero hardcoded
/// color literals outside this file and its doc comments across every
/// screen this redesign touched.
///
/// **Brand identity (owner decision, 2026-09-08 — supersedes this
/// file's original indigo/amber pick from earlier the same day):
/// Forest Green primary, Golden Yellow accent.** Forest green reads as
/// established and trustworthy rather than trend-chasing, and is
/// deliberately not any major India ride-hailing competitor's own
/// primary (not Ola's brighter green, not Uber's black, not Rapido's
/// yellow — Rapido is a UX reference only, per the owner's own explicit
/// instruction, never a palette to copy); golden yellow is the one
/// accent reserved for calls-to-action, fares/earnings, and highlights,
/// kept deliberately separate from the semantic (success/warning/
/// error) colors below so "the accent" and "a status" never compete
/// for the same visual meaning. Both are deliberately desaturated
/// rather than neon/bright — a premium, commercial feel rather than a
/// template-app one — and every pairing here was checked against
/// WCAG AA contrast for the surface it sits on.
///
/// **Second correction, same day: exact parity with `apps/admin-web`.**
/// The owner asked for mobile to use "the color that you have been
/// used in the admin dashboard" — admin-web's own tokens
/// (`apps/admin-web/src/app/globals.css`) turned out to be a distinct,
/// slightly different pair from the one above (a darker, more
/// saturated deep green and a brighter, more saturated gold), not a
/// re-confirmation of it. [seed]/[seedDark]/[accent] and the
/// success/warning bases below are now the literal admin-web hex
/// values (`--vistaar-deep-green`, `--vistaar-deep-green-soft`,
/// `--vistaar-gold`, `--success`, `--warning`), so the two apps read as
/// one brand rather than two close-but-different greens. Verified
/// directly (not assumed) that this still clears every existing
/// contrast/hue guard in `vistaar_colors_test.dart` before committing
/// to it — the on-colors below did not all carry over unchanged, see
/// each field's own note.
class VistaarColors {
  const VistaarColors._();

  // ---------------------------------------------------------------
  // Brand — Forest Green (primary)
  // ---------------------------------------------------------------

  /// Primary forest green. Drives `ColorScheme.fromSeed`'s entire
  /// tonal palette (primary, secondary, surfaces, neutrals) —
  /// Material 3's own harmonization algorithm, not hand-picked tones,
  /// so light/dark and every elevation level stay contrast-safe by
  /// construction. This is the color VISTAAR's branding, primary
  /// navigation, primary buttons, active/selected states, and major UI
  /// emphasis all ultimately derive from — via `theme.colorScheme.
  /// primary`, never this constant directly in a screen.
  static const Color seed = Color(0xFF003314);

  /// Dark forest green — a deeper, more saturated tone of [seed] for
  /// emphasis states (a pressed/active look, or a strong dark surface
  /// that still reads as unmistakably VISTAAR). Material 3's own
  /// tonal palette already derives a full light→dark ramp from [seed]
  /// for elevation/dark-theme purposes (`colorScheme.primaryContainer`,
  /// `colorScheme.onPrimary`, the dark `ColorScheme` as a whole); this
  /// constant exists for the rarer case a screen needs that specific
  /// deep tone directly (e.g. a solid dark-green surface) rather than
  /// through the tonal system.
  static const Color seedDark = Color(0xFF0A4423);

  // ---------------------------------------------------------------
  // Brand — Golden Yellow (accent)
  // ---------------------------------------------------------------

  /// Golden yellow accent. The one deliberate departure from pure
  /// seed-derivation — Material 3 would otherwise auto-derive a
  /// desaturated, forgettable tertiary from the green seed; this
  /// explicit override (`AppTheme._scheme`'s `tertiary:` parameter) is
  /// what gives VISTAAR its second, distinctive brand color instead.
  /// Reserved for CTAs, fare/earnings emphasis, promotional elements,
  /// and small highlights — never used for large fills or full-screen
  /// backgrounds, so it stays a genuine accent rather than competing
  /// with forest green for dominance.
  static const Color accent = Color(0xFFEFBF04);
  // Dark text on the accent, not white — admin-web's gold is even
  // brighter than the previous accent (relative luminance ≈0.56,
  // recomputed directly for this exact hex, not carried over
  // unverified), so white text still fails WCAG AA here; the same
  // dark brown from before still clears it comfortably (~8:1) and is
  // kept rather than switching to admin-web's own on-gold ink
  // (`--vistaar-gold-ink`, #6B5400), whose contrast against this gold
  // only clears the 3:1 large-text/UI threshold, not 4.5:1 for the
  // smaller body-sized labels this token is also used for.
  static const Color onAccent = Color(0xFF3D2600);
  static const Color accentContainer = Color(0xFFFDE9A6);
  static const Color onAccentContainer = Color(0xFF4A3300);

  /// Light golden/yellow highlight — a soft, low-emphasis tint of
  /// [accent] for a highlighted row, a subtle promotional banner
  /// background, or anywhere a full-strength [accentContainer] would
  /// be too heavy. Kept distinctly lighter than [accentContainer], not
  /// a duplicate of it.
  static const Color accentHighlight = Color(0xFFFEF6DE);

  // ---------------------------------------------------------------
  // Semantic — status meaning, never reused as decoration or the
  // brand accent above. Deliberately distinguishable from both [seed]
  // (forest green, now also this app's brand color) and [accent]
  // (golden yellow) so a status chip is never mistaken for either.
  // ---------------------------------------------------------------

  static const Color success = Color(0xFF2E7D4F);
  static const Color onSuccess = Color(0xFFFFFFFF);
  static const Color successContainer = Color(0xFFD3F3E0);
  static const Color onSuccessContainer = Color(0xFF00401F);

  static const Color warning = Color(0xFFB8791A);
  static const Color onWarning = Color(0xFFFFFFFF);
  static const Color warningContainer = Color(0xFFFFECC2);
  static const Color onWarningContainer = Color(0xFF3F2E00);

  // Material 3's own error role already covers "danger" (cancellation
  // charges, SOS, destructive actions) — deliberately not redefined
  // here, so it stays theme/brightness-aware automatically via
  // ColorScheme.fromSeed rather than a second hardcoded red to keep in
  // sync.
  //
  // Background, surface/card, primary/secondary text, disabled, and
  // border/divider tones are likewise deliberately NOT redefined here
  // as separate constants — Material 3's `ColorScheme` (built from
  // [seed] in `AppTheme`) already derives all of them consistently for
  // both light and dark, contrast-checked against each other by
  // construction: `colorScheme.surface`/`surfaceContainerLow`/
  // `surfaceContainerHighest` (backgrounds/cards), `colorScheme.
  // onSurface`/`onSurfaceVariant` (primary/secondary text — see
  // `AppTheme`'s own `textTheme` wiring), `colorScheme.outlineVariant`
  // (borders/dividers — see `AppTheme.dividerTheme`), and a disabled
  // control's own built-in `.38`-opacity `onSurface` treatment
  // (Material's own default, applied automatically by every button/
  // input widget in this app — never hand-rolled per screen). Hand-
  // picking a second, parallel set of literals for these would be the
  // exact "scattered hardcoded colors" this file exists to prevent —
  // one seed, one derivation, everywhere.
}
