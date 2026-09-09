import 'api_client.dart';
import 'api_exception.dart';

/// Result of `POST /api/v1/drivers/me/online` (api-contracts.md §10).
class GoOnlineResult {
  GoOnlineResult({required this.status, required this.vehicleId});

  final String status;

  /// The driver's currently ACTIVE vehicle (BR-122: at most one) — always
  /// present on a successful Go Online response.
  final String? vehicleId;
}

/// Calls the three Sarthi (driver) availability/location endpoints
/// (api-contracts.md §10, §15) — this app's first authenticated calls
/// past login. `AuthSession`'s current access token is read fresh on
/// every call (not captured at construction time), so this object never
/// goes stale across a sign-out/sign-in.
class DriverAvailabilityApi {
  DriverAvailabilityApi(this._client, this._accessToken);

  final ApiClient _client;

  /// Returns the current session's access token, or throws
  /// `AUTH_REQUIRED` if there isn't one — mirrors what the backend itself
  /// would return for an unauthenticated call, so callers handle both
  /// identically via the same `ApiException` catch.
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<GoOnlineResult> goOnline() async {
    final data = await _client.post(
      '/api/v1/drivers/me/online',
      body: const {},
      accessToken: _requireToken(),
    );
    return GoOnlineResult(
      status: data['status'] as String,
      vehicleId: data['vehicle_id'] as String?,
    );
  }

  Future<void> goOffline() async {
    await _client.post(
      '/api/v1/drivers/me/offline',
      body: const {},
      accessToken: _requireToken(),
    );
  }

  /// `accuracyMeters`/`recordedAt` are accepted-but-not-deeply-validated
  /// by the backend (api-contracts.md §15's own documented "no timestamp
  /// sanity rule exists" note) — sent when available since the device
  /// position always has both, not because the backend requires either.
  Future<void> updateLocation({
    required double latitude,
    required double longitude,
    double? accuracyMeters,
    DateTime? recordedAt,
  }) async {
    await _client.post(
      '/api/v1/drivers/me/location',
      body: {
        'latitude': latitude,
        'longitude': longitude,
        'accuracy_meters': ?accuracyMeters,
        'recorded_at': ?recordedAt?.toUtc().toIso8601String(),
      },
      accessToken: _requireToken(),
    );
  }
}
