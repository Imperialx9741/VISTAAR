import 'package:flutter_test/flutter_test.dart';
import 'package:customer_mobile/main.dart';

void main() {
  testWidgets('App renders VISTAAR Customer App text', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const VistaarCustomerApp());

    // Verify that the placeholder/home screen displays "VISTAAR Customer App"
    expect(find.text('VISTAAR Customer App'), findsOneWidget);
    expect(find.text('Initial Application Skeleton'), findsOneWidget);
  });
}
