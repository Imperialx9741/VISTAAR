// Unit tests for AppTheme (dark theme added 2026-09-07 — see that
// class's own doc comment for why this exists).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';

void main() {
  test('light is a light-brightness scheme', () {
    expect(AppTheme.light.colorScheme.brightness, Brightness.light);
  });

  test('dark is a dark-brightness scheme derived from the same seed', () {
    expect(AppTheme.dark.colorScheme.brightness, Brightness.dark);
  });

  test('light and dark use the same seed color, so different surfaces', () {
    // Not the same scheme object, and their surface colors differ —
    // proves `dark` isn't accidentally just a copy of `light`.
    expect(
      AppTheme.dark.colorScheme.surface,
      isNot(AppTheme.light.colorScheme.surface),
    );
  });
}
