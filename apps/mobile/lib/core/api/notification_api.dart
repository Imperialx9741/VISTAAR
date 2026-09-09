import 'api_client.dart';
import 'api_exception.dart';

/// A registered push-notification device (api-contracts.md §46's
/// notification module, ADR-0052). `platform` is one of `"ANDROID"`,
/// `"IOS"`, `"WEB"` (`modules/notification/domain/entities.py`'s
/// `Platform` enum — matches Firebase's own client SDKs, not this
/// codebase's invention).
class DeviceRegistration {
  const DeviceRegistration({
    required this.deviceId,
    required this.platform,
    required this.token,
  });

  factory DeviceRegistration.fromJson(Map<String, dynamic> json) =>
      DeviceRegistration(
        deviceId: json['device_id'] as String,
        platform: json['platform'] as String,
        token: json['token'] as String,
      );

  final String deviceId;
  final String platform;
  final String token;
}

/// Calls the two live device-token endpoints
/// (`POST`/`DELETE /api/v1/notifications/me/devices`, ADR-0052).
/// Identity-agnostic — reachable by either role, no `account_type`
/// restriction (verified directly against
/// `modules/notification/router.py`).
///
/// **Not wired into any screen yet, deliberately** (build order step
/// 9): registering a *real* device needs the `firebase_messaging`
/// Flutter SDK, a real Firebase project, and its generated
/// `google-services.json`/`GoogleService-Info.plist` config files —
/// none of which exist yet (no Firebase project has been created; the
/// backend's own `PUSH_PROVIDER` still defaults to `dev`, ADR-0052).
/// Calling this class with a fabricated placeholder token would
/// register a device nothing could ever actually deliver a push to —
/// that would be worse than not registering at all, so this app
/// doesn't. This class exists now, tested against the real backend
/// contract, so wiring the actual SDK later is only that SDK
/// integration work, not also a fresh backend-contract question.
class NotificationApi {
  NotificationApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<DeviceRegistration> registerDevice({
    required String platform,
    required String token,
  }) async {
    final data = await _client.post(
      '/api/v1/notifications/me/devices',
      body: {'platform': platform, 'token': token},
      accessToken: _requireToken(),
    );
    return DeviceRegistration.fromJson(data);
  }

  Future<void> unregisterDevice(String token) async {
    await _client.delete(
      '/api/v1/notifications/me/devices/$token',
      accessToken: _requireToken(),
    );
  }
}
