// Widget tests for LocationPermissionScreen (owner decision, 2026-08-29
// — docs/16-mobile/mobile-app-implementation-plan.md §6.1).
//
// Geolocator is mocked via a [FakeGeolocatorPlatform] (the plugin's own
// documented testing seam, GeolocatorPlatform.instance) — no real OS
// permission dialog, no platform channel required to run these.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';

import 'package:vistaar_mobile/features/auth/app_role.dart';
import 'package:vistaar_mobile/features/auth/phone_entry_screen.dart';
import 'package:vistaar_mobile/features/location/location_permission_screen.dart';

/// Only overrides what [LocationPermissionScreen] actually calls — every
/// other [GeolocatorPlatform] method keeps the base class's own
/// `UnimplementedError`, which is fine since nothing here calls them.
class FakeGeolocatorPlatform extends GeolocatorPlatform {
  FakeGeolocatorPlatform({
    required this.checkResult,
    LocationPermission? requestResult,
  }) : requestResult = requestResult ?? checkResult;

  LocationPermission checkResult;
  LocationPermission requestResult;
  int requestCount = 0;
  int openAppSettingsCount = 0;

  @override
  Future<LocationPermission> checkPermission() async => checkResult;

  @override
  Future<LocationPermission> requestPermission() async {
    requestCount++;
    return requestResult;
  }

  @override
  Future<bool> openAppSettings() async {
    openAppSettingsCount++;
    return true;
  }
}

Widget _wrap(Widget child) => MaterialApp(home: child);

void main() {
  testWidgets(
    'already-granted permission skips straight to phone entry, no prompt',
    (tester) async {
      GeolocatorPlatform.instance = FakeGeolocatorPlatform(
        checkResult: LocationPermission.whileInUse,
      );

      await tester.pumpWidget(
        _wrap(const LocationPermissionScreen(role: AppRole.user)),
      );
      await tester.pumpAndSettle();

      expect(find.byType(PhoneEntryScreen), findsOneWidget);
      expect(find.text('Allow location access'), findsNothing);
    },
  );

  testWidgets('not-yet-decided permission shows role-appropriate copy', (
    tester,
  ) async {
    GeolocatorPlatform.instance = FakeGeolocatorPlatform(
      checkResult: LocationPermission.denied,
    );

    await tester.pumpWidget(
      _wrap(const LocationPermissionScreen(role: AppRole.sarthi)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Allow location access'), findsOneWidget);
    expect(
      find.text('VISTAAR uses your location to show you nearby ride requests.'),
      findsOneWidget,
    );
  });

  testWidgets('tapping Allow requests permission and continues once granted', (
    tester,
  ) async {
    final fake = FakeGeolocatorPlatform(
      checkResult: LocationPermission.denied,
      requestResult: LocationPermission.whileInUse,
    );
    GeolocatorPlatform.instance = fake;

    await tester.pumpWidget(
      _wrap(const LocationPermissionScreen(role: AppRole.user)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Allow location'));
    await tester.pumpAndSettle();

    expect(fake.requestCount, 1);
    expect(find.byType(PhoneEntryScreen), findsOneWidget);
  });

  testWidgets(
    'a denial that is not permanent stays on this screen, does not block login',
    (tester) async {
      GeolocatorPlatform.instance = FakeGeolocatorPlatform(
        checkResult: LocationPermission.denied,
        requestResult: LocationPermission.denied,
      );

      await tester.pumpWidget(
        _wrap(const LocationPermissionScreen(role: AppRole.user)),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Allow location'));
      await tester.pumpAndSettle();

      expect(find.text('Allow location access'), findsOneWidget);

      // "Not now" still lets the user continue to login.
      await tester.tap(find.text('Not now'));
      await tester.pumpAndSettle();

      expect(find.byType(PhoneEntryScreen), findsOneWidget);
    },
  );

  testWidgets('permanently denied shows an Open Settings button, not Allow', (
    tester,
  ) async {
    final fake = FakeGeolocatorPlatform(
      checkResult: LocationPermission.deniedForever,
    );
    GeolocatorPlatform.instance = fake;

    await tester.pumpWidget(
      _wrap(const LocationPermissionScreen(role: AppRole.sarthi)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Open Settings'), findsOneWidget);
    expect(find.text('Allow location'), findsNothing);

    await tester.tap(find.text('Open Settings'));
    await tester.pumpAndSettle();

    expect(fake.openAppSettingsCount, 1);
  });

  testWidgets('"Not now" continues to login without requesting permission', (
    tester,
  ) async {
    final fake = FakeGeolocatorPlatform(checkResult: LocationPermission.denied);
    GeolocatorPlatform.instance = fake;

    await tester.pumpWidget(
      _wrap(const LocationPermissionScreen(role: AppRole.sarthi)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Not now'));
    await tester.pumpAndSettle();

    expect(fake.requestCount, 0);
    expect(find.byType(PhoneEntryScreen), findsOneWidget);
  });
}
