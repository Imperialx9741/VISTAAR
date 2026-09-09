import 'package:razorpay_flutter/razorpay_flutter.dart' as rzp;

/// What [RechargeWalletScreen] needs from a checkout SDK — deliberately
/// small and provider-agnostic, mirroring the backend's own
/// `WalletRechargeGateway` Protocol abstraction (ADR-0060): everything
/// above this interface never mentions "Razorpay," and everything below
/// it (`RealRazorpayCheckout`) is where that concrete name is allowed to
/// appear. A future SBI checkout SDK (or any other) would only need a
/// second implementation of this same interface, not a screen rewrite.
abstract class RazorpayCheckout {
  /// Launches the gateway's own hosted checkout UI. [amountPaise] is the
  /// amount in the smallest currency unit (paise for INR) — the same
  /// convention `RazorpayWalletRechargeGateway.create_order()` uses
  /// server-side (payment_gateway.py).
  void open({
    required String keyId,
    required String orderId,
    required int amountPaise,
    required String currency,
    String? description,
  });

  /// Registers the callback fired when the checkout UI reports a
  /// completed payment. The three fields reported back
  /// (`orderId`/`paymentId`/`signature`) are exactly what
  /// `WalletApi.confirmRecharge()` forwards to the backend for
  /// server-side verification — this app never itself decides a
  /// payment succeeded.
  void onSuccess(
    void Function(String orderId, String paymentId, String signature)
    handler,
  );

  /// Registers the callback fired when the checkout UI reports a failed
  /// payment (declined, network error inside the checkout flow, etc.)
  /// — distinct from the driver simply backing out of the checkout UI
  /// without completing it, which most checkout SDKs (including
  /// Razorpay's) report as neither success nor error; see
  /// `RechargeWalletScreen`'s own doc comment for how that case is
  /// handled.
  void onError(void Function(String message) handler);

  /// Releases the underlying SDK's native event listeners — must be
  /// called from the owning widget's `dispose()`.
  void dispose();
}

/// Wraps razorpay_flutter's `Razorpay` class — the real implementation
/// used outside tests. Never unit-tested directly: it drives a native
/// platform channel this environment has no Android/iOS
/// device/emulator to back (same limitation this session's Contacts
/// picker work already documented for `flutter_contacts`). See
/// `test/features/wallet/recharge_wallet_screen_test.dart`'s own doc
/// comment for how [RechargeWalletScreen]'s business logic is verified
/// instead, via a fake [RazorpayCheckout].
class RealRazorpayCheckout implements RazorpayCheckout {
  RealRazorpayCheckout() : _razorpay = rzp.Razorpay();

  final rzp.Razorpay _razorpay;

  @override
  void open({
    required String keyId,
    required String orderId,
    required int amountPaise,
    required String currency,
    String? description,
  }) {
    _razorpay.open({
      'key': keyId,
      'order_id': orderId,
      'amount': amountPaise,
      'currency': currency,
      'description': ?description,
    });
  }

  @override
  void onSuccess(
    void Function(String orderId, String paymentId, String signature)
    handler,
  ) {
    _razorpay.on(rzp.Razorpay.EVENT_PAYMENT_SUCCESS, (
      rzp.PaymentSuccessResponse response,
    ) {
      handler(
        response.orderId ?? '',
        response.paymentId ?? '',
        response.signature ?? '',
      );
    });
  }

  @override
  void onError(void Function(String message) handler) {
    _razorpay.on(rzp.Razorpay.EVENT_PAYMENT_ERROR, (
      rzp.PaymentFailureResponse response,
    ) {
      handler(response.message ?? 'Payment failed.');
    });
  }

  @override
  void dispose() => _razorpay.clear();
}
