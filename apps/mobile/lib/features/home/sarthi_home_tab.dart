import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart' as latlong;
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/driver_availability_api.dart';
import '../../core/api/ride_api.dart' show RideGeoPoint;
import '../../core/api/ride_offer_api.dart';
import '../../core/api/wallet_api.dart';
import '../../shared/design/vistaar_colors.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/map/current_location_map.dart';
import '../../shared/widgets/primary_button.dart';
import '../rides/ride_execution_screen.dart';
import '../rides/ride_offer_screen.dart';

/// How often a location update is sent while online (PRD §15 — "target
/// location update interval is approximately 5 seconds").
const Duration _locationUpdateInterval = Duration(seconds: 5);

/// How often this screen polls for a new ride offer while online. There
/// is no push/websocket channel yet (a documented gap — see the app's
/// README), so polling is the only mechanism; picked faster than the
/// location update interval so a driver doesn't lose much of a PENDING
/// offer's own countdown window (PRD §17) to poll latency.
const Duration _offerPollInterval = Duration(seconds: 4);

/// How often the wallet summary card refreshes — deliberately slower
/// than the offer/location polls above (balance doesn't need
/// second-by-second freshness), but frequent enough that a recharge
/// made from the Wallet tab (`WalletScreen`) shows up here without the
/// driver needing to background/foreground the app. Since
/// [VistaarNavShell] keeps this tab's State alive across tab switches
/// (by design — see that class's own doc comment), nothing else would
/// ever tell this screen a recharge just happened elsewhere.
const Duration _walletRefreshInterval = Duration(seconds: 30);

/// The real, backend-enforced minimum wallet balance for accepting a
/// new ride offer (ADR-0058) — `LOW_BALANCE_THRESHOLD` in
/// `modules/wallet/domain/entities.py`, confirmed directly against the
/// backend source, not assumed. A driver at or below this after using
/// their one grace-ride acceptance cannot accept another offer until
/// they recharge; shown here so that rule is visible before it blocks
/// anyone, per the owner's brief ("Sarthi home must clearly show...
/// minimum wallet requirement"). Purely informational — this screen
/// enforces nothing itself, the backend still does.
const double _minimumWalletBalanceForOffers = 20;

/// The Sarthi role's Home tab — Go Online/Offline (api-contracts.md
/// §10), periodic location updates (api-contracts.md §15), and — while
/// online — polling for incoming ride offers (api-contracts.md §16.1),
/// pushing [RideOfferScreen] the moment one shows up (build order steps
/// 2 and 3, docs/16-mobile/mobile-app-implementation-plan.md §5.2-5.3).
///
/// Redesigned 2026-09-08 around a **workflow, not a dashboard** (the
/// owner's Rapido-Captain-benchmarked brief): a full-screen live map is
/// now the background — "map/current location" — with a bottom panel
/// whose Go Online/Offline control is the single dominant element on
/// the screen; the wallet summary sits below it deliberately smaller
/// and quieter so it never visually competes with that control, per
/// the brief's own explicit instruction. "Today's earnings" and "rides
/// completed" are NOT shown — no backend endpoint returns that data for
/// a driver (verified directly against `modules/wallet/service.py`;
/// the only related figure is an admin-dashboard aggregate, never
/// exposed to this app) — this screen shows real numbers only, per the
/// brief's own "do not invent unavailable backend information."
///
/// All Go Online/Offline, location, and offer-polling *behavior* is
/// byte-for-byte unchanged from before this pass — only the map and the
/// panel layout are new.
///
/// Android: location updates run as a real foreground service while
/// online (`AndroidSettings.foregroundNotificationConfig`, `geolocator`
/// — already an existing dependency, no new package added), with its
/// own persistent, non-dismissible notification
/// (AndroidManifest.xml declares the required `FOREGROUND_SERVICE`/
/// `FOREGROUND_SERVICE_LOCATION` permissions; `geolocator_android`'s own
/// AAR manifest declares the service itself). This keeps updates flowing
/// while the app is minimized or the screen is locked — Android's
/// documented "foreground service" exception to its background-location
/// restrictions applies here (the service is started while the app has
/// foreground access, going online), so `ACCESS_BACKGROUND_LOCATION`
/// ("Always" location) is still deliberately not requested; declaring an
/// unused permission risks exactly the kind of unjustified-permission
/// rejection both app stores flag. One documented limit, not silently
/// claimed away: `geolocator`'s own foreground-notification config
/// raises process priority and keeps the location subsystem active, but
/// does not guarantee survival if Android fully destroys the Activity
/// under severe memory pressure — a dedicated background-isolate
/// service package would be needed to close that specific remaining
/// gap, flagged as a possible future hardening step, not built here.
///
/// Other platforms (iOS, postponed — must not block Android; web/
/// desktop, not a real target) fall back to a plain
/// [Geolocator.getPositionStream] with no platform-specific foreground
/// config — foreground-only there, same limitation this screen
/// previously had everywhere.
class SarthiHomeTab extends StatefulWidget {
  const SarthiHomeTab({super.key});

  @override
  State<SarthiHomeTab> createState() => _SarthiHomeTabState();
}

enum _AvailabilityStatus { offline, online }

class _SarthiHomeTabState extends State<SarthiHomeTab> {
  _AvailabilityStatus _status = _AvailabilityStatus.offline;
  bool _isBusy = false;
  String? _errorMessage;
  DateTime? _lastLocationSentAt;
  StreamSubscription<Position>? _locationSubscription;
  Timer? _offerPollTimer;
  bool _isShowingOffer = false;

  Wallet? _wallet;
  Timer? _walletRefreshTimer;

  /// The map's "you are here" point — set once from a best-effort
  /// initial fix, then kept live from the same location stream
  /// [_sendLocation] already sends to the backend while online (no
  /// extra GPS reads added for this).
  latlong.LatLng? _currentPosition;

  @override
  void initState() {
    super.initState();
    unawaited(_loadInitialPosition());
    unawaited(_loadWallet());
    _walletRefreshTimer = Timer.periodic(
      _walletRefreshInterval,
      (_) => unawaited(_loadWallet()),
    );
  }

  @override
  void dispose() {
    unawaited(_locationSubscription?.cancel());
    _offerPollTimer?.cancel();
    _walletRefreshTimer?.cancel();
    super.dispose();
  }

  /// Best-effort, one-time — purely to give the background map a
  /// starting center before the driver ever goes online (location
  /// permission was already granted earlier in this app's own login
  /// flow, same assumption `LocationPickerScreen` already makes). A
  /// failure just leaves the map showing its loading state; going
  /// online still works regardless, since that path has its own
  /// location handling ([_startLocationUpdates]).
  Future<void> _loadInitialPosition() async {
    try {
      final position = await Geolocator.getCurrentPosition().timeout(
        const Duration(seconds: 8),
      );
      if (mounted) {
        setState(
          () => _currentPosition = latlong.LatLng(
            position.latitude,
            position.longitude,
          ),
        );
      }
    } on Object {
      // Swallowed — see doc comment above.
    }
  }

  /// Best-effort, same "a background tick must not disrupt the screen"
  /// tolerance every other timer on this screen already gets — the
  /// wallet summary simply stays at its last known value if a
  /// refresh fails.
  Future<void> _loadWallet() async {
    final api = context.read<WalletApi>();
    try {
      final wallet = await api.getWallet();
      if (mounted) setState(() => _wallet = wallet);
    } on ApiException {
      // Swallowed — see above.
    }
  }

  Future<void> _goOnline() async {
    setState(() {
      _isBusy = true;
      _errorMessage = null;
    });
    final api = context.read<DriverAvailabilityApi>();
    try {
      await api.goOnline();
      if (!mounted) return;
      setState(() => _status = _AvailabilityStatus.online);
      _startLocationUpdates();
      _startOfferPolling();
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _goOffline() async {
    setState(() {
      _isBusy = true;
      _errorMessage = null;
    });
    final api = context.read<DriverAvailabilityApi>();
    try {
      await api.goOffline();
      if (!mounted) return;
      _stopLocationUpdates();
      _stopOfferPolling();
      setState(() => _status = _AvailabilityStatus.offline);
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  /// Android: `AndroidSettings.foregroundNotificationConfig` makes
  /// `Geolocator.getPositionStream()` run the plugin's own
  /// `GeolocatorLocationService` as a real foreground service — see this
  /// screen's own class doc comment for exactly what that does and does
  /// not guarantee. `intervalDuration` targets the same ~5s cadence PRD
  /// §15 already specified.
  LocationSettings _buildLocationSettings() {
    if (defaultTargetPlatform == TargetPlatform.android) {
      return AndroidSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 0,
        intervalDuration: _locationUpdateInterval,
        foregroundNotificationConfig: const ForegroundNotificationConfig(
          notificationTitle: 'VISTAAR — You are online',
          notificationText: 'Sharing your location so nearby rides can find you.',
          notificationChannelName: 'Sarthi location sharing',
          setOngoing: true,
        ),
      );
    }
    return LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: 0);
  }

  void _startLocationUpdates() {
    unawaited(_locationSubscription?.cancel());
    _locationSubscription = Geolocator.getPositionStream(
      locationSettings: _buildLocationSettings(),
    ).listen(
      (position) => unawaited(_sendLocation(position)),
      // Best-effort — see _sendLocation's own doc comment. A stream
      // error (a transient GPS/provider hiccup) must not tear the
      // subscription down or flip the whole screen into an error state
      // while the driver is trying to stay online; geolocator keeps the
      // stream alive and simply emits the next successful fix whenever
      // one arrives.
      onError: (Object _) {},
      cancelOnError: false,
    );
  }

  void _stopLocationUpdates() {
    unawaited(_locationSubscription?.cancel());
    _locationSubscription = null;
  }

  /// Best-effort — one missed update (a transient network hiccup
  /// sending it to the backend) must not flip the whole screen into an
  /// error state while the driver is trying to stay online; the stream
  /// simply keeps emitting. Going online/offline itself still surfaces
  /// a real error (above) since that's a deliberate, one-off action the
  /// driver is waiting on. A lightweight time-based throttle
  /// (`_lastLocationSentAt`) guards against sending more often than the
  /// target interval even if the underlying platform stream ever emits
  /// faster than `intervalDuration` requests (its own documented
  /// behavior on some devices/OS versions).
  Future<void> _sendLocation(Position position) async {
    // The map recenters on every fix regardless of the throttle below
    // — that's just a local setState, not a network call, so there's
    // no cost to keeping it live even between throttled backend sends.
    if (mounted) {
      setState(
        () => _currentPosition = latlong.LatLng(
          position.latitude,
          position.longitude,
        ),
      );
    }
    final now = DateTime.now();
    if (_lastLocationSentAt != null &&
        now.difference(_lastLocationSentAt!) < _locationUpdateInterval) {
      return;
    }
    final api = context.read<DriverAvailabilityApi>();
    try {
      await api.updateLocation(
        latitude: position.latitude,
        longitude: position.longitude,
        accuracyMeters: position.accuracy,
        recordedAt: DateTime.now().toUtc(),
      );
      if (mounted) setState(() => _lastLocationSentAt = now);
    } on Object {
      // Swallowed deliberately — see the doc comment above.
    }
  }

  void _startOfferPolling() {
    _offerPollTimer?.cancel();
    _offerPollTimer = Timer.periodic(
      _offerPollInterval,
      (_) => unawaited(_pollForOffers()),
    );
  }

  void _stopOfferPolling() {
    _offerPollTimer?.cancel();
    _offerPollTimer = null;
  }

  /// Best-effort, same rationale as [_sendLocation] — a missed poll
  /// simply tries again on the next tick. Guarded by [_isShowingOffer]
  /// so a second PENDING offer found mid-poll never stacks a second
  /// [RideOfferScreen] on top of one already showing.
  ///
  /// A successful Accept pops [RideOfferScreen] with the new ride's id
  /// — this then pauses offer polling (but not location updates, which
  /// keep running: the driver is still on the move) and pushes
  /// [RideExecutionScreen], resuming polling only once that ride is
  /// done and the driver is still online. Whether the *backend* itself
  /// already excludes a driver with an active ride from new dispatches
  /// is unverified (not confirmed in `modules/matching/service.py`) —
  /// this client-side pause is a safeguard either way, not a substitute
  /// for checking that.
  Future<void> _pollForOffers() async {
    if (_isShowingOffer) return;
    final api = context.read<RideOfferApi>();
    List<RideOffer> offers;
    try {
      offers = await api.listOffers();
    } on Object {
      return;
    }
    if (!mounted) return;
    final pending = offers.where((offer) => offer.isPending).toList();
    if (pending.isEmpty) return;
    _isShowingOffer = true;
    final position = _currentPosition;
    final acceptedRideId = await Navigator.of(context).push<String?>(
      MaterialPageRoute<String?>(
        builder: (_) => RideOfferScreen(
          offer: pending.first,
          driverPosition: position == null
              ? null
              : RideGeoPoint(latitude: position.latitude, longitude: position.longitude),
        ),
      ),
    );
    _isShowingOffer = false;
    if (acceptedRideId == null || !mounted) return;

    _stopOfferPolling();
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => RideExecutionScreen(rideId: acceptedRideId),
      ),
    );
    if (mounted && _status == _AvailabilityStatus.online) {
      _startOfferPolling();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isOnline = _status == _AvailabilityStatus.online;
    return Scaffold(
      // Transparent, not the default surface — the map fills the whole
      // body behind it (Rapido-Captain-benchmarked "map/current
      // location" requirement); the AppBar sits on top as a thin
      // overlay rather than pushing the map down.
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Sarthi'),
        backgroundColor: theme.colorScheme.surface.withValues(alpha: 0.9),
        elevation: 0,
      ),
      body: Stack(
        children: [
          Positioned.fill(
            child: CurrentLocationMap(
              center: _currentPosition,
              markerColor: isOnline ? VistaarColors.success : theme.colorScheme.onSurfaceVariant,
            ),
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: _buildControlPanel(context, isOnline),
          ),
        ],
      ),
    );
  }

  /// The one dominant control on this screen, per the owner's brief
  /// ("Do NOT allow secondary information to visually compete with the
  /// ONLINE/OFFLINE control") — status + the tall Go Online/Offline
  /// button sit right at the top of this panel at full visual weight;
  /// the wallet summary is deliberately smaller, quieter, and placed
  /// last so it reads as secondary at a glance.
  Widget _buildControlPanel(BuildContext context, bool isOnline) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(VistaarRadius.surface),
        ),
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
              Row(
                children: [
                  Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isOnline ? VistaarColors.success : theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(width: VistaarSpacing.sm),
                  Expanded(
                    child: Text(
                      isOnline ? 'You are Online' : 'You are Offline',
                      style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: VistaarSpacing.xs),
              Text(
                isOnline
                    ? 'You can now receive ride requests.'
                    : 'Go online to start receiving ride requests.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: VistaarSpacing.sm),
                Text(
                  _errorMessage!,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ],
              const SizedBox(height: VistaarSpacing.md),
              PrimaryButton(
                label: isOnline ? 'Go Offline' : 'Go Online',
                isLoading: _isBusy,
                height: 60,
                onPressed: isOnline ? _goOffline : _goOnline,
              ),
              const SizedBox(height: VistaarSpacing.md),
              const Divider(height: 1),
              const SizedBox(height: VistaarSpacing.sm),
              _buildWalletStrip(context),
            ],
          ),
        ),
      ),
    );
  }

  /// Wallet balance + outstanding debt + the real minimum-balance rule,
  /// per the owner's brief ("Sarthi home must clearly show... current
  /// wallet balance, minimum wallet requirement, outstanding debt where
  /// applicable") — kept deliberately compact (a single row plus, at
  /// most, one short warning line) so it never competes with the
  /// Online/Offline control above it. Full transaction history and
  /// recharge live on the Wallet tab ([WalletScreen]); this doesn't
  /// duplicate that screen.
  Widget _buildWalletStrip(BuildContext context) {
    final theme = Theme.of(context);
    final wallet = _wallet;
    if (wallet == null) {
      // Best-effort, not an error state — see _loadWallet()'s own doc
      // comment. Nothing shown while unknown rather than a misleading
      // ₹0.
      return const SizedBox.shrink();
    }
    final isBelowMinimum = wallet.balance <= _minimumWalletBalanceForOffers;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              Icons.account_balance_wallet_outlined,
              size: 18,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: VistaarSpacing.xs),
            Flexible(
              child: Text(
                'Wallet balance',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
            const SizedBox(width: VistaarSpacing.sm),
            Flexible(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerRight,
                child: Text(
                  '${wallet.currency} ${wallet.balance.toStringAsFixed(2)}',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: isBelowMinimum ? theme.colorScheme.error : theme.colorScheme.tertiary,
                  ),
                ),
              ),
            ),
          ],
        ),
        if (isBelowMinimum) ...[
          const SizedBox(height: VistaarSpacing.xs),
          Text(
            'A minimum of ${wallet.currency} '
            '${_minimumWalletBalanceForOffers.toStringAsFixed(0)} is required '
            'to accept new ride offers.',
            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
          ),
        ],
        if (wallet.outstandingDebt > 0) ...[
          const SizedBox(height: VistaarSpacing.xs),
          Text(
            'Unpaid cancellation penalty: ${wallet.currency} '
            '${wallet.outstandingDebt.toStringAsFixed(2)} '
            '(recovered from your next recharge)',
            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
          ),
        ],
      ],
    );
  }
}
