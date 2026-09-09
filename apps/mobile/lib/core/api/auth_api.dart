import 'api_client.dart';

/// Result of `POST /api/v1/auth/otp/request` (api-contracts.md §6.1).
class OtpChallenge {
  OtpChallenge({required this.challengeId, required this.expiresInSeconds});

  final String challengeId;
  final int expiresInSeconds;
}

/// Result of `POST /api/v1/auth/otp/verify` (api-contracts.md §7).
class AuthTokens {
  AuthTokens({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresInSeconds,
  });

  final String accessToken;
  final String refreshToken;
  final int expiresInSeconds;
}

/// Calls VISTAAR's two-step OTP authentication flow
/// (api-contracts.md §6-7) — shared by both the User (customer) and
/// Sarthi (driver) login paths; only `accountType` differs between them.
class AuthApi {
  AuthApi(this._client);

  final ApiClient _client;

  /// `accountType` is the backend's exact `identity.accounts.account_type`
  /// value — `"CUSTOMER"` or `"DRIVER"` for this app's two roles.
  Future<OtpChallenge> requestOtp({
    required String phone,
    required String accountType,
  }) async {
    final data = await _client.post(
      '/api/v1/auth/otp/request',
      body: {'phone': phone, 'account_type': accountType},
    );
    return OtpChallenge(
      challengeId: data['challenge_id'] as String,
      expiresInSeconds: data['expires_in'] as int,
    );
  }

  Future<AuthTokens> verifyOtp({
    required String challengeId,
    required String otp,
  }) async {
    final data = await _client.post(
      '/api/v1/auth/otp/verify',
      body: {'challenge_id': challengeId, 'otp': otp},
    );
    return AuthTokens(
      accessToken: data['access_token'] as String,
      refreshToken: data['refresh_token'] as String,
      expiresInSeconds: data['expires_in'] as int,
    );
  }

  /// Token Refresh (api-contracts.md §7.1, ADR-0076). Refresh tokens are
  /// single-use and rotated server-side on every call
  /// (`IdentityService.refresh()` revokes the old session and issues a
  /// brand new pair) — the returned [AuthTokens.refreshToken] is a
  /// *different* value from [refreshToken] and must replace it
  /// wherever it's stored; the old one is no longer valid the instant
  /// this call succeeds. No `accessToken` is sent — a refresh token
  /// alone authenticates this call, same as OTP verify needs no prior
  /// session either.
  Future<AuthTokens> refresh(String refreshToken) async {
    final data = await _client.post(
      '/api/v1/auth/refresh',
      body: {'refresh_token': refreshToken},
    );
    return AuthTokens(
      accessToken: data['access_token'] as String,
      refreshToken: data['refresh_token'] as String,
      expiresInSeconds: data['expires_in'] as int,
    );
  }
}
