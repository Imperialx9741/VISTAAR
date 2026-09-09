// Navigation smoke test for SarthiHomeScreen (Phase 14 of the
// redesign, "Testing", 2026-09-08) — the Sarthi counterpart to
// user_home_screen_test.dart: assembles the real nav shell with its
// real four tabs (Home/Wallet/Activity/Account) and taps through all
// of them. Go Online/Offline and offer-handling behavior is already
// covered in sarthi_home_screen_test.dart — this file only proves the
// shell itself wires together without exception.

import 'dart:convert';

import 'package:flutter/material.dart';
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
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/features/home/sarthi_home_screen.dart';
import 'package:vistaar_mobile/features/wallet/wallet_screen.dart';

/// `SarthiHomeTab` now reads the device position once on mount, for the
/// background map (Rapido-Captain-benchmarked redesign, 2026-09-08) —
/// same fake-platform seam every other Geolocator-touching test in
/// this app already uses; without it, the real (unavailable in
/// `flutter test`) platform implementation would be hit instead.
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

Widget _wrap() {
  final apiClient = ApiClient(
    httpClient: MockClient((request) async {
      if (request.url.path == '/api/v1/drivers/me/wallet') {
        return http.Response(
          _envelope({
            'balance': 340.5,
            'currency': 'INR',
            'outstanding_settlement': 0,
            'outstanding_debt': 0,
          }),
          200,
        );
      }
      if (request.url.path.endsWith('/transactions')) {
        return http.Response(
          _envelope({
            'items': [],
            'pagination': {'page': 1, 'total_pages': 1},
          }),
          200,
        );
      }
      return http.Response('not called', 500);
    }),
  );
  return MultiProvider(
    providers: [
      Provider<DriverAvailabilityApi>(
        create: (_) => DriverAvailabilityApi(apiClient, () => 'sarthi-token'),
      ),
      Provider<RideOfferApi>(
        create: (_) => RideOfferApi(apiClient, () => 'sarthi-token'),
      ),
      Provider<RideApi>(
        create: (_) => RideApi(apiClient, () => 'sarthi-token'),
      ),
      Provider<WalletApi>(
        create: (_) => WalletApi(apiClient, () => 'sarthi-token'),
      ),
    ],
    child: MaterialApp(theme: AppTheme.light, home: const SarthiHomeScreen()),
  );
}

void main() {
  setUp(() {
    GeolocatorPlatform.instance = _FakeGeolocatorPlatform();
  });

  testWidgets('lands on the Home tab, showing Go Online', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    expect(find.text('You are Offline'), findsOneWidget);
    expect(find.text('Go Online'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('every tab renders without an exception', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    for (final tab in const ['Wallet', 'Activity', 'Account', 'Home']) {
      await tester.tap(find.text(tab));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'on the $tab tab');
    }
  });

  testWidgets('Wallet tab shows the real WalletScreen with its balance', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Wallet'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(AppBar, 'Wallet'), findsOneWidget);
    // Not findsOneWidget: the Home tab's own wallet strip (still built,
    // just unpainted — VistaarNavShell keeps visited tabs alive) shows
    // the same balance text, so this scopes to WalletScreen specifically.
    expect(
      find.descendant(
        of: find.byType(WalletScreen),
        matching: find.text('INR 340.50'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('Activity tab shows the shared ride-history screen', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Activity'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(AppBar, 'Ride History'), findsOneWidget);
  });

  testWidgets('Account tab shows the Sarthi account menu entries', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();

    expect(find.text('Sarthi Onboarding'), findsOneWidget);
    expect(find.text('My Strikes'), findsOneWidget);
    expect(find.text('My Support Cases'), findsOneWidget);
    expect(find.text('Contact Support'), findsOneWidget);
    expect(find.byTooltip('Sign out'), findsOneWidget);
  });

  testWidgets(
    'switching away and back preserves the Home tab state (still Offline)',
    (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Wallet'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Home'));
      await tester.pumpAndSettle();

      expect(find.text('You are Offline'), findsOneWidget);
    },
  );
}
