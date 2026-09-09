import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart' as latlong;

import '../../core/config/app_config.dart';
import '../design/state_views.dart';
import 'maptiler_tile_layer.dart';

/// A full-size, "you are here" map — the map-first background both
/// User Home and Sarthi Home now use (Rapido-benchmarked redesign,
/// 2026-09-08 — see each screen's own doc comment for the UX rationale;
/// this widget only exists so neither screen hand-rolls its own
/// `FlutterMap` setup). Uses the existing MapTiler integration
/// unchanged — [maptilerLayers]/[MapUnavailableNotice], the same
/// contract every other map screen in this app already follows.
///
/// Deliberately non-interactive by default (no pan/zoom) — this is
/// ambient context ("where am I"), not a picker or a route preview;
/// [interactive] exists for the one case that needs it.
///
/// [center] may be `null` while the device position is still being
/// read — shows a loading state rather than guessing a location.
/// When [center] changes after the map has already built once (a new
/// GPS fix), the map recenters smoothly via its own [MapController]
/// rather than jumping — `flutter_map`'s `initialCenter` only applies
/// on first build, so this widget tracks it explicitly instead of
/// relying on that.
class CurrentLocationMap extends StatefulWidget {
  const CurrentLocationMap({
    required this.center,
    this.zoom = 15,
    this.interactive = false,
    this.markerColor,
    super.key,
  });

  final latlong.LatLng? center;
  final double zoom;
  final bool interactive;
  final Color? markerColor;

  @override
  State<CurrentLocationMap> createState() => _CurrentLocationMapState();
}

class _CurrentLocationMapState extends State<CurrentLocationMap> {
  final _controller = MapController();

  @override
  void didUpdateWidget(CurrentLocationMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    final center = widget.center;
    if (center != null && center != oldWidget.center) {
      // Only after the map has actually mounted with a real center once
      // — recentering before that is `initialCenter`'s own job.
      if (oldWidget.center != null) {
        _controller.move(center, _controller.camera.zoom);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!AppConfig.hasMapTilerApiKey) {
      return const MapUnavailableNotice();
    }
    final center = widget.center;
    if (center == null) {
      return const LoadingView();
    }
    final markerColor = widget.markerColor ?? Theme.of(context).colorScheme.primary;
    return FlutterMap(
      mapController: _controller,
      options: MapOptions(
        initialCenter: center,
        initialZoom: widget.zoom,
        interactionOptions: InteractionOptions(
          flags: widget.interactive
              ? InteractiveFlag.pinchZoom | InteractiveFlag.drag
              : InteractiveFlag.none,
        ),
      ),
      children: [
        ...maptilerLayers(),
        MarkerLayer(
          markers: [
            Marker(
              point: center,
              width: 36,
              height: 36,
              child: Icon(Icons.my_location, color: markerColor, size: 28),
            ),
          ],
        ),
      ],
    );
  }
}
