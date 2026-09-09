// Widget tests for RideOfferScreen (build order step 3 —
// docs/16-mobile/mobile-app-implementation-plan.md §5.3): Accept,
// Reject, and local countdown-to-expiry behaviour.
//
// The backend is mocked via `http`'s own `MockClient` (same convention
// as the other API-backed screens in this app).

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart' show RideGeoPoint;
import 'package:vistaar_mobile/core/api/ride_offer_api.dart';
import 'package:vistaar_mobile/features/rides/ride_offer_screen.dart';
import 'package:vistaar_mobile/shared/widgets/route_map_preview.dart';

RideOffer _offer({Duration expiresIn = const Duration(seconds: 20)}) =>
    RideOffer(
      offerId: 'offer-1',
      rideId: 'ride-1',
      status: 'PENDING',
      expiresAt: DateTime.now().toUtc().add(expiresIn),
      pickup: const OfferPickup(latitude: 25.5941, longitude: 85.1376),
    );

/// Provides [RideOfferApi] around [child] — deliberately no `MaterialApp`
/// here, so a test that needs to push [RideOfferScreen] via a real
/// `Navigator.push` (to observe the pop) can supply its own single
/// `MaterialApp` shell instead of nesting a second one inside a route.
Widget _withApi(Widget child, http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<RideOfferApi>(
        create: (_) => RideOfferApi(apiClient, () => 'sarthi-token'),
      ),
    ],
    child: child,
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

void main() {
  testWidgets('shows the pickup location and a countdown', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: _withApi(
          RideOfferScreen(offer: _offer()),
          MockClient((_) async => http.Response('unused', 500)),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('New Ride Request'), findsWidgets);
    // A RouteMapPreview for the offer's pickup (2026-09-07, single-
    // point — offers carry no destination) — degrading to its own
    // fallback without a maps key configured for this build, same as
    // route_map_preview_test.dart.
    expect(find.byType(RouteMapPreview), findsOneWidget);
    expect(find.textContaining('25.59410'), findsOneWidget);
    expect(find.textContaining('Responds in'), findsOneWidget);
  });

  testWidgets(
    'with a driverPosition, shows a computed pickup distance',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: _withApi(
            RideOfferScreen(
              offer: _offer(),
              driverPosition: const RideGeoPoint(latitude: 25.60, longitude: 85.15),
            ),
            MockClient((_) async => http.Response('unused', 500)),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('km away'), findsOneWidget);
    },
  );

  testWidgets(
    'with no driverPosition, shows no distance line',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: _withApi(
            RideOfferScreen(offer: _offer()),
            MockClient((_) async => http.Response('unused', 500)),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('km away'), findsNothing);
    },
  );

  testWidgets('Accept sends an Idempotency-Key header and pops on success', (
    tester,
  ) async {
    String? capturedIdempotencyKey;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: ElevatedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => _withApi(
                    RideOfferScreen(offer: _offer()),
                    MockClient((request) async {
                      capturedIdempotencyKey =
                          request.headers['Idempotency-Key'];
                      return http.Response(
                        _envelope({
                          'offer_id': 'offer-1',
                          'ride_id': 'ride-1',
                          'status': 'ACCEPTED',
                          'wallet_balance': 120.5,
                        }),
                        200,
                      );
                    }),
                  ),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Accept'));
    await tester.pumpAndSettle();

    expect(capturedIdempotencyKey, isNotNull);
    expect(capturedIdempotencyKey, isNotEmpty);
    expect(find.byType(RideOfferScreen), findsNothing);
  });

  testWidgets(
    'Accept at or below the ₹20 threshold shows a low-balance warning '
    '(ADR-0058)',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => _withApi(
                      RideOfferScreen(offer: _offer()),
                      MockClient(
                        (_) async => http.Response(
                          _envelope({
                            'offer_id': 'offer-1',
                            'ride_id': 'ride-1',
                            'status': 'ACCEPTED',
                            'wallet_balance': 15.0,
                          }),
                          200,
                        ),
                      ),
                    ),
                  ),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Accept'));
      await tester.pump(); // let the SnackBar animate in, before it pops

      // SnackBar renders its content twice (visible + an accessibility
      // announcement duplicate) — findsWidgets, not findsOneWidget.
      expect(find.textContaining('Wallet balance is low'), findsWidgets);
      expect(find.textContaining('₹15.00'), findsWidgets);
    },
  );

  testWidgets(
    'Accept above the ₹20 threshold shows no low-balance warning',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => _withApi(
                      RideOfferScreen(offer: _offer()),
                      MockClient(
                        (_) async => http.Response(
                          _envelope({
                            'offer_id': 'offer-1',
                            'ride_id': 'ride-1',
                            'status': 'ACCEPTED',
                            'wallet_balance': 120.5,
                          }),
                          200,
                        ),
                      ),
                    ),
                  ),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Accept'));
      await tester.pump();

      expect(find.textContaining('Wallet balance is low'), findsNothing);
    },
  );

  testWidgets('a failed Accept surfaces the backend error and stays open', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: _withApi(
          RideOfferScreen(offer: _offer()),
          MockClient(
            (_) async => http.Response(
              _errorEnvelope('OFFER_EXPIRED', 'This offer has expired.'),
              409,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Accept'));
    await tester.pumpAndSettle();

    expect(find.text('This offer has expired.'), findsOneWidget);
    expect(find.byType(RideOfferScreen), findsOneWidget);
  });

  testWidgets(
    'a WALLET_RECHARGE_REQUIRED Accept failure shows a Recharge Wallet '
    'action (ADR-0058 §6, wired up via ADR-0060) — not tapped here, since '
    'that would instantiate the real Razorpay plugin outside a device',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: _withApi(
            RideOfferScreen(offer: _offer()),
            MockClient(
              (_) async => http.Response(
                _errorEnvelope(
                  'WALLET_RECHARGE_REQUIRED',
                  'Your wallet balance is too low. Please recharge.',
                ),
                409,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Accept'));
      await tester.pumpAndSettle();

      expect(
        find.text('Your wallet balance is too low. Please recharge.'),
        findsOneWidget,
      );
      expect(find.text('Recharge Wallet'), findsOneWidget);
    },
  );

  testWidgets('Reject calls the backend and pops', (tester) async {
    final requestedPaths = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: ElevatedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => _withApi(
                    RideOfferScreen(offer: _offer()),
                    MockClient((request) async {
                      requestedPaths.add(request.url.path);
                      return http.Response(
                        _envelope({
                          'offer_id': 'offer-1',
                          'status': 'REJECTED',
                        }),
                        200,
                      );
                    }),
                  ),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Reject'));
    await tester.pumpAndSettle();

    expect(
      requestedPaths,
      contains('/api/v1/drivers/me/ride-offers/offer-1/reject'),
    );
    expect(find.byType(RideOfferScreen), findsNothing);
  });

  // The live one-second countdown tick is driven by a real `Timer` reading
  // real `DateTime.now()` — deliberately not exercised here, since
  // `tester.pump(duration)` only advances the widget-test scheduler clock,
  // not wall-clock time, so it can't be used to simulate seconds actually
  // passing. An offer that is *already* past its `expiresAt` sidesteps
  // that mismatch entirely: `initState` computes the expired state
  // synchronously, with no timer tick required.
  testWidgets('an offer that is already past expiry shows the expired state', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: _withApi(
          RideOfferScreen(
            offer: _offer(expiresIn: const Duration(seconds: -1)),
          ),
          MockClient((_) async => http.Response('unused', 500)),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('This request has expired'), findsOneWidget);
    expect(find.text('Accept'), findsNothing);
    expect(find.text('Reject'), findsNothing);
    expect(find.text('Close'), findsOneWidget);
  });
}
