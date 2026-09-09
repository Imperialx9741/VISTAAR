// Widget tests for ScheduledRidesScreen (build order step 10 —
// docs/16-mobile/mobile-app-implementation-plan.md §4.10, ADR-0057):
// listing, pagination, empty state, and opening a ride.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/features/rides/ride_status_screen.dart';
import 'package:vistaar_mobile/features/rides/scheduled_rides_screen.dart';

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
    child: const MaterialApp(home: ScheduledRidesScreen()),
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
  String scheduledFor = '2026-09-01T14:00:00Z',
}) => {
  'ride_id': id,
  'status': 'SCHEDULED',
  'scheduled_for': scheduledFor,
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
  testWidgets('shows scheduled rides fetched on load', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          expect(request.url.queryParameters['status'], 'SCHEDULED');
          return http.Response(
            _envelope(_pageJson(items: [_rideItemJson()])),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('2026-09-01'), findsOneWidget);
  });

  testWidgets('shows an empty state with no scheduled rides', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(_envelope(_pageJson(items: [])), 200),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No scheduled rides yet.'), findsOneWidget);
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
                items: [
                  _rideItemJson(
                    id: 'ride-2',
                    scheduledFor: '2026-09-02T09:00:00Z',
                  ),
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
    expect(find.textContaining('2026-09-02'), findsNothing);

    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(requestedPages, containsAllInOrder(['1', '2']));
    expect(find.textContaining('2026-09-02'), findsOneWidget);
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
              'status': 'SCHEDULED',
              'scheduled_for': '2026-09-01T14:00:00Z',
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

    await tester.tap(find.textContaining('2026-09-01'));
    await tester.pumpAndSettle();

    expect(find.byType(RideStatusScreen), findsOneWidget);
  });
}
