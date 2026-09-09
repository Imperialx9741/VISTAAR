import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/ride_api.dart';
import '../../core/api/safety_api.dart';
import '../../shared/design/state_views.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/widgets/cancel_reason_dialog.dart';
import '../../shared/widgets/primary_button.dart';
import '../../shared/widgets/route_map_preview.dart';
import '../../shared/widgets/sos_dialog.dart';
import '../gps_dispute/gps_dispute_screen.dart';
import '../support/contact_support_screen.dart';

/// How often this screen re-fetches ride status — same interval and
/// same "no push channel exists" rationale as `RideStatusScreen` (the
/// customer-side equivalent).
const Duration _statusPollInterval = Duration(seconds: 4);

const Map<String, String> _statusLabels = {
  'ACCEPTED': 'Head to pickup',
  'ARRIVED': 'Waiting for the customer',
  'STARTED': 'Ride in progress',
  'COMPLETED': 'Ride completed',
  'CANCELLED': 'Ride cancelled',
  'CLOSED': 'Ride completed',
};

/// One icon per status, purely decorative next to [_statusLabels] —
/// same "status reads at a glance" pass as `RideStatusScreen` (Phase 5
/// of the redesign, "Active ride experience", 2026-09-08).
const Map<String, IconData> _statusIcons = {
  'ACCEPTED': Icons.directions_car_outlined,
  'ARRIVED': Icons.place_outlined,
  'STARTED': Icons.navigation_outlined,
  'COMPLETED': Icons.check_circle_outline,
  'CANCELLED': Icons.cancel_outlined,
  'CLOSED': Icons.check_circle_outline,
};

/// Sarthi (driver) ride execution — build order steps 5 and 6
/// (docs/16-mobile/mobile-app-implementation-plan.md §5.4). Pushed by
/// [SarthiHomeScreen] the moment a ride offer is accepted; polls
/// `GET /api/v1/rides/{ride_id}` and shows the action appropriate to
/// the current status: Mark Arrived (ACCEPTED, GPS-gated), enter the
/// customer's OTP to Start (ARRIVED), Complete (STARTED, GPS-gated).
/// While ACCEPTED, a Cancel action is also offered — driver
/// cancellation (§20) is state-machines.md §13's ACCEPTED-only
/// transition, deliberately excluding ARRIVED (confirmed by reading
/// `RideService.driver_cancel_ride()` directly), so it does not appear
/// once the driver has already marked arrival. Also (build order step
/// 8, while the ride isn't terminal) an SOS action in the AppBar
/// (BR-112, api-contracts.md §41) and, always, a Contact Support link
/// pre-filled with this ride's id (api-contracts.md §44) — the same
/// two additions `RideStatusScreen` gets, since BR-112 requires SOS
/// access for both roles.
///
/// Shows a static pickup/destination map (`RouteMapPreview`,
/// 2026-09-07, MapTiler map rendering).
///
/// Deliberately NOT included, flagged rather than silently skipped:
/// - **Turn-by-turn navigation.** A real routing/directions API is a
///   separate need from the tile-rendering credential this app now
///   has (MapTiler Cloud renders map imagery; it doesn't compute a
///   route) — this screen shows pickup/destination as pins, not a
///   driving route, and does not open an external navigation app
///   either (a real, deliberate scope line, not an oversight).
/// - **Cash payment confirmation.** api-contracts.md §33 documents
///   `POST .../cash-payment/confirm` as a *possible future* shape
///   ("Not built today; kept here as the corrected target shape") —
///   verified 2026-08-31 by grepping the entire backend source: no
///   such route exists anywhere. There is nothing this screen could
///   call, so it shows none.
/// - **Pickup/destination-change handling.** §23/§25-26 exist at the
///   API level but are a genuinely separate, multi-actor async flow
///   (customer requests → driver decides → customer confirms) — not
///   folded into this screen; still open for a later increment.
class RideExecutionScreen extends StatefulWidget {
  const RideExecutionScreen({required this.rideId, super.key});

  final String rideId;

  @override
  State<RideExecutionScreen> createState() => _RideExecutionScreenState();
}

class _RideExecutionScreenState extends State<RideExecutionScreen> {
  Timer? _pollTimer;
  RideStatusDetail? _ride;
  String? _loadErrorMessage;
  bool _isBusy = false;
  String? _actionErrorMessage;
  bool _isCancelling = false;
  final _otpController = TextEditingController();
  bool _isSendingSos = false;
  String? _sosMessage;
  String? _sosErrorMessage;

  @override
  void initState() {
    super.initState();
    unawaited(_fetchOnce());
    _pollTimer = Timer.periodic(
      _statusPollInterval,
      (_) => unawaited(_fetchOnce()),
    );
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _fetchOnce() async {
    final api = context.read<RideApi>();
    try {
      final ride = await api.getRide(widget.rideId);
      if (!mounted) return;
      setState(() {
        _ride = ride;
        _loadErrorMessage = null;
      });
      if (ride.isTerminal) {
        _pollTimer?.cancel();
      }
    } on ApiException catch (error) {
      // Surfaced, same reasoning as RideStatusScreen — a driver mid-ride
      // needs to know a status poll is failing, not just see a stale
      // screen.
      if (mounted) setState(() => _loadErrorMessage = error.message);
    }
  }

  /// `GPS_VERIFICATION_FAILED` (ADR-0032/ADR-0074) carries the dispute
  /// this same failed call just opened — pushes [GpsDisputeScreen]
  /// straight to it instead of just showing the error text, same as
  /// every other error would. Returns `true` if it handled the error
  /// this way (caller should not also set `_actionErrorMessage`).
  Future<bool> _handleGpsDisputeIfAny(ApiException error) async {
    final disputeId = error.details?['dispute_id'] as String?;
    if (error.code != 'GPS_VERIFICATION_FAILED' || disputeId == null) {
      return false;
    }
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            GpsDisputeScreen(rideId: widget.rideId, disputeId: disputeId),
      ),
    );
    if (mounted) await _fetchOnce();
    return true;
  }

  Future<void> _markArrived() async {
    setState(() {
      _isBusy = true;
      _actionErrorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      final position = await Geolocator.getCurrentPosition();
      if (!mounted) return;
      await api.markArrived(
        widget.rideId,
        latitude: position.latitude,
        longitude: position.longitude,
      );
      if (mounted) await _fetchOnce();
    } on ApiException catch (error) {
      if (!mounted) return;
      final handled = await _handleGpsDisputeIfAny(error);
      if (!handled && mounted) {
        setState(() => _actionErrorMessage = error.message);
      }
    } on Object catch (error) {
      // Geolocator itself throwing (permission revoked mid-session,
      // location services off) — surfaced the same as a backend error;
      // this is a deliberate, one-off driver action, not a background
      // best-effort tick like the location-update timer.
      if (mounted) {
        setState(
          () => _actionErrorMessage = 'Could not get your location: $error',
        );
      }
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _startRide() async {
    final otp = _otpController.text.trim();
    if (otp.isEmpty) {
      setState(
        () => _actionErrorMessage = 'Enter the code the customer gives you.',
      );
      return;
    }
    setState(() {
      _isBusy = true;
      _actionErrorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      await api.startRide(widget.rideId, otp: otp);
      if (mounted) await _fetchOnce();
    } on ApiException catch (error) {
      if (mounted) setState(() => _actionErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _completeRide() async {
    setState(() {
      _isBusy = true;
      _actionErrorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      final position = await Geolocator.getCurrentPosition();
      if (!mounted) return;
      await api.completeRide(
        widget.rideId,
        latitude: position.latitude,
        longitude: position.longitude,
      );
      if (mounted) await _fetchOnce();
    } on ApiException catch (error) {
      if (!mounted) return;
      final handled = await _handleGpsDisputeIfAny(error);
      if (!handled && mounted) {
        setState(() => _actionErrorMessage = error.message);
      }
    } on Object catch (error) {
      if (mounted) {
        setState(
          () => _actionErrorMessage = 'Could not get your location: $error',
        );
      }
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  /// SOS (BR-112, api-contracts.md §41) — same rationale and gating
  /// (offered while the ride isn't terminal) as `RideStatusScreen`'s
  /// own `_triggerSos()`, the customer-side equivalent.
  Future<void> _triggerSos() async {
    final incidentType = await showSosDialog(context);
    if (incidentType == null || !mounted) return;

    setState(() {
      _isSendingSos = true;
      _sosErrorMessage = null;
      _sosMessage = null;
    });
    final api = context.read<SafetyApi>();
    try {
      final position = await Geolocator.getCurrentPosition();
      if (!mounted) return;
      await api.triggerSos(
        widget.rideId,
        incidentType: incidentType,
        latitude: position.latitude,
        longitude: position.longitude,
      );
      if (mounted) {
        setState(
          () => _sosMessage = 'VISTAAR\'s safety team has been notified.',
        );
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _sosErrorMessage = error.message);
    } on Object catch (error) {
      if (mounted) {
        setState(
          () => _sosErrorMessage = 'Could not get your location: $error',
        );
      }
    } finally {
      if (mounted) setState(() => _isSendingSos = false);
    }
  }

  Future<void> _cancelRide() async {
    final reason = await showCancelReasonDialog(
      context,
      title: 'Cancel this ride?',
    );
    if (reason == null || !mounted) return;

    setState(() {
      _isCancelling = true;
      _actionErrorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      await api.driverCancelRide(widget.rideId, reason: reason);
      if (mounted) await _fetchOnce();
    } on ApiException catch (error) {
      if (mounted) setState(() => _actionErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isCancelling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ride = _ride;
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Your Ride'),
        backgroundColor: Theme.of(context).colorScheme.surface.withValues(alpha: 0.9),
        elevation: 0,
        actions: [
          if (ride != null && !ride.isTerminal)
            IconButton(
              tooltip: 'SOS',
              icon: Icon(Icons.sos, color: Theme.of(context).colorScheme.error),
              onPressed: _isSendingSos ? null : _triggerSos,
            ),
        ],
      ),
      body: ride == null
          ? Padding(
              padding: const EdgeInsets.all(VistaarSpacing.md),
              child: _loadErrorMessage != null
                  ? ErrorView(message: _loadErrorMessage!)
                  : const LoadingView(),
            )
          : _buildRideDetail(context, ride),
    );
  }

  /// Map-first (Rapido-Captain-benchmarked redesign, 2026-09-08 —
  /// "make the map the primary visual area"): the route fills the
  /// whole screen behind a single bottom panel, which shows status,
  /// pickup/destination, fare, and — per the brief's own explicit
  /// instruction — **only the single most important next action**
  /// (Mark Arrived, then Start Ride, then Complete Ride), never
  /// multiple competing primary buttons. Cancel (ACCEPTED only) is
  /// demoted to a plain text action beneath it, not a second button of
  /// comparable weight.
  Widget _buildRideDetail(BuildContext context, RideStatusDetail ride) {
    return Stack(
      children: [
        Positioned.fill(
          child: RouteMapPreview(
            pickup: ride.pickup,
            destination: ride.destination,
            height: double.infinity,
          ),
        ),
        Align(
          alignment: Alignment.bottomCenter,
          child: _buildBottomPanel(context, ride),
        ),
      ],
    );
  }

  Widget _buildBottomPanel(BuildContext context, RideStatusDetail ride) {
    final theme = Theme.of(context);
    final fare = ride.fare;
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
        child: SingleChildScrollView(
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
              // Cross-fades on an actual status change (Phase 10 of the
              // redesign, "Animations", 2026-09-08) — same treatment
              // and rationale as RideStatusScreen's own status header.
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 250),
                child: Row(
                  key: ValueKey(ride.status),
                  children: [
                    Icon(
                      _statusIcons[ride.status] ?? Icons.info_outline,
                      color: theme.colorScheme.primary,
                      size: 24,
                    ),
                    const SizedBox(width: VistaarSpacing.sm),
                    Expanded(
                      child: Text(
                        _statusLabels[ride.status] ?? ride.status,
                        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                      ),
                    ),
                    if (fare != null)
                      Flexible(
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerRight,
                          child: Text(
                            '${fare.currency} ${fare.total.toStringAsFixed(2)}',
                            // Golden yellow — "fare/earning emphasis"
                            // per the owner's brand brief.
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.tertiary,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: VistaarSpacing.sm),
              Row(
                children: [
                  Icon(Icons.trip_origin, size: 16, color: theme.colorScheme.primary),
                  const SizedBox(width: VistaarSpacing.xs),
                  Expanded(
                    child: Text(
                      '${ride.pickup.latitude.toStringAsFixed(5)}, '
                      '${ride.pickup.longitude.toStringAsFixed(5)}',
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: VistaarSpacing.xs),
              Row(
                children: [
                  Icon(Icons.place_outlined, size: 16, color: theme.colorScheme.primary),
                  const SizedBox(width: VistaarSpacing.xs),
                  Expanded(
                    child: Text(
                      '${ride.destination.latitude.toStringAsFixed(5)}, '
                      '${ride.destination.longitude.toStringAsFixed(5)}',
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
              if (_actionErrorMessage != null) ...[
                const SizedBox(height: VistaarSpacing.sm),
                Text(
                  _actionErrorMessage!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ],
              if (_sosMessage != null) ...[
                const SizedBox(height: VistaarSpacing.sm),
                Text(_sosMessage!, textAlign: TextAlign.center),
              ],
              if (_sosErrorMessage != null) ...[
                const SizedBox(height: VistaarSpacing.sm),
                Text(
                  _sosErrorMessage!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ],
              if (_loadErrorMessage != null) ...[
                const SizedBox(height: VistaarSpacing.sm),
                Text(
                  _loadErrorMessage!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ],
              const SizedBox(height: VistaarSpacing.md),
              ..._buildActionArea(context, ride),
              TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => ContactSupportScreen(rideId: widget.rideId),
                  ),
                ),
                child: const Text('Contact Support'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// The single most important next action for the current status,
  /// per the owner's brief ("REACHED PICKUP then START RIDE then
  /// COMPLETE RIDE... avoid showing multiple competing primary
  /// buttons"). Cancel (ACCEPTED only) is a plain text action beneath
  /// the primary one, never a second button of comparable weight.
  List<Widget> _buildActionArea(BuildContext context, RideStatusDetail ride) {
    switch (ride.status) {
      case 'ACCEPTED':
        return [
          PrimaryButton(
            label: 'Mark Arrived',
            isLoading: _isBusy,
            height: 56,
            onPressed: _markArrived,
          ),
          Align(
            alignment: Alignment.center,
            child: TextButton(
              onPressed: _isCancelling ? null : _cancelRide,
              child: _isCancelling
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    )
                  : const Text('Cancel'),
            ),
          ),
        ];
      case 'ARRIVED':
        return [
          TextField(
            controller: _otpController,
            keyboardType: TextInputType.number,
            maxLength: 6,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: const InputDecoration(
              labelText: "Customer's pickup code",
              border: OutlineInputBorder(),
              counterText: '',
            ),
          ),
          const SizedBox(height: VistaarSpacing.sm),
          PrimaryButton(
            label: 'Start Ride',
            isLoading: _isBusy,
            height: 56,
            onPressed: _startRide,
          ),
        ];
      case 'STARTED':
        return [
          PrimaryButton(
            label: 'Complete Ride',
            isLoading: _isBusy,
            height: 56,
            onPressed: _completeRide,
          ),
        ];
      case 'COMPLETED':
      case 'CLOSED':
      case 'CANCELLED':
        return [
          PrimaryButton(
            label: 'Done',
            height: 56,
            onPressed: () => Navigator.of(context).pop(),
          ),
        ];
      default:
        return const [];
    }
  }
}
