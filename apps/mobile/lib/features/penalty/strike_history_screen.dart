import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/driver_api.dart';

/// My Strikes — Sarthi-side, built 2026-09-04 (ADR-0073) to close the
/// next highest-priority gap after the User-side profile/ride-history/
/// promotions/referrals screens: `GET /api/v1/drivers/me/strikes` (the
/// self-service counterpart to the admin-only Driver Strike History,
/// api-contracts.md §46.18) existed at neither the HTTP nor mobile
/// layer before this ADR — a Sarthi could see their bare `strikes`
/// count (already shown on the onboarding screen's status summary) but
/// never which ride, or why. This screen shows the detail behind that
/// count; it does not add a dispute/appeal capability, since none
/// exists anywhere in the backend either (see that ADR's own scope
/// note).
class StrikeHistoryScreen extends StatefulWidget {
  const StrikeHistoryScreen({super.key});

  @override
  State<StrikeHistoryScreen> createState() => _StrikeHistoryScreenState();
}

class _StrikeHistoryScreenState extends State<StrikeHistoryScreen> {
  final List<Strike> _items = [];
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
    final api = context.read<DriverApi>();
    try {
      final page = await api.listStrikes();
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
    final api = context.read<DriverApi>();
    try {
      final page = await api.listStrikes(page: _nextPage);
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Strikes')),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _loadInitial,
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    if (_items.isEmpty && _errorMessage == null)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 24),
                        child: Text(
                          'No strikes on your record.',
                          textAlign: TextAlign.center,
                        ),
                      )
                    else
                      for (final strike in _items) _buildTile(context, strike),
                    if (_errorMessage != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _errorMessage!,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    if (_hasMore) ...[
                      const SizedBox(height: 12),
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

  Widget _buildTile(BuildContext context, Strike strike) {
    return Card(
      child: ListTile(
        leading: Icon(
          Icons.warning_amber_outlined,
          color: Theme.of(context).colorScheme.error,
        ),
        title: Text(strike.reason),
        subtitle: Text(
          strike.createdAt.toLocal().toString().split('.').first,
        ),
      ),
    );
  }
}
