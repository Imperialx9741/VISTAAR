/// Raised when the backend returns a non-null `error` in the standard
/// VISTAAR response envelope (api-contracts.md §3), or when the HTTP call
/// itself fails (network error, non-2xx with no parseable envelope).
class ApiException implements Exception {
  ApiException({required this.code, required this.message, this.details});

  /// One of api-contracts.md §49's documented error codes (e.g.
  /// `OTP_INVALID`, `OTP_EXPIRED`, `VALIDATION_FAILED`), or
  /// `NETWORK_ERROR`/`UNKNOWN_ERROR` for failures that never reached the
  /// documented envelope shape.
  final String code;
  final String message;

  /// The error envelope's optional `details` field
  /// (shared/api_envelope.py) — null for every error except
  /// `GPS_VERIFICATION_FAILED`, which carries `{"dispute_id": "uuid"}`
  /// (ADR-0032) so the caller can discover and act on the dispute that
  /// same failure just opened.
  final Map<String, dynamic>? details;

  @override
  String toString() => 'ApiException($code): $message';
}
