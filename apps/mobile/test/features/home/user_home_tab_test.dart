// Widget tests for UserHomeTab (Phase 4 of the redesign, "User home +
// booking", 2026-09-08; map-first layout added in the Rapido-
// benchmarked redesign pass, 2026-09-08): the greeting, the "Where are
// you headed?" booking entry point, and the two quick actions
// (Scheduled Rides, Book for Someone Else) all navigate to the same
// existing screens as before this screen's visual pass — these tests
// only prove the navigation wiring, not those destination screens' own
// behavior (covered in their own test files).

import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/core/contacts/contacts_api.dart';
import 'package:vistaar_mobile/features/home/user_home_tab.dart';
import 'package:vistaar_mobile/features/rides/book_ride_screen.dart';
import 'package:vistaar_mobile/features/rides/scheduled_rides_screen.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// `UserHomeTab` now reads the device position once on mount, for its
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
    httpClient: MockClient((_) async => http.Response('unused', 500)),
  );
  return MultiProvider(
    providers: [
      Provider<RideApi>(create: (_) => RideApi(apiClient, () => 'user-token')),
      Provider<ContactsApi>(
        create: (_) =>
            ContactsApi(requestPermission: () async => PermissionStatus.denied),
      ),
    ],
    child: const MaterialApp(home: UserHomeTab()),
  );
}

void main() {
  setUp(() {
    GeolocatorPlatform.instance = _FakeGeolocatorPlatform();
  });

  testWidgets('shows the booking entry point', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    expect(find.text('Where are you headed?'), findsOneWidget);
    expect(find.text('Book'), findsOneWidget);
  });

  testWidgets('tapping "Where are you headed?" opens BookRideScreen with no '
      'pre-selected toggle', (tester) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Where are you headed?'));
    await tester.pumpAndSettle();

    expect(find.byType(BookRideScreen), findsOneWidget);
    expect(find.text("Rider's name"), findsNothing);
  });

  testWidgets('Scheduled Rides quick action opens ScheduledRidesScreen', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Scheduled Rides'));
    await tester.pumpAndSettle();

    expect(find.byType(ScheduledRidesScreen), findsOneWidget);
  });

  testWidgets(
    'Book for Someone Else quick action opens BookRideScreen pre-toggled',
    (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Book for Someone Else'));
      await tester.pumpAndSettle();

      expect(find.byType(BookRideScreen), findsOneWidget);
      await tester.ensureVisible(find.text("Rider's name"));
      expect(find.text("Rider's name"), findsOneWidget);
    },
  );
}
