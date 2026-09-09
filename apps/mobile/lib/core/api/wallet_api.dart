import 'api_client.dart';
import 'api_exception.dart';

/// `GET /api/v1/drivers/me/wallet` (api-contracts.md §34, ADR-0013 —
/// Minimal Wallet Foundation). Driver-only — there is no customer-
/// facing wallet endpoint anywhere in the backend (verified directly
/// against `modules/wallet/router.py`: both routes require
/// `require_driver`); see `WalletApi`'s own doc comment for what that
/// means for the User side of this build-order step.
class Wallet {
  const Wallet({
    required this.balance,
    required this.currency,
    required this.outstandingSettlement,
    required this.outstandingDebt,
  });

  factory Wallet.fromJson(Map<String, dynamic> json) => Wallet(
    balance: (json['balance'] as num).toDouble(),
    currency: json['currency'] as String,
    outstandingSettlement: (json['outstanding_settlement'] as num).toDouble(),
    outstandingDebt: (json['outstanding_debt'] as num).toDouble(),
  );

  final double balance;
  final String currency;

  /// Always `0` on the wire today — not a placeholder for an unknown
  /// value, genuinely accurate: `wallet.outstanding_settlements`
  /// doesn't exist yet in the backend, so nothing can ever populate it
  /// (the backend's own `_wallet_data()` docstring says the same).
  /// Shown anyway, for when that changes.
  final double outstandingSettlement;

  /// Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062, 2026-09-03)
  /// — unlike [outstandingSettlement] above, this one is genuinely
  /// real: an unpaid driver-cancellation penalty the wallet balance
  /// couldn't cover at cancellation time, awaiting recovery from a
  /// future wallet recharge. `0` for the common case.
  final double outstandingDebt;
}

/// One row of `GET /api/v1/drivers/me/wallet/transactions`
/// (api-contracts.md §34, ADR-0024) — this driver's own immutable
/// ledger. `rideId`/`referenceId` are `null` for a transaction not tied
/// to a specific ride (e.g. a future `WALLET_RECHARGE`).
class WalletTransaction {
  const WalletTransaction({
    required this.transactionId,
    required this.rideId,
    required this.transactionType,
    required this.amount,
    required this.direction,
    required this.balanceAfter,
    required this.createdAt,
  });

  factory WalletTransaction.fromJson(Map<String, dynamic> json) =>
      WalletTransaction(
        transactionId: json['transaction_id'] as String,
        rideId: json['ride_id'] as String?,
        transactionType: json['transaction_type'] as String,
        amount: (json['amount'] as num).toDouble(),
        direction: json['direction'] as String,
        balanceAfter: (json['balance_after'] as num).toDouble(),
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  final String transactionId;
  final String? rideId;

  /// One of `TransactionType`'s wire values (backend
  /// `modules/wallet/domain/entities.py`) — `PLATFORM_FEE`/
  /// `DRIVER_PENALTY` are the only two this app's own flows can
  /// actually produce today (ride-offer accept, driver cancellation);
  /// the rest exist in the enum for future callers.
  final String transactionType;
  final double amount;

  /// `"CREDIT"` or `"DEBIT"`.
  final String direction;
  final double balanceAfter;
  final DateTime createdAt;

  bool get isCredit => direction == 'CREDIT';
}

/// One page of `GET /api/v1/drivers/me/wallet/transactions`
/// (api-contracts.md §50's shared pagination shape).
class WalletTransactionPage {
  const WalletTransactionPage({
    required this.items,
    required this.page,
    required this.totalPages,
  });

  final List<WalletTransaction> items;
  final int page;
  final int totalPages;

  bool get hasMore => page < totalPages;
}

/// Response to `POST /api/v1/drivers/me/wallet/recharge`
/// (api-contracts.md §35, ADR-0060) — a pending order with the
/// configured payment gateway (Razorpay, TEST/DEVELOPMENT only). No
/// wallet effect yet; [clientKey]/[orderId] are handed to
/// [RazorpayCheckout] to launch the actual checkout UI.
class RechargeOrder {
  const RechargeOrder({
    required this.orderId,
    required this.amount,
    required this.currency,
    required this.clientKey,
  });

  factory RechargeOrder.fromJson(Map<String, dynamic> json) => RechargeOrder(
    orderId: json['order_id'] as String,
    amount: (json['amount'] as num).toDouble(),
    currency: json['currency'] as String,
    clientKey: json['client_key'] as String,
  );

  final String orderId;
  final double amount;
  final String currency;
  final String clientKey;
}

/// Response to `POST /api/v1/drivers/me/wallet/recharge/confirm`
/// (api-contracts.md §35, ADR-0060) — [walletBalance] is the driver's
/// real post-credit balance, verified server-side; never trust a
/// locally-computed "old balance + amount" instead of this value.
class RechargeConfirmation {
  const RechargeConfirmation({
    required this.status,
    required this.walletBalance,
    this.debtRecovered,
    this.outstandingDebtRemaining,
  });

  factory RechargeConfirmation.fromJson(Map<String, dynamic> json) =>
      RechargeConfirmation(
        status: json['status'] as String,
        walletBalance: (json['wallet_balance'] as num).toDouble(),
        debtRecovered: (json['debt_recovered'] as num?)?.toDouble(),
        outstandingDebtRemaining: (json['outstanding_debt_remaining'] as num?)
            ?.toDouble(),
      );

  final String status;
  final double walletBalance;

  /// Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062, 2026-09-03)
  /// — `null` for a plain recharge with no outstanding debt (the
  /// common case); non-null only when this recharge paid some or all
  /// of an earlier unpaid cancellation penalty down before
  /// [walletBalance] was credited.
  final double? debtRecovered;
  final double? outstandingDebtRemaining;
}

/// Calls the driver-side wallet endpoints (api-contracts.md §34).
/// There is no customer-facing equivalent: `GET /api/v1/customers/me`
/// does not return `outstanding_penalty`/`total_payable` despite
/// ADR-0026 documenting that as a target shape (a real, separately
/// tracked backend gap — GAP-6, docs/16-mobile/mobile-app-
/// implementation-plan.md) — so build order step 7's "Wallet views,
/// both sides" is Sarthi-only for now; there is nothing for a User
/// wallet screen to call yet.
class WalletApi {
  WalletApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<Wallet> getWallet() async {
    final data = await _client.get(
      '/api/v1/drivers/me/wallet',
      accessToken: _requireToken(),
    );
    return Wallet.fromJson(data);
  }

  Future<WalletTransactionPage> listTransactions({
    int page = 1,
    int pageSize = 20,
  }) async {
    final data = await _client.get(
      '/api/v1/drivers/me/wallet/transactions?page=$page&page_size=$pageSize',
      accessToken: _requireToken(),
    );
    final items = (data['items'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(WalletTransaction.fromJson)
        .toList(growable: false);
    final pagination = data['pagination'] as Map<String, dynamic>;
    return WalletTransactionPage(
      items: items,
      page: pagination['page'] as int,
      totalPages: pagination['total_pages'] as int,
    );
  }

  /// Step 1 of Sarthi Wallet Recharge (api-contracts.md §35, ADR-0060) —
  /// creates a pending order; throws [ApiException] with code
  /// `RECHARGE_AMOUNT_TOO_LOW` if [amount] is below the backend's
  /// configured minimum (₹200 by default), which
  /// [RechargeWalletScreen] itself also checks first so the error
  /// message can appear without a round trip whenever possible.
  Future<RechargeOrder> createRechargeOrder(double amount) async {
    final data = await _client.post(
      '/api/v1/drivers/me/wallet/recharge',
      body: {'amount': amount},
      accessToken: _requireToken(),
    );
    return RechargeOrder.fromJson(data);
  }

  /// Step 2 of Sarthi Wallet Recharge — called once
  /// [RazorpayCheckout] reports a completed payment. The backend
  /// re-verifies server-side before crediting anything (ADR-0060 §3) —
  /// this call reporting success does not by itself mean money moved;
  /// a `PAYMENT_VERIFICATION_FAILED` [ApiException] means it didn't.
  Future<RechargeConfirmation> confirmRecharge({
    required String orderId,
    required String paymentId,
    required String signature,
  }) async {
    final data = await _client.post(
      '/api/v1/drivers/me/wallet/recharge/confirm',
      body: {
        'order_id': orderId,
        'payment_id': paymentId,
        'signature': signature,
      },
      accessToken: _requireToken(),
    );
    return RechargeConfirmation.fromJson(data);
  }
}
