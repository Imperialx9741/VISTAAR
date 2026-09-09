// Widget tests for RideHistoryScreen (User-side, built 2026-09-04 — see
// that screen's own doc comment for why this exists, and
// scheduled_rides_screen_test.dart for the pattern this mirrors):
// listing every status (no filter), empty state, pagination, and
// opening a ride.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/features/rides/ride_history_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_status_screen.dart';

/// [RideStatusScreen] (opened when a list item is tapped) starts its
/// own periodic poll `Timer` — unmount before the test ends so the
/// framework doesn't fail on "Timer still pending".
Future<void> _disposeScreen(WidgetTester tester) =>
    tester.pumpWidget(const SizedBox());

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<RideApi>(create: (_) => RideApi(apiClient, () => 'user-token')),
    ],
    child: const MaterialApp(home: RideHistoryScreen()),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Map<String, dynamic> _rideItemJson({
  String id = 'ride-1',
  String status = 'COMPLETED',
}) => {
  'ride_id': id,
  'status': status,
  'scheduled_for': null,
  'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
  'destination': {'latitude': 25.6120, 'longitude': 85.1580},
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
  testWidgets('fetches with no status filter and shows every ride', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          expect(request.url.queryParameters.containsKey('status'), isFalse);
          return http.Response(
            _envelope(_pageJson(items: [_rideItemJson()])),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('COMPLETED'), findsOneWidget);
  });

  testWidgets('shows an empty state with no rides', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(_envelope(_pageJson(items: [])), 200),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No rides yet.'), findsOneWidget);
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
                  items: [_rideItemJson(id: 'ride-1')],
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
                items: [_rideItemJson(id: 'ride-2', status: 'CANCELLED')],
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
    expect(find.text('CANCELLED'), findsNothing);

    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(requestedPages, containsAllInOrder(['1', '2']));
    expect(find.text('CANCELLED'), findsOneWidget);
    expect(find.text('Load more'), findsNothing);
  });

  testWidgets('tapping a ride opens RideStatusScreen', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides') {
            return http.Response(
              _envelope(_pageJson(items: [_rideItemJson()])),
              200,
            );
          }
          return http.Response(
            _envelope({
              'ride_id': 'ride-1',
              'status': 'COMPLETED',
              'scheduled_for': null,
              'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
              'destination': {'latitude': 25.6120, 'longitude': 85.1580},
              'driver': null,
              'vehicle': null,
              'fare': null,
            }),
            200,
          );
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.text('COMPLETED'));
    await tester.pumpAndSettle();

    expect(find.byType(RideStatusScreen), findsOneWidget);
  });
}
