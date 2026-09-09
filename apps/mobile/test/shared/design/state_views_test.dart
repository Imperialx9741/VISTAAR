import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/shared/design/state_views.dart';

void main() {
  testWidgets('LoadingView shows a spinner and an optional message', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: LoadingView(message: 'Finding your Sarthi…')),
      ),
    );

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Finding your Sarthi…'), findsOneWidget);
  });

  testWidgets('EmptyView shows an icon, title, and optional subtitle', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(
          body: EmptyView(
            icon: Icons.receipt_long_outlined,
            title: 'No rides yet',
            subtitle: 'Your ride history will show up here.',
          ),
        ),
      ),
    );

    expect(find.byIcon(Icons.receipt_long_outlined), findsOneWidget);
    expect(find.text('No rides yet'), findsOneWidget);
    expect(find.text('Your ride history will show up here.'), findsOneWidget);
  });

  testWidgets('ErrorView shows the message and calls onRetry when tapped', (tester) async {
    var retried = false;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: ErrorView(
            message: 'Could not load your wallet.',
            onRetry: () => retried = true,
          ),
        ),
      ),
    );

    expect(find.text('Could not load your wallet.'), findsOneWidget);
    await tester.tap(find.text('Retry'));
    expect(retried, isTrue);
  });

  testWidgets('ErrorView with no onRetry shows no retry button', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: ErrorView(message: 'Something went wrong.')),
      ),
    );

    expect(find.text('Retry'), findsNothing);
  });
}
