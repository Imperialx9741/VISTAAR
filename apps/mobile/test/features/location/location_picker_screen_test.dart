// Widget tests for LocationPickerScreen (2026-09-07, MapTiler map
// rendering — see that screen's own doc comment for why this exists).
// Interaction logic (pin position, Confirm, current-location) is
// independent of whether real tiles load — `maptilerLayers()` returns
// no layers in a plain `flutter test` run (see
// test/shared/map/route_map_preview_test.dart's own header for why),
// so `FlutterMap` here renders tile-less but fully interactive, which
// is exactly what these tests exercise.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/features/location/location_picker_screen.dart';

class _FakeGeolocatorPlatform extends GeolocatorPlatform {
  _FakeGeolocatorPlatform({this.fail = false});

  final bool fail;
  int callCount = 0;

  @override
  Future<Position> getCurrentPosition({
    LocationSettings? locationSettings,
  }) async {
    callCount++;
    if (fail) throw Exception('location unavailable');
    return Position(
      latitude: 12.9716,
      longitude: 77.5946,
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

void main() {
  testWidgets(
    'with an initialCenter, Confirm Location pops that same point '
    'without needing to tap the map',
    (tester) async {
      GeolocatorPlatform.instance = _FakeGeolocatorPlatform();
      const initial = RideGeoPoint(latitude: 25.5941, longitude: 85.1376);
      RideGeoPoint? result;

      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () async {
                  result = await Navigator.of(context).push<RideGeoPoint>(
                    MaterialPageRoute<RideGeoPoint>(
                      builder: (_) => const LocationPickerScreen(
                        title: 'Pickup Location',
                        initialCenter: initial,
                      ),
                    ),
                  );
                },
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(find.text('Pickup Location'), findsOneWidget);

      await tester.tap(find.text('Confirm Location'));
      await tester.pumpAndSettle();

      expect(result?.latitude, initial.latitude);
      expect(result?.longitude, initial.longitude);
    },
  );

  testWidgets(
    'with no initialCenter, tries the device position and confirms that',
    (tester) async {
      GeolocatorPlatform.instance = _FakeGeolocatorPlatform();

      RideGeoPoint? result;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () async {
                  result = await Navigator.of(context).push<RideGeoPoint>(
                    MaterialPageRoute<RideGeoPoint>(
                      builder: (_) =>
                          const LocationPickerScreen(title: 'Destination'),
                    ),
                  );
                },
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Confirm Location'));
      await tester.pumpAndSettle();

      expect(result?.latitude, 12.9716);
      expect(result?.longitude, 77.5946);
    },
  );

  testWidgets(
    'a failed current-position lookup leaves the fallback center, no crash',
    (tester) async {
      GeolocatorPlatform.instance = _FakeGeolocatorPlatform(fail: true);

      await tester.pumpWidget(
        const MaterialApp(
          home: LocationPickerScreen(title: 'Pickup Location'),
        ),
      );
      await tester.pumpAndSettle();

      // No exception surfaced, screen still usable.
      expect(find.text('Confirm Location'), findsOneWidget);
    },
  );

  testWidgets('tapping "Use my current location" re-centers on the device', (
    tester,
  ) async {
    final fake = _FakeGeolocatorPlatform();
    GeolocatorPlatform.instance = fake;
    RideGeoPoint? result;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: ElevatedButton(
              onPressed: () async {
                result = await Navigator.of(context).push<RideGeoPoint>(
                  MaterialPageRoute<RideGeoPoint>(
                    builder: (_) => const LocationPickerScreen(
                      title: 'Pickup Location',
                      initialCenter: RideGeoPoint(latitude: 1, longitude: 1),
                    ),
                  ),
                );
              },
              child: const Text('Open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    final callsBefore = fake.callCount;

    await tester.tap(find.byTooltip('Use my current location'));
    await tester.pumpAndSettle();

    expect(fake.callCount, callsBefore + 1);

    await tester.tap(find.text('Confirm Location'));
    await tester.pumpAndSettle();

    expect(result?.latitude, 12.9716);
    expect(result?.longitude, 77.5946);
  });
}
