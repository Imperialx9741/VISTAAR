import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart' as latlong;

import '../../core/api/ride_api.dart';
import '../../core/config/app_config.dart';
import '../map/maptiler_tile_layer.dart';

/// A compact, mostly non-interactive map card showing [pickup] and
/// (when known) [destination] as pins (2026-09-07, MapTiler map
/// rendering) — used on `RideStatusScreen` (User), `RideExecutionScreen`
/// (Sarthi), and `RideOfferScreen` (Sarthi). With both points, the
/// camera auto-fits to show both; [destination] is optional because a
/// ride *offer* (`RideOfferScreen`) only ever carries `pickup` —
/// api-contracts.md §16.1's own documented shape, not a client
/// omission — in which case this centers on [pickup] alone at a fixed
/// street-level zoom.
///
/// **Static, not live** — there is no driver-location tracking feed
/// anywhere in the backend (`/tracking` documents only a route name and
/// an unimplemented WebSocket, verified directly against the live
/// router) — flagged here rather than silently built as if it were a
/// real live-tracking map. This shows where the ride starts/ends, not
/// where the driver currently is.
class RouteMapPreview extends StatelessWidget {
  const RouteMapPreview({
    required this.pickup,
    this.destination,
    this.height = 200,
    super.key,
  });

  final RideGeoPoint pickup;
  final RideGeoPoint? destination;
  final double height;

  latlong.LatLng _point(RideGeoPoint p) =>
      latlong.LatLng(p.latitude, p.longitude);

  @override
  Widget build(BuildContext context) {
    if (!AppConfig.hasMapTilerApiKey) {
      return SizedBox(height: height, child: const MapUnavailableNotice());
    }
    final destination = this.destination;
    final pickupPoint = _point(pickup);
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        height: height,
        child: FlutterMap(
          options: MapOptions(
            initialCameraFit: destination == null
                ? null
                : CameraFit.bounds(
                    bounds: LatLngBounds(pickupPoint, _point(destination)),
                    padding: const EdgeInsets.all(40),
                  ),
            initialCenter: pickupPoint,
            initialZoom: 15,
            // A preview, not a navigation tool — panning/zooming a small
            // embedded card fights the surrounding screen's own scroll
            // gesture more than it helps, so only pinch-zoom is allowed.
            interactionOptions: const InteractionOptions(
              flags: InteractiveFlag.pinchZoom,
            ),
          ),
          children: [
            ...maptilerLayers(),
            MarkerLayer(
              markers: [
                Marker(
                  point: pickupPoint,
                  width: 36,
                  height: 36,
                  child: Icon(
                    Icons.trip_origin,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
                if (destination != null)
                  Marker(
                    point: _point(destination),
                    width: 36,
                    height: 36,
                    child: Icon(
                      Icons.location_on,
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
