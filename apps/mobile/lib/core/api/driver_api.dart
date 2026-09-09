import 'api_client.dart';
import 'api_exception.dart';
import 'upload_target.dart';

/// A Sarthi's own profile (api-contracts.md §9, ADR-0004).
class DriverProfile {
  const DriverProfile({
    required this.driverId,
    required this.fullName,
    required this.verificationStatus,
    required this.operationalStatus,
    required this.strikes,
  });

  factory DriverProfile.fromJson(Map<String, dynamic> json) => DriverProfile(
    driverId: json['driver_id'] as String,
    fullName: json['full_name'] as String,
    verificationStatus: json['verification_status'] as String,
    operationalStatus: json['operational_status'] as String,
    strikes: json['strikes'] as int,
  );

  final String driverId;
  final String fullName;

  /// `"PENDING"` | `"APPROVED"` | `"REJECTED"` (state-machines.md §67).
  final String verificationStatus;
  final String operationalStatus;
  final int strikes;

  bool get isApproved => verificationStatus == 'APPROVED';
}

/// One driver.documents row (api-contracts.md §9, ADR-0072's List
/// endpoint added 2026-09-04). `documentNumber`/`evidenceUri`/
/// `expiresAt` are all optional, matching the backend's own opaque,
/// unvalidated `document_type` treatment (ADR-0007 — never a canonical
/// vocabulary here either).
class DriverDocument {
  const DriverDocument({
    required this.documentId,
    required this.documentType,
    required this.documentNumber,
    required this.evidenceUri,
    required this.verificationStatus,
    required this.expiresAt,
    required this.createdAt,
  });

  factory DriverDocument.fromJson(Map<String, dynamic> json) => DriverDocument(
    documentId: json['document_id'] as String,
    documentType: json['document_type'] as String,
    documentNumber: json['document_number'] as String?,
    evidenceUri: json['evidence_uri'] as String?,
    verificationStatus: json['verification_status'] as String,
    expiresAt: json['expires_at'] == null
        ? null
        : DateTime.parse(json['expires_at'] as String),
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  final String documentId;
  final String documentType;
  final String? documentNumber;
  final String? evidenceUri;

  /// `"PENDING"` | `"APPROVED"` | `"REJECTED"`.
  final String verificationStatus;
  final DateTime? expiresAt;
  final DateTime createdAt;
}

/// One `penalty.strikes` row (api-contracts.md §9, ADR-0073's List My
/// Strikes endpoint added 2026-09-04) — the self-service counterpart to
/// the admin-only Driver Strike History (§46.18). `reason` is whatever
/// free text the driver themselves entered when cancelling (BR-068) —
/// not a fixed vocabulary.
class Strike {
  const Strike({
    required this.strikeId,
    required this.rideId,
    required this.reason,
    required this.createdAt,
  });

  factory Strike.fromJson(Map<String, dynamic> json) => Strike(
    strikeId: json['strike_id'] as String,
    rideId: json['ride_id'] as String?,
    reason: json['reason'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  final String strikeId;
  final String? rideId;
  final String reason;
  final DateTime createdAt;
}

/// One page of `GET /api/v1/drivers/me/strikes` (§50's shared
/// pagination shape).
class StrikePage {
  const StrikePage({required this.items, required this.page, required this.totalPages});

  final List<Strike> items;
  final int page;
  final int totalPages;

  bool get hasMore => page < totalPages;
}

/// Calls the driver profile/document endpoints (api-contracts.md §9).
/// `SubmitDriverDocumentBody`'s `evidence_uri` is a plain opaque string
/// — [requestUploadUrl] (`POST /me/uploads`, ADR-0031/ADR-0065) is the
/// real presigned-S3-upload target a picked photo is sent to first
/// (`EvidenceUploadService`, 2026-09-04); this same endpoint also backs
/// vehicle-document evidence (`VehicleApi.submitDocument`) — there is
/// no separate vehicle-scoped upload endpoint anywhere in the backend.
class DriverApi {
  DriverApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  /// Throws [ApiException] with code `RESOURCE_NOT_FOUND` if no profile
  /// has been created yet (api-contracts.md §9 — unlike the customer
  /// equivalent, this does not auto-provision).
  Future<DriverProfile> getProfile() async {
    final data = await _client.get('/api/v1/drivers/me', accessToken: _requireToken());
    return DriverProfile.fromJson(data);
  }

  /// `fullName` is required only on the very first call (creates the
  /// profile) — optional thereafter (PATCH semantics).
  Future<DriverProfile> updateProfile({String? fullName}) async {
    final data = await _client.patch(
      '/api/v1/drivers/me',
      body: {'full_name': ?fullName},
      accessToken: _requireToken(),
    );
    return DriverProfile.fromJson(data);
  }

  Future<DriverDocument> submitDocument({
    required String documentType,
    String? documentNumber,
    String? evidenceUri,
  }) async {
    final data = await _client.post(
      '/api/v1/drivers/me/documents',
      body: {
        'document_type': documentType,
        'document_number': ?documentNumber,
        'evidence_uri': ?evidenceUri,
      },
      accessToken: _requireToken(),
    );
    return DriverDocument.fromJson(data);
  }

  Future<List<DriverDocument>> listDocuments() async {
    final data = await _client.get(
      '/api/v1/drivers/me/documents',
      accessToken: _requireToken(),
    );
    return (data['documents'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(DriverDocument.fromJson)
        .toList(growable: false);
  }

  /// Request Upload URL (api-contracts.md §9, ADR-0031/ADR-0065) —
  /// [contentType] must be one of `image/jpeg`, `image/png`,
  /// `image/webp`, `application/pdf`.
  Future<UploadTarget> requestUploadUrl({required String contentType}) async {
    final data = await _client.post(
      '/api/v1/drivers/me/uploads',
      body: {'content_type': contentType},
      accessToken: _requireToken(),
    );
    return UploadTarget.fromJson(data);
  }

  Future<StrikePage> listStrikes({int page = 1}) async {
    final data = await _client.get(
      '/api/v1/drivers/me/strikes?page=$page',
      accessToken: _requireToken(),
    );
    final items = (data['items'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(Strike.fromJson)
        .toList(growable: false);
    final pagination = data['pagination'] as Map<String, dynamic>;
    return StrikePage(
      items: items,
      page: pagination['page'] as int,
      totalPages: pagination['total_pages'] as int,
    );
  }
}
