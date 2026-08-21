import 'package:flutter_test/flutter_test.dart';
import 'package:driver_mobile/main.dart';

void main() {
  testWidgets('App renders VISTAAR Driver App text', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const VistaarDriverApp());

    // Verify that the placeholder/home screen displays "VISTAAR Driver App"
    expect(find.text('VISTAAR Driver App'), findsOneWidget);
    expect(find.text('Initial Application Skeleton'), findsOneWidget);
  });
}
