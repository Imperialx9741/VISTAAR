import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'api_exception.dart';

/// Thin JSON HTTP client for the FastAPI backend, matching the standard
/// response envelope every endpoint in api-contracts.md §3 uses:
///
///   {"data": {...}, "error": null, "request_id": "..."}
///   {"data": null, "error": {"code": "...", "message": "..."}, "request_id": "..."}
///
/// Deliberately minimal — no interceptors, no general retry policy.
/// [accessToken], when supplied, adds an `Authorization: Bearer <token>`
/// header — every endpoint past login needs one (`require_driver`/
/// `require_customer`); login itself (`AuthApi`) never passes one, since
/// no session exists yet at that point. `post()`'s [extraHeaders] exists
/// for the rare endpoint that needs something beyond auth — e.g.
/// accept-offer's required `Idempotency-Key` (api-contracts.md §16.3).
///
/// [onAuthInvalid] (ADR-0076, 2026-09-07) is the one exception to "no
/// retry policy": set once by `AuthSession` (main.dart), it's called on
/// an `AUTH_INVALID` response (an expired/revoked access token —
/// `AUTH_REQUIRED`, no token sent at all, is never retried, there being
/// nothing to refresh from context) to obtain a fresh access token via
/// a real refresh-token exchange, then retries the same request exactly
/// once with it. Left `null` (the construction-time default, and every
/// test's own `ApiClient`) means no behavior change at all — the
/// original `AUTH_INVALID` propagates exactly as it always did.
class ApiClient {
  ApiClient({http.Client? httpClient})
    : _httpClient = httpClient ?? http.Client();

  final http.Client _httpClient;

  Future<String?> Function()? onAuthInvalid;

  Future<Map<String, dynamic>> get(String path, {String? accessToken}) {
    return _withAuthRetry(
      accessToken,
      (token) => _rawGet(path, accessToken: token),
    );
  }

  Future<Map<String, dynamic>> post(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
    Map<String, String>? extraHeaders,
  }) {
    return _withAuthRetry(
      accessToken,
      (token) => _rawPost(
        path,
        body: body,
        accessToken: token,
        extraHeaders: extraHeaders,
      ),
    );
  }

  Future<Map<String, dynamic>> patch(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
  }) {
    return _withAuthRetry(
      accessToken,
      (token) => _rawPatch(path, body: body, accessToken: token),
    );
  }

  Future<Map<String, dynamic>> delete(String path, {String? accessToken}) {
    return _withAuthRetry(
      accessToken,
      (token) => _rawDelete(path, accessToken: token),
    );
  }

  /// [attempt] is called with [accessToken] first; if that raises
  /// `AUTH_INVALID` and both [onAuthInvalid] is set and [accessToken]
  /// was non-null (nothing to refresh from a call that never had a
  /// token to begin with), calls it for a fresh token and retries
  /// [attempt] exactly once with that instead. Any other exception, or
  /// a `null` refresh result (refresh itself failed), propagates the
  /// original error unchanged.
  Future<Map<String, dynamic>> _withAuthRetry(
    String? accessToken,
    Future<Map<String, dynamic>> Function(String? token) attempt,
  ) async {
    try {
      return await attempt(accessToken);
    } on ApiException catch (error) {
      final refresh = onAuthInvalid;
      if (error.code != 'AUTH_INVALID' || accessToken == null || refresh == null) {
        rethrow;
      }
      final newToken = await refresh();
      if (newToken == null) rethrow;
      return attempt(newToken);
    }
  }

  Future<Map<String, dynamic>> _rawGet(
    String path, {
    String? accessToken,
  }) async {
    final Uri uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    final http.Response response;
    try {
      response = await _httpClient.get(
        uri,
        headers: {
          if (accessToken != null) 'Authorization': 'Bearer $accessToken',
        },
      );
    } on Object catch (error) {
      throw ApiException(
        code: 'NETWORK_ERROR',
        message: 'Could not reach the server: $error',
      );
    }

    return _decodeEnvelope(response);
  }

  Future<Map<String, dynamic>> _rawPost(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
    Map<String, String>? extraHeaders,
  }) async {
    final Uri uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    final http.Response response;
    try {
      response = await _httpClient.post(
        uri,
        headers: {
          'Content-Type': 'application/json',
          if (accessToken != null) 'Authorization': 'Bearer $accessToken',
          ...?extraHeaders,
        },
        body: jsonEncode(body),
      );
    } on Object catch (error) {
      throw ApiException(
        code: 'NETWORK_ERROR',
        message: 'Could not reach the server: $error',
      );
    }

    return _decodeEnvelope(response);
  }

  Future<Map<String, dynamic>> _rawPatch(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
  }) async {
    final Uri uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    final http.Response response;
    try {
      response = await _httpClient.patch(
        uri,
        headers: {
          'Content-Type': 'application/json',
          if (accessToken != null) 'Authorization': 'Bearer $accessToken',
        },
        body: jsonEncode(body),
      );
    } on Object catch (error) {
      throw ApiException(
        code: 'NETWORK_ERROR',
        message: 'Could not reach the server: $error',
      );
    }

    return _decodeEnvelope(response);
  }

  Future<Map<String, dynamic>> _rawDelete(
    String path, {
    String? accessToken,
  }) async {
    final Uri uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    final http.Response response;
    try {
      response = await _httpClient.delete(
        uri,
        headers: {
          if (accessToken != null) 'Authorization': 'Bearer $accessToken',
        },
      );
    } on Object catch (error) {
      throw ApiException(
        code: 'NETWORK_ERROR',
        message: 'Could not reach the server: $error',
      );
    }

    return _decodeEnvelope(response);
  }

  Map<String, dynamic> _decodeEnvelope(http.Response response) {
    late final Map<String, dynamic> envelope;
    try {
      envelope = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException(
        code: 'UNKNOWN_ERROR',
        message: 'Unexpected server response (HTTP ${response.statusCode}).',
      );
    }

    final Object? error = envelope['error'];
    if (error is Map<String, dynamic>) {
      throw ApiException(
        code: (error['code'] as String?) ?? 'UNKNOWN_ERROR',
        message: (error['message'] as String?) ?? 'Something went wrong.',
        details: error['details'] as Map<String, dynamic>?,
      );
    }

    return (envelope['data'] as Map<String, dynamic>?) ?? const {};
  }

  void close() => _httpClient.close();
}
