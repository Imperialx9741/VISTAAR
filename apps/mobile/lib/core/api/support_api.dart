import 'api_client.dart';
import 'api_exception.dart';

/// One row of a support case's message thread — the shape both Create
/// Support Case's implicit first message and Get Support Case's
/// `messages` array share (api-contracts.md §44).
class SupportMessage {
  const SupportMessage({
    required this.senderType,
    required this.senderId,
    required this.message,
    required this.createdAt,
  });

  factory SupportMessage.fromJson(Map<String, dynamic> json) => SupportMessage(
    senderType: json['sender_type'] as String,
    senderId: json['sender_id'] as String?,
    message: json['message'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
  );

  /// `"CUSTOMER"`, `"DRIVER"`, `"ADMIN"`, or `"AI"` (the last never
  /// actually produced anywhere — AI Support is BLOCKED, ADR-0022
  /// Decision 4).
  final String senderType;
  final String? senderId;
  final String message;
  final DateTime createdAt;
}

/// A support case (api-contracts.md §44, ADR-0022). `messages` is empty
/// on the result of [SupportApi.createCase] — the create response
/// doesn't echo the thread back (verified directly against
/// `modules/support/router.py`'s `_case_data()`) — and populated once
/// [SupportApi.getCase] is called, which this app always does right
/// after creating a case to show the thread including that first
/// message.
class SupportCase {
  const SupportCase({
    required this.caseId,
    required this.rideId,
    required this.category,
    required this.priority,
    required this.status,
    required this.createdAt,
    required this.messages,
  });

  factory SupportCase.fromJson(Map<String, dynamic> json) => SupportCase(
    caseId: json['case_id'] as String,
    rideId: json['ride_id'] as String?,
    category: json['category'] as String?,
    priority: json['priority'] as String,
    status: json['status'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
    messages: (json['messages'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(SupportMessage.fromJson)
        .toList(growable: false),
  );

  final String caseId;
  final String? rideId;
  final String? category;
  final String priority;
  final String status;
  final DateTime createdAt;
  final List<SupportMessage> messages;
}

/// One page of `GET /api/v1/support/cases` (api-contracts.md §44,
/// added 2026-09-04 — the previously-missing list endpoint).
class SupportCasePage {
  const SupportCasePage({
    required this.items,
    required this.page,
    required this.totalPages,
  });

  final List<SupportCase> items;
  final int page;
  final int totalPages;

  bool get hasMore => page < totalPages;
}

/// Calls the three live Support endpoints (api-contracts.md §44,
/// ADR-0022): Create, List (own cases only, added 2026-09-04), and
/// Get-by-id. Posting a follow-up message still has no endpoint
/// (Assign/Resolve/PostMessage are all undocumented at the HTTP layer,
/// same ADR — genuinely decision-required, not built here) — a case's
/// thread can be viewed but not replied to from this app.
class SupportApi {
  SupportApi(this._client, this._accessToken);

  final ApiClient _client;
  final String? Function() _accessToken;

  String _requireToken() {
    final token = _accessToken();
    if (token == null) {
      throw ApiException(code: 'AUTH_REQUIRED', message: 'Not signed in.');
    }
    return token;
  }

  Future<SupportCase> createCase({
    String? category,
    String? rideId,
    required String message,
  }) async {
    final data = await _client.post(
      '/api/v1/support/cases',
      body: {'message': message, 'category': ?category, 'ride_id': ?rideId},
      accessToken: _requireToken(),
    );
    return SupportCase.fromJson(data);
  }

  Future<SupportCase> getCase(String caseId) async {
    final data = await _client.get(
      '/api/v1/support/cases/$caseId',
      accessToken: _requireToken(),
    );
    return SupportCase.fromJson(data);
  }

  /// The caller's own cases, newest first. [status], when supplied,
  /// must be one of CaseStatus's documented values (state-machines.md
  /// §46) — an unknown value is rejected server-side with
  /// `VALIDATION_FAILED`, surfaced as an [ApiException] like any other
  /// backend error.
  Future<SupportCasePage> listCases({
    String? status,
    int page = 1,
    int pageSize = 20,
  }) async {
    final query = {
      'status': ?status,
      'page': '$page',
      'page_size': '$pageSize',
    };
    final path =
        '/api/v1/support/cases?${Uri(queryParameters: query).query}';
    final data = await _client.get(path, accessToken: _requireToken());
    final items = (data['items'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(SupportCase.fromJson)
        .toList(growable: false);
    final pagination = data['pagination'] as Map<String, dynamic>;
    return SupportCasePage(
      items: items,
      page: pagination['page'] as int,
      totalPages: pagination['total_pages'] as int,
    );
  }
}
