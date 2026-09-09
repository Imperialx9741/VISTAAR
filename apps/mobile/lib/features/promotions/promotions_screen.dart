import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/promotion_api.dart';
import '../../shared/widgets/primary_button.dart';

/// My Promotions — lists active entitlements
/// (`GET /api/v1/customers/me/promotions`, api-contracts.md §37) and
/// lets the customer redeem a campaign code
/// (`POST .../redeem`, ADR-0041 Decision 2). Redeeming asks for a
/// vehicle category and fare directly on this screen because the
/// backend validates a code's eligibility against those two values —
/// not because a ride needs to exist first: once redeemed, the new
/// entitlement is picked up automatically the next time this customer
/// books a ride (no selection step anywhere in the app; see
/// [PromotionApi]'s own doc comment for how).
class PromotionsScreen extends StatefulWidget {
  const PromotionsScreen({super.key});

  @override
  State<PromotionsScreen> createState() => _PromotionsScreenState();
}

class _PromotionsScreenState extends State<PromotionsScreen> {
  List<Entitlement> _promotions = const [];
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final promotions = await context.read<PromotionApi>().listPromotions();
      if (!mounted) return;
      setState(() => _promotions = promotions);
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _redeem(
    String code,
    String vehicleCategory,
    double fare,
  ) async {
    try {
      await context.read<PromotionApi>().redeemCode(
        code: code,
        vehicleCategory: vehicleCategory,
        fare: fare,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Code redeemed.')));
      await _load();
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
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
      appBar: AppBar(title: const Text('Promotions')),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    Text(
                      'Active Promotions',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    if (_promotions.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 12),
                        child: Text('No active promotions.'),
                      )
                    else
                      for (final promo in _promotions) _buildTile(context, promo),
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
                    const SizedBox(height: 24),
                    const Divider(),
                    const SizedBox(height: 16),
                    _RedeemForm(onRedeem: _redeem),
                  ],
                ),
              ),
      ),
    );
  }

  Widget _buildTile(BuildContext context, Entitlement promo) {
    return Card(
      child: ListTile(
        title: Text(_humanizeType(promo.type)),
        subtitle: Text(
          '${promo.discountPercent.toStringAsFixed(0)}% off · '
          '${promo.remainingUses} use${promo.remainingUses == 1 ? '' : 's'} left · '
          'expires ${promo.expiresAt.toLocal().toString().split(' ').first}',
        ),
        trailing: promo.isExpired
            ? Chip(
                label: const Text('Expired'),
                labelStyle: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                ),
                visualDensity: VisualDensity.compact,
              )
            : null,
      ),
    );
  }
}

class _RedeemForm extends StatefulWidget {
  const _RedeemForm({required this.onRedeem});

  final Future<void> Function(String code, String vehicleCategory, double fare)
  onRedeem;

  @override
  State<_RedeemForm> createState() => _RedeemFormState();
}

class _RedeemFormState extends State<_RedeemForm> {
  static const _vehicleCategories = [
    ('BIKE', 'Bike'),
    ('AUTO', 'Auto'),
    ('CAB', 'Cab'),
  ];

  final _codeController = TextEditingController();
  final _fareController = TextEditingController();
  String _vehicleCategory = _vehicleCategories.first.$1;
  bool _isSubmitting = false;

  @override
  void dispose() {
    _codeController.dispose();
    _fareController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final code = _codeController.text.trim();
    final fare = double.tryParse(_fareController.text.trim());
    if (code.isEmpty || fare == null) return;
    setState(() => _isSubmitting = true);
    await widget.onRedeem(code, _vehicleCategory, fare);
    if (mounted) {
      _codeController.clear();
      _fareController.clear();
      setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Redeem a Code', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        TextField(
          controller: _codeController,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(
            labelText: 'Campaign code',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          initialValue: _vehicleCategory,
          decoration: const InputDecoration(
            labelText: 'Vehicle',
            border: OutlineInputBorder(),
          ),
          items: [
            for (final (value, label) in _vehicleCategories)
              DropdownMenuItem(value: value, child: Text(label)),
          ],
          onChanged: (value) => setState(
            () => _vehicleCategory = value ?? _vehicleCategory,
          ),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _fareController,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Estimated fare (₹)',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        PrimaryButton(
          label: 'Redeem',
          isLoading: _isSubmitting,
          onPressed: _submit,
        ),
      ],
    );
  }
}
