// Widget tests for SarthiHomeScreen (build order step 2 —
// docs/16-mobile/mobile-app-implementation-plan.md §5.2): Go Online/
// Offline and the location-update stream it starts (a real Android
// foreground service, added 2026-09-04).
//
// The backend is mocked via `http`'s own `MockClient` (same convention
// as the login-flow tests), and the device position via a
// [FakeGeolocatorPlatform] (geolocator's own documented testing seam).

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
import 'package:vistaar_mobile/core/api/driver_availability_api.dart';
import 'package:vistaar_mobile/core/api/notification_api.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/core/api/ride_offer_api.dart';
import 'package:vistaar_mobile/core/api/wallet_api.dart';
import 'package:vistaar_mobile/core/notifications/push_notification_manager.dart';
import 'package:vistaar_mobile/core/storage/token_storage.dart';
import 'package:vistaar_mobile/features/auth/app_role.dart';
import 'package:vistaar_mobile/features/auth/auth_session.dart';
import 'package:vistaar_mobile/features/home/sarthi_home_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_execution_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_offer_screen.dart';

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

class _FakeTokenStorage implements TokenStorage {
  @override
  Future<void> save(StoredSession session) async {}
  @override
  Future<StoredSession?> load() async => null;
  @override
  Future<void> clear() async {}
}

/// Only overrides [getPositionStream] — the one call SarthiHomeScreen
/// actually makes (a real Android foreground-service position stream,
/// added 2026-09-04 — see that screen's own doc comment).
class FakeGeolocatorPlatform extends GeolocatorPlatform {
  int callCount = 0;

  Position _fixedPosition() => Position(
    latitude: 25.5941,
    longitude: 85.1376,
    timestamp: DateTime.now(),
    accuracy: 8,
    altitude: 0,
    altitudeAccuracy: 0,
    heading: 0,
    headingAccuracy: 0,
    speed: 0,
    speedAccuracy: 0,
  );

  @override
  Future<Position> getCurrentPosition({LocationSettings? locationSettings}) async {
    callCount++;
    return _fixedPosition();
  }

  @override
  Stream<Position> getPositionStream({LocationSettings? locationSettings}) {
    callCount++;
    return Stream<Position>.value(_fixedPosition());
  }
}

Widget _wrap({
  required http.Client mockHttpClient,
  AuthSession? authSession,
  PushNotificationManager? pushNotificationManager,
}) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  final session =
      authSession ??
      (AuthSession(
          storage: _FakeTokenStorage(),
          authApi: AuthApi(apiClient),
          apiClient: apiClient,
        )
        ..signIn(
          role: AppRole.sarthi,
          tokens: AuthTokens(
            accessToken: 'sarthi-token',
            refreshToken: 'r',
            expiresInSeconds: 3600,
          ),
        ));
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<AuthSession>.value(value: session),
      Provider<DriverAvailabilityApi>(
        create: (_) =>
            DriverAvailabilityApi(apiClient, () => session.tokens?.accessToken),
      ),
      Provider<RideOfferApi>(
        create: (_) =>
            RideOfferApi(apiClient, () => session.tokens?.accessToken),
      ),
      Provider<RideApi>(
        create: (_) => RideApi(apiClient, () => session.tokens?.accessToken),
      ),
      // SarthiHomeTab's own wallet summary card (Phase 6 of the
      // redesign, "Sarthi home + wallet", 2026-09-08) — every test
      // using this wrapper now triggers one `GET .../wallet` call on
      // mount; tests that don't specifically stub it just get whatever
      // this shared mockHttpClient returns for an unhandled path
      // (typically a 404, wrapped into an ApiException _loadWallet()
      // already swallows — see that method's own doc comment).
      Provider<WalletApi>(
        create: (_) => WalletApi(apiClient, () => session.tokens?.accessToken),
      ),
      Provider<PushNotificationManager>(
        create: (_) => pushNotificationManager ?? _fakePushNotificationManager(),
      ),
    ],
    child: const MaterialApp(home: SarthiHomeScreen()),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

void main() {
  setUp(() {
    GeolocatorPlatform.instance = FakeGeolocatorPlatform();
  });

  testWidgets('starts Offline', (tester) async {
    await tester.pumpWidget(
      _wrap(
        mockHttpClient: MockClient((_) async {
          return http.Response('not called', 500);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('You are Offline'), findsOneWidget);
    expect(find.text('Go Online'), findsOneWidget);
  });

  // --- Wallet summary card (Phase 6 of the redesign, "Sarthi home +
  // wallet", 2026-09-08) -----------------------------------------------

  testWidgets('shows the wallet balance once loaded', (tester) async {
    await tester.pumpWidget(
      _wrap(
        mockHttpClient: MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(
              _envelope({
                'balance': 340.5,
                'currency': 'INR',
                'outstanding_settlement': 0,
                'outstanding_debt': 0,
              }),
              200,
            );
          }
          return http.Response('not called', 500);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Wallet balance'), findsOneWidget);
    expect(find.text('INR 340.50'), findsOneWidget);
  });

  testWidgets(
    'a balance at or below ₹20 shows the minimum-balance warning',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          mockHttpClient: MockClient((request) async {
            if (request.url.path == '/api/v1/drivers/me/wallet') {
              return http.Response(
                _envelope({
                  'balance': 15.0,
                  'currency': 'INR',
                  'outstanding_settlement': 0,
                  'outstanding_debt': 0,
                }),
                200,
              );
            }
            return http.Response('not called', 500);
          }),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(
          'A minimum of INR 20 is required to accept new ride offers.',
        ),
        findsOneWidget,
      );
    },
  );

  testWidgets('an outstanding debt shows the recovery note', (tester) async {
    await tester.pumpWidget(
      _wrap(
        mockHttpClient: MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(
              _envelope({
                'balance': 100.0,
                'currency': 'INR',
                'outstanding_settlement': 0,
                'outstanding_debt': 25.0,
              }),
              200,
            );
          }
          return http.Response('not called', 500);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(
        'Unpaid cancellation penalty: INR 25.00 (recovered from your next '
        'recharge)',
      ),
      findsOneWidget,
    );
  });

  testWidgets(
    'no wallet card while the balance has never loaded successfully',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          mockHttpClient: MockClient((_) async {
            return http.Response('not called', 500);
          }),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Wallet balance'), findsNothing);
    },
  );

  testWidgets('Go Online calls the backend, flips to Online, and sends an '
      'immediate location update', (tester) async {
    final requestedPaths = <String>[];
    final fakeGeo = FakeGeolocatorPlatform();
    GeolocatorPlatform.instance = fakeGeo;

    await tester.pumpWidget(
      _wrap(
        mockHttpClient: MockClient((request) async {
          requestedPaths.add(request.url.path);
          if (request.url.path == '/api/v1/drivers/me/online') {
            return http.Response(
              _envelope({'status': 'ONLINE', 'vehicle_id': 'vehicle-1'}),
              200,
            );
          }
          if (request.url.path == '/api/v1/drivers/me/location') {
            return http.Response(_envelope({'status': 'OK'}), 200);
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Go Online'));
    await tester.pumpAndSettle();

    expect(find.text('You are Online'), findsOneWidget);
    expect(find.text('Go Offline'), findsOneWidget);
    expect(requestedPaths, contains('/api/v1/drivers/me/online'));
    expect(requestedPaths, contains('/api/v1/drivers/me/location'));
    expect(fakeGeo.callCount, greaterThanOrEqualTo(1));

    // Stop the periodic timer this screen started, so it doesn't outlive
    // the test.
    await tester.tap(find.text('Go Offline'));
    await tester.pumpAndSettle();
  });

  testWidgets(
    'a PENDING ride offer found while polling opens RideOfferScreen',
    (tester) async {
      var offerListed = false;
      await tester.pumpWidget(
        _wrap(
          mockHttpClient: MockClient((request) async {
            if (request.url.path == '/api/v1/drivers/me/online') {
              return http.Response(
                _envelope({'status': 'ONLINE', 'vehicle_id': 'vehicle-1'}),
                200,
              );
            }
            if (request.url.path == '/api/v1/drivers/me/location') {
              return http.Response(_envelope({'status': 'OK'}), 200);
            }
            if (request.url.path == '/api/v1/drivers/me/offline') {
              return http.Response(_envelope({'status': 'OFFLINE'}), 200);
            }
            if (request.url.path == '/api/v1/drivers/me/ride-offers') {
              offerListed = true;
              return http.Response(
                _envelope({
                  'offers': [
                    {
                      'offer_id': 'offer-1',
                      'ride_id': 'ride-1',
                      'status': 'PENDING',
                      'expires_at': DateTime.now()
                          .toUtc()
                          .add(const Duration(seconds: 20))
                          .toIso8601String(),
                      'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
                    },
                  ],
                }),
                200,
              );
            }
            if (request.url.path ==
                '/api/v1/drivers/me/ride-offers/offer-1/reject') {
              return http.Response(
                _envelope({'offer_id': 'offer-1', 'status': 'REJECTED'}),
                200,
              );
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Go Online'));
      await tester.pumpAndSettle();

      // The screen's own offer-poll interval is 4 seconds
      // (SarthiHomeScreen's private `_offerPollInterval`) — advance the
      // fake clock past the first tick.
      await tester.pump(const Duration(seconds: 4, milliseconds: 100));
      await tester.pumpAndSettle();

      expect(offerListed, isTrue);
      expect(find.byType(RideOfferScreen), findsOneWidget);
      expect(find.textContaining('25.59410'), findsOneWidget);

      // Reject to pop back, then go offline to stop the timers before the
      // test ends.
      await tester.tap(find.text('Reject'));
      await tester.pumpAndSettle();
      expect(find.byType(RideOfferScreen), findsNothing);

      await tester.tap(find.text('Go Offline'));
      await tester.pumpAndSettle();
    },
  );

  testWidgets(
    'accepting an offer opens RideExecutionScreen and pauses offer polling '
    'until it returns',
    (tester) async {
      var offerListCount = 0;
      var acceptCalled = false;
      // A real backend would stop listing an offer once it's ACCEPTED
      // (no longer PENDING) — mirrored here so resumed polling doesn't
      // find the same offer again and push a second RideOfferScreen.
      var offerStillAvailable = true;

      await tester.pumpWidget(
        _wrap(
          mockHttpClient: MockClient((request) async {
            if (request.url.path == '/api/v1/drivers/me/online') {
              return http.Response(
                _envelope({'status': 'ONLINE', 'vehicle_id': 'vehicle-1'}),
                200,
              );
            }
            if (request.url.path == '/api/v1/drivers/me/location') {
              return http.Response(_envelope({'status': 'OK'}), 200);
            }
            if (request.url.path == '/api/v1/drivers/me/offline') {
              return http.Response(_envelope({'status': 'OFFLINE'}), 200);
            }
            if (request.url.path == '/api/v1/drivers/me/ride-offers') {
              offerListCount++;
              return http.Response(
                _envelope({
                  'offers': offerStillAvailable
                      ? [
                          {
                            'offer_id': 'offer-1',
                            'ride_id': 'ride-1',
                            'status': 'PENDING',
                            'expires_at': DateTime.now()
                                .toUtc()
                                .add(const Duration(seconds: 20))
                                .toIso8601String(),
                            'pickup': {
                              'latitude': 25.5941,
                              'longitude': 85.1376,
                            },
                          },
                        ]
                      : <Object>[],
                }),
                200,
              );
            }
            if (request.url.path ==
                '/api/v1/drivers/me/ride-offers/offer-1/accept') {
              acceptCalled = true;
              offerStillAvailable = false;
              return http.Response(
                _envelope({
                  'offer_id': 'offer-1',
                  'ride_id': 'ride-1',
                  'status': 'ACCEPTED',
                  'wallet_balance': 80.0,
                }),
                200,
              );
            }
            if (request.url.path == '/api/v1/rides/ride-1') {
              return http.Response(
                _envelope({
                  'ride_id': 'ride-1',
                  'status': 'ACCEPTED',
                  'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
                  'destination': {'latitude': 25.6120, 'longitude': 85.1580},
                  'driver': null,
                  'vehicle': null,
                  'fare': null,
                }),
                200,
              );
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Go Online'));
      await tester.pumpAndSettle();

      await tester.pump(const Duration(seconds: 4, milliseconds: 100));
      await tester.pumpAndSettle();
      expect(find.byType(RideOfferScreen), findsOneWidget);

      await tester.tap(find.text('Accept'));
      await tester.pumpAndSettle();

      expect(acceptCalled, isTrue);
      expect(find.byType(RideExecutionScreen), findsOneWidget);
      expect(find.text('Head to pickup'), findsOneWidget);

      // Offer polling stays paused while ride execution is showing, even
      // past another poll interval.
      final offerListCountAtHandoff = offerListCount;
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      expect(offerListCount, offerListCountAtHandoff);

      // Backing out of ride execution resumes it.
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      expect(find.byType(RideExecutionScreen), findsNothing);

      await tester.pump(const Duration(seconds: 4, milliseconds: 100));
      await tester.pumpAndSettle();
      expect(offerListCount, greaterThan(offerListCountAtHandoff));

      await tester.tap(find.text('Go Offline'));
      await tester.pumpAndSettle();
    },
  );

  testWidgets(
    'a Go Online failure surfaces the backend error and stays Offline',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          mockHttpClient: MockClient((request) async {
            if (request.url.path == '/api/v1/drivers/me/online') {
              return http.Response(
                _errorEnvelope(
                  'DRIVER_NOT_ELIGIBLE',
                  'Your documents are not yet approved.',
                ),
                422,
              );
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Go Online'));
      await tester.pumpAndSettle();

      expect(find.text('Your documents are not yet approved.'), findsOneWidget);
      expect(find.text('You are Offline'), findsOneWidget);
    },
  );

  testWidgets('Go Offline calls the backend and flips back to Offline', (
    tester,
  ) async {
    final requestedPaths = <String>[];
    await tester.pumpWidget(
      _wrap(
        mockHttpClient: MockClient((request) async {
          requestedPaths.add(request.url.path);
          if (request.url.path == '/api/v1/drivers/me/online') {
            return http.Response(
              _envelope({'status': 'ONLINE', 'vehicle_id': 'vehicle-1'}),
              200,
            );
          }
          if (request.url.path == '/api/v1/drivers/me/location') {
            return http.Response(_envelope({'status': 'OK'}), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/offline') {
            return http.Response(_envelope({'status': 'OFFLINE'}), 200);
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Go Online'));
    await tester.pumpAndSettle();
    expect(find.text('You are Online'), findsOneWidget);

    await tester.tap(find.text('Go Offline'));
    await tester.pumpAndSettle();

    expect(find.text('You are Offline'), findsOneWidget);
    expect(requestedPaths, contains('/api/v1/drivers/me/offline'));
  });

  testWidgets('signing out navigates back to role selection', (tester) async {
    await tester.pumpWidget(
      _wrap(
        mockHttpClient: MockClient((_) async {
          return http.Response('not called', 500);
        }),
      ),
    );
    await tester.pumpAndSettle();

    // Sign out moved from the Home tab's own AppBar onto the Account
    // tab (Phase 3 of the redesign, navigation shell, 2026-09-08) — see
    // SarthiAccountHubScreen.
    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Sign out'));
    await tester.pumpAndSettle();

    expect(find.text('Continue as'), findsOneWidget);
  });

  testWidgets(
    'signing out unregisters the device token while the session is still '
    'signed in, before AuthSession clears it',
    (tester) async {
      // Regression test for the ordering PushNotificationManager's own
      // doc comment calls out: _signOut() must call stop() *before*
      // AuthSession.signOut() clears the access token. Get this
      // backwards and NotificationApi.unregisterDevice's own
      // _requireToken() throws AUTH_REQUIRED before any HTTP call is
      // even made — silently swallowed by stop()'s best-effort catch,
      // so a wrong ordering would pass every other test in this file
      // (sign-out still "succeeds") while quietly never unregistering
      // the device. Wires a *real* PushNotificationManager (not the
      // no-op fake) against a real NotificationApi sharing this test's
      // own AuthSession, so the DELETE actually fires and its captured
      // Authorization header can be checked.
      String? capturedAuthHeader;
      String? capturedPath;
      final apiClient = ApiClient(
        httpClient: MockClient((request) async {
          if (request.method == 'DELETE') {
            capturedAuthHeader = request.headers['Authorization'];
            capturedPath = request.url.path;
          }
          return http.Response(
            _envelope({'status': 'UNREGISTERED'}),
            200,
          );
        }),
      );
      final session =
          AuthSession(
            storage: _FakeTokenStorage(),
            authApi: AuthApi(apiClient),
            apiClient: apiClient,
          )
          ..signIn(
            role: AppRole.sarthi,
            tokens: AuthTokens(
              accessToken: 'sarthi-token',
              refreshToken: 'r',
              expiresInSeconds: 3600,
            ),
          );
      final pushNotificationManager = PushNotificationManager(
        notificationApi: NotificationApi(
          apiClient,
          () => session.tokens?.accessToken,
        ),
        getToken: () async => 'fcm-token-abc',
        deleteToken: () async {},
        onTokenRefresh: () => const Stream<String>.empty(),
        onMessage: () => const Stream<RemoteMessage>.empty(),
        onMessageOpenedApp: () => const Stream<RemoteMessage>.empty(),
      );

      await tester.pumpWidget(
        _wrap(
          mockHttpClient: MockClient((_) async {
            return http.Response('not called', 500);
          }),
          authSession: session,
          pushNotificationManager: pushNotificationManager,
        ),
      );
      await tester.pumpAndSettle();

      // Sign out moved from the Home tab's own AppBar onto the Account
      // tab (Phase 3 of the redesign, navigation shell, 2026-09-08) —
      // see SarthiAccountHubScreen.
      await tester.tap(find.text('Account'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Sign out'));
      await tester.pumpAndSettle();

      expect(capturedPath, endsWith('/devices/fcm-token-abc'));
      expect(capturedAuthHeader, 'Bearer sarthi-token');
    },
  );
}
