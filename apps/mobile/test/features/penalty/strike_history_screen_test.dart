// Widget tests for StrikeHistoryScreen (Sarthi-side, built 2026-09-04,
// ADR-0073 — see that screen's own doc comment for why this exists):
// listing, empty state, pagination, each driven against a real
// MockClient standing in for the backend.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/driver_api.dart';
import 'package:vistaar_mobile/features/penalty/strike_history_screen.dart';

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<DriverApi>(create: (_) => DriverApi(apiClient, () => 'token')),
    ],
    child: const MaterialApp(home: StrikeHistoryScreen()),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Map<String, dynamic> _strikeJson({
  String id = 'strike-1',
  String reason = 'DRIVER_CANCELLATION',
}) => {
  'strike_id': id,
  'driver_id': 'driver-1',
  'ride_id': 'ride-1',
  'reason': reason,
  'created_at': '2026-09-04T10:00:00Z',
};

Map<String, dynamic> _pageJson({
  required List<Map<String, dynamic>> items,
  int page = 1,
  int totalPages = 1,
}) => {
  'items': items,
  'pagination': {
    'page': page,
    'page_size': 20,
    'total': items.length,
    'total_pages': totalPages,
  },
};

void main() {
  testWidgets('shows strikes fetched on load', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _envelope(_pageJson(items: [_strikeJson()])),
            200,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('DRIVER_CANCELLATION'), findsOneWidget);
  });

  testWidgets('shows an empty state with no strikes', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(_envelope(_pageJson(items: [])), 200),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No strikes on your record.'), findsOneWidget);
  });

  testWidgets('a load failure surfaces the backend error', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _errorEnvelope('AUTH_REQUIRED', 'Not signed in.'),
            401,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Not signed in.'), findsOneWidget);
  });

  testWidgets('Load more fetches and appends the next page', (tester) async {
    final requestedPages = <String>[];
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          final page = request.url.queryParameters['page'] ?? '1';
          requestedPages.add(page);
          if (page == '1') {
            return http.Response(
              _envelope(
                _pageJson(
                  items: [_strikeJson(id: 'strike-1')],
                  page: 1,
                  totalPages: 2,
                ),
              ),
              200,
            );
          }
          return http.Response(
            _envelope(
              _pageJson(
                items: [
                  _strikeJson(id: 'strike-2', reason: 'UNWILLING_TO_PROCEED'),
                ],
                page: 2,
                totalPages: 2,
              ),
            ),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Load more'), findsOneWidget);
    expect(find.text('UNWILLING_TO_PROCEED'), findsNothing);

    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(requestedPages, containsAllInOrder(['1', '2']));
    expect(find.text('UNWILLING_TO_PROCEED'), findsOneWidget);
    expect(find.text('Load more'), findsNothing);
  });
}
