import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/ride_api.dart';
import '../../core/api/safety_api.dart';
import '../../shared/design/state_views.dart';
import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_colors.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/widgets/cancel_reason_dialog.dart';
import '../../shared/widgets/change_destination_dialog.dart';
import '../../shared/widgets/change_pickup_dialog.dart';
import '../../shared/widgets/primary_button.dart';
import '../../shared/widgets/sos_dialog.dart';
import '../../shared/widgets/route_map_preview.dart';
import '../gps_dispute/gps_dispute_screen.dart';
import '../support/contact_support_screen.dart';

/// Destination-change cases that carry a fare impact (api-contracts.md
/// §25, `DestinationChangeCase`) — see `_changeDestination()`'s own doc
/// comment for why this app can't offer a confirm step for these yet.
const Set<String> _fareChangingDestinationCases = {
  'BEYOND_ORIGINAL',
  'DIFFERENT_ROUTE',
};

/// Statuses from which a customer may still cancel (api-contracts.md
/// §19 — SCHEDULED/SEARCHING/ACCEPTED/ARRIVED (SCHEDULED added by
/// ADR-0057); STARTED is deliberately excluded, same as the backend's
/// own `RideService.cancel_ride()` gate).
const Set<String> _cancellableStatuses = {
  'SCHEDULED',
  'SEARCHING',
  'ACCEPTED',
  'ARRIVED',
};

/// How often this screen re-fetches ride status. There is no push/
/// websocket channel (api-contracts.md §14's documented WebSocket has no
/// server behind it anywhere in this codebase — verified against the
/// live backend, not just the doc's own "TBD" host note) — polling is
/// the only mechanism, same rationale as the Sarthi offer/location
/// timers.
const Duration _statusPollInterval = Duration(seconds: 4);

const Map<String, String> _statusLabels = {
  'SCHEDULED': 'Ride scheduled',
  'SEARCHING': 'Looking for a driver…',
  'ACCEPTED': 'Driver is on the way',
  'ARRIVED': 'Your driver has arrived',
  'STARTED': 'Ride in progress',
  'COMPLETED': 'Ride completed',
  'CANCELLED': 'Ride cancelled',
  'CLOSED': 'Ride closed',
};

/// One icon per status, purely decorative next to [_statusLabels] —
/// Phase 5 of the redesign ("Active ride experience", 2026-09-08), so
/// the current stage of a ride reads at a glance instead of as plain
/// text alone.
const Map<String, IconData> _statusIcons = {
  'SCHEDULED': Icons.event_outlined,
  'SEARCHING': Icons.search,
  'ACCEPTED': Icons.directions_car_outlined,
  'ARRIVED': Icons.place_outlined,
  'STARTED': Icons.navigation_outlined,
  'COMPLETED': Icons.check_circle_outline,
  'CANCELLED': Icons.cancel_outlined,
  'CLOSED': Icons.cancel_outlined,
};

/// Ride Status / Tracking — build order steps 4 and 6
/// (docs/16-mobile/mobile-app-implementation-plan.md §4.2, §4.3, §4.4).
/// Polls `GET /api/v1/rides/{ride_id}` and shows the current status,
/// driver/vehicle info once assigned, fare, (once ARRIVED) the pickup
/// OTP, (while ACCEPTED) a Change Pickup action (api-contracts.md §22,
/// ADR-0056 — a ≤100m change applies immediately, a >100m one is
/// rejected outright with no driver decision or charge, unlike the
/// original >250m PROCEED/PASS design this replaced), (while STARTED) a
/// Change Destination action (api-contracts.md §25 — a free WITHIN_
/// ROUTE change applies immediately; a fare-changing one is rejected by
/// this app itself rather than confirmed blind, see
/// `_changeDestination()`'s own doc comment for the real backend gap
/// behind that), and — while SEARCHING/ACCEPTED/ARRIVED — a Cancel Ride
/// action (api-contracts.md §19). Also (build order step 8, while the
/// ride isn't terminal) an SOS action in the AppBar (BR-112, api-
/// contracts.md §41) and, always, a Contact Support link pre-filled
/// with this ride's id (api-contracts.md §44).
///
/// Shows a static pickup/destination map (`RouteMapPreview`,
/// 2026-09-07, MapTiler map rendering) — **not live driver tracking**,
/// flagged rather than silently implied: verified directly against
/// `apps/backend/src/modules/ride/router.py`, there is no `/tracking`
/// endpoint in the live backend at all (api-contracts.md §14 documents
/// only a route name and an unimplemented WebSocket) — a real backend
/// gap this task does not touch, so there is no driver position to
/// render even though a real maps provider now exists.
///
/// One other thing this screen deliberately does NOT do, flagged rather
/// than silently skipped:
/// - **No "no driver found" retry/increase-fare UI.** api-contracts.md
///   §21 documents `GET .../no-driver-options` and
///   `POST .../fare-increase`; neither exists anywhere in the live
///   backend (verified by grepping the whole backend source, not just
///   this router) — a ride that finds no driver simply stays SEARCHING
///   indefinitely today. This screen shows that honestly rather than
///   inventing retry buttons the backend can't answer.
///
/// Also (ADR-0074, 2026-09-04) polls `GET .../gps-disputes` alongside
/// the ride itself — the only way a customer discovers a GPS dispute
/// exists on their ride at all (unlike the driver, who receives one
/// directly in the error that opened it; see [RideExecutionScreen]).
/// Shows a banner to [GpsDisputeScreen] whenever an OPEN one exists.
class RideStatusScreen extends StatefulWidget {
  const RideStatusScreen({required this.rideId, super.key});

  final String rideId;

  @override
  State<RideStatusScreen> createState() => _RideStatusScreenState();
}

class _RideStatusScreenState extends State<RideStatusScreen> {
  Timer? _pollTimer;
  RideStatusDetail? _ride;
  String? _loadErrorMessage;
  List<GpsDispute> _disputes = const [];
  bool _isRefreshingOtp = false;
  String? _otpErrorMessage;
  String? _revealedOtp;
  bool _isCancelling = false;
  String? _cancelErrorMessage;
  bool _hasCancelled = false;
  CancellationCharge? _cancellationCharge;
  bool _isChangingPickup = false;
  String? _pickupChangeErrorMessage;
  String? _pickupChangeMessage;
  bool _isChangingDestination = false;
  String? _destinationChangeErrorMessage;
  String? _destinationChangeMessage;
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
      // Surfaced, unlike the Sarthi location/offer timers' best-effort
      // swallow — a customer waiting on their own ride's status needs to
      // know a poll is failing, not just silently see a stale screen.
      if (mounted) setState(() => _loadErrorMessage = error.message);
    }

    // Best-effort, not surfaced as an error — a dispute is rare, and a
    // failure here shouldn't hide the ride status this screen already
    // showed. See this screen's own doc comment (ADR-0074).
    try {
      final disputes = await api.listGpsDisputes(widget.rideId);
      if (mounted) setState(() => _disputes = disputes);
    } on ApiException {
      // Swallowed — see above.
    }
  }

  Future<void> _openDispute(String disputeId) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            GpsDisputeScreen(rideId: widget.rideId, disputeId: disputeId),
      ),
    );
    if (mounted) await _fetchOnce();
  }

  Future<void> _cancelRide() async {
    final reason = await showCancelReasonDialog(
      context,
      title: 'Cancel this ride?',
    );
    if (reason == null || !mounted) return;

    setState(() {
      _isCancelling = true;
      _cancelErrorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      final result = await api.cancelRide(widget.rideId, reason: reason);
      if (!mounted) return;
      setState(() {
        _hasCancelled = true;
        _cancellationCharge = result.charge;
      });
      await _fetchOnce();
    } on ApiException catch (error) {
      if (mounted) setState(() => _cancelErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isCancelling = false);
    }
  }

  Future<void> _changePickup() async {
    final coords = await showChangePickupDialog(context);
    if (coords == null || !mounted) return;

    setState(() {
      _isChangingPickup = true;
      _pickupChangeErrorMessage = null;
      _pickupChangeMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      await api.changePickup(
        widget.rideId,
        latitude: coords.$1,
        longitude: coords.$2,
      );
      if (!mounted) return;
      setState(() => _pickupChangeMessage = 'Pickup updated.');
      await _fetchOnce();
    } on ApiException catch (error) {
      // Includes PICKUP_CHANGE_TOO_FAR (ADR-0056) — the backend's own
      // message already tells the customer to cancel and rebook
      // instead, shown as-is rather than adding a second explanation.
      if (mounted) setState(() => _pickupChangeErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isChangingPickup = false);
    }
  }

  /// Destination Change (api-contracts.md §25). WITHIN_ROUTE (no fare
  /// impact, BR-079) applies cleanly. For BEYOND_ORIGINAL/
  /// DIFFERENT_ROUTE, the request response never includes the computed
  /// fare — only confirming does, after the fact — so there is no way
  /// to show the customer the revised fare *before* they'd have to
  /// decide, which BR-082 requires ("Customer sees revised fare →
  /// Customer confirms"). Verified directly against the live router,
  /// not assumed. Rather than build a screen that asks the customer to
  /// confirm a fare change blind, this app immediately rejects that
  /// pending request (`RideApi.rejectDestinationChange()`, always
  /// `confirmed: false`) and tells the customer honestly that this
  /// particular change needs a fare adjustment this app can't preview
  /// yet — the alternative (leaving the request pending) would lock
  /// them out of trying any destination change again, since the
  /// backend allows only one pending request per ride.
  Future<void> _changeDestination() async {
    final coords = await showChangeDestinationDialog(context);
    if (coords == null || !mounted) return;

    setState(() {
      _isChangingDestination = true;
      _destinationChangeErrorMessage = null;
      _destinationChangeMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      final result = await api.changeDestination(
        widget.rideId,
        latitude: coords.$1,
        longitude: coords.$2,
      );
      if (!mounted) return;
      if (_fareChangingDestinationCases.contains(result.caseType)) {
        assert(result.changeRequestId != null);
        await api.rejectDestinationChange(
          widget.rideId,
          changeRequestId: result.changeRequestId!,
        );
        if (!mounted) return;
        setState(() {
          _destinationChangeMessage =
              'This destination needs a fare adjustment that can\'t be '
              'previewed in the app yet — try a closer destination, or '
              'contact support.';
        });
      } else {
        setState(() => _destinationChangeMessage = 'Destination updated.');
      }
      await _fetchOnce();
    } on ApiException catch (error) {
      if (mounted) {
        setState(() => _destinationChangeErrorMessage = error.message);
      }
    } finally {
      if (mounted) setState(() => _isChangingDestination = false);
    }
  }

  /// SOS (BR-112, api-contracts.md §41). Does not gate on ride status —
  /// the backend itself doesn't either, only ownership — but this
  /// screen only offers it while the ride isn't terminal (see
  /// `_buildRideDetail`); triggering it for a CLOSED/CANCELLED ride
  /// serves no purpose.
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

  Future<void> _revealOtp() async {
    setState(() {
      _isRefreshingOtp = true;
      _otpErrorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      final otp = await api.refreshOtp(widget.rideId);
      if (mounted) setState(() => _revealedOtp = otp);
    } on ApiException catch (error) {
      if (mounted) setState(() => _otpErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isRefreshingOtp = false);
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

  /// Map-first (Rapido-benchmarked redesign, 2026-09-08 — "make the map
  /// the primary visual area", same treatment as
  /// [RideExecutionScreen]'s Sarthi-side counterpart): the route fills
  /// the whole screen behind a single scrollable bottom panel carrying
  /// everything else — status, driver/vehicle, fare, and every status-
  /// specific action — in the exact same order and with the exact same
  /// widgets as before this pass, just re-containered.
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
    final driver = ride.driver;
    final vehicle = ride.vehicle;
    final fare = ride.fare;
    return Container(
      width: double.infinity,
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
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
          // Status — the single most important thing on this screen at
          // a glance, per the owner's brief ("where-am-I-going/status"
          // strong visual hierarchy). One Text widget carries the exact
          // label (unchanged from before this pass); the icon beside it
          // is purely decorative, not a second copy of the same text.
          // Cross-fades on an actual status change (Phase 10 of the
          // redesign, "Animations", 2026-09-08) — keyed by `ride.status`
          // so the ~4s poll re-render never re-triggers it while the
          // status is unchanged, only a genuine SEARCHING→ACCEPTED-style
          // transition does.
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 250),
            child: Row(
              key: ValueKey(ride.status),
              children: [
                Icon(
                  _statusIcons[ride.status] ?? Icons.info_outline,
                  color: theme.colorScheme.primary,
                  size: 28,
                ),
                const SizedBox(width: VistaarSpacing.sm),
                Expanded(
                  child: Text(
                    _statusLabels[ride.status] ?? ride.status,
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (ride.status == 'SCHEDULED' && ride.scheduledFor != null) ...[
            const SizedBox(height: VistaarSpacing.sm),
            Text(
              'For ${ride.scheduledFor!.toLocal().toString().split('.').first}',
              textAlign: TextAlign.center,
            ),
          ],
          if (ride.status == 'SEARCHING') ...[
            const SizedBox(height: VistaarSpacing.md),
            const Center(child: CircularProgressIndicator()),
          ],
          for (final dispute in _disputes.where((d) => d.isOpen)) ...[
            const SizedBox(height: VistaarSpacing.md),
            _buildDisputeBanner(context, dispute),
          ],
          if (driver != null || vehicle != null) ...[
            const SizedBox(height: VistaarSpacing.md),
            VistaarCard(
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 24,
                    backgroundColor: theme.colorScheme.primaryContainer,
                    child: Icon(
                      Icons.person_outline,
                      color: theme.colorScheme.onPrimaryContainer,
                    ),
                  ),
                  const SizedBox(width: VistaarSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (driver != null)
                          Text(driver.fullName, style: theme.textTheme.titleMedium),
                        if (vehicle != null)
                          Text(
                            '${vehicle.make} ${vehicle.model} · '
                            '${vehicle.registrationNumber}',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (fare != null) ...[
            const SizedBox(height: VistaarSpacing.md),
            VistaarCard(
              child: Row(
                children: [
                  Icon(
                    Icons.currency_rupee,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: VistaarSpacing.sm),
                  Text('Fare', style: theme.textTheme.titleMedium),
                  const Spacer(),
                  // A large fare figure at a narrow width or a large
                  // accessibility text scale must shrink to fit rather
                  // than overflow the card or truncate a digit off a
                  // money amount (verified directly — a real overflow
                  // at 320dp width, fixed here, not assumed).
                  Flexible(
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerRight,
                      child: Text(
                        '${fare.currency} ${fare.total.toStringAsFixed(2)}',
                        // Golden yellow — "fare/earning emphasis" per
                        // the owner's brand brief.
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
          ],
          if (ride.status == 'ARRIVED') ...[
            const SizedBox(height: VistaarSpacing.lg),
            if (_revealedOtp != null)
              VistaarCard(
                child: Column(
                  children: [
                    Text(
                      'Pickup code',
                      style: theme.textTheme.labelLarge?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: VistaarSpacing.xs),
                    Text(
                      'Pickup code: $_revealedOtp',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineMedium,
                    ),
                  ],
                ),
              )
            else
              PrimaryButton(
                label: 'Show pickup code',
                isLoading: _isRefreshingOtp,
                onPressed: _revealOtp,
              ),
            if (_otpErrorMessage != null) ...[
              const SizedBox(height: VistaarSpacing.sm),
              Text(
                _otpErrorMessage!,
                textAlign: TextAlign.center,
                style: TextStyle(color: theme.colorScheme.error),
              ),
            ],
          ],
          if (ride.status == 'ACCEPTED') ...[
            const SizedBox(height: VistaarSpacing.lg),
            OutlinedButton(
              onPressed: _isChangingPickup ? null : _changePickup,
              child: _isChangingPickup
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    )
                  : const Text('Change Pickup'),
            ),
            if (_pickupChangeMessage != null) ...[
              const SizedBox(height: VistaarSpacing.sm),
              Text(_pickupChangeMessage!, textAlign: TextAlign.center),
            ],
            if (_pickupChangeErrorMessage != null) ...[
              const SizedBox(height: VistaarSpacing.sm),
              Text(
                _pickupChangeErrorMessage!,
                textAlign: TextAlign.center,
                style: TextStyle(color: theme.colorScheme.error),
              ),
            ],
          ],
          if (ride.status == 'STARTED') ...[
            const SizedBox(height: VistaarSpacing.lg),
            OutlinedButton(
              onPressed: _isChangingDestination ? null : _changeDestination,
              child: _isChangingDestination
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    )
                  : const Text('Change Destination'),
            ),
            if (_destinationChangeMessage != null) ...[
              const SizedBox(height: VistaarSpacing.sm),
              Text(_destinationChangeMessage!, textAlign: TextAlign.center),
            ],
            if (_destinationChangeErrorMessage != null) ...[
              const SizedBox(height: VistaarSpacing.sm),
              Text(
                _destinationChangeErrorMessage!,
                textAlign: TextAlign.center,
                style: TextStyle(color: theme.colorScheme.error),
              ),
            ],
          ],
          if (_hasCancelled) ...[
            const SizedBox(height: VistaarSpacing.md),
            Text(
              _cancellationCharge != null && _cancellationCharge!.amount > 0
                  ? 'Cancellation charge: ${_cancellationCharge!.currency} '
                        '${_cancellationCharge!.amount.toStringAsFixed(2)}'
                  : 'No cancellation charge.',
              textAlign: TextAlign.center,
            ),
          ] else if (_cancellableStatuses.contains(ride.status)) ...[
            const SizedBox(height: VistaarSpacing.lg),
            OutlinedButton(
              onPressed: _isCancelling ? null : _cancelRide,
              child: _isCancelling
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    )
                  : const Text('Cancel Ride'),
            ),
          ],
          if (_cancelErrorMessage != null) ...[
            const SizedBox(height: VistaarSpacing.sm),
            Text(
              _cancelErrorMessage!,
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
            const SizedBox(height: VistaarSpacing.md),
            Text(
              _loadErrorMessage!,
              textAlign: TextAlign.center,
              style: TextStyle(color: theme.colorScheme.error),
            ),
          ],
          const SizedBox(height: VistaarSpacing.md),
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

  Widget _buildDisputeBanner(BuildContext context, GpsDispute dispute) {
    return Container(
      padding: const EdgeInsets.all(VistaarSpacing.md),
      decoration: BoxDecoration(
        color: VistaarColors.warningContainer,
        borderRadius: BorderRadius.circular(VistaarRadius.control),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_outlined, color: VistaarColors.onWarningContainer),
          const SizedBox(width: VistaarSpacing.sm),
          Expanded(
            child: Text(
              'A GPS dispute is open on this ride — evidence needed.',
              style: TextStyle(color: VistaarColors.onWarningContainer),
            ),
          ),
          TextButton(
            onPressed: () => _openDispute(dispute.disputeId),
            child: const Text('View'),
          ),
        ],
      ),
    );
  }
}
