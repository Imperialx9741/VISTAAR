// Guards the owner's brand-color correction (2026-09-08: Forest Green
// primary, Golden Yellow accent — supersedes this file's original
// indigo/amber pick from earlier the same day) against silent drift.
// Checked by hue, not exact RGB equality, so a legitimate future
// fine-tune within the same brand family doesn't need to update this
// test — only an actual departure from "green" or "gold" would fail it.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/shared/design/vistaar_colors.dart';

void main() {
  test('the brand seed is a forest green, not the old indigo', () {
    final hue = HSLColor.fromColor(VistaarColors.seed).hue;
    // Green hues fall roughly 90°-160° on the color wheel.
    expect(hue, inInclusiveRange(90, 160));
    // "Forest", not neon — a muted, fairly dark green, not a bright
    // saturated one.
    expect(HSLColor.fromColor(VistaarColors.seed).lightness, lessThan(0.3));
  });

  test('the brand accent is a golden yellow, not the old amber-orange', () {
    final hue = HSLColor.fromColor(VistaarColors.accent).hue;
    // Golden-yellow hues fall roughly 35°-55°.
    expect(hue, inInclusiveRange(35, 55));
  });

  test('AppTheme.light derives primary/tertiary from the brand colors', () {
    final scheme = AppTheme.light.colorScheme;
    expect(HSLColor.fromColor(scheme.primary).hue, inInclusiveRange(90, 160));
    expect(scheme.tertiary, VistaarColors.accent);
  });

  test('AppTheme.dark also derives primary from the forest-green seed', () {
    final scheme = AppTheme.dark.colorScheme;
    expect(HSLColor.fromColor(scheme.primary).hue, inInclusiveRange(90, 160));
  });

  test('onAccent has sufficient contrast against accent (WCAG AA-ish)', () {
    // A quick, real check rather than an assumption — the accent is a
    // mid-toned gold, light enough that white text would fail contrast
    // against it; this asserts the chosen on-color is the dark one.
    expect(
      HSLColor.fromColor(VistaarColors.onAccent).lightness,
      lessThan(HSLColor.fromColor(VistaarColors.accent).lightness),
    );
  });
}
