// Unit tests for PushNotificationManager (ADR-0052, build order step
// 11): permission handling, real-token registration, token-refresh
// re-registration, unregister-on-stop, and that every failure mode is
// genuinely best-effort (never propagates).
//
// Every actual Firebase call is injected (see that class's own doc
// comment) — no real `FirebaseMessaging` instance is ever touched here,
// since no widget/unit test in this app can reach the native platform
// channel it needs. `NotificationApi` itself is exercised for real,
// against `http`'s own `MockClient`, same convention
// notification_api_test.dart already established.

import 'dart:async';
import 'dart:convert';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/notification_api.dart';
import 'package:vistaar_mobile/core/notifications/push_notification_manager.dart';

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

NotificationSettings _settings(AuthorizationStatus status) =>
    NotificationSettings(
      alert: AppleNotificationSetting.disabled,
      announcement: AppleNotificationSetting.disabled,
      authorizationStatus: status,
      badge: AppleNotificationSetting.disabled,
      carPlay: AppleNotificationSetting.disabled,
      lockScreen: AppleNotificationSetting.disabled,
      notificationCenter: AppleNotificationSetting.disabled,
      showPreviews: AppleShowPreviewSetting.never,
      timeSensitive: AppleNotificationSetting.disabled,
      criticalAlert: AppleNotificationSetting.disabled,
      sound: AppleNotificationSetting.disabled,
      providesAppNotificationSettings: AppleNotificationSetting.disabled,
    );

RemoteMessage _message(String id) => RemoteMessage(messageId: id);

NotificationApi _notificationApi(http.Client mockHttpClient) =>
    NotificationApi(ApiClient(httpClient: mockHttpClient), () => 'user-token');

void main() {
  test('a denied permission never registers a device', () async {
    var registerCalled = false;
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient((_) async {
          registerCalled = true;
          return http.Response('unused', 500);
        }),
      ),
      requestPermission: () async => _settings(AuthorizationStatus.denied),
      getToken: () async => 'a-real-token',
    );

    await manager.start();

    expect(registerCalled, isFalse);
  });

  test(
    'an authorized permission with a real token registers the device',
    () async {
      Map<String, dynamic>? capturedBody;
      final manager = PushNotificationManager(
        notificationApi: _notificationApi(
          MockClient((request) async {
            capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              _envelope({
                'device_id': 'device-1',
                'platform': 'ANDROID',
                'token': 'a-real-token',
              }),
              201,
            );
          }),
        ),
        requestPermission: () async =>
            _settings(AuthorizationStatus.authorized),
        getToken: () async => 'a-real-token',
        platformName: () => 'ANDROID',
      );

      await manager.start();

      expect(capturedBody, {'platform': 'ANDROID', 'token': 'a-real-token'});
    },
  );

  test('a provisional (iOS) authorization also registers the device', () async {
    var registerCalled = false;
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient((_) async {
          registerCalled = true;
          return http.Response(
            _envelope({
              'device_id': 'device-1',
              'platform': 'IOS',
              'token': 'a-real-token',
            }),
            201,
          );
        }),
      ),
      requestPermission: () async => _settings(AuthorizationStatus.provisional),
      getToken: () async => 'a-real-token',
      platformName: () => 'IOS',
    );

    await manager.start();

    expect(registerCalled, isTrue);
  });

  test('authorized but no token yet does not register', () async {
    var registerCalled = false;
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient((_) async {
          registerCalled = true;
          return http.Response('unused', 500);
        }),
      ),
      requestPermission: () async => _settings(AuthorizationStatus.authorized),
      getToken: () async => null,
    );

    await manager.start();

    expect(registerCalled, isFalse);
  });

  test('a refreshed token re-registers the device', () async {
    final registeredTokens = <String>[];
    final refreshController = StreamController<String>();
    addTearDown(refreshController.close);
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient((request) async {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          registeredTokens.add(body['token'] as String);
          return http.Response(
            _envelope({
              'device_id': 'device-1',
              'platform': 'ANDROID',
              'token': body['token'],
            }),
            201,
          );
        }),
      ),
      requestPermission: () async => _settings(AuthorizationStatus.authorized),
      getToken: () async => 'initial-token',
      onTokenRefresh: () => refreshController.stream,
    );

    await manager.start();
    refreshController.add('refreshed-token');
    // The refresh listener is async — pump the event loop once.
    await Future<void>.delayed(Duration.zero);

    expect(registeredTokens, ['initial-token', 'refreshed-token']);
  });

  test('a backend error while registering is swallowed, not thrown', () async {
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient(
          (_) async => http.Response(
            _errorEnvelope('VALIDATION_FAILED', 'Unsupported platform.'),
            422,
          ),
        ),
      ),
      requestPermission: () async => _settings(AuthorizationStatus.authorized),
      getToken: () async => 'a-real-token',
    );

    await expectLater(manager.start(), completes);
  });

  test('requestPermission itself throwing is swallowed, not thrown', () async {
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient((_) async => http.Response('', 500)),
      ),
      requestPermission: () async => throw StateError('no Play Services'),
    );

    await expectLater(manager.start(), completes);
  });

  test(
    'start() called twice does not double-register on a later refresh',
    () async {
      // .broadcast() — matches the real FirebaseMessaging.onTokenRefresh,
      // which supports being listened to more than once over the app's
      // lifetime (a plain single-subscription controller would throw
      // "Stream has already been listened to" on the second start()'s
      // listen() call, even though the first subscription was already
      // cancelled — not representative of the real stream's behavior).
      var registerCount = 0;
      final refreshController = StreamController<String>.broadcast();
      addTearDown(refreshController.close);
      final manager = PushNotificationManager(
        notificationApi: _notificationApi(
          MockClient((_) async {
            registerCount++;
            return http.Response(
              _envelope({
                'device_id': 'device-1',
                'platform': 'ANDROID',
                'token': 'token',
              }),
              201,
            );
          }),
        ),
        requestPermission: () async =>
            _settings(AuthorizationStatus.authorized),
        getToken: () async => 'token',
        onTokenRefresh: () => refreshController.stream,
      );

      await manager.start(); // registers once (initial token)
      await manager.start(); // registers again (initial token) — 2 so far
      refreshController.add('refreshed');
      await Future<void>.delayed(Duration.zero);

      // Exactly one refresh-triggered registration, not two — the first
      // start()'s subscription was cancelled by the second start(), so
      // only the second one's listener is still live.
      expect(registerCount, 3);
    },
  );

  test('a granted permission subscribes to foreground/opened-app messages, '
      'and an event on each does not throw', () async {
    final onMessageController = StreamController<RemoteMessage>.broadcast();
    final onOpenedController = StreamController<RemoteMessage>.broadcast();
    addTearDown(onMessageController.close);
    addTearDown(onOpenedController.close);
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient(
          (_) async => http.Response(
            _envelope({
              'device_id': 'device-1',
              'platform': 'ANDROID',
              'token': 'token',
            }),
            201,
          ),
        ),
      ),
      requestPermission: () async => _settings(AuthorizationStatus.authorized),
      getToken: () async => null,
      onMessage: () => onMessageController.stream,
      onMessageOpenedApp: () => onOpenedController.stream,
    );

    await manager.start();
    onMessageController.add(_message('msg-1'));
    onOpenedController.add(_message('msg-2'));
    await Future<void>.delayed(Duration.zero);

    // No assertion beyond "didn't throw" — PushNotificationManager's
    // own doc comment explains why the handling here is deliberately
    // just a debug log, not real UI: no notification content/target
    // has ever been designed for this app to act on.
  });

  test('stop() unregisters the current token and deletes it locally', () async {
    String? unregisteredToken;
    var deleteTokenCalled = false;
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient((request) async {
          unregisteredToken = request.url.pathSegments.last;
          return http.Response(_envelope({'status': 'UNREGISTERED'}), 200);
        }),
      ),
      requestPermission: () async => _settings(AuthorizationStatus.authorized),
      getToken: () async => 'current-token',
      deleteToken: () async => deleteTokenCalled = true,
    );

    await manager.stop();

    expect(unregisteredToken, 'current-token');
    expect(deleteTokenCalled, isTrue);
  });

  test(
    'stop() with no current token still deletes locally, no crash',
    () async {
      var unregisterCalled = false;
      var deleteTokenCalled = false;
      final manager = PushNotificationManager(
        notificationApi: _notificationApi(
          MockClient((_) async {
            unregisterCalled = true;
            return http.Response('unused', 500);
          }),
        ),
        getToken: () async => null,
        deleteToken: () async => deleteTokenCalled = true,
      );

      await manager.stop();

      expect(unregisterCalled, isFalse);
      expect(deleteTokenCalled, isTrue);
    },
  );

  test('stop() swallows a backend error rather than throwing', () async {
    final manager = PushNotificationManager(
      notificationApi: _notificationApi(
        MockClient(
          (_) async => http.Response(
            _errorEnvelope('AUTH_REQUIRED', 'Not signed in.'),
            401,
          ),
        ),
      ),
      getToken: () async => 'current-token',
    );

    await expectLater(manager.stop(), completes);
  });
}
