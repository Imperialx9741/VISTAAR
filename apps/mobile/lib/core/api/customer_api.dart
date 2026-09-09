import 'api_client.dart';
import 'api_exception.dart';

/// A User's own profile (api-contracts.md §8, ADR-0019 Decision 4).
/// Unlike [DriverApi]'s equivalent, `GET /me` here always succeeds for a
/// signed-in customer — the backend auto-provisions the
/// `customer.customers` row (and grants the welcome promotion) on first
/// access, so there is no "not created yet" state to handle here.
class CustomerProfile {
  const CustomerProfile({
    required this.customerId,
    required this.phone,
    required this.fullName,
    required this.profilePhotoUri,
    required this.language,
    required this.notificationEnabled,
    required this.status,
  });

  factory CustomerProfile.fromJson(Map<String, dynamic> json) =>
      CustomerProfile(
        customerId: json['customer_id'] as String,
        phone: json['phone'] as String,
        fullName: json['full_name'] as String?,
        profilePhotoUri: json['profile_photo_uri'] as String?,
        language: json['language'] as String?,
        notificationEnabled: json['notification_enabled'] as bool,
        status: json['status'] as String,
      );

  final String customerId;
  final String phone;
  final String? fullName;
  final String? profilePhotoUri;
  final String? language;
  final bool notificationEnabled;

  /// `"ACTIVE"` | `"SUSPENDED"` | `"BANNED"` (state-machines.md).
  final String status;
}

/// Calls the customer profile endpoints (api-contracts.md §8).
class CustomerApi {
  CustomerApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<CustomerProfile> getProfile() async {
    final data = await _client.get(
      '/api/v1/customers/me',
      accessToken: _requireToken(),
    );
    return CustomerProfile.fromJson(data);
  }

  /// All fields optional — PATCH semantics (an omitted field is left
  /// untouched, not cleared).
  Future<CustomerProfile> updateProfile({
    String? fullName,
    String? profilePhotoUri,
    String? language,
    bool? notificationEnabled,
  }) async {
    final data = await _client.patch(
      '/api/v1/customers/me',
      body: {
        'full_name': ?fullName,
        'profile_photo_uri': ?profilePhotoUri,
        'language': ?language,
        'notification_enabled': ?notificationEnabled,
      },
      accessToken: _requireToken(),
    );
    return CustomerProfile.fromJson(data);
  }
}
