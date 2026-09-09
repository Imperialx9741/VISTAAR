import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/shared/design/vistaar_bottom_sheet.dart';

void main() {
  testWidgets('shows the sheet content and returns the popped value', (tester) async {
    Object? result;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () async {
                  result = await showVistaarBottomSheet<String>(
                    context: context,
                    builder: (context) => TextButton(
                      onPressed: () => Navigator.of(context).pop('picked'),
                      child: const Text('Pick vehicle'),
                    ),
                  );
                },
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.text('Pick vehicle'), findsOneWidget);

    await tester.tap(find.text('Pick vehicle'));
    await tester.pumpAndSettle();

    expect(result, 'picked');
  });
}
