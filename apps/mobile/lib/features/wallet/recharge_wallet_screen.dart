import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/wallet_api.dart';
import '../../core/payments/razorpay_checkout.dart';
import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/widgets/primary_button.dart';

/// Quick-amount shortcuts shown above the amount field — a real,
/// common recharge-screen affordance (Phase 6 of the redesign,
/// "Sarthi home + wallet", 2026-09-08); each one simply fills the same
/// [TextEditingController] a driver could type into directly, so it
/// changes nothing about validation or the recharge call itself.
const List<double> _quickAmounts = [200, 500, 1000, 2000];

/// Sarthi Wallet Recharge (api-contracts.md §35, ADR-0060) — the
/// deferred "Recharge Wallet" action ADR-0058 left for this work: a
/// driver enters an amount, [WalletApi.createRechargeOrder] creates a
/// pending order, [RazorpayCheckout] launches Razorpay's own hosted
/// checkout UI (TEST-mode only — see ADR-0060), and
/// [WalletApi.confirmRecharge] reports the completed payment back for
/// server-side verification before the wallet is ever credited. Pops
/// with the new wallet balance (a `double?`) on success, `null`
/// otherwise, so callers (e.g. [WalletScreen]) can refresh without a
/// second network round trip.
///
/// [checkout] exists purely as a test seam — production code never
/// passes it, always falling back to the real [RealRazorpayCheckout].
class RechargeWalletScreen extends StatefulWidget {
  const RechargeWalletScreen({super.key, RazorpayCheckout? checkout})
    : _checkoutOverride = checkout;

  final RazorpayCheckout? _checkoutOverride;

  @override
  State<RechargeWalletScreen> createState() => _RechargeWalletScreenState();
}

class _RechargeWalletScreenState extends State<RechargeWalletScreen> {
  // Mirrors api-contracts.md §35's documented minimum — checked
  // locally first so the common "too low" mistake never needs a round
  // trip, but the backend's own check (WALLET_RECHARGE_MINIMUM_AMOUNT)
  // remains authoritative; this is only a UX shortcut, not the source
  // of truth.
  static const double _minimumAmount = 200;

  final _amountController = TextEditingController(
    text: _minimumAmount.toStringAsFixed(0),
  );
  late final RazorpayCheckout _checkout;
  bool _isBusy = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _checkout = widget._checkoutOverride ?? RealRazorpayCheckout();
    _checkout.onSuccess(_handleCheckoutSuccess);
    _checkout.onError(_handleCheckoutError);
  }

  @override
  void dispose() {
    _checkout.dispose();
    _amountController.dispose();
    super.dispose();
  }

  Future<void> _startRecharge() async {
    final amount = double.tryParse(_amountController.text.trim());
    if (amount == null || amount < _minimumAmount) {
      setState(
        () => _errorMessage =
            'Enter an amount of at least ₹${_minimumAmount.toStringAsFixed(0)}.',
      );
      return;
    }

    setState(() {
      _isBusy = true;
      _errorMessage = null;
    });

    final api = context.read<WalletApi>();
    try {
      final order = await api.createRechargeOrder(amount);
      // _isBusy is deliberately left true from here on, through
      // whichever of _handleCheckoutSuccess/_handleCheckoutError fires
      // next — razorpay_flutter reports success or a genuine payment
      // error, but has no distinct "the driver simply closed the
      // checkout UI without paying" callback, so there is no reliable
      // signal to reset the button on that specific path. A driver who
      // backs out this way must leave and re-enter this screen to try
      // again — a known, narrow limitation, not a bug to work around
      // with a guess.
      _checkout.open(
        keyId: order.clientKey,
        orderId: order.orderId,
        amountPaise: (order.amount * 100).round(),
        currency: order.currency,
        description: 'VISTAAR Wallet Recharge',
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage = error.message;
        _isBusy = false;
      });
    }
  }

  Future<void> _handleCheckoutSuccess(
    String orderId,
    String paymentId,
    String signature,
  ) async {
    if (!mounted) return;
    final api = context.read<WalletApi>();
    try {
      final confirmation = await api.confirmRecharge(
        orderId: orderId,
        paymentId: paymentId,
        signature: signature,
      );
      if (!mounted) return;
      // Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062,
      // 2026-09-03) — a blocking dialog, not a SnackBar, so the driver
      // reliably sees why their credited balance is less than what
      // they just paid before this screen pops away. Same "AlertDialog
      // before navigating on" pattern book_ride_screen.dart already
      // uses for ADR-0059's outstanding-penalty display.
      if ((confirmation.debtRecovered ?? 0) > 0) {
        await showDialog<void>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Recharge applied to unpaid penalty'),
            content: Text(
              '₹${confirmation.debtRecovered!.toStringAsFixed(2)} of this '
              'recharge went toward an earlier unpaid cancellation '
              'penalty. ₹${confirmation.walletBalance.toStringAsFixed(2)} '
              'is now available in your wallet.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('OK'),
              ),
            ],
          ),
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(confirmation.walletBalance);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage = error.message;
        _isBusy = false;
      });
    }
  }

  void _handleCheckoutError(String message) {
    if (!mounted) return;
    setState(() {
      _errorMessage = message;
      _isBusy = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Recharge Wallet')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(VistaarSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              VistaarCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.account_balance_wallet_outlined,
                          color: theme.colorScheme.primary,
                        ),
                        const SizedBox(width: VistaarSpacing.sm),
                        // Flexible, not a bare Text — at a narrow width
                        // or a large accessibility text scale this
                        // sentence needs to wrap onto a second line
                        // rather than overflow the row (verified
                        // directly — a real overflow at 320dp width,
                        // fixed here, not assumed).
                        Flexible(
                          child: Text(
                            'Minimum recharge: ₹${_minimumAmount.toStringAsFixed(0)}',
                            style: theme.textTheme.bodyMedium,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: VistaarSpacing.md),
                    Wrap(
                      spacing: VistaarSpacing.sm,
                      runSpacing: VistaarSpacing.sm,
                      children: [
                        for (final amount in _quickAmounts)
                          ChoiceChip(
                            label: Text('₹${amount.toStringAsFixed(0)}'),
                            selected:
                                _amountController.text.trim() ==
                                amount.toStringAsFixed(0),
                            onSelected: _isBusy
                                ? null
                                : (_) => setState(
                                    () => _amountController.text =
                                        amount.toStringAsFixed(0),
                                  ),
                          ),
                      ],
                    ),
                    const SizedBox(height: VistaarSpacing.md),
                    TextField(
                      controller: _amountController,
                      enabled: !_isBusy,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: false,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Amount (₹)',
                        border: OutlineInputBorder(),
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
                  ],
                ),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: VistaarSpacing.sm),
                Text(
                  _errorMessage!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ],
              const SizedBox(height: VistaarSpacing.lg),
              PrimaryButton(
                label: 'Recharge',
                isLoading: _isBusy,
                onPressed: _startRecharge,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
