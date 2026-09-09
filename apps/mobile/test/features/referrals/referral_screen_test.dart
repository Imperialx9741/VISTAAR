// Widget tests for ReferralScreen (User-side, built 2026-09-04 — see
// that screen's own doc comment for why this exists): showing the
// customer's own code and attaching a code someone else shared, each
// driven against a real MockClient standing in for the backend.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/referral_api.dart';
import 'package:vistaar_mobile/features/referrals/referral_screen.dart';

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<ReferralApi>(
        create: (_) => ReferralApi(apiClient, () => 'token'),
      ),
    ],
    child: const MaterialApp(home: ReferralScreen()),
  );
}

String _envelope(Object? data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

void main() {
  testWidgets('shows the fetched referral code', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(_envelope({'code': 'ANITA123'}), 200),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('ANITA123'), findsOneWidget);
  });

  testWidgets('attaching posts the entered code and shows the status', (
    tester,
  ) async {
    Map<String, dynamic>? attachBody;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'POST') {
            attachBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(_envelope({'status': 'QUALIFIED'}), 200);
          }
          return http.Response(_envelope({'code': 'ANITA123'}), 200);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Referral code'),
      'FRIEND99',
    );
    await tester.tap(find.text('Attach Code'));
    await tester.pumpAndSettle();

    expect(attachBody?['code'], 'FRIEND99');
    expect(find.text('Referral QUALIFIED.'), findsOneWidget);
  });

  testWidgets('a load failure shows the error message', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            jsonEncode({
              'data': null,
              'error': {'code': 'AUTH_REQUIRED', 'message': 'Not signed in.'},
              'request_id': 'req_test',
            }),
            401,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Not signed in.'), findsOneWidget);
  });
}
