import 'api_client.dart';
import 'api_exception.dart';

/// Result of `POST /api/v1/rides/{ride_id}/sos` (api-contracts.md §41).
/// `status` is always `"OPEN"` on creation — `Acknowledge`/`Escalate`/
/// `Resolve` (state-machines.md §45) have no documented HTTP endpoint
/// anywhere (ADR-0022 Decision 6, verified directly against
/// `modules/safety/router.py`: only this one route exists), so there is
/// no way for this app to poll an incident's status afterwards — the
/// confirmation this screen shows is the last thing it can ever tell
/// the caller.
class SosResult {
  const SosResult({required this.incidentId, required this.status});

  factory SosResult.fromJson(Map<String, dynamic> json) => SosResult(
    incidentId: json['incident_id'] as String,
    status: json['status'] as String,
  );

  final String incidentId;
  final String status;
}

/// Calls the SOS endpoint (api-contracts.md §41, BR-112). Shared by both
/// roles — "Both customers and drivers must have access to SOS
/// functionality" — the caller just needs to be that ride's customer or
/// driver (`RIDE_NOT_FOUND` otherwise, the same IDOR-safe response used
/// throughout this backend). There is no real emergency-service
/// integration behind this (ADR-0050): triggering it escalates to
/// VISTAAR's own internal safety/call-center team over IN_APP + SMS, not
/// to police or an ambulance directly — this app must never imply
/// otherwise in its own copy.
class SafetyApi {
  SafetyApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<SosResult> triggerSos(
    String rideId, {
    required String incidentType,
    required double latitude,
    required double longitude,
  }) async {
    final data = await _client.post(
      '/api/v1/rides/$rideId/sos',
      body: {
        'incident_type': incidentType,
        'latitude': latitude,
        'longitude': longitude,
      },
      accessToken: _requireToken(),
    );
    return SosResult.fromJson(data);
  }
}
