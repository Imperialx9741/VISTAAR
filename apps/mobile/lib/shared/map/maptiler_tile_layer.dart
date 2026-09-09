import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';

import '../../core/config/app_config.dart';
import '../design/vistaar_spacing.dart';

/// MapTiler Cloud tile rendering (owner's final maps-provider decision,
/// 2026-08-29 — see `AppConfig.mapTilerApiKey`'s own doc comment). This
/// is the **only** file in the app that ever reads
/// [AppConfig.mapTilerApiKey] and builds a URL with it — every map
/// screen goes through [maptilerLayers] instead of touching the key
/// itself, so the real value never needs to be duplicated, logged, or
/// printed anywhere else.
///
/// `streets-v2` is MapTiler's own standard default street style — a
/// cosmetic pick, not a business decision; nothing about the owner's
/// actual maps-provider choice depended on which visual style renders.
/// Raster PNG tiles (not vector) — the simplest format `flutter_map`'s
/// `TileLayer` consumes natively, no extra vector-tile rendering
/// package needed.
const String _mapTilerStyle = 'streets-v2';

/// The widgets every real map screen in this app needs, in the z-order
/// `flutter_map` expects them (`FlutterMap(children: maptilerLayers())`
/// plus that screen's own marker/interaction layers on top). Returns an
/// empty list when [AppConfig.hasMapTilerApiKey] is `false` — callers
/// must check that themselves before ever building a `FlutterMap` at
/// all (see `MapUnavailableNotice`), the same "no key configured is a
/// real, supported state" contract `AppConfig` itself documents.
List<Widget> maptilerLayers() {
  if (!AppConfig.hasMapTilerApiKey) return const [];
  return [
    TileLayer(
      urlTemplate:
          'https://api.maptiler.com/maps/$_mapTilerStyle/{z}/{x}/{y}.png'
          '?key=${AppConfig.mapTilerApiKey}',
      userAgentPackageName: 'io.vistaar.mobile',
      maxNativeZoom: 20,
    ),
    // MapTiler's Terms of Service require visible attribution on every
    // map that uses their tiles — not optional cosmetic chrome.
    RichAttributionWidget(
      alignment: AttributionAlignment.bottomLeft,
      attributions: [
        TextSourceAttribution(
          '© MapTiler © OpenStreetMap contributors',
          onTap: null,
        ),
      ],
    ),
  ];
}

/// Shown in place of a map on any screen where
/// [AppConfig.hasMapTilerApiKey] is `false` — every map-touching screen
/// in this app must degrade to this rather than crash or show a blank
/// grey rectangle, the same contract `AppConfig.mapTilerApiKey`'s own
/// doc comment requires.
class MapUnavailableNotice extends StatelessWidget {
  const MapUnavailableNotice({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      alignment: Alignment.center,
      padding: const EdgeInsets.all(VistaarSpacing.md),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(VistaarRadius.control),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.map_outlined, color: scheme.onSurfaceVariant),
          const SizedBox(height: VistaarSpacing.xs),
          Text(
            'Map unavailable — no maps key configured for this build.',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}
