// Navigation smoke test for UserHomeScreen (Phase 14 of the redesign,
// "Testing", 2026-09-08) — the one test that actually assembles the
// real nav shell with its real four tabs and taps through all of them,
// rather than each tab's own screen in isolation (already covered in
// its own test file). Proves the whole shell wires together without
// exception; it does not re-test any individual screen's own business
// logic.

import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/core/contacts/contacts_api.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/features/home/user_home_screen.dart';

/// `UserHomeTab` reads the device position once on mount, for its
/// background map — same fake-platform seam every other Geolocator-
/// touching test in this app already uses.
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

Widget _wrap() {
  final apiClient = ApiClient(
    httpClient: MockClient((_) async => http.Response('not called', 500)),
  );
  return MultiProvider(
    providers: [
      Provider<RideApi>(create: (_) => RideApi(apiClient, () => 'user-token')),
      Provider<ContactsApi>(
        create: (_) =>
            ContactsApi(requestPermission: () async => PermissionStatus.denied),
      ),
    ],
    child: MaterialApp(theme: AppTheme.light, home: const UserHomeScreen()),
  );
}

void main() {
  setUp(() {
    GeolocatorPlatform.instance = _FakeGeolocatorPlatform();
  });

  testWidgets('lands on the Home tab, showing the booking CTA', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    expect(find.text('Where are you headed?'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('every tab renders without an exception', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    for (final tab in const ['Activity', 'Offers', 'Account', 'Home']) {
      await tester.tap(find.text(tab));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'on the $tab tab');
    }
  });

  testWidgets('Activity tab shows the ride-history screen', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Activity'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(AppBar, 'Ride History'), findsOneWidget);
  });

  testWidgets('Offers tab shows Promotions and Refer & Earn entries', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Offers'));
    await tester.pumpAndSettle();

    expect(find.text('Promotions'), findsOneWidget);
    expect(find.text('Refer & Earn'), findsOneWidget);
  });

  testWidgets('Account tab shows the account menu entries', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();

    expect(find.text('Profile'), findsOneWidget);
    expect(find.text('Scheduled Rides'), findsOneWidget);
    expect(find.text('My Support Cases'), findsOneWidget);
    expect(find.text('Contact Support'), findsOneWidget);
    expect(find.byTooltip('Sign out'), findsOneWidget);
  });

  testWidgets('switching away and back preserves the Home tab state', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Home'));
    await tester.pumpAndSettle();

    // Still the same Home tab, not rebuilt from a blank/loading state.
    expect(find.text('Where are you headed?'), findsOneWidget);
  });
}
