import 'package:flutter/material.dart';

import '../../shared/design/vistaar_colors.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/design/vistaar_typography.dart';

/// One shared theme for both roles — role identity is communicated by
/// screen content (which role you picked, and which home screen you land
/// on), not by re-skinning the whole app, since it is one app now
/// (ADR-0027).
///
/// Rebuilt 2026-09-08 for the owner-requested UI/UX redesign (Phase 2,
/// design system) — same single-seed, `ColorScheme.fromSeed` mechanism
/// as before (so light/dark and every Material 3 surface/elevation
/// tone stay contrast-safe by construction, per the existing
/// [dark]-support rationale below), now seeded from
/// [VistaarColors.seed] instead of an arbitrary blue, with an explicit
/// `tertiary` override for [VistaarColors.accent] — `ColorScheme.
/// fromSeed` only accepts one `seedColor` (confirmed directly against
/// the installed Flutter SDK's own `color_scheme.dart`; there is no
/// second "accent seed" parameter), so a deliberately distinctive
/// second brand color requires overriding that one role explicitly
/// rather than letting Material 3 auto-derive a desaturated tertiary
/// from the indigo seed. Component themes below (buttons, inputs,
/// cards, chips, app bar, bottom sheet) exist so every redesigned
/// screen picks up VISTAAR's look by using the ambient `Theme.of
/// (context)` defaults, rather than each screen re-specifying its own
/// button/card style — the "reusable components rather than styling
/// each screen independently" requirement.
///
/// [dark] added 2026-09-07 — the app previously defined only [light]
/// and had no `darkTheme` wired in `main.dart` at all, so a device set
/// to system dark mode was silently forced into the light theme
/// regardless. Verified before adding this that it was safe to do with
/// no other changes: every screen in this app already pulls its colors
/// from `Theme.of(context).colorScheme` rather than a hardcoded
/// literal, so defining the second palette here is the entire fix. (A
/// handful of semantic status tints — `Colors.green`/`Colors.orange`/
/// `Colors.blue` for online/warning/decorative indicators — were the
/// one exception at the time; a brand-color compliance sweep,
/// 2026-09-08, replaced every one of them with [VistaarColors]'
/// success/warning tokens or `colorScheme.primary`, so that exception
/// no longer applies — verified via a repo-wide grep, not assumed.)
class AppTheme {
  const AppTheme._();

  static ColorScheme _scheme(Brightness brightness) => ColorScheme.fromSeed(
        seedColor: VistaarColors.seed,
        brightness: brightness,
        tertiary: VistaarColors.accent,
        onTertiary: VistaarColors.onAccent,
        tertiaryContainer: VistaarColors.accentContainer,
        onTertiaryContainer: VistaarColors.onAccentContainer,
      );

  static ThemeData _build(Brightness brightness) {
    final scheme = _scheme(brightness);
    final textTheme = VistaarTypography.textTheme(
      ThemeData(brightness: brightness, useMaterial3: true).textTheme,
      displayColor: scheme.onSurface,
      bodyColor: scheme.onSurface,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      textTheme: textTheme,
      scaffoldBackgroundColor: scheme.surface,
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 1,
        centerTitle: false,
        titleTextStyle: textTheme.titleLarge,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surfaceContainerLow,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(VistaarRadius.surface),
        ),
        margin: EdgeInsets.zero,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(VistaarRadius.control),
          ),
          textStyle: textTheme.labelLarge,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(VistaarRadius.control),
          ),
          textStyle: textTheme.labelLarge,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          textStyle: textTheme.labelLarge,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest.withValues(alpha: 0.4),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: VistaarSpacing.md,
          vertical: VistaarSpacing.md,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(VistaarRadius.control),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(VistaarRadius.control),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(VistaarRadius.control),
          borderSide: BorderSide(color: scheme.primary, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(VistaarRadius.control),
          borderSide: BorderSide(color: scheme.error, width: 1.5),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: scheme.surfaceContainerHighest,
        // A selected ChoiceChip (vehicle category, cab tier, quick
        // recharge amount) is exactly the "selected accents" role the
        // owner's brand brief calls out for golden yellow — set once
        // here so every chip in the app picks it up, not per screen.
        selectedColor: scheme.tertiaryContainer,
        labelStyle: textTheme.labelMedium,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(VistaarRadius.control),
        ),
        side: BorderSide.none,
        padding: const EdgeInsets.symmetric(horizontal: VistaarSpacing.sm, vertical: VistaarSpacing.xs),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: scheme.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(VistaarRadius.surface)),
        ),
        showDragHandle: true,
      ),
      dialogTheme: DialogThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(VistaarRadius.surface),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: scheme.surface,
        elevation: 0,
        indicatorColor: scheme.primaryContainer,
        labelTextStyle: WidgetStateProperty.all(textTheme.labelSmall),
      ),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: VistaarSpacing.lg),
    );
  }

  static ThemeData get light => _build(Brightness.light);

  static ThemeData get dark => _build(Brightness.dark);
}
