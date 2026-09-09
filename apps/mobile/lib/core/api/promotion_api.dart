import 'api_client.dart';
import 'api_exception.dart';

/// One `promotion.entitlements` row (api-contracts.md §37). `campaignId`
/// is null for a welcome/referral grant (ADR-0041) — set only when this
/// entitlement came from [PromotionApi.redeemCode].
class Entitlement {
  const Entitlement({
    required this.type,
    required this.discountPercent,
    required this.remainingUses,
    required this.expiresAt,
    required this.campaignId,
  });

  factory Entitlement.fromJson(Map<String, dynamic> json) => Entitlement(
    type: json['type'] as String,
    discountPercent: (json['discount_percent'] as num).toDouble(),
    remainingUses: json['remaining_uses'] as int,
    expiresAt: DateTime.parse(json['expires_at'] as String),
    campaignId: json['campaign_id'] as String?,
  );

  /// `"WELCOME"` | `"REFERRAL"` | `"CAMPAIGN"` (ADR-0019/ADR-0041).
  final String type;
  final double discountPercent;
  final int remainingUses;
  final DateTime expiresAt;
  final String? campaignId;

  bool get isExpired => expiresAt.isBefore(DateTime.now());
}

/// Calls the customer promotions endpoints (api-contracts.md §37,
/// ADR-0041 Decision 2). `redeemCode`'s `vehicleCategory`/`fare` are the
/// caller's *proposed* ride's own values, validated server-side against
/// the campaign's own vehicle_category/minimum_fare — this call itself
/// does not create or touch a ride. It doesn't need to: `POST
/// /api/v1/rides` (Book a Ride) already auto-reserves the customer's
/// soonest-expiring ACTIVE entitlement — including one just redeemed
/// here — with no client-supplied promotion/code field at all
/// (ADR-0070, modules/promotion/router.py's own docstring). The
/// discount simply appears in that ride's own fare quote; nothing on
/// this screen or in [BookRideScreen] needs to select or apply it.
class PromotionApi {
  PromotionApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<List<Entitlement>> listPromotions() async {
    final data = await _client.get(
      '/api/v1/customers/me/promotions',
      accessToken: _requireToken(),
    );
    return (data['promotions'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(Entitlement.fromJson)
        .toList(growable: false);
  }

  Future<Entitlement> redeemCode({
    required String code,
    required String vehicleCategory,
    required double fare,
  }) async {
    final data = await _client.post(
      '/api/v1/customers/me/promotions/redeem',
      body: {
        'code': code,
        'vehicle_category': vehicleCategory,
        'fare': fare.toStringAsFixed(2),
      },
      accessToken: _requireToken(),
    );
    return Entitlement.fromJson(data);
  }
}
