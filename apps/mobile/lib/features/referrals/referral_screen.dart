import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/referral_api.dart';
import '../../shared/widgets/primary_button.dart';

/// My Referrals — shows the customer's own referral code
/// (`GET /api/v1/customers/me/referral`, api-contracts.md §38, lazily
/// provisioned on first call) and lets them attach a code someone else
/// shared with them (`POST /api/v1/referrals/attach`). BR-060: a
/// customer referral qualifies immediately on attach and grants a
/// promotion entitlement to both sides — visible afterward on
/// [PromotionsScreen], not repeated here. Deliberately no share-sheet
/// integration (`share_plus` or similar) — copy-to-clipboard is the only
/// "share" affordance; a native share sheet is a separate, cosmetic
/// addition, not a missing capability.
class ReferralScreen extends StatefulWidget {
  const ReferralScreen({super.key});

  @override
  State<ReferralScreen> createState() => _ReferralScreenState();
}

class _ReferralScreenState extends State<ReferralScreen> {
  String? _code;
  bool _isLoading = true;
  bool _isAttaching = false;
  String? _errorMessage;
  final _attachController = TextEditingController();

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _attachController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final code = await context.read<ReferralApi>().getMyCode();
      if (!mounted) return;
      setState(() => _code = code);
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _copyCode() async {
    final code = _code;
    if (code == null) return;
    await Clipboard.setData(ClipboardData(text: code));
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('Code copied.')));
  }

  Future<void> _attach() async {
    final code = _attachController.text.trim();
    if (code.isEmpty) return;
    setState(() => _isAttaching = true);
    try {
      final status = await context.read<ReferralApi>().attachCode(code);
      if (!mounted) return;
      _attachController.clear();
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Referral $status.')));
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _isAttaching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Referrals')),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    Text(
                      'Your Referral Code',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    if (_code != null)
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.primaryContainer,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                _code!,
                                style: Theme.of(context).textTheme.headlineSmall
                                    ?.copyWith(fontWeight: FontWeight.bold),
                              ),
                            ),
                            IconButton(
                              tooltip: 'Copy code',
                              icon: const Icon(Icons.copy_outlined),
                              onPressed: _copyCode,
                            ),
                          ],
                        ),
                      )
                    else if (_errorMessage != null)
                      Text(
                        _errorMessage!,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    Text(
                      'Share this code — when someone signs up with it, you '
                      'both get a promotion.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 24),
                    const Divider(),
                    const SizedBox(height: 16),
                    Text(
                      'Have a Code?',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _attachController,
                      textCapitalization: TextCapitalization.characters,
                      decoration: const InputDecoration(
                        labelText: 'Referral code',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 8),
                    PrimaryButton(
                      label: 'Attach Code',
                      isLoading: _isAttaching,
                      onPressed: _attach,
                    ),
                  ],
                ),
              ),
      ),
    );
  }
}
