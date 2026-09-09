import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/ride_api.dart';
import '../../shared/design/state_views.dart';
import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_spacing.dart';
import 'ride_status_screen.dart';

/// My Scheduled Rides — build order step 10
/// (docs/16-mobile/mobile-app-implementation-plan.md §4.10, ADR-0057).
/// `GET /api/v1/rides?status=SCHEDULED` (api-contracts.md §12.1) — the
/// endpoint added specifically to make Schedule a Ride usable: without
/// it, a customer could only ever see a scheduled ride they'd just
/// booked in that same session, with no way to browse it again later.
/// Tapping a ride opens the same [RideStatusScreen] every other ride
/// status view already uses (it already handles SCHEDULED — see that
/// screen's own status label/cancel gating), including Cancel Ride,
/// which for a SCHEDULED ride applies BR-135's ≥3h/₹0-<3h/₹30 rule
/// instead of the post-acceptance one.
class ScheduledRidesScreen extends StatefulWidget {
  const ScheduledRidesScreen({super.key});

  @override
  State<ScheduledRidesScreen> createState() => _ScheduledRidesScreenState();
}

class _ScheduledRidesScreenState extends State<ScheduledRidesScreen> {
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
      final page = await api.listMyRides(status: 'SCHEDULED');
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
      final page = await api.listMyRides(status: 'SCHEDULED', page: _nextPage);
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
    // The ride may have just been cancelled on that screen — refresh so
    // it drops off this list.
    if (mounted) unawaited(_loadInitial());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scheduled Rides')),
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
                        icon: Icons.event_outlined,
                        title: 'No scheduled rides yet.',
                        subtitle: 'Schedule a ride for later from Book a Ride.',
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

  Widget _buildTile(BuildContext context, RideListItem item) {
    final theme = Theme.of(context);
    final scheduledFor = item.scheduledFor;
    return VistaarCard(
      onTap: () => _openRide(item.rideId),
      child: Row(
        children: [
          CircleAvatar(
            radius: 20,
            backgroundColor: theme.colorScheme.primaryContainer,
            child: Icon(
              Icons.event_outlined,
              color: theme.colorScheme.onPrimaryContainer,
            ),
          ),
          const SizedBox(width: VistaarSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  scheduledFor == null
                      ? 'Scheduled ride'
                      : scheduledFor.toLocal().toString().split('.').first,
                  style: theme.textTheme.titleMedium,
                ),
                Text(
                  'Pickup ${item.pickup.latitude.toStringAsFixed(4)}, '
                  '${item.pickup.longitude.toStringAsFixed(4)}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          Icon(Icons.chevron_right, color: theme.colorScheme.onSurfaceVariant),
        ],
      ),
    );
  }
}
