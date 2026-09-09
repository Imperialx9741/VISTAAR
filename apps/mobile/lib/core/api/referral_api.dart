import 'api_client.dart';
import 'api_exception.dart';

/// Calls the referral endpoints (api-contracts.md §38, ADR-0019
/// Decision 5). Customer-only here — [getMyCode] is documented at the
/// customer-facing path `/api/v1/customers/me/referral`; there is no
/// driver-facing equivalent route to reach the same underlying
/// lazily-provisioned code for a Sarthi (a real, documented gap, not an
/// oversight of this screen).
class ReferralApi {
  ReferralApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  /// Lazily provisions the code on first call (ReferralService's own
  /// `get_or_create_code`) — never fails with "not found".
  Future<String> getMyCode() async {
    final data = await _client.get(
      '/api/v1/customers/me/referral',
      accessToken: _requireToken(),
    );
    return data['code'] as String;
  }

  /// BR-060: a customer referral qualifies immediately on attach (no
  /// completed ride required) and grants both sides a promotion
  /// entitlement server-side — this call's only visible result here is
  /// the new `status`; the granted entitlements show up back on
  /// [PromotionApi.listPromotions].
  Future<String> attachCode(String code) async {
    final data = await _client.post(
      '/api/v1/referrals/attach',
      body: {'code': code},
      accessToken: _requireToken(),
    );
    return data['status'] as String;
  }
}
