// Widget tests for RouteMapPreview (2026-09-07, MapTiler map rendering
// — see that widget's own doc comment for why this exists).
//
// AppConfig.mapTilerApiKey is a compile-time constant
// (String.fromEnvironment) — a plain `flutter test` run (no
// --dart-define) always resolves it to empty, so `hasMapTilerApiKey`
// is always false here. That's the real, meaningful case to cover:
// every screen using this widget must degrade to MapUnavailableNotice,
// not crash or show a blank tile-less map, whenever no key is
// configured for a build — exactly what these tests prove. The
// key-present path (real FlutterMap/tile rendering) is not exercised
// by this suite; it would need `--dart-define=MAPTILER_API_KEY=...`
// passed to `flutter test` itself to compile in a real value.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/shared/map/maptiler_tile_layer.dart';
import 'package:vistaar_mobile/shared/widgets/route_map_preview.dart';

const _pickup = RideGeoPoint(latitude: 25.5941, longitude: 85.1376);
const _destination = RideGeoPoint(latitude: 25.6120, longitude: 85.1580);

void main() {
  testWidgets(
    'shows MapUnavailableNotice, not a blank map, with no maps key configured',
    (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: RouteMapPreview(pickup: _pickup, destination: _destination),
          ),
        ),
      );

      expect(find.byType(MapUnavailableNotice), findsOneWidget);
      expect(find.textContaining('Map unavailable'), findsOneWidget);
    },
  );

  testWidgets(
    'still degrades cleanly with only a pickup (no destination, e.g. a ride offer)',
    (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: RouteMapPreview(pickup: _pickup)),
        ),
      );

      expect(find.byType(MapUnavailableNotice), findsOneWidget);
    },
  );

  testWidgets('respects the height parameter for its fallback too', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: RouteMapPreview(
            pickup: _pickup,
            destination: _destination,
            height: 120,
          ),
        ),
      ),
    );

    final size = tester.getSize(find.byType(RouteMapPreview));
    expect(size.height, 120);
  });
}
