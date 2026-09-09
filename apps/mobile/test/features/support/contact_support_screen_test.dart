// Widget tests for ContactSupportScreen and SupportCaseScreen (build
// order step 8 — docs/16-mobile/mobile-app-implementation-plan.md
// §4.9/§5.7): creating a support case and being shown its detail.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/support_api.dart';
import 'package:vistaar_mobile/features/support/contact_support_screen.dart';

Widget _wrap(http.Client mockHttpClient, {String? rideId}) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<SupportApi>(
        create: (_) => SupportApi(apiClient, () => 'user-token'),
      ),
    ],
    child: MaterialApp(home: ContactSupportScreen(rideId: rideId)),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Map<String, dynamic> _caseJson({
  String? category,
  List<Map<String, dynamic>> messages = const [],
}) => {
  'case_id': 'case-1',
  'ride_id': null,
  'category': category,
  'priority': 'NORMAL',
  'status': 'OPEN',
  'assigned_admin_id': null,
  'created_at': '2026-08-31T10:00:00Z',
  'updated_at': '2026-08-31T10:00:00Z',
  'messages': messages,
};

void main() {
  testWidgets('an empty message blocks submission without calling the API', (
    tester,
  ) async {
    var called = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((_) async {
          called = true;
          return http.Response(_envelope(_caseJson()), 201);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();

    expect(called, isFalse);
    expect(find.text('Enter a message.'), findsOneWidget);
  });

  testWidgets(
    'submitting creates the case, fetches it, and shows the detail screen',
    (tester) async {
      Map<String, dynamic>? createBody;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.method == 'POST' &&
                request.url.path == '/api/v1/support/cases') {
              createBody = jsonDecode(request.body) as Map<String, dynamic>;
              return http.Response(_envelope(_caseJson()), 201);
            }
            if (request.url.path == '/api/v1/support/cases/case-1') {
              return http.Response(
                _envelope(
                  _caseJson(
                    category: 'PAYMENT',
                    messages: [
                      {
                        'sender_type': 'CUSTOMER',
                        'sender_id': 'user-1',
                        'message': 'Payment issue',
                        'created_at': '2026-08-31T10:00:00Z',
                      },
                    ],
                  ),
                ),
                200,
              );
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextField, 'Category (optional)'),
        'payment',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'How can we help?'),
        'Payment issue',
      );
      await tester.tap(find.text('Submit'));
      await tester.pumpAndSettle();

      expect(createBody?['message'], 'Payment issue');
      expect(createBody?['category'], 'payment');
      expect(createBody?.containsKey('ride_id'), isFalse);
      expect(find.text('Support Case'), findsOneWidget);
      expect(find.text('Case case-1'), findsOneWidget);
      expect(find.text('Category: PAYMENT'), findsOneWidget);
      expect(find.text('Payment issue'), findsOneWidget);
    },
  );

  testWidgets('a rideId is included in the create request when supplied', (
    tester,
  ) async {
    Map<String, dynamic>? createBody;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'POST' &&
              request.url.path == '/api/v1/support/cases') {
            createBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(_envelope(_caseJson()), 201);
          }
          return http.Response(_envelope(_caseJson()), 200);
        }),
        rideId: 'ride-42',
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('About ride ride-42'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextField, 'How can we help?'),
      'Fare seems wrong',
    );
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();

    expect(createBody?['ride_id'], 'ride-42');
  });

  testWidgets('a failed create surfaces the backend error', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _errorEnvelope('RIDE_NOT_FOUND', 'Ride not found.'),
            404,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'How can we help?'),
      'Fare seems wrong',
    );
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();

    expect(find.text('Ride not found.'), findsOneWidget);
  });
}
