import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/wallet_api.dart';
import '../../shared/design/state_views.dart';
import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_colors.dart';
import '../../shared/design/vistaar_spacing.dart';
import 'recharge_wallet_screen.dart';

/// Sarthi (driver) Wallet — build order step 7
/// (docs/16-mobile/mobile-app-implementation-plan.md §5.5). Shows the
/// current balance and a paginated transaction ledger
/// (api-contracts.md §34).
///
/// Driver-side only, flagged rather than silently assumed complete:
/// there is no customer-facing wallet/outstanding-charges endpoint
/// anywhere in the backend today (verified against
/// `modules/wallet/router.py` and `modules/customer/router.py` — see
/// `WalletApi`'s own doc comment, GAP-6) — nothing exists yet for a
/// User-side wallet screen to call.
class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen> {
  Wallet? _wallet;
  final List<WalletTransaction> _transactions = [];
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
    final api = context.read<WalletApi>();
    try {
      final results = await Future.wait([
        api.getWallet(),
        api.listTransactions(),
      ]);
      if (!mounted) return;
      final wallet = results[0] as Wallet;
      final page = results[1] as WalletTransactionPage;
      setState(() {
        _wallet = wallet;
        _transactions
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
    final api = context.read<WalletApi>();
    try {
      final page = await api.listTransactions(page: _nextPage);
      if (!mounted) return;
      setState(() {
        _transactions.addAll(page.items);
        _nextPage = page.page + 1;
        _hasMore = page.hasMore;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoadingMore = false);
    }
  }

  /// api-contracts.md §35 / ADR-0060 — pushes [RechargeWalletScreen] and
  /// refreshes this screen's balance/transactions on return if it
  /// popped with a non-null result (a successful recharge); a `null`
  /// pop (dismissed/failed before completion) leaves this screen
  /// untouched.
  Future<void> _openRecharge() async {
    final result = await Navigator.of(
      context,
    ).push<double>(MaterialPageRoute(builder: (_) => const RechargeWalletScreen()));
    if (result != null && mounted) {
      await _loadInitial();
    }
  }

  String _humanizeType(String type) {
    final words = type
        .split('_')
        .map((w) => w.isEmpty ? w : '${w[0]}${w.substring(1).toLowerCase()}');
    return words.join(' ');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Wallet')),
      body: SafeArea(
        child: _isLoading
            ? const LoadingView()
            : _wallet == null
            ? ErrorView(message: _errorMessage ?? 'Could not load your wallet.')
            : RefreshIndicator(
                onRefresh: _loadInitial,
                child: ListView(
                  padding: const EdgeInsets.all(VistaarSpacing.md),
                  children: [
                    _buildBalanceCard(context, _wallet!),
                    const SizedBox(height: VistaarSpacing.lg),
                    Text(
                      'Transactions',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: VistaarSpacing.sm),
                    if (_transactions.isEmpty)
                      const EmptyView(
                        icon: Icons.receipt_long_outlined,
                        title: 'No transactions yet.',
                      )
                    else
                      ..._transactions.map(
                        (t) => _buildTransactionTile(context, t),
                      ),
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

  Widget _buildBalanceCard(BuildContext context, Wallet wallet) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(VistaarSpacing.lg),
      decoration: BoxDecoration(
        color: theme.colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(VistaarRadius.surface),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.account_balance_wallet_outlined,
                color: theme.colorScheme.onPrimaryContainer,
              ),
              const SizedBox(width: VistaarSpacing.sm),
              Flexible(
                child: Text(
                  'Available Balance',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onPrimaryContainer,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: VistaarSpacing.xs),
          Text(
            '${wallet.currency} ${wallet.balance.toStringAsFixed(2)}',
            style: theme.textTheme.headlineMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.onPrimaryContainer,
            ),
          ),
          // "Outstanding Debt" as its own clearly-labeled fintech-style
          // figure (Rapido-benchmarked redesign, 2026-09-08 — "Top:
          // Available Balance, Outstanding Debt"), not just embedded in
          // a sentence as before. The recovery rule itself — recovered
          // from the *next recharge* — stays exactly as worded;
          // preserved word-for-word, business logic untouched.
          if (wallet.outstandingDebt > 0) ...[
            const SizedBox(height: VistaarSpacing.md),
            Container(
              padding: const EdgeInsets.all(VistaarSpacing.sm),
              decoration: BoxDecoration(
                color: VistaarColors.warningContainer,
                borderRadius: BorderRadius.circular(VistaarRadius.control),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          'Outstanding Debt',
                          style: theme.textTheme.labelLarge?.copyWith(
                            color: VistaarColors.onWarningContainer,
                          ),
                        ),
                      ),
                      const SizedBox(width: VistaarSpacing.sm),
                      Flexible(
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerRight,
                          child: Text(
                            '${wallet.currency} ${wallet.outstandingDebt.toStringAsFixed(2)}',
                            style: theme.textTheme.labelLarge?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: VistaarColors.onWarningContainer,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: VistaarSpacing.xs),
                  Text(
                    'Unpaid cancellation penalty — recovered from your '
                    'next recharge.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: VistaarColors.onWarningContainer,
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (wallet.outstandingSettlement > 0) ...[
            const SizedBox(height: VistaarSpacing.sm),
            Text(
              'Outstanding settlement: ${wallet.currency} '
              '${wallet.outstandingSettlement.toStringAsFixed(2)}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onPrimaryContainer,
              ),
            ),
          ],
          const SizedBox(height: VistaarSpacing.md),
          FilledButton.tonal(
            onPressed: _openRecharge,
            child: const Text('Recharge Wallet'),
          ),
        ],
      ),
    );
  }

  Widget _buildTransactionTile(BuildContext context, WalletTransaction t) {
    final theme = Theme.of(context);
    final sign = t.isCredit ? '+' : '−';
    final color = t.isCredit ? VistaarColors.success : theme.colorScheme.onSurface;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: VistaarSpacing.xs),
      child: VistaarCard(
        padding: const EdgeInsets.all(VistaarSpacing.sm),
        child: Row(
          children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: color.withValues(alpha: 0.12),
              child: Icon(
                t.isCredit ? Icons.arrow_downward : Icons.arrow_upward,
                size: 18,
                color: color,
              ),
            ),
            const SizedBox(width: VistaarSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_humanizeType(t.transactionType)),
                  Text(
                    '${t.createdAt.toLocal()}'.split('.').first,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Text(
              '$sign${t.amount.toStringAsFixed(2)}',
              style: TextStyle(color: color, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}
