import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

import 'core/api/api_client.dart';
import 'core/api/auth_api.dart';
import 'core/api/customer_api.dart';
import 'core/api/driver_api.dart';
import 'core/api/driver_availability_api.dart';
import 'core/api/notification_api.dart';
import 'core/api/promotion_api.dart';
import 'core/api/referral_api.dart';
import 'core/api/ride_api.dart';
import 'core/api/ride_offer_api.dart';
import 'core/api/safety_api.dart';
import 'core/api/support_api.dart';
import 'core/api/vehicle_api.dart';
import 'core/api/wallet_api.dart';
import 'core/bootstrap/session_bootstrapper.dart';
import 'core/config/app_config.dart';
import 'core/contacts/contacts_api.dart';
import 'core/uploads/evidence_upload_service.dart';
import 'core/notifications/push_notification_manager.dart';
import 'core/storage/secure_token_storage.dart';
import 'core/storage/token_storage.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/auth_session.dart';
import 'firebase_options.dart';

/// Runs when a push arrives while the app is backgrounded/terminated —
/// Firebase requires a top-level (or static), `@pragma('vm:entry-point')`
/// function registered before `runApp()`; it runs in its own isolate,
/// which needs its own `Firebase.initializeApp()` call (the one in
/// [main] below doesn't carry over). Deliberately a no-op beyond that:
/// see [PushNotificationManager]'s own doc comment for why no
/// notification content/handling has been designed yet to act on here.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  debugPrint(
    'firebaseMessagingBackgroundHandler: received ${message.messageId}',
  );
}

/// Security review discipline mirrored from the backend (security.md
/// §65 / `_scrub_sensitive_sentry_data`, `apps/backend/src/main.py`,
/// ADR-0053) — "never let OTP/access/refresh tokens reach a third-
/// party error tracker" applies just as much to this client-side SDK.
/// `sendDefaultPii: false` below already keeps device identifiers out
/// of every event by default (Sentry Flutter's own documented
/// behavior); this additionally redacts any `Bearer <token>` or bare
/// 6-digit OTP-shaped substring that ends up *inside* an exception's
/// own message — the one path `sendDefaultPii` doesn't cover, e.g. an
/// `ApiException` built from a raw backend error string.
SentryEvent? _scrubSensitiveSentryData(SentryEvent event, Hint hint) {
  String scrub(String value) => value
      .replaceAll(
        RegExp(r'Bearer\s+\S+', caseSensitive: false),
        'Bearer [redacted]',
      )
      .replaceAll(RegExp(r'\b\d{6}\b'), '[redacted]');

  for (final exception in event.exceptions ?? const <SentryException>[]) {
    if (exception.value != null) exception.value = scrub(exception.value!);
  }
  return event;
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Error tracking (2026-09-08, owner decision) — mirrors the
  // backend's own Sentry wiring (ADR-0053) as its own separate Sentry
  // project (`AppConfig.sentryDsn`'s own doc comment), so mobile
  // crashes don't mix into the backend's error feed. An empty DSN
  // (the default until `dart_define.json` supplies a real one — see
  // README's "Sentry DSN" section) is `SentryFlutter.init`'s own
  // documented disabled state, the same "wired, real credential
  // arrives later" pattern this codebase already follows everywhere
  // else — no special-case code needed here for that.
  await SentryFlutter.init(
    (options) {
      options.dsn = AppConfig.sentryDsn;
      options.environment = kReleaseMode ? 'production' : 'development';
      // Cost/volume call for whoever holds the real Sentry account,
      // not this app to make blindly — same 0.1 default the backend
      // uses (ADR-0053), not full tracing on every session.
      options.tracesSampleRate = 0.1;
      options.sendDefaultPii = false;
      options.beforeSend = _scrubSensitiveSentryData;
    },
    appRunner: () async {
      // ADR-0052, build order step 9/11 — ONE Firebase project
      // ("VISTAAR Production", vistaar-production-3a79a) covering this
      // ONE Flutter app for both roles; lib/firebase_options.dart is
      // FlutterFire CLI output (gitignored — never committed, same
      // secrets-out-of-git discipline this codebase already applies to
      // MSG91/S3/Sentry).
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
      runApp(const VistaarApp());
    },
  );
}

/// VISTAAR's unified mobile app (ADR-0027) — one Flutter app, two login
/// roles (User / Sarthi) chosen at login, with the session persisted
/// across restarts (see [SessionBootstrapper]).
class VistaarApp extends StatelessWidget {
  const VistaarApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ApiClient>(create: (_) => ApiClient()),
        ProxyProvider<ApiClient, AuthApi>(
          update: (context, apiClient, previous) => AuthApi(apiClient),
        ),
        Provider<TokenStorage>(create: (_) => SecureTokenStorage()),
        // Book for Someone Else's native Contacts picker (owner-approved
        // 2026-09-01). Purely device-local — no backend calls, no
        // AuthSession dependency — so a plain Provider, not a
        // ProxyProvider, same treatment TokenStorage above gets.
        Provider<ContactsApi>(create: (_) => ContactsApi()),
        // Camera/gallery capture + presigned upload (2026-09-04) — no
        // AuthSession dependency of its own (the upload target's
        // request/response is composed by the caller), so a plain
        // Provider, same treatment ContactsApi above gets.
        Provider<EvidenceUploadService>(create: (_) => EvidenceUploadService()),
        ChangeNotifierProvider<AuthSession>(
          create: (context) => AuthSession(
            storage: context.read<TokenStorage>(),
            authApi: context.read<AuthApi>(),
            apiClient: context.read<ApiClient>(),
          ),
        ),
        ProxyProvider2<ApiClient, AuthSession, DriverAvailabilityApi>(
          update: (context, apiClient, authSession, previous) =>
              DriverAvailabilityApi(
                apiClient,
                () => authSession.tokens?.accessToken,
              ),
        ),
        ProxyProvider2<ApiClient, AuthSession, RideOfferApi>(
          update: (context, apiClient, authSession, previous) =>
              RideOfferApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, RideApi>(
          update: (context, apiClient, authSession, previous) =>
              RideApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, WalletApi>(
          update: (context, apiClient, authSession, previous) =>
              WalletApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, SafetyApi>(
          update: (context, apiClient, authSession, previous) =>
              SafetyApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, SupportApi>(
          update: (context, apiClient, authSession, previous) =>
              SupportApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, DriverApi>(
          update: (context, apiClient, authSession, previous) =>
              DriverApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, VehicleApi>(
          update: (context, apiClient, authSession, previous) =>
              VehicleApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        // User-side profile/ride-history/promotions/referrals screens,
        // added 2026-09-04 — the next highest-priority gap after Sarthi
        // onboarding, per the same "backend endpoint exists, no mobile
        // caller yet" pattern.
        ProxyProvider2<ApiClient, AuthSession, CustomerApi>(
          update: (context, apiClient, authSession, previous) =>
              CustomerApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, PromotionApi>(
          update: (context, apiClient, authSession, previous) =>
              PromotionApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        ProxyProvider2<ApiClient, AuthSession, ReferralApi>(
          update: (context, apiClient, authSession, previous) =>
              ReferralApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        // Unchanged — NotificationApi itself is not modified by the real
        // FCM integration below. Not read directly by any screen yet;
        // kept for whichever future screen (e.g. notification settings)
        // wants it directly.
        ProxyProvider2<ApiClient, AuthSession, NotificationApi>(
          update: (context, apiClient, authSession, previous) =>
              NotificationApi(apiClient, () => authSession.tokens?.accessToken),
        ),
        // A singleton, NOT a ProxyProvider like the ones above: this
        // holds live StreamSubscriptions (token-refresh, foreground
        // messages) that must survive across an AuthSession change, not
        // get silently recreated (and their old subscriptions leaked)
        // every time the user signs in/out — HomeRouter/sign-out call
        // start()/stop() explicitly instead. Builds its own private
        // NotificationApi (same pattern as the provider above, just not
        // shared) so its token closure still always reads the *current*
        // AuthSession.tokens, not a stale snapshot from creation time.
        Provider<PushNotificationManager>(
          create: (context) {
            final authSession = context.read<AuthSession>();
            return PushNotificationManager(
              notificationApi: NotificationApi(
                context.read<ApiClient>(),
                () => authSession.tokens?.accessToken,
              ),
            );
          },
        ),
      ],
      child: MaterialApp(
        title: 'VISTAAR',
        theme: AppTheme.light,
        // ADR/2026-09-07 — darkTheme + ThemeMode.system (the default,
        // spelled out for clarity) means the app now actually follows
        // the device's own dark-mode setting instead of forcing light
        // regardless of it.
        darkTheme: AppTheme.dark,
        themeMode: ThemeMode.system,
        home: const SessionBootstrapper(),
      ),
    );
  }
}
