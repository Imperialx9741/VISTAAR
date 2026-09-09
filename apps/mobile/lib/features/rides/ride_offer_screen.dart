import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/ride_api.dart' show RideGeoPoint;
import '../../core/api/ride_offer_api.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/widgets/primary_button.dart';
import '../../shared/widgets/route_map_preview.dart';
import '../wallet/recharge_wallet_screen.dart';

/// Straight-line (haversine) distance in kilometers between two points
/// — real math on real data (the offer's own pickup coordinates and
/// this driver's own last-known GPS fix, both already available to
/// this screen), not a value the backend sends. `RideOffer` itself
/// carries no distance field (verified directly against
/// `modules/matching/router.py`'s `_offer_data()` — the backend
/// genuinely doesn't compute or send one), so this is the one honest
/// way to show "how far is this pickup" without inventing data.
double _distanceKm(RideGeoPoint a, RideGeoPoint b) {
  const earthRadiusKm = 6371.0;
  final dLat = _toRadians(b.latitude - a.latitude);
  final dLng = _toRadians(b.longitude - a.longitude);
  final lat1 = _toRadians(a.latitude);
  final lat2 = _toRadians(b.latitude);
  final h =
      math.sin(dLat / 2) * math.sin(dLat / 2) +
      math.sin(dLng / 2) * math.sin(dLng / 2) * math.cos(lat1) * math.cos(lat2);
  return earthRadiusKm * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h));
}

double _toRadians(double degrees) => degrees * math.pi / 180;

/// A ride offer dispatched to this Sarthi (driver) — build order step 3
/// (docs/16-mobile/mobile-app-implementation-plan.md §5.3). Pushed by
/// [SarthiHomeScreen]'s polling loop whenever `GET .../ride-offers`
/// (api-contracts.md §16.1) returns a PENDING offer; pops with the new
/// ride's id (a `String?`) on a successful Accept, `null` otherwise
/// (Reject, expiry-Close) — [SarthiHomeScreen] uses that to know whether
/// to open [RideExecutionScreen] next.
///
/// Redesigned 2026-09-08 around the owner's Rapido-Captain-benchmarked
/// brief: "the driver should understand the request within 1-2
/// seconds." The countdown is now the dominant visual (a large ring +
/// number, not a line of body text), Accept is a tall, unmistakably
/// primary action, and Reject is deliberately quieter — a text button,
/// not a second button of equal visual weight. [driverPosition], when
/// supplied, adds a real computed pickup distance (see [_distanceKm]'s
/// own doc comment for why that's honest, not invented, data); vehicle
/// category, fare, destination, and payment mode are **not** shown —
/// none of them exist anywhere in the offer response the backend sends
/// (verified directly against `matching/router.py`), and this redesign
/// does not invent them.
///
/// The countdown is computed locally from [RideOffer.expiresAt] on a
/// one-second [Timer.periodic] — it does not re-poll the backend, so a
/// slow/stalled clock on this device is the only thing that could make
/// it drift from the backend's own expiry, same tradeoff the location
/// update timer already accepts. Back navigation is disabled
/// ([PopScope] `canPop: false`) so a driver can't swipe the request away
/// without actually choosing Accept or Reject — once expired, an
/// explicit "Close" button is the only way out.
class RideOfferScreen extends StatefulWidget {
  const RideOfferScreen({required this.offer, this.driverPosition, super.key});

  final RideOffer offer;

  /// This driver's own last-known position (from `SarthiHomeTab`'s
  /// already-running location stream while online) — optional, since a
  /// driver could in principle receive an offer before any fix has
  /// landed yet. `null` simply omits the distance line rather than
  /// guessing.
  final RideGeoPoint? driverPosition;

  @override
  State<RideOfferScreen> createState() => _RideOfferScreenState();
}

class _RideOfferScreenState extends State<RideOfferScreen> {
  Timer? _countdownTimer;
  Duration _remaining = Duration.zero;
  Duration _totalWindow = Duration.zero;
  bool _isExpired = false;
  bool _isBusy = false;
  String? _errorMessage;

  /// Set alongside [_errorMessage] on a failed Accept — lets the build
  /// method show a "Recharge Wallet" action specifically for
  /// `WALLET_RECHARGE_REQUIRED` (ADR-0058 §6's deferred action, now
  /// wired up per ADR-0060), without the generic error display needing
  /// to parse [_errorMessage]'s free-text content to decide that.
  String? _errorCode;

  /// Generated once, on first Accept tap, and reused for every retry of
  /// that same attempt — accept-offer's `Idempotency-Key` requirement
  /// (api-contracts.md §16.3) exists precisely so a retried tap after a
  /// network error replays the same attempt instead of risking two
  /// accepts.
  String? _acceptIdempotencyKey;

  @override
  void initState() {
    super.initState();
    _totalWindow = widget.offer.remaining();
    if (_totalWindow.isNegative) _totalWindow = Duration.zero;
    _updateRemaining();
    _countdownTimer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => _updateRemaining(),
    );
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }

  void _updateRemaining() {
    final remaining = widget.offer.remaining();
    final clamped = remaining.isNegative ? Duration.zero : remaining;
    if (!mounted) return;
    setState(() {
      _remaining = clamped;
      if (_remaining == Duration.zero) _isExpired = true;
    });
    if (_isExpired) _countdownTimer?.cancel();
  }

  Future<void> _accept() async {
    final api = context.read<RideOfferApi>();
    final idempotencyKey = _acceptIdempotencyKey ??= const Uuid().v4();
    setState(() {
      _isBusy = true;
      _errorMessage = null;
      _errorCode = null;
    });
    try {
      final result = await api.acceptOffer(
        widget.offer.offerId,
        idempotencyKey: idempotencyKey,
      );
      if (!mounted) return;
      // Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02) — the
      // backend's own IN_APP notification (WALLET_LOW_BALANCE) has
      // nowhere to surface yet (this app has no notification-inbox
      // screen at all, for any of its existing notification types
      // either — not a gap this one feature invents). Shown here
      // instead, right where it's most actionable: the moment this
      // Sarthi sees their post-acceptance balance.
      if (result.walletBalance <= 20) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Wallet balance is low (₹${result.walletBalance.toStringAsFixed(2)}). '
              "You can accept one more ride, but you'll need to recharge "
              'before accepting another.',
            ),
            duration: const Duration(seconds: 5),
            action: SnackBarAction(
              label: 'Recharge',
              onPressed: () => unawaited(_openRecharge()),
            ),
          ),
        );
      }
      // Pops with the new ride's id rather than pushing RideExecutionScreen
      // directly — [SarthiHomeScreen] is the one that owns this driver's
      // offer-poll timer, and needs to know a ride was just accepted so it
      // can pause polling for new offers while this one is executed (see
      // its own doc comment for why).
      Navigator.of(context).pop(result.rideId);
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _errorMessage = error.message;
          _errorCode = error.code;
        });
      }
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  /// ADR-0058 §6's deferred action, wired up here per ADR-0060 — shown
  /// both from the low-balance warning above and from the
  /// `WALLET_RECHARGE_REQUIRED` error state in [build] below. Does not
  /// itself retry Accept on return: the driver's balance/grace state
  /// may have changed, and a fresh tap on Accept re-reads it correctly
  /// rather than this screen guessing.
  Future<void> _openRecharge() async {
    if (!mounted) return;
    await Navigator.of(
      context,
    ).push<double>(MaterialPageRoute(builder: (_) => const RechargeWalletScreen()));
  }

  Future<void> _reject() async {
    final api = context.read<RideOfferApi>();
    setState(() {
      _isBusy = true;
      _errorMessage = null;
    });
    try {
      await api.rejectOffer(widget.offer.offerId);
      if (!mounted) return;
      Navigator.of(context).pop();
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pickup = widget.offer.pickup;
    final distanceKm = (pickup != null && widget.driverPosition != null)
        ? _distanceKm(
            RideGeoPoint(latitude: pickup.latitude, longitude: pickup.longitude),
            widget.driverPosition!,
          )
        : null;
    return PopScope(
      canPop: false,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('New Ride Request'),
          automaticallyImplyLeading: false,
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(VistaarSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // The countdown is the dominant, "understand this in
                // 1-2 seconds" element — a ring + a large number, not
                // a line of body text buried in a scroll column.
                _CountdownRing(
                  remaining: _remaining,
                  total: _totalWindow,
                  isExpired: _isExpired,
                ),
                if (_isExpired)
                  Center(
                    child: Text(
                      'This request has expired',
                      style: theme.textTheme.titleMedium,
                    ),
                  )
                else
                  _CountdownCaption(remaining: _remaining, isExpired: _isExpired),
                const SizedBox(height: VistaarSpacing.md),
                Expanded(
                  child: pickup == null
                      ? Center(
                          child: Text(
                            'Pickup location unavailable',
                            style: theme.textTheme.bodyLarge,
                          ),
                        )
                      : ClipRRect(
                          borderRadius: BorderRadius.circular(VistaarRadius.surface),
                          child: RouteMapPreview(
                            pickup: RideGeoPoint(
                              latitude: pickup.latitude,
                              longitude: pickup.longitude,
                            ),
                            height: double.infinity,
                          ),
                        ),
                ),
                const SizedBox(height: VistaarSpacing.sm),
                Row(
                  children: [
                    Icon(Icons.trip_origin, size: 18, color: theme.colorScheme.primary),
                    const SizedBox(width: VistaarSpacing.xs),
                    Expanded(
                      child: Text(
                        pickup == null
                            ? 'Pickup location unavailable'
                            : 'Pickup: ${pickup.latitude.toStringAsFixed(5)}, '
                                  '${pickup.longitude.toStringAsFixed(5)}',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                    if (distanceKm != null) ...[
                      const SizedBox(width: VistaarSpacing.sm),
                      Text(
                        '${distanceKm.toStringAsFixed(1)} km away',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: theme.colorScheme.tertiary,
                        ),
                      ),
                    ],
                  ],
                ),
                if (_errorMessage != null) ...[
                  const SizedBox(height: VistaarSpacing.sm),
                  Text(
                    _errorMessage!,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ],
                const SizedBox(height: VistaarSpacing.md),
                if (_isExpired)
                  PrimaryButton(
                    label: 'Close',
                    onPressed: () => Navigator.of(context).pop(),
                  )
                else ...[
                  if (_errorCode == 'WALLET_RECHARGE_REQUIRED') ...[
                    PrimaryButton(
                      label: 'Recharge Wallet',
                      onPressed: () => unawaited(_openRecharge()),
                    ),
                    const SizedBox(height: VistaarSpacing.sm),
                  ],
                  // Very large — the owner's brief calls this out
                  // explicitly ("very large ACCEPT button").
                  PrimaryButton(
                    label: 'Accept',
                    isLoading: _isBusy,
                    height: 64,
                    onPressed: _accept,
                  ),
                  const SizedBox(height: VistaarSpacing.sm),
                  // Deliberately a plain text button, not a second
                  // outlined button of near-equal weight — "a secondary
                  // REJECT/SKIP action", not a competing primary.
                  TextButton(
                    onPressed: _isBusy ? null : _reject,
                    child: const Text('Reject'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A countdown ring + large numeral — the one thing on this screen
/// designed to be read in under a second. Turns error-red inside the
/// last 5 seconds so urgency is communicated by color, not just the
/// number itself.
class _CountdownRing extends StatelessWidget {
  const _CountdownRing({
    required this.remaining,
    required this.total,
    required this.isExpired,
  });

  final Duration remaining;
  final Duration total;
  final bool isExpired;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final totalSeconds = total.inSeconds;
    final progress = isExpired
        ? 0.0
        : totalSeconds <= 0
        ? 1.0
        : (remaining.inMilliseconds / total.inMilliseconds).clamp(0.0, 1.0);
    final isUrgent = !isExpired && remaining.inSeconds <= 5;
    final ringColor = isExpired
        ? theme.colorScheme.onSurfaceVariant
        : isUrgent
        ? theme.colorScheme.error
        : theme.colorScheme.primary;
    return Center(
      child: SizedBox(
        width: 96,
        height: 96,
        child: Stack(
          alignment: Alignment.center,
          children: [
            SizedBox(
              width: 96,
              height: 96,
              child: CircularProgressIndicator(
                value: progress,
                strokeWidth: 6,
                backgroundColor: theme.colorScheme.surfaceContainerHighest,
                valueColor: AlwaysStoppedAnimation(ringColor),
              ),
            ),
            Text(
              isExpired ? 'Expired' : '${remaining.inSeconds}s',
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: ringColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The ring's own accessible/semantic caption — visually secondary
/// (small, muted) since the ring itself already communicates urgency
/// at a glance, but present so the countdown is legible to a screen
/// reader too, not just conveyed by color and shape.
class _CountdownCaption extends StatelessWidget {
  const _CountdownCaption({required this.remaining, required this.isExpired});

  final Duration remaining;
  final bool isExpired;

  @override
  Widget build(BuildContext context) {
    if (isExpired) return const SizedBox.shrink();
    return Center(
      child: Text(
        'Responds in ${remaining.inSeconds}s',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }
}
