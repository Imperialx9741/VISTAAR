import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/ride_api.dart';
import '../../shared/design/state_views.dart';
import '../../shared/design/status_chip.dart';
import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_spacing.dart';
import 'ride_status_screen.dart';

/// My Ride History — the User-side counterpart to
/// [ScheduledRidesScreen] (which only ever shows `status=SCHEDULED`):
/// this screen calls the exact same `GET /api/v1/rides`
/// (api-contracts.md §12.1) with no `status` filter, so every ride the
/// customer has ever taken — completed, cancelled, in-progress, or
/// scheduled — shows up here, newest first. Tapping a ride opens the
/// same [RideStatusScreen] every other ride status view already uses.
class RideHistoryScreen extends StatefulWidget {
  const RideHistoryScreen({super.key});

  @override
  State<RideHistoryScreen> createState() => _RideHistoryScreenState();
}

class _RideHistoryScreenState extends State<RideHistoryScreen> {
  final List<RideListItem> _items = [];
  int _nextPage = 1;
  bool _hasMore = true;
  bool _isLoading = false;
  bool _isLoadingMore = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    unawaited(_loadInitial());
  }

  Future<void> _loadInitial() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      final page = await api.listMyRides();
      if (!mounted) return;
      setState(() {
        _items
          ..clear()
          ..addAll(page.items);
        _nextPage = page.page + 1;
        _hasMore = page.hasMore;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _loadMore() async {
    setState(() {
      _isLoadingMore = true;
      _errorMessage = null;
    });
    final api = context.read<RideApi>();
    try {
      final page = await api.listMyRides(page: _nextPage);
      if (!mounted) return;
      setState(() {
        _items.addAll(page.items);
        _nextPage = page.page + 1;
        _hasMore = page.hasMore;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoadingMore = false);
    }
  }

  Future<void> _openRide(String rideId) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => RideStatusScreen(rideId: rideId)),
    );
  }

  StatusTone _statusTone(String status) {
    switch (status) {
      case 'COMPLETED':
      case 'CLOSED':
        return StatusTone.success;
      case 'CANCELLED':
        return StatusTone.danger;
      default:
        return StatusTone.neutral;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ride History')),
      body: SafeArea(
        child: _isLoading
            ? const LoadingView()
            : RefreshIndicator(
                onRefresh: _loadInitial,
                child: ListView(
                  padding: const EdgeInsets.all(VistaarSpacing.md),
                  children: [
                    if (_items.isEmpty && _errorMessage == null)
                      const EmptyView(
                        icon: Icons.receipt_long_outlined,
                        title: 'No rides yet.',
                        subtitle: 'Your ride history will show up here.',
                      )
                    else
                      for (final item in _items) ...[
                        _buildTile(context, item),
                        const SizedBox(height: VistaarSpacing.sm),
                      ],
                    if (_errorMessage != null) ...[
                      const SizedBox(height: VistaarSpacing.sm),
                      Text(
                        _errorMessage!,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    if (_hasMore) ...[
                      const SizedBox(height: VistaarSpacing.sm),
                      Center(
                        child: _isLoadingMore
                            ? const Padding(
                                padding: EdgeInsets.all(12),
                                child: CircularProgressIndicator(
                                  strokeWidth: 2.5,
                                ),
                              )
                            : TextButton(
                                onPressed: _loadMore,
                                child: const Text('Load more'),
                              ),
                      ),
                    ],
                  ],
                ),
              ),
      ),
    );
  }

  /// Rapido-style route row (2026-09-08 redesign): a pickup/destination
  /// dot-and-line marker in place of the old plain two-line text block,
  /// same visual language Rapido uses for its own ride-history cards.
  ///
  /// Deliberately still showing raw coordinates, not a fare or a
  /// human-readable "12 Sep, 4:30 PM · ₹186"-style line the way Rapido's
  /// own cards do — `GET /api/v1/rides` (`_ride_list_item_data`,
  /// `modules/ride/router.py`) is documented there as *deliberately*
  /// lighter than the single-ride detail endpoint: no fare, no
  /// `created_at`, no address, only `scheduled_for` (present only for
  /// still-scheduled rides). Flagging this as a real backend gap rather
  /// than inventing a date or fare figure the API never actually sends
  /// — per the owner's explicit "do not invent unavailable backend
  /// information" instruction. A future backend change adding those
  /// fields to this endpoint is what would let this row show them for
  /// real.
  Widget _buildTile(BuildContext context, RideListItem item) {
    final theme = Theme.of(context);
    final scheduledFor = item.scheduledFor;
    return VistaarCard(
      onTap: () => _openRide(item.rideId),
      // IntrinsicHeight — `_buildRouteMarker`'s connecting line uses
      // `Expanded` to stretch between the two dots, which needs a
      // bounded height to size against; without this wrapper the Row
      // sits in this screen's `ListView` with no explicit height at
      // all, and `Expanded` throws (real bug, caught by
      // ride_history_screen_test.dart before it shipped, not shipped
      // silently).
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildRouteMarker(context),
            const SizedBox(width: VistaarSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (scheduledFor != null) ...[
                    Text(
                      scheduledFor.toLocal().toString().split('.').first,
                      style: theme.textTheme.labelMedium?.copyWith(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: VistaarSpacing.xs),
                  ],
                  Text(
                    '${item.pickup.latitude.toStringAsFixed(4)}, '
                    '${item.pickup.longitude.toStringAsFixed(4)}',
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: VistaarSpacing.sm),
                  Text(
                    '${item.destination.latitude.toStringAsFixed(4)}, '
                    '${item.destination.longitude.toStringAsFixed(4)}',
                    style: theme.textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
            const SizedBox(width: VistaarSpacing.sm),
            StatusChip(label: item.status, tone: _statusTone(item.status)),
          ],
        ),
      ),
    );
  }

  /// Pickup dot → dotted line → destination pin, the same route-marker
  /// language Rapido's ride-history/active-ride cards use, built from
  /// plain `Container`/`Icon` widgets — no new asset or package needed.
  Widget _buildRouteMarker(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      width: 12,
      child: Column(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: scheme.primary, width: 2),
            ),
          ),
          Expanded(
            child: Container(
              width: 2,
              margin: const EdgeInsets.symmetric(vertical: 2),
              color: scheme.outlineVariant,
            ),
          ),
          Icon(Icons.location_on, size: 14, color: scheme.error),
        ],
      ),
    );
  }
}
