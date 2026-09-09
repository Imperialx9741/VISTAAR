import 'api_client.dart';
import 'api_exception.dart';

/// One vehicle.vehicles row (api-contracts.md §11).
class Vehicle {
  const Vehicle({
    required this.vehicleId,
    required this.category,
    required this.cabTier,
    required this.registrationNumber,
    required this.verificationStatus,
    required this.operationalStatus,
  });

  factory Vehicle.fromJson(Map<String, dynamic> json) => Vehicle(
    vehicleId: json['vehicle_id'] as String,
    category: json['category'] as String,
    cabTier: json['cab_tier'] as String?,
    registrationNumber: json['registration_number'] as String,
    verificationStatus: json['verification_status'] as String,
    operationalStatus: json['operational_status'] as String,
  );

  final String vehicleId;

  /// `"BIKE"` | `"AUTO"` | `"CAB"`.
  final String category;

  /// Only meaningful (non-null) when [category] is `"CAB"` (ADR-0020
  /// Decision 1) — `"ECO"` | `"PREMIUM"` | `"PREMIUM_PLUS"`.
  final String? cabTier;
  final String registrationNumber;

  /// `"PENDING"` | `"APPROVED"` | `"REJECTED"`.
  final String verificationStatus;

  /// `"INACTIVE"` | `"ACTIVE"` — at most one of a driver's vehicles is
  /// ever ACTIVE (BR-122).
  final String operationalStatus;

  bool get isApproved => verificationStatus == 'APPROVED';
  bool get isActive => operationalStatus == 'ACTIVE';
}

/// One vehicle.documents row (api-contracts.md §11, ADR-0072, added
/// 2026-09-04). No `updatedAt` — see that table's own documented schema
/// (database-design.md §8.2); `VehicleDocument` (backend entity) has no
/// such column either.
class VehicleDocument {
  const VehicleDocument({
    required this.documentId,
    required this.documentType,
    required this.documentNumber,
    required this.evidenceUri,
    required this.verificationStatus,
    required this.expiresAt,
    required this.createdAt,
  });

  factory VehicleDocument.fromJson(Map<String, dynamic> json) => VehicleDocument(
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
  final String verificationStatus;
  final DateTime? expiresAt;
  final DateTime createdAt;
}

/// Calls the vehicle registration/document endpoints (api-contracts.md
/// §11). Activate/Deactivate are deliberately not included here — this
/// client exists for the onboarding flow (register + document
/// submission), not day-to-day vehicle switching, which has no UI yet
/// either.
class VehicleApi {
  VehicleApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<List<Vehicle>> listVehicles() async {
    final data = await _client.get(
      '/api/v1/drivers/me/vehicles',
      accessToken: _requireToken(),
    );
    return (data['vehicles'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(Vehicle.fromJson)
        .toList(growable: false);
  }

  Future<Vehicle> addVehicle({
    required String category,
    String? cabTier,
    required String registrationNumber,
    String? make,
    String? model,
  }) async {
    final data = await _client.post(
      '/api/v1/drivers/me/vehicles',
      body: {
        'category': category,
        'cab_tier': ?cabTier,
        'registration_number': registrationNumber,
        'make': ?make,
        'model': ?model,
      },
      accessToken: _requireToken(),
    );
    return Vehicle.fromJson(data);
  }

  Future<Vehicle> activateVehicle(String vehicleId) async {
    final data = await _client.post(
      '/api/v1/drivers/me/vehicles/$vehicleId/activate',
      body: const {},
      accessToken: _requireToken(),
    );
    return Vehicle.fromJson(data);
  }

  Future<VehicleDocument> submitDocument({
    required String vehicleId,
    required String documentType,
    String? documentNumber,
    String? evidenceUri,
  }) async {
    final data = await _client.post(
      '/api/v1/drivers/me/vehicles/$vehicleId/documents',
      body: {
        'document_type': documentType,
        'document_number': ?documentNumber,
        'evidence_uri': ?evidenceUri,
      },
      accessToken: _requireToken(),
    );
    return VehicleDocument.fromJson(data);
  }

  Future<List<VehicleDocument>> listDocuments(String vehicleId) async {
    final data = await _client.get(
      '/api/v1/drivers/me/vehicles/$vehicleId/documents',
      accessToken: _requireToken(),
    );
    return (data['documents'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(VehicleDocument.fromJson)
        .toList(growable: false);
  }
}
