import 'dart:async';
import 'dart:io' show Platform;

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show kIsWeb, debugPrint;

import '../api/notification_api.dart';

/// Push notifications (ADR-0052, build order step 9/11) — the real FCM
/// half `NotificationApi`'s own doc comment said was still missing:
/// permission, a real device token, and wiring both device-token
/// endpoints to it. `NotificationApi` itself is untouched — this class
/// is the only thing composed on top of it.
///
/// Every actual Firebase call is behind an injected closure (all
/// optional, defaulting to the real `FirebaseMessaging.instance` calls)
/// — the same "constructor-injected dependency, real implementation by
/// default" shape every other API class in this app already uses
/// (`RideApi`'s own `_accessToken` closure, for instance). This is what
/// makes [start]/[stop] genuinely unit-testable without ever touching
/// the real Firebase SDK (which needs a native platform channel no
/// widget test here can provide) — tests substitute plain closures,
/// mirroring `geolocator`'s own `GeolocatorPlatform.instance` testing
/// seam used elsewhere in this app, just via plain DI instead of a
/// package-provided fake platform.
///
/// Deliberately minimal on the receiving side: [start] wires
/// `FirebaseMessaging.onMessage`/`onMessageOpenedApp`, but neither does
/// anything beyond a debug log — no in-app banner, no tap-to-navigate
/// routing. No notification template/content/target screen has ever
/// been designed for any push this backend could send (`PUSH_PROVIDER`
/// still defaults to `dev` server-side; nothing has ever sent a real
/// payload) — building UI around content that doesn't exist yet would
/// be inventing a design, not implementing one.
class PushNotificationManager {
  PushNotificationManager({
    required NotificationApi notificationApi,
    Future<NotificationSettings> Function()? requestPermission,
    Future<String?> Function()? getToken,
    Stream<String> Function()? onTokenRefresh,
    Future<void> Function()? deleteToken,
    Stream<RemoteMessage> Function()? onMessage,
    Stream<RemoteMessage> Function()? onMessageOpenedApp,
    String Function()? platformName,
  }) : // The public constructor parameter is deliberately named
       // `notificationApi` (not `_notificationApi`) — call sites
       // shouldn't have to spell a private field name to construct
       // this class, same precedent AuthSession's own constructor
       // already established.
       // ignore: prefer_initializing_formals
       _notificationApi = notificationApi,
       _requestPermission =
           requestPermission ??
           (() => FirebaseMessaging.instance.requestPermission()),
       _getToken = getToken ?? (() => FirebaseMessaging.instance.getToken()),
       _onTokenRefresh =
           onTokenRefresh ?? (() => FirebaseMessaging.instance.onTokenRefresh),
       _deleteToken =
           deleteToken ?? (() => FirebaseMessaging.instance.deleteToken()),
       _onMessage = onMessage ?? (() => FirebaseMessaging.onMessage),
       _onMessageOpenedApp =
           onMessageOpenedApp ?? (() => FirebaseMessaging.onMessageOpenedApp),
       _platformName = platformName ?? _defaultPlatformName;

  final NotificationApi _notificationApi;
  final Future<NotificationSettings> Function() _requestPermission;
  final Future<String?> Function() _getToken;
  final Stream<String> Function() _onTokenRefresh;
  final Future<void> Function() _deleteToken;
  final Stream<RemoteMessage> Function() _onMessage;
  final Stream<RemoteMessage> Function() _onMessageOpenedApp;
  final String Function() _platformName;

  StreamSubscription<String>? _tokenRefreshSubscription;
  StreamSubscription<RemoteMessage>? _onMessageSubscription;
  StreamSubscription<RemoteMessage>? _onMessageOpenedAppSubscription;

  /// Requests notification permission, registers the current device
  /// token if granted, and starts listening for a refreshed token (an
  /// FCM token can change at any time — a new install, an app
  /// reinstall, cleared app data — api-contracts.md never documented
  /// this because no mobile client existed yet to need it) and for
  /// incoming messages. Best-effort throughout: a denied permission, a
  /// `null` token (both real, expected outcomes — an emulator/simulator
  /// without Play Services or APNs, a user declining the system
  /// prompt), or any Firebase/network failure is swallowed, never
  /// surfaced to the caller — push notifications are an enhancement,
  /// never a reason to block or crash sign-in/the home screen. Safe to
  /// call more than once (e.g. sign out then sign back in within the
  /// same app run) — always cancels its own previous subscriptions
  /// first.
  Future<void> start() async {
    await _cancelSubscriptions();
    try {
      final settings = await _requestPermission();
      final authorized =
          settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional;
      if (!authorized) return;

      final token = await _getToken();
      if (token != null) {
        await _registerBestEffort(token);
      }

      _tokenRefreshSubscription = _onTokenRefresh().listen(
        (newToken) => unawaited(_registerBestEffort(newToken)),
      );
      _onMessageSubscription = _onMessage().listen(
        (message) => debugPrint(
          'PushNotificationManager: foreground message ${message.messageId}',
        ),
      );
      _onMessageOpenedAppSubscription = _onMessageOpenedApp().listen(
        (message) => debugPrint(
          'PushNotificationManager: notification opened ${message.messageId}',
        ),
      );
    } on Object {
      // See doc comment above — best-effort.
    }
  }

  Future<void> _registerBestEffort(String token) async {
    try {
      await _notificationApi.registerDevice(
        platform: _platformName(),
        token: token,
      );
    } on Object {
      // Best-effort — same reasoning as start() itself.
    }
  }

  /// Unregisters the current device token
  /// (`DELETE /api/v1/notifications/me/devices/{token}`) and stops
  /// listening for further token refreshes/messages. Must be called
  /// *before* `AuthSession.signOut()` clears the access token this
  /// still needs — see `UserHomeScreen`/`SarthiHomeScreen`'s own
  /// `_signOut()`. Also calls Firebase's own `deleteToken()` so a fresh
  /// token is generated the next time someone signs in on this device
  /// (correct behavior for switching accounts on a shared device, not
  /// just cleanup). Best-effort, same reasoning as [start] — sign-out
  /// itself must never be blocked or fail because of this.
  Future<void> stop() async {
    await _cancelSubscriptions();
    try {
      final token = await _getToken();
      if (token != null) {
        await _notificationApi.unregisterDevice(token);
      }
      await _deleteToken();
    } on Object {
      // Best-effort — see doc comment above.
    }
  }

  Future<void> _cancelSubscriptions() async {
    await _tokenRefreshSubscription?.cancel();
    await _onMessageSubscription?.cancel();
    await _onMessageOpenedAppSubscription?.cancel();
    _tokenRefreshSubscription = null;
    _onMessageSubscription = null;
    _onMessageOpenedAppSubscription = null;
  }

  /// Matches `modules.notification.domain.entities.Platform`'s exactly
  /// three wire values (backend `modules/notification/domain/
  /// entities.py`) — ANDROID/IOS/WEB, no "other" case needed. `kIsWeb`
  /// is checked first: `dart:io`'s `Platform.isIOS`/`isAndroid` throw
  /// on web (no underlying OS to report), so it must never be reached
  /// there.
  static String _defaultPlatformName() {
    if (kIsWeb) return 'WEB';
    if (Platform.isIOS) return 'IOS';
    return 'ANDROID';
  }
}
