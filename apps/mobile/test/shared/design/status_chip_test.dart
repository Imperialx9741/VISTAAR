import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/shared/design/status_chip.dart';

void main() {
  for (final tone in StatusTone.values) {
    testWidgets('renders its label for tone $tone', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          home: Scaffold(body: StatusChip(label: 'Online', tone: tone)),
        ),
      );

      expect(find.text('Online'), findsOneWidget);
    });
  }

  testWidgets('defaults to neutral tone', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: StatusChip(label: 'Pending')),
      ),
    );

    expect(find.text('Pending'), findsOneWidget);
  });
}
