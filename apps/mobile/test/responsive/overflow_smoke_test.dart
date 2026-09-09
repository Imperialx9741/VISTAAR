// Phase 11 of the redesign ("Responsive design", 2026-09-08) — a
// direct, evidence-based check rather than an eyeballed one: pumps the
// highest-risk redesigned screens (the ones with a Row containing more
// than one piece of text, which is exactly where a fixed-width layout
// silently overflows) at a small phone's width (320dp — narrower than
// almost any real Android device sold today, so it's a safe worst
// case) and at 1.3x text scale (Android's own "Large" accessibility
// font setting, a realistic setting real users choose, not an extreme
// synthetic one). A genuine overflow throws a `FlutterError` during
// layout, which `tester.takeException()` surfaces — these tests fail
// loudly if any of them do, rather than a human having to notice a
// yellow-and-black stripe in a screenshot.
//
// This deliberately doesn't re-test each screen's own business logic
// (already covered in that screen's own test file) — only that its
// layout survives a narrow, large-text device.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/driver_availability_api.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/core/api/ride_offer_api.dart';
import 'package:vistaar_mobile/core/api/wallet_api.dart';
import 'package:vistaar_mobile/core/contacts/contacts_api.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/features/home/sarthi_home_tab.dart';
import 'package:vistaar_mobile/features/home/user_home_tab.dart';
import 'package:vistaar_mobile/features/profile/account_hub_screen.dart';
import 'package:vistaar_mobile/features/promotions/offers_hub_screen.dart';
import 'package:vistaar_mobile/features/rides/book_ride_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_execution_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_history_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_status_screen.dart';
import 'package:vistaar_mobile/features/wallet/recharge_wallet_screen.dart';
import 'package:vistaar_mobile/features/wallet/wallet_screen.dart';

/// `SarthiHomeTab` reads the device position once on mount, for its
/// background map (Rapido-Captain-benchmarked redesign, 2026-09-08) —
/// same fake-platform seam every other Geolocator-touching test in
/// this app already uses.
class _FakeGeolocatorPlatform extends GeolocatorPlatform {
  @override
  Future<Position> getCurrentPosition({LocationSettings? locationSettings}) async {
    return Position(
      latitude: 25.5941,
      longitude: 85.1376,
      timestamp: DateTime.now(),
      accuracy: 8,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    );
  }
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

/// A ride with a long driver name and vehicle description — the exact
/// kind of real-world content length (not a short placeholder) that
/// would actually reveal a fixed-width layout problem in the driver/
/// vehicle/fare cards.
Map<String, dynamic> _rideWithDriverJson({String status = 'ACCEPTED'}) => {
  'ride_id': 'ride-1',
  'status': status,
  'scheduled_for': null,
  'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
  'destination': {'latitude': 25.6120, 'longitude': 85.1580},
  'driver': {
    'driver_id': 'driver-1',
    'full_name': 'Rajendra Prasad Chaudhary',
    'profile_photo_uri': null,
  },
  'vehicle': {
    'vehicle_id': 'vehicle-1',
    'category': 'CAB',
    'registration_number': 'BR-01-AB-1234',
    'make': 'Mahindra',
    'model': 'XUV700 Premium',
  },
  'fare': {'base': 1289.75, 'discount': 0, 'total': 1289.75, 'currency': 'INR'},
};

/// Runs [testFn] at a small-phone width (320dp — narrower than almost
/// any real device) and, separately, at Android's "Large" text-scale
/// accessibility setting (1.3x) — both real, common conditions, not
/// synthetic extremes. Fails if either pump leaves an uncaught
/// exception (a `RenderFlex overflowed` error, most commonly).
Future<void> _expectNoOverflow(
  WidgetTester tester,
  Widget Function() build,
) async {
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

  tester.view.physicalSize = const Size(320, 640);
  tester.view.devicePixelRatio = 1.0;
  await tester.pumpWidget(build());
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull, reason: 'at 320dp width');

  tester.view.physicalSize = const Size(400, 800);
  tester.platformDispatcher.textScaleFactorTestValue = 1.3;
  await tester.pumpWidget(build());
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull, reason: 'at 1.3x text scale');
}

void main() {
  setUp(() {
    GeolocatorPlatform.instance = _FakeGeolocatorPlatform();
  });

  testWidgets('UserHomeTab', (tester) async {
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient((_) async => http.Response('unused', 500)),
      );
      return MultiProvider(
        providers: [
          Provider<RideApi>(create: (_) => RideApi(apiClient, () => 't')),
          Provider<ContactsApi>(
            create: (_) => ContactsApi(
              requestPermission: () async => PermissionStatus.denied,
            ),
          ),
        ],
        child: MaterialApp(theme: AppTheme.light, home: const UserHomeTab()),
      );
    });
  });

  testWidgets('SarthiHomeTab with a large wallet balance', (tester) async {
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(
              _envelope({
                'balance': 123456.78,
                'currency': 'INR',
                'outstanding_settlement': 0,
                'outstanding_debt': 0,
              }),
              200,
            );
          }
          return http.Response('unused', 500);
        }),
      );
      return MultiProvider(
        providers: [
          Provider<DriverAvailabilityApi>(
            create: (_) => DriverAvailabilityApi(apiClient, () => 't'),
          ),
          Provider<RideOfferApi>(
            create: (_) => RideOfferApi(apiClient, () => 't'),
          ),
          Provider<WalletApi>(create: (_) => WalletApi(apiClient, () => 't')),
        ],
        child: MaterialApp(theme: AppTheme.light, home: const SarthiHomeTab()),
      );
    });
  });

  testWidgets('OffersHubScreen', (tester) async {
    await _expectNoOverflow(
      tester,
      () => MaterialApp(theme: AppTheme.light, home: const OffersHubScreen()),
    );
  });

  testWidgets('AccountHubScreen', (tester) async {
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient((_) async => http.Response('unused', 500)),
      );
      return MultiProvider(
        providers: [
          Provider<ApiClient>.value(value: apiClient),
        ],
        child: MaterialApp(theme: AppTheme.light, home: const AccountHubScreen()),
      );
    });
  });

  testWidgets('BookRideScreen', (tester) async {
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient((_) async => http.Response('unused', 500)),
      );
      return MultiProvider(
        providers: [
          Provider<RideApi>(create: (_) => RideApi(apiClient, () => 't')),
          Provider<ContactsApi>(
            create: (_) => ContactsApi(
              requestPermission: () async => PermissionStatus.denied,
            ),
          ),
        ],
        child: MaterialApp(theme: AppTheme.light, home: const BookRideScreen()),
      );
    });
  });

  testWidgets('RideStatusScreen with a long driver/vehicle name, ACCEPTED', (
    tester,
  ) async {
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(_envelope(_rideWithDriverJson()), 200),
        ),
      );
      return MultiProvider(
        providers: [
          Provider<RideApi>(create: (_) => RideApi(apiClient, () => 't')),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const RideStatusScreen(rideId: 'ride-1'),
        ),
      );
    });
  });

  testWidgets(
    'RideExecutionScreen with a long driver/vehicle name, ACCEPTED',
    (tester) async {
      await _expectNoOverflow(tester, () {
        final apiClient = ApiClient(
          httpClient: MockClient(
            (_) async => http.Response(_envelope(_rideWithDriverJson()), 200),
          ),
        );
        return MultiProvider(
          providers: [
            Provider<RideApi>(create: (_) => RideApi(apiClient, () => 't')),
          ],
          child: MaterialApp(
            theme: AppTheme.light,
            home: const RideExecutionScreen(rideId: 'ride-1'),
          ),
        );
      });
    },
  );

  testWidgets('RideHistoryScreen with a scheduled ride', (tester) async {
    // The Rapido-style route-marker row (2026-09-08 redesign) uses
    // Expanded inside an IntrinsicHeight-wrapped Row — exactly the
    // layout shape that silently breaks at a narrow width if
    // IntrinsicHeight is ever dropped; this is that guard.
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(
            _envelope({
              'items': [
                {
                  'ride_id': 'ride-1',
                  'status': 'SCHEDULED',
                  'scheduled_for': '2026-09-10T14:30:00Z',
                  'pickup': {'latitude': 25.594112, 'longitude': 85.137566},
                  'destination': {
                    'latitude': 25.612034,
                    'longitude': 85.158091,
                  },
                },
              ],
              'pagination': {'page': 1, 'total_pages': 1},
            }),
            200,
          ),
        ),
      );
      return MultiProvider(
        providers: [
          Provider<RideApi>(create: (_) => RideApi(apiClient, () => 't')),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const RideHistoryScreen(),
        ),
      );
    });
  });

  testWidgets('WalletScreen with a large balance and a debt note', (
    tester,
  ) async {
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient((request) async {
          if (request.url.path.endsWith('/transactions')) {
            return http.Response(
              _envelope({
                'items': [],
                'pagination': {'page': 1, 'total_pages': 1},
              }),
              200,
            );
          }
          return http.Response(
            _envelope({
              'balance': 123456.78,
              'currency': 'INR',
              'outstanding_settlement': 0,
              'outstanding_debt': 999.99,
            }),
            200,
          );
        }),
      );
      return MultiProvider(
        providers: [
          Provider<WalletApi>(create: (_) => WalletApi(apiClient, () => 't')),
        ],
        child: MaterialApp(theme: AppTheme.light, home: const WalletScreen()),
      );
    });
  });

  testWidgets('RechargeWalletScreen with its quick-amount chips', (
    tester,
  ) async {
    await _expectNoOverflow(tester, () {
      final apiClient = ApiClient(
        httpClient: MockClient((_) async => http.Response('unused', 500)),
      );
      return MultiProvider(
        providers: [
          Provider<WalletApi>(create: (_) => WalletApi(apiClient, () => 't')),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const RechargeWalletScreen(),
        ),
      );
    });
  });
}
