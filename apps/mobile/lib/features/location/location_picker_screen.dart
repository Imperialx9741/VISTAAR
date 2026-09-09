import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart' as latlong;

import '../../core/api/ride_api.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/map/maptiler_tile_layer.dart';
import '../../shared/widgets/primary_button.dart';

/// Roughly central India (Nagpur) — used only as a last-resort starting
/// center when the device's own position can't be read at all (denied/
/// disabled location, or a timeout); the user can still pan/zoom
/// freely from there. Not a default *value* ever submitted anywhere —
/// [LocationPickerScreen] never returns a point the user didn't
/// explicitly confirm.
const latlong.LatLng _fallbackCenter = latlong.LatLng(21.1458, 79.0882);

/// Real map-based pickup/destination picker (2026-09-07, MapTiler map
/// rendering) — replaces the plain latitude/longitude text entry
/// `BookRideScreen` and the Change Pickup/Destination dialogs
/// previously used as their only input. Tap anywhere to move the pin;
/// [initialCenter] (if supplied — e.g. the ride's current pickup, when
/// changing it) seeds the starting view, otherwise this screen tries
/// the device's own current position first (permission was already
/// granted earlier in this app's login flow — see
/// `LocationPermissionScreen`) and falls back to a fixed, roughly-
/// central starting view if that fails, never blocking the picker on
/// it. Returns the confirmed [RideGeoPoint], or `null` if dismissed.
///
/// Callers must check `AppConfig.hasMapTilerApiKey` themselves before
/// ever navigating here — this screen assumes a map can actually be
/// rendered, matching `RouteMapPreview`'s own fallback contract instead
/// of duplicating it (a "Pick on Map" entry point simply shouldn't
/// exist in the UI when there's no key, same as every other
/// `AppConfig.mapTilerApiKey`-gated screen in this app).
class LocationPickerScreen extends StatefulWidget {
  const LocationPickerScreen({
    required this.title,
    this.initialCenter,
    super.key,
  });

  final String title;
  final RideGeoPoint? initialCenter;

  @override
  State<LocationPickerScreen> createState() => _LocationPickerScreenState();
}

class _LocationPickerScreenState extends State<LocationPickerScreen> {
  final _mapController = MapController();
  late latlong.LatLng _selected;
  bool _isLocating = false;

  @override
  void initState() {
    super.initState();
    final initial = widget.initialCenter;
    _selected = initial != null
        ? latlong.LatLng(initial.latitude, initial.longitude)
        : _fallbackCenter;
    if (initial == null) unawaited(_centerOnCurrentPosition());
  }

  /// Best-effort — a failure here just leaves the picker at
  /// [_fallbackCenter], never blocks or errors the screen; the user can
  /// always pan/zoom/tap manually regardless.
  Future<void> _centerOnCurrentPosition() async {
    setState(() => _isLocating = true);
    try {
      final position = await Geolocator.getCurrentPosition().timeout(
        const Duration(seconds: 8),
      );
      if (!mounted) return;
      final point = latlong.LatLng(position.latitude, position.longitude);
      setState(() => _selected = point);
      _mapController.move(point, 15);
    } on Object {
      // Denied/disabled location, no GPS fix yet, or timed out — stay
      // at _fallbackCenter, same as this method's own doc comment.
    } finally {
      if (mounted) setState(() => _isLocating = false);
    }
  }

  void _onTap(TapPosition _, latlong.LatLng point) {
    setState(() => _selected = point);
  }

  void _confirm() {
    Navigator.of(context).pop(
      RideGeoPoint(latitude: _selected.latitude, longitude: _selected.longitude),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              children: [
                FlutterMap(
                  mapController: _mapController,
                  options: MapOptions(
                    initialCenter: _selected,
                    initialZoom: 15,
                    onTap: _onTap,
                  ),
                  children: [
                    ...maptilerLayers(),
                    MarkerLayer(
                      markers: [
                        Marker(
                          point: _selected,
                          width: 44,
                          height: 44,
                          alignment: Alignment.topCenter,
                          // A small drop-in "bounce" each time the pin
                          // moves (Phase 10 of the redesign,
                          // "Animations", 2026-09-08 — the brief's own
                          // "location selection" case) — keyed by the
                          // point so Flutter rebuilds this as a fresh
                          // widget on every tap/current-location move,
                          // restarting the animation instead of easing
                          // continuously between arbitrary begin/end
                          // values.
                          child: TweenAnimationBuilder<double>(
                            key: ValueKey(_selected),
                            tween: Tween(begin: 0.5, end: 1),
                            duration: const Duration(milliseconds: 300),
                            curve: Curves.easeOutBack,
                            builder: (context, scale, child) =>
                                Transform.scale(
                                  scale: scale,
                                  alignment: Alignment.bottomCenter,
                                  child: child,
                                ),
                            child: Icon(
                              Icons.location_pin,
                              size: 44,
                              color: theme.colorScheme.primary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                // A floating current-location control over the map
                // itself, not an AppBar icon — the standard placement
                // for this action in a map-first picker (Phase 7 of the
                // redesign, "Map experience", 2026-09-08); same
                // tooltip/behavior as before.
                Positioned(
                  right: VistaarSpacing.md,
                  bottom: VistaarSpacing.md,
                  child: FloatingActionButton(
                    heroTag: 'location-picker-current-location',
                    tooltip: 'Use my current location',
                    onPressed: _isLocating ? null : _centerOnCurrentPosition,
                    child: _isLocating
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2.5),
                          )
                        : const Icon(Icons.my_location),
                  ),
                ),
              ],
            ),
          ),
          SafeArea(
            top: false,
            child: Container(
              padding: const EdgeInsets.all(VistaarSpacing.md),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                boxShadow: [
                  BoxShadow(
                    color: theme.colorScheme.shadow.withValues(alpha: 0.08),
                    blurRadius: 8,
                    offset: const Offset(0, -2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Tap the map to move the pin.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: VistaarSpacing.sm),
                  PrimaryButton(label: 'Confirm Location', onPressed: _confirm),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
