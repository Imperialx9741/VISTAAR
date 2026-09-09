import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart' as latlong;

import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/map/current_location_map.dart';
import '../../shared/widgets/primary_button.dart';
import '../rides/book_ride_screen.dart';
import '../rides/scheduled_rides_screen.dart';

/// The User role's Home tab — booking entry point (build order step 4,
/// docs/16-mobile/mobile-app-implementation-plan.md §4.1).
///
/// Redesigned 2026-09-08 around the owner's Rapido-benchmarked brief:
/// **map-first** — a full-screen live map of the device's current
/// location is now the background, with a bottom panel carrying the
/// booking entry point and quick actions, rather than the previous
/// card-based, map-less layout. "Where are you headed?" is now a
/// tappable search-bar-style affordance (still opens the same
/// [BookRideScreen] — this app has no address search/geocoding to back
/// a real inline search box; see that screen's own doc comment for
/// why), not a separate button below a description card. Scheduled
/// Rides and Book for Someone Else remain the same two quick actions,
/// routing to the exact same screens/APIs as before — this is a
/// presentation-only change plus one read-only GPS fix for the map
/// background (no new write/API call).
class UserHomeTab extends StatefulWidget {
  const UserHomeTab({super.key});

  @override
  State<UserHomeTab> createState() => _UserHomeTabState();
}

class _UserHomeTabState extends State<UserHomeTab> {
  latlong.LatLng? _currentPosition;

  @override
  void initState() {
    super.initState();
    unawaited(_loadInitialPosition());
  }

  /// Best-effort, one-time — purely to give the background map a
  /// starting center (location permission was already granted earlier
  /// in this app's own login flow, same assumption `LocationPickerScreen`
  /// and `SarthiHomeTab` already make). A failure just leaves the map
  /// showing its loading state; booking a ride is entirely unaffected,
  /// since [BookRideScreen] does its own location handling.
  Future<void> _loadInitialPosition() async {
    try {
      final position = await Geolocator.getCurrentPosition().timeout(
        const Duration(seconds: 8),
      );
      if (mounted) {
        setState(
          () => _currentPosition = latlong.LatLng(position.latitude, position.longitude),
        );
      }
    } on Object {
      // Swallowed — see doc comment above.
    }
  }

  String _greeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('VISTAAR'),
        backgroundColor: theme.colorScheme.surface.withValues(alpha: 0.9),
        elevation: 0,
      ),
      body: Stack(
        children: [
          Positioned.fill(child: CurrentLocationMap(center: _currentPosition)),
          Align(
            alignment: Alignment.bottomCenter,
            child: _buildBottomPanel(context),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomPanel(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(VistaarRadius.surface)),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.shadow.withValues(alpha: 0.12),
            blurRadius: 16,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            VistaarSpacing.lg,
            VistaarSpacing.md,
            VistaarSpacing.lg,
            VistaarSpacing.lg,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(_greeting(), style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              )),
              const SizedBox(height: VistaarSpacing.xs),
              // A tappable "Where to?" affordance, not a real search
              // box — this app has no address search/geocoding to back
              // one (see BookRideScreen's own doc comment); tapping it
              // opens the exact same booking flow the old "Book a
              // Ride" button did.
              _WhereToButton(
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => const BookRideScreen()),
                ),
              ),
              const SizedBox(height: VistaarSpacing.md),
              Row(
                children: [
                  Expanded(
                    child: _QuickAction(
                      icon: Icons.event_outlined,
                      label: 'Scheduled Rides',
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => const ScheduledRidesScreen(),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: VistaarSpacing.sm),
                  Expanded(
                    child: _QuickAction(
                      icon: Icons.person_add_alt_outlined,
                      label: 'Book for Someone Else',
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) =>
                              const BookRideScreen(startForSomeoneElse: true),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The "strongest, most prominent action on the screen" — a tall,
/// search-bar-shaped, tappable card (not a real text field: no
/// address search exists to back one). Deliberately more visually
/// dominant than the two quick actions below it.
class _WhereToButton extends StatelessWidget {
  const _WhereToButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return VistaarCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(
        horizontal: VistaarSpacing.md,
        vertical: VistaarSpacing.lg,
      ),
      child: Row(
        children: [
          Icon(Icons.search, color: theme.colorScheme.primary),
          const SizedBox(width: VistaarSpacing.md),
          Expanded(
            child: Text(
              'Where are you headed?',
              style: theme.textTheme.titleMedium,
            ),
          ),
          SizedBox(
            width: 88,
            child: PrimaryButton(label: 'Book', onPressed: onTap, height: 40),
          ),
        ],
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return VistaarCard(
      onTap: onTap,
      padding: const EdgeInsets.all(VistaarSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: theme.colorScheme.primary),
          const SizedBox(height: VistaarSpacing.sm),
          Text(label, style: theme.textTheme.labelLarge),
        ],
      ),
    );
  }
}
