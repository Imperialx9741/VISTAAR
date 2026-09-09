// Widget tests for VISTAAR's unified login flow (ADR-0027) and session
// persistence: role selection -> location permission -> phone entry ->
// OTP verify -> role-appropriate home screen, and restoring/clearing
// that session across a simulated app restart.
//
// The backend is mocked via `http`'s own `MockClient`, token storage via
// an in-memory [FakeTokenStorage], and location permission via a
// granted-by-default [FakeGeolocatorPlatform] (see test/features/
// location/location_permission_screen_test.dart for that screen's own
// dedicated behavior coverage — these tests only need it to skip
// straight through, since they're testing login, not permission
// handling) — no real network call, no real Postgres/Redis, no platform
// keychain/keystore, and no OS permission dialog required to run these.

import 'dart:convert';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/auth_api.dart';
import 'package:vistaar_mobile/core/api/notification_api.dart';
import 'package:vistaar_mobile/core/api/wallet_api.dart';
import 'package:vistaar_mobile/core/bootstrap/session_bootstrapper.dart';
import 'package:vistaar_mobile/core/notifications/push_notification_manager.dart';
import 'package:vistaar_mobile/core/storage/token_storage.dart';
import 'package:vistaar_mobile/core/theme/app_theme.dart';
import 'package:vistaar_mobile/features/auth/app_role.dart';
import 'package:vistaar_mobile/features/auth/auth_session.dart';

/// A [PushNotificationManager] wired entirely to no-op closures — every
/// real Firebase call is injected (see that class's own doc comment),
/// so this exercises none of the actual Firebase SDK, which no widget
/// test here can reach (no native platform channel). `requestPermission`
/// returning `denied` makes `start()` a no-op past that point; `stop()`
/// only ever calls `getToken`/`deleteToken`, both harmless no-ops below.
PushNotificationManager _fakePushNotificationManager() {
  return PushNotificationManager(
    notificationApi: NotificationApi(ApiClient(), () => null),
    requestPermission: () async => const NotificationSettings(
      alert: AppleNotificationSetting.disabled,
      announcement: AppleNotificationSetting.disabled,
      authorizationStatus: AuthorizationStatus.denied,
      badge: AppleNotificationSetting.disabled,
      carPlay: AppleNotificationSetting.disabled,
      lockScreen: AppleNotificationSetting.disabled,
      notificationCenter: AppleNotificationSetting.disabled,
      showPreviews: AppleShowPreviewSetting.never,
      timeSensitive: AppleNotificationSetting.disabled,
      criticalAlert: AppleNotificationSetting.disabled,
      sound: AppleNotificationSetting.disabled,
      providesAppNotificationSettings: AppleNotificationSetting.disabled,
    ),
    getToken: () async => null,
    deleteToken: () async {},
    onTokenRefresh: () => const Stream<String>.empty(),
    onMessage: () => const Stream<RemoteMessage>.empty(),
    onMessageOpenedApp: () => const Stream<RemoteMessage>.empty(),
  );
}

/// Always reports location as already granted — these tests exercise
/// login, not the permission prompt itself (see location_permission_
/// screen_test.dart for that).
class _GrantedGeolocatorPlatform extends GeolocatorPlatform {
  @override
  Future<LocationPermission> checkPermission() async =>
      LocationPermission.whileInUse;
}

/// In-memory [TokenStorage] — the same "fake implementation of a port"
/// pattern the backend uses throughout (e.g. modules/*/ports.py +
/// tests/test_*_service.py's Fake*Repository classes).
class FakeTokenStorage implements TokenStorage {
  StoredSession? saved;
  int saveCount = 0;
  int clearCount = 0;

  @override
  Future<void> save(StoredSession session) async {
    saved = session;
    saveCount++;
  }

  @override
  Future<StoredSession?> load() async => saved;

  @override
  Future<void> clear() async {
    saved = null;
    clearCount++;
  }
}

/// Builds the same provider tree `VistaarApp` does, but with a
/// [MockClient] standing in for the real HTTP client (matching the
/// backend's documented response envelope, api-contracts.md §3, §6-7)
/// and a [FakeTokenStorage] standing in for the platform keychain.
Widget _testApp({
  required http.Client mockHttpClient,
  required TokenStorage tokenStorage,
}) {
  return MultiProvider(
    providers: [
      Provider<ApiClient>(create: (_) => ApiClient(httpClient: mockHttpClient)),
      ProxyProvider<ApiClient, AuthApi>(
        update: (context, apiClient, previous) => AuthApi(apiClient),
      ),
      Provider<TokenStorage>(create: (_) => tokenStorage),
      ChangeNotifierProvider<AuthSession>(
        create: (context) => AuthSession(
          storage: context.read<TokenStorage>(),
          authApi: context.read<AuthApi>(),
          apiClient: context.read<ApiClient>(),
        ),
      ),
      // SarthiHomeTab's own wallet summary card (Phase 6 of the
      // redesign, "Sarthi home + wallet", 2026-09-08) — a cold start
      // landing on the Sarthi home screen now reads this on mount.
      ProxyProvider2<ApiClient, AuthSession, WalletApi>(
        update: (context, apiClient, authSession, previous) =>
            WalletApi(apiClient, () => authSession.tokens?.accessToken),
      ),
      Provider<PushNotificationManager>(
        create: (_) => _fakePushNotificationManager(),
      ),
    ],
    child: MaterialApp(
      theme: AppTheme.light,
      home: const SessionBootstrapper(),
    ),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

final _unreachableClient = MockClient((_) async => http.Response('', 404));

void main() {
  setUp(() {
    GeolocatorPlatform.instance = _GrantedGeolocatorPlatform();
  });

  testWidgets('role selection shows both roles', (tester) async {
    await tester.pumpWidget(
      _testApp(
        mockHttpClient: _unreachableClient,
        tokenStorage: FakeTokenStorage(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('User'), findsOneWidget);
    expect(find.text('Sarthi'), findsOneWidget);
  });

  testWidgets('tapping User opens phone entry for the user role', (
    tester,
  ) async {
    await tester.pumpWidget(
      _testApp(
        mockHttpClient: _unreachableClient,
        tokenStorage: FakeTokenStorage(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('User'));
    await tester.pumpAndSettle();

    expect(find.text("What's your mobile number?"), findsOneWidget);
    // The AppBar title confirms which role this phone-entry screen is for.
    expect(find.widgetWithText(AppBar, 'User'), findsOneWidget);
  });

  testWidgets('phone entry rejects a short number without calling the API', (
    tester,
  ) async {
    var requestCount = 0;
    await tester.pumpWidget(
      _testApp(
        mockHttpClient: MockClient((_) async {
          requestCount++;
          return http.Response('', 500);
        }),
        tokenStorage: FakeTokenStorage(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('User'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField), '123');
    await tester.tap(find.text('Send OTP'));
    await tester.pumpAndSettle();

    expect(find.text('Enter a valid 10-digit mobile number'), findsOneWidget);
    expect(requestCount, 0);
  });

  testWidgets('full login flow: phone -> OTP -> user home screen, and the '
      'session is persisted', (tester) async {
    final storage = FakeTokenStorage();
    await tester.pumpWidget(
      _testApp(
        mockHttpClient: MockClient((request) async {
          if (request.url.path == '/api/v1/auth/otp/request') {
            return http.Response(
              _envelope({'challenge_id': 'challenge-1', 'expires_in': 300}),
              200,
            );
          }
          if (request.url.path == '/api/v1/auth/otp/verify') {
            final body = jsonDecode(request.body) as Map<String, dynamic>;
            expect(body['challenge_id'], 'challenge-1');
            expect(body['otp'], '123456');
            return http.Response(
              _envelope({
                'access_token': 'access-token',
                'refresh_token': 'refresh-token',
                'expires_in': 3600,
              }),
              200,
            );
          }
          return http.Response('not found', 404);
        }),
        tokenStorage: storage,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('User'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField), '9999999999');
    await tester.tap(find.text('Send OTP'));
    await tester.pumpAndSettle();

    expect(find.text('+919999999999'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField), '123456');
    await tester.tap(find.text('Verify'));
    await tester.pumpAndSettle();

    expect(find.text('Where are you headed?'), findsOneWidget);
    expect(storage.saved?.role, AppRole.user);
    expect(storage.saved?.tokens.accessToken, 'access-token');
  });

  testWidgets('an invalid OTP shows the backend error and does not navigate', (
    tester,
  ) async {
    await tester.pumpWidget(
      _testApp(
        mockHttpClient: MockClient((request) async {
          if (request.url.path == '/api/v1/auth/otp/request') {
            return http.Response(
              _envelope({'challenge_id': 'challenge-1', 'expires_in': 300}),
              200,
            );
          }
          return http.Response(
            _errorEnvelope('OTP_INVALID', 'Invalid OTP.'),
            400,
          );
        }),
        tokenStorage: FakeTokenStorage(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sarthi'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField), '9999999999');
    await tester.tap(find.text('Send OTP'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField), '000000');
    await tester.tap(find.text('Verify'));
    await tester.pumpAndSettle();

    expect(find.text('Invalid OTP.'), findsOneWidget);
    expect(find.text('You are Offline'), findsNothing);
  });

  testWidgets(
    'a saved, non-expired session restores straight to the home screen '
    'on cold start',
    (tester) async {
      final storage = FakeTokenStorage()
        ..saved = StoredSession(
          role: AppRole.sarthi,
          tokens: AuthTokens(
            accessToken: 'a',
            refreshToken: 'r',
            expiresInSeconds: 3600,
          ),
          expiresAt: DateTime.now().add(const Duration(hours: 1)),
        );

      await tester.pumpWidget(
        _testApp(mockHttpClient: _unreachableClient, tokenStorage: storage),
      );
      await tester.pumpAndSettle();

      expect(find.text('You are Offline'), findsOneWidget);
      expect(find.text('User'), findsNothing); // never saw role selection
    },
  );

  testWidgets(
    'a saved, expired session is cleared and falls back to role selection',
    (tester) async {
      final storage = FakeTokenStorage()
        ..saved = StoredSession(
          role: AppRole.user,
          tokens: AuthTokens(
            accessToken: 'a',
            refreshToken: 'r',
            expiresInSeconds: 3600,
          ),
          expiresAt: DateTime.now().subtract(const Duration(minutes: 1)),
        );

      await tester.pumpWidget(
        _testApp(mockHttpClient: _unreachableClient, tokenStorage: storage),
      );
      await tester.pumpAndSettle();

      expect(find.text('User'), findsOneWidget);
      expect(find.text('Sarthi'), findsOneWidget);
      expect(storage.saved, isNull); // expired session was cleared
      expect(storage.clearCount, 1);
    },
  );

  testWidgets('signing out clears the persisted session', (tester) async {
    final storage = FakeTokenStorage()
      ..saved = StoredSession(
        role: AppRole.user,
        tokens: AuthTokens(
          accessToken: 'a',
          refreshToken: 'r',
          expiresInSeconds: 3600,
        ),
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );

    await tester.pumpWidget(
      _testApp(mockHttpClient: _unreachableClient, tokenStorage: storage),
    );
    await tester.pumpAndSettle();
    expect(find.text('Where are you headed?'), findsOneWidget);

    // Sign out moved from the Home tab's own AppBar onto the Account
    // tab (Phase 3 of the redesign, navigation shell, 2026-09-08) — see
    // AccountHubScreen.
    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Sign out'));
    await tester.pumpAndSettle();

    expect(find.text('User'), findsOneWidget); // back at role selection
    expect(storage.saved, isNull);
  });

  test(
    'AuthSession starts signed out and persists on signIn/signOut',
    () async {
      final storage = FakeTokenStorage();
      final apiClient = ApiClient();
      final session = AuthSession(
        storage: storage,
        authApi: AuthApi(apiClient),
        apiClient: apiClient,
      );
      expect(session.isAuthenticated, isFalse);

      session.signIn(
        role: AppRole.user,
        tokens: AuthTokens(
          accessToken: 'a',
          refreshToken: 'r',
          expiresInSeconds: 3600,
        ),
      );
      expect(session.isAuthenticated, isTrue);
      expect(session.role, AppRole.user);
      // signIn's storage write is fire-and-forget; give it a tick to land.
      await Future<void>.delayed(Duration.zero);
      expect(storage.saveCount, 1);
      expect(storage.saved?.role, AppRole.user);

      session.signOut();
      expect(session.isAuthenticated, isFalse);
      expect(session.role, isNull);
      await Future<void>.delayed(Duration.zero);
      expect(storage.clearCount, 1);
    },
  );

  test('AuthSession.restore loads a valid saved session', () async {
    final storage = FakeTokenStorage()
      ..saved = StoredSession(
        role: AppRole.sarthi,
        tokens: AuthTokens(
          accessToken: 'a',
          refreshToken: 'r',
          expiresInSeconds: 3600,
        ),
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );
    final apiClient = ApiClient();
    final session = AuthSession(
      storage: storage,
      authApi: AuthApi(apiClient),
      apiClient: apiClient,
    );

    await session.restore();

    expect(session.isAuthenticated, isTrue);
    expect(session.role, AppRole.sarthi);
  });

  test(
    'AuthSession.restore clears an expired session whose refresh token '
    'itself no longer works (ADR-0076)',
    () async {
      final storage = FakeTokenStorage()
        ..saved = StoredSession(
          role: AppRole.user,
          tokens: AuthTokens(
            accessToken: 'a',
            refreshToken: 'r',
            expiresInSeconds: 3600,
          ),
          expiresAt: DateTime.now().subtract(const Duration(minutes: 1)),
        );
      final apiClient = ApiClient(
        httpClient: MockClient(
          (_) async => http.Response(
            _errorEnvelope('AUTH_INVALID', 'Refresh token is invalid.'),
            401,
          ),
        ),
      );
      final session = AuthSession(
        storage: storage,
        authApi: AuthApi(apiClient),
        apiClient: apiClient,
      );

      await session.restore();

      expect(session.isAuthenticated, isFalse);
      expect(storage.saved, isNull);
    },
  );

  test(
    'AuthSession.restore refreshes an expired access token instead of '
    'forcing re-login when the refresh token still works (ADR-0076)',
    () async {
      final storage = FakeTokenStorage()
        ..saved = StoredSession(
          role: AppRole.sarthi,
          tokens: AuthTokens(
            accessToken: 'stale-access',
            refreshToken: 'still-valid-refresh',
            expiresInSeconds: 3600,
          ),
          expiresAt: DateTime.now().subtract(const Duration(minutes: 1)),
        );
      Map<String, dynamic>? refreshRequestBody;
      final apiClient = ApiClient(
        httpClient: MockClient((request) async {
          refreshRequestBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            _envelope({
              'access_token': 'fresh-access',
              'refresh_token': 'fresh-refresh',
              'expires_in': 3600,
            }),
            200,
          );
        }),
      );
      final session = AuthSession(
        storage: storage,
        authApi: AuthApi(apiClient),
        apiClient: apiClient,
      );

      await session.restore();

      expect(session.isAuthenticated, isTrue);
      expect(session.role, AppRole.sarthi);
      expect(session.tokens?.accessToken, 'fresh-access');
      expect(refreshRequestBody?['refresh_token'], 'still-valid-refresh');
      // Persisted, not just held in memory.
      await Future<void>.delayed(Duration.zero);
      expect(storage.saved?.tokens.accessToken, 'fresh-access');
    },
  );

  test(
    'concurrent AUTH_INVALID failures share one real refresh call '
    '(ADR-0076 single-flight)',
    () async {
      final storage = FakeTokenStorage();
      var refreshCallCount = 0;
      final apiClient = ApiClient(
        httpClient: MockClient((request) async {
          refreshCallCount++;
          return http.Response(
            _envelope({
              'access_token': 'fresh-access',
              'refresh_token': 'fresh-refresh',
              'expires_in': 3600,
            }),
            200,
          );
        }),
      );
      final session = AuthSession(
        storage: storage,
        authApi: AuthApi(apiClient),
        apiClient: apiClient,
      )..signIn(
        role: AppRole.user,
        tokens: AuthTokens(
          accessToken: 'a',
          refreshToken: 'r',
          expiresInSeconds: 3600,
        ),
      );

      // Two "different API calls" both hitting AUTH_INVALID around the
      // same moment — ApiClient.onAuthInvalid is exactly what each of
      // them would call independently.
      final results = await Future.wait([
        apiClient.onAuthInvalid!(),
        apiClient.onAuthInvalid!(),
      ]);

      expect(refreshCallCount, 1);
      expect(results, ['fresh-access', 'fresh-access']);
      expect(session.tokens?.accessToken, 'fresh-access');
    },
  );
}
