import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/support_api.dart';
import 'support_case_screen.dart';

/// My Support Cases — Phase 14 (api-contracts.md §44, added 2026-09-04:
/// the previously-missing list endpoint). Shows every case the caller
/// has filed, newest first, paginated the same way [WalletScreen]'s
/// transaction ledger already does — loading/error/empty states all
/// follow that same established shape.
class SupportCasesListScreen extends StatefulWidget {
  const SupportCasesListScreen({super.key});

  @override
  State<SupportCasesListScreen> createState() =>
      _SupportCasesListScreenState();
}

class _SupportCasesListScreenState extends State<SupportCasesListScreen> {
  final List<SupportCase> _cases = [];
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
    final api = context.read<SupportApi>();
    try {
      final page = await api.listCases();
      if (!mounted) return;
      setState(() {
        _cases
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
    final api = context.read<SupportApi>();
    try {
      final page = await api.listCases(page: _nextPage);
      if (!mounted) return;
      setState(() {
        _cases.addAll(page.items);
        _nextPage = page.page + 1;
        _hasMore = page.hasMore;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoadingMore = false);
    }
  }

  /// Re-fetches the full case (with its message thread) before opening
  /// it — the list response deliberately omits `messages` (same shape
  /// api-contracts.md §44 documents for the create response), same
  /// "fetch the real detail before showing it" step
  /// [ContactSupportScreen] already takes.
  Future<void> _openCase(SupportCase summary) async {
    final api = context.read<SupportApi>();
    try {
      final full = await api.getCase(summary.caseId);
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => SupportCaseScreen(initialCase: full)),
      );
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Support Cases')),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _loadInitial,
                child: _cases.isEmpty && _errorMessage != null
                    ? _buildFullPageError(context)
                    : _cases.isEmpty
                    ? _buildEmptyState(context)
                    : _buildList(context),
              ),
      ),
    );
  }

  Widget _buildFullPageError(BuildContext context) {
    return ListView(
      // A scrollable single child keeps pull-to-refresh working even
      // when there is nothing else on screen.
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 96, horizontal: 24),
          child: Column(
            children: [
              Icon(
                Icons.error_outline,
                size: 40,
                color: Theme.of(context).colorScheme.error,
              ),
              const SizedBox(height: 12),
              Text(
                _errorMessage!,
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return ListView(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 96, horizontal: 24),
          child: Column(
            children: [
              Icon(
                Icons.support_agent_outlined,
                size: 40,
                color: Theme.of(context).colorScheme.outline,
              ),
              const SizedBox(height: 12),
              const Text(
                'You have not contacted support yet.',
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildList(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.all(24),
      itemCount: _cases.length + 1,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        if (index == _cases.length) {
          return _buildFooter(context);
        }
        return _buildCaseTile(context, _cases[index]);
      },
    );
  }

  Widget _buildFooter(BuildContext context) {
    if (_errorMessage != null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Text(
          _errorMessage!,
          textAlign: TextAlign.center,
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
      );
    }
    if (!_hasMore) return const SizedBox.shrink();
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: _isLoadingMore
            ? const CircularProgressIndicator(strokeWidth: 2.5)
            : TextButton(onPressed: _loadMore, child: const Text('Load more')),
      ),
    );
  }

  Widget _buildCaseTile(BuildContext context, SupportCase supportCase) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(supportCase.category ?? 'General'),
      subtitle: Text(
        '${supportCase.createdAt.toLocal()}'.split('.').first,
        style: Theme.of(context).textTheme.bodySmall,
      ),
      trailing: Chip(
        label: Text(supportCase.status),
        visualDensity: VisualDensity.compact,
      ),
      onTap: () => _openCase(supportCase),
    );
  }
}
