import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/shared/design/vistaar_card.dart';

void main() {
  testWidgets('renders its child', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: VistaarCard(child: Text('Ride summary'))),
      ),
    );

    expect(find.text('Ride summary'), findsOneWidget);
  });

  testWidgets('with no onTap, is not tappable', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: VistaarCard(child: Text('Static'))),
      ),
    );

    expect(find.byType(InkWell), findsNothing);
  });

  testWidgets('with onTap, calls it when tapped', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: VistaarCard(
            onTap: () => tapped = true,
            child: const Text('Tap me'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Tap me'));
    expect(tapped, isTrue);
  });
}
