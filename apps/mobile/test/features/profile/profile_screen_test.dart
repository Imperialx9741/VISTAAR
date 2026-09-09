// Widget tests for ProfileScreen (User-side, built 2026-09-04 — see
// that screen's own doc comment for why this exists): loads the
// existing profile and saves an edit, each driven against a real
// MockClient standing in for the backend.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/customer_api.dart';
import 'package:vistaar_mobile/features/profile/profile_screen.dart';

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<CustomerApi>(
        create: (_) => CustomerApi(apiClient, () => 'token'),
      ),
    ],
    child: const MaterialApp(home: ProfileScreen()),
  );
}

String _envelope(Object? data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

Map<String, dynamic> _profileJson({String fullName = 'Anita Rao'}) => {
  'customer_id': 'customer-1',
  'phone': '+919999999999',
  'full_name': fullName,
  'profile_photo_uri': null,
  'language': 'en',
  'notification_enabled': true,
  'status': 'ACTIVE',
  'created_at': '2026-09-04T00:00:00Z',
  'updated_at': '2026-09-04T00:00:00Z',
};

void main() {
  testWidgets('loads and shows the existing profile', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(_envelope(_profileJson()), 200),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('+919999999999'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Full name'), findsOneWidget);
    expect(
      (tester.widget(find.widgetWithText(TextField, 'Full name')) as TextField)
          .controller
          ?.text,
      'Anita Rao',
    );
  });

  testWidgets('saving sends the edited name via PATCH', (tester) async {
    Map<String, dynamic>? patchedBody;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'PATCH') {
            patchedBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              _envelope(_profileJson(fullName: 'Anita R.')),
              200,
            );
          }
          return http.Response(_envelope(_profileJson()), 200);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Full name'),
      'Anita R.',
    );
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(patchedBody?['full_name'], 'Anita R.');
    expect(find.text('Profile updated.'), findsOneWidget);
  });

  testWidgets('a load failure shows the error banner', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            jsonEncode({
              'data': null,
              'error': {'code': 'UNKNOWN_ERROR', 'message': 'Something went wrong.'},
              'request_id': 'req_test',
            }),
            500,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong.'), findsOneWidget);
  });
}
