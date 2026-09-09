// Unit tests for NotificationApi (build order step 9 —
// docs/16-mobile/mobile-app-implementation-plan.md §6.3): request
// shape and response parsing for both device-token endpoints
// (ADR-0052). A plain-Dart `test()` suite, not `testWidgets()` — this
// class has no screen wired to it yet (NotificationApi's own doc
// comment explains why), so there is nothing to pump; the backend is
// still mocked via `http`'s own `MockClient`, same as every widget
// test in this app.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/api_exception.dart';
import 'package:vistaar_mobile/core/api/notification_api.dart';

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

void main() {
  test('registerDevice sends platform/token and parses the response', () async {
    Map<String, dynamic>? capturedBody;
    String? capturedAuth;
    final api = NotificationApi(
      ApiClient(
        httpClient: MockClient((request) async {
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          capturedAuth = request.headers['Authorization'];
          return http.Response(
            _envelope({
              'device_id': 'device-1',
              'platform': 'ANDROID',
              'token': 'fcm-token-1',
              'created_at': '2026-08-31T10:00:00Z',
              'updated_at': '2026-08-31T10:00:00Z',
            }),
            201,
          );
        }),
      ),
      () => 'user-token',
    );

    final result = await api.registerDevice(
      platform: 'ANDROID',
      token: 'fcm-token-1',
    );

    expect(capturedBody, {'platform': 'ANDROID', 'token': 'fcm-token-1'});
    expect(capturedAuth, 'Bearer user-token');
    expect(result.deviceId, 'device-1');
    expect(result.platform, 'ANDROID');
    expect(result.token, 'fcm-token-1');
  });

  test(
    'registerDevice without a signed-in session throws AUTH_REQUIRED',
    () async {
      final api = NotificationApi(
        ApiClient(httpClient: MockClient((_) async => http.Response('', 500))),
        () => null,
      );

      await expectLater(
        api.registerDevice(platform: 'IOS', token: 'fcm-token-2'),
        throwsA(
          isA<ApiException>().having((e) => e.code, 'code', 'AUTH_REQUIRED'),
        ),
      );
    },
  );

  test('registerDevice surfaces a backend validation error', () async {
    final api = NotificationApi(
      ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(
            _errorEnvelope('VALIDATION_FAILED', 'Unsupported platform.'),
            422,
          ),
        ),
      ),
      () => 'user-token',
    );

    await expectLater(
      api.registerDevice(platform: 'BAD', token: 'fcm-token-3'),
      throwsA(
        isA<ApiException>().having(
          (e) => e.message,
          'message',
          'Unsupported platform.',
        ),
      ),
    );
  });

  test('unregisterDevice calls DELETE with the token in the path', () async {
    String? capturedMethod;
    String? capturedPath;
    final api = NotificationApi(
      ApiClient(
        httpClient: MockClient((request) async {
          capturedMethod = request.method;
          capturedPath = request.url.path;
          return http.Response(_envelope({'status': 'UNREGISTERED'}), 200);
        }),
      ),
      () => 'sarthi-token',
    );

    await api.unregisterDevice('fcm-token-1');

    expect(capturedMethod, 'DELETE');
    expect(capturedPath, '/api/v1/notifications/me/devices/fcm-token-1');
  });

  test(
    'unregisterDevice is a no-op success even if never registered',
    () async {
      final api = NotificationApi(
        ApiClient(
          httpClient: MockClient(
            (_) async =>
                http.Response(_envelope({'status': 'UNREGISTERED'}), 200),
          ),
        ),
        () => 'sarthi-token',
      );

      await expectLater(api.unregisterDevice('never-registered'), completes);
    },
  );
}
