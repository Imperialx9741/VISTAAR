// Unit tests for ApiClient's onAuthInvalid retry mechanism (ADR-0076,
// 2026-09-07) — see that class's own doc comment for why this exists.
// AuthSession's own wiring/single-flight behavior is covered separately
// in test/widget_test.dart's AuthSession tests; this file exercises
// ApiClient's side of the contract in isolation, via a plain injected
// callback rather than a real AuthSession.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/api_exception.dart';

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

void main() {
  test(
    'a successful call never invokes onAuthInvalid',
    () async {
      var refreshCalls = 0;
      final client = ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(_envelope({'ok': true}), 200),
        ),
      )..onAuthInvalid = () async {
        refreshCalls++;
        return 'new-token';
      };

      final data = await client.get('/x', accessToken: 'old-token');

      expect(data['ok'], true);
      expect(refreshCalls, 0);
    },
  );

  test(
    'AUTH_INVALID refreshes once and retries with the new token',
    () async {
      final seenTokens = <String?>[];
      final client = ApiClient(
        httpClient: MockClient((request) async {
          final token = request.headers['Authorization'];
          seenTokens.add(token);
          if (token == 'Bearer old-token') {
            return http.Response(
              _errorEnvelope('AUTH_INVALID', 'Token expired.'),
              401,
            );
          }
          return http.Response(_envelope({'ok': true}), 200);
        }),
      )..onAuthInvalid = () async => 'new-token';

      final data = await client.get('/x', accessToken: 'old-token');

      expect(data['ok'], true);
      expect(seenTokens, ['Bearer old-token', 'Bearer new-token']);
    },
  );

  test(
    'AUTH_INVALID with a failed refresh (null) surfaces the original error',
    () async {
      var attempts = 0;
      final client = ApiClient(
        httpClient: MockClient((_) async {
          attempts++;
          return http.Response(
            _errorEnvelope('AUTH_INVALID', 'Token expired.'),
            401,
          );
        }),
      )..onAuthInvalid = () async => null;

      await expectLater(
        client.get('/x', accessToken: 'old-token'),
        throwsA(
          isA<ApiException>().having((e) => e.code, 'code', 'AUTH_INVALID'),
        ),
      );
      // Never retried — the failed refresh short-circuits immediately.
      expect(attempts, 1);
    },
  );

  test(
    'AUTH_INVALID with no onAuthInvalid set surfaces the original error',
    () async {
      final client = ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(
            _errorEnvelope('AUTH_INVALID', 'Token expired.'),
            401,
          ),
        ),
      );

      await expectLater(
        client.get('/x', accessToken: 'old-token'),
        throwsA(
          isA<ApiException>().having((e) => e.code, 'code', 'AUTH_INVALID'),
        ),
      );
    },
  );

  test(
    'AUTH_INVALID on a call with no accessToken is never retried',
    () async {
      var refreshCalls = 0;
      final client = ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(
            _errorEnvelope('AUTH_INVALID', 'Token expired.'),
            401,
          ),
        ),
      )..onAuthInvalid = () async {
        refreshCalls++;
        return 'new-token';
      };

      await expectLater(
        client.get('/x'),
        throwsA(
          isA<ApiException>().having((e) => e.code, 'code', 'AUTH_INVALID'),
        ),
      );
      expect(refreshCalls, 0);
    },
  );

  test(
    'a non-AUTH_INVALID error never triggers a refresh',
    () async {
      var refreshCalls = 0;
      final client = ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(
            _errorEnvelope('VALIDATION_FAILED', 'Bad input.'),
            422,
          ),
        ),
      )..onAuthInvalid = () async {
        refreshCalls++;
        return 'new-token';
      };

      await expectLater(
        client.get('/x', accessToken: 'old-token'),
        throwsA(
          isA<ApiException>().having((e) => e.code, 'code', 'VALIDATION_FAILED'),
        ),
      );
      expect(refreshCalls, 0);
    },
  );

  test(
    'post()/patch()/delete() retry on AUTH_INVALID the same way get() does',
    () async {
      final client = ApiClient(
        httpClient: MockClient((request) async {
          final token = request.headers['Authorization'];
          if (token == 'Bearer old-token') {
            return http.Response(
              _errorEnvelope('AUTH_INVALID', 'Token expired.'),
              401,
            );
          }
          return http.Response(_envelope({'ok': true}), 200);
        }),
      )..onAuthInvalid = () async => 'new-token';

      final postResult = await client.post(
        '/x',
        body: const {},
        accessToken: 'old-token',
      );
      final patchResult = await client.patch(
        '/x',
        body: const {},
        accessToken: 'old-token',
      );
      final deleteResult = await client.delete('/x', accessToken: 'old-token');

      expect(postResult['ok'], true);
      expect(patchResult['ok'], true);
      expect(deleteResult['ok'], true);
    },
  );
}
