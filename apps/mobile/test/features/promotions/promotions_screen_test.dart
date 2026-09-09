// Widget tests for PromotionsScreen (User-side, built 2026-09-04 — see
// that screen's own doc comment for why this exists): listing active
// entitlements, empty state, and redeeming a campaign code, each driven
// against a real MockClient standing in for the backend.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/promotion_api.dart';
import 'package:vistaar_mobile/features/promotions/promotions_screen.dart';

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<PromotionApi>(
        create: (_) => PromotionApi(apiClient, () => 'token'),
      ),
    ],
    child: const MaterialApp(home: PromotionsScreen()),
  );
}

String _envelope(Object? data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

Map<String, dynamic> _entitlementJson({
  String type = 'WELCOME',
  String? campaignId,
}) => {
  'type': type,
  'discount_percent': 10.0,
  'remaining_uses': 3,
  'expires_at': '2099-01-01T00:00:00Z',
  'campaign_id': campaignId,
};

void main() {
  testWidgets('shows active promotions fetched on load', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _envelope({
              'promotions': [_entitlementJson()],
            }),
            200,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Welcome'), findsOneWidget);
    expect(find.textContaining('10% off'), findsOneWidget);
  });

  testWidgets('shows an empty state with no promotions', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async =>
              http.Response(_envelope({'promotions': <dynamic>[]}), 200),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No active promotions.'), findsOneWidget);
  });

  testWidgets('redeeming posts the code/vehicle/fare and refreshes', (
    tester,
  ) async {
    Map<String, dynamic>? redeemBody;
    var redeemed = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'POST') {
            redeemBody = jsonDecode(request.body) as Map<String, dynamic>;
            redeemed = true;
            return http.Response(
              _envelope(_entitlementJson(type: 'CAMPAIGN', campaignId: 'c1')),
              201,
            );
          }
          return http.Response(
            _envelope({
              'promotions': redeemed ? [_entitlementJson(type: 'CAMPAIGN')] : <dynamic>[],
            }),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Campaign code'),
      'SAVE10',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Estimated fare (₹)'),
      '150',
    );
    await tester.ensureVisible(find.text('Redeem'));
    await tester.tap(find.text('Redeem'));
    await tester.pumpAndSettle();

    expect(redeemBody?['code'], 'SAVE10');
    expect(redeemBody?['vehicle_category'], 'BIKE');
    expect(redeemBody?['fare'], '150.00');
    expect(find.text('Code redeemed.'), findsOneWidget);
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
