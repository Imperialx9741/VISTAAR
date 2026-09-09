# VISTAAR Mobile

The unified VISTAAR mobile app — **one app, two login roles**: User
(customer) and Sarthi (driver). See
[`docs/14-decisions/ADR-0027-unified-mobile-app-role-based-login.md`](../../docs/14-decisions/ADR-0027-unified-mobile-app-role-based-login.md)
for why this replaced the previous separate `customer-mobile`/
`driver-mobile` projects. "User"/"Sarthi" are the user-facing display
labels only (owner decision, 2026-08-29) — the wire `account_type`
values sent to the backend are still exactly `CUSTOMER`/`DRIVER`
(api-contracts.md §6.1), unchanged.

## What's built so far

The complete login flow, wired to the real backend
(`apps/backend`, api-contracts.md §6-7):

1. **Role selection** — User or Sarthi.
2. **Location permission** — asked right after role selection, with
   role-appropriate copy (`LocationPermissionScreen`). "When in use"
   only; background location is deferred until a Sarthi go-online
   screen exists to need it. The app never blocks login on this —
   denying (or tapping "Not now") still continues to login.
3. **Phone entry** — `POST /api/v1/auth/otp/request`.
4. **OTP verify** (with resend) — `POST /api/v1/auth/otp/verify`.
5. **Book a Ride** (User) — pickup/destination as plain latitude/
   longitude entry (no maps/geocoding provider selected yet), a vehicle
   category + cab tier picker, and a payment-method picker, via
   `POST /api/v1/rides`.
6. **Ride Status/Tracking** (User) — polls `GET /api/v1/rides/{id}`
   every 4 seconds; shows status, driver/vehicle once assigned, fare,
   and (once the ride is ARRIVED) a "Show pickup code" button that calls
   `POST .../otp/refresh`. While ACCEPTED, a **Change Pickup** button
   calls `POST .../pickup-change` with a new lat/lng — a ≤100m change
   applies immediately, a >100m one is rejected outright with a message
   to cancel and rebook (ADR-0056, 2026-08-31; no driver decision or
   charge is involved either way). While STARTED, a
   **Change Destination** button calls `POST .../destination-change` —
   a free (WITHIN_ROUTE) change applies immediately; a fare-changing one
   is auto-rejected with an honest explanation rather than confirmed
   blind (see "Known gaps" below). While SEARCHING/ACCEPTED/ARRIVED, a
   **Cancel Ride** button calls `POST .../cancel` and shows the
   resulting charge, if any. No map — see "Known gaps" below.
7. **Session persistence** — the session (role + tokens) is saved to the
   platform keychain/keystore on sign-in and restored on cold start
   (`SessionBootstrapper`), so the user isn't asked to log in again every
   time the app launches. An expired session is detected and cleared
   automatically, falling back to role selection.

For **Sarthi** (driver), past login:

8. **Go Online / Go Offline** — `POST /api/v1/drivers/me/online`/
   `.../offline`, this app's first *authenticated* backend calls (an
   `Authorization: Bearer` header, added to `ApiClient` for this).
9. **Location updates while online** — sent immediately on going online,
   then every 5 seconds, via `POST /api/v1/drivers/me/location`, stopped
   on going offline. **Foreground only right now** — this uses an
   in-app timer, which stops if the app is minimized/suspended by the
   OS. Real background operation (an Android foreground service, iOS's
   `location` background mode) is a distinct, not-yet-built task —
   background/"Always" location permission is deliberately not
   requested until that exists to actually use it.
10. **Incoming ride offers, while online** — `SarthiHomeScreen` polls
    `GET /api/v1/drivers/me/ride-offers` every 4 seconds (no push/
    websocket channel exists). A PENDING offer opens `RideOfferScreen`
    showing the pickup location and a live countdown to its expiry, with
    Accept (`POST .../accept`, requires an `Idempotency-Key`) and Reject
    (`POST .../reject`).
11. **Ride execution** — accepting an offer opens `RideExecutionScreen`,
    which polls `GET /api/v1/rides/{id}` every 4 seconds and shows
    **Mark Arrived** (GPS-gated, ACCEPTED), **Start Ride** (the driver
    types the code the customer reads aloud, ARRIVED), and
    **Complete Ride** (GPS-gated, STARTED). While ACCEPTED, a **Cancel**
    button calls `POST .../driver-cancel` — it disappears once the
    driver has marked arrival, since driver cancellation is
    ACCEPTED-only server-side. Offer polling pauses while a ride is
    being executed and resumes once it's done (location updates keep
    running throughout). No cash-payment confirmation — see "Known gaps"
    below.

Both cancellation flows share one dialog
(`lib/shared/widgets/cancel_reason_dialog.dart`) that collects a
free-text reason — the backend enforces no canonical reason enum for
either endpoint, just non-blank/≤100 chars.

12. **Wallet** (Sarthi only) — a new wallet icon on `SarthiHomeScreen`'s
    AppBar opens `WalletScreen`: the current balance (plus outstanding
    settlement, currently always `0` on the wire) via
    `GET /api/v1/drivers/me/wallet`, and a paginated transaction ledger
    (`Load more`, pull-to-refresh) via
    `GET /api/v1/drivers/me/wallet/transactions`. **Driver-side only** —
    there is no customer-facing wallet/outstanding-charges endpoint
    anywhere in the backend yet (see "Known gaps" below), so there is
    nothing for a User-side wallet screen to call. No Recharge —
    blocked on the same payment-gateway gap as online ride payment.
13. **SOS** (both roles) — an SOS icon in the AppBar of both
    `RideStatusScreen` (User) and `RideExecutionScreen` (Sarthi),
    shown while the ride isn't terminal, calls
    `POST /api/v1/rides/{ride_id}/sos` with the device's live GPS
    position after the caller picks one of four presets in a
    confirmation dialog (no canonical `incident_type` enum is
    documented anywhere — shape-validated free text, same treatment
    other undocumented-enum fields already get). This escalates to
    VISTAAR's own internal safety/call-center team over IN_APP + SMS
    (ADR-0050) — it does not contact police or an ambulance directly,
    and the dialog's own copy says so.
14. **Contact Support** (both roles) — a support icon on both home
    screens (general contact) and a "Contact Support" link on both ride
    screens (pre-filled with that ride's id) open
    `ContactSupportScreen`: a category + message form that calls
    `POST /api/v1/support/cases`, then shows the created case and its
    message thread via `SupportCaseScreen`. There is no "list my cases"
    endpoint anywhere in the backend — only create and get-by-id — so
    this app can only ever show a case right after creating it, not a
    support history (see "Known gaps" below).

15. **Schedule a Ride** (User) — a "Schedule for later" toggle on
    `BookRideScreen` opens a date/time picker (`showDatePicker`/
    `showTimePicker` — no new package); the 1-24 hour window itself is
    enforced server-side (BR-137), not duplicated here. A new
    `ScheduledRidesScreen` (an icon on `UserHomeScreen`) lists upcoming
    scheduled rides (`GET /api/v1/rides?status=SCHEDULED`, paginated) —
    tapping one opens the same `RideStatusScreen` every other ride
    already uses, which shows the scheduled time and offers Cancel Ride
    (charged per BR-135: ≥3h before → free, <3h → ₹30).
16. **Book for Someone Else** (User) — a "Book for someone else" toggle
    on `BookRideScreen` collects the actual rider's name and phone,
    either typed by hand or via a new **Choose from Contacts** button
    (`flutter_contacts`, owner-approved 2026-09-01) that opens the
    device's native contact picker (`lib/core/contacts/contacts_api.dart`)
    and prefills both fields. Contacts permission is requested only when
    that button is tapped, never at app launch; a denied permission, a
    cancelled picker, or a contact with no phone number all fall back to
    the manual fields unchanged (see "Known gaps" below for what's still
    untested on iOS). The pickup OTP is sent by SMS to this number in
    addition to the booker seeing it in-app (`RideStatusScreen`'s
    existing "Show pickup code", unchanged).

17. **Push notifications** — `NotificationApi`
    (`lib/core/api/notification_api.dart`, unchanged) calls the
    backend's device-token endpoints (`POST`/`DELETE
    /api/v1/notifications/me/devices`, ADR-0052). A new
    `PushNotificationManager`
    (`lib/core/notifications/push_notification_manager.dart`) wires it
    to the real `firebase_messaging` SDK against the owner's Firebase
    project ("VISTAAR Production", one project/app for both roles):
    permission request, real token registration on login, token-refresh
    re-registration, unregistration on sign-out (before the access
    token is cleared), and foreground/background message listening.
    Started/stopped from `HomeRouter` and both home screens'
    `_signOut()`. Android is fully configured; iOS still needs its own
    `GoogleService-Info.plist`, Xcode capability, and APNs key — see
    "Known gaps" below.

18. **Token refresh** (ADR-0076, 2026-09-07) — `AuthApi.refresh()` calls
    `POST /api/v1/auth/refresh`. `ApiClient.onAuthInvalid` (wired by
    `AuthSession` at construction) transparently refreshes and retries
    any call that hits an expired access token, and `AuthSession.
    restore()` now attempts a refresh before giving up on a
    cold-start session whose access token has expired — a working
    refresh token no longer means a forced re-login. Single-flight
    (concurrent callers share one real `/refresh`), since refresh
    tokens are rotated single-use server-side.
19. **Map rendering** (2026-09-07) — `flutter_map` + MapTiler Cloud
    tiles (`lib/shared/map/maptiler_tile_layer.dart`, the one file that
    ever touches the real key). Real map-based pickup/destination
    picking (`LocationPickerScreen`) in `BookRideScreen` and the Change
    Pickup/Destination dialogs; a static pickup/destination preview
    (`RouteMapPreview`) on `RideStatusScreen`/`RideExecutionScreen`/
    `RideOfferScreen` — **not live driver tracking**, since no
    `/tracking` endpoint exists in the backend (unaffected by this
    task, on purpose — see "Known gaps" below). Every map-touching
    screen degrades to a plain notice, not a crash, when no maps key is
    configured for a build.

This list itself has fallen behind the app's real state in places —
several features built later in the same project (User-side profile/
ride-history/promotions/referrals, Sarthi strike history, the shared
GPS-dispute/evidence flow, real camera/gallery evidence capture) were
never folded back into it. `docs/VISTAAR_STATUS.md` is the
authoritative, actively-maintained record of what's actually built;
treat this list as a snapshot of the app's first pass, not the current
whole picture. See
`docs/16-mobile/mobile-app-implementation-plan.md`.

## Project layout

```
lib/
  core/
    api/        HTTP client (auth-header-aware, extra-header-aware,
                GET/DELETE-capable) + typed calls (AuthApi,
                DriverAvailabilityApi, RideOfferApi, RideApi, WalletApi,
                SafetyApi, SupportApi, NotificationApi)
    notifications/ PushNotificationManager — real firebase_messaging
                integration wired on top of NotificationApi
    contacts/   ContactsApi — native Contacts picker for Book for
                Someone Else, wraps flutter_contacts
    bootstrap/  SessionBootstrapper — decides login flow vs. home screen
                on app start
    config/     AppConfig (backend base URL, MapTiler API key)
    storage/    TokenStorage (persists the session) + its real
                (SecureTokenStorage) implementation
    theme/      Shared Material theme
  features/
    auth/       Role selection, phone entry, OTP verify, session state
    home/       UserHomeScreen (entry to Book a Ride), SarthiHomeScreen
                (Go Online/Offline + location updates + ride-offer
                polling)
    location/   LocationPermissionScreen
    rides/      BookRideScreen, RideStatusScreen, ScheduledRidesScreen
                (User); RideOfferScreen, RideExecutionScreen (Sarthi —
                offer response, then arrive/start/complete)
    wallet/     WalletScreen (Sarthi only — balance + transaction ledger)
    support/    ContactSupportScreen, SupportCaseScreen (both roles)
  shared/
    widgets/    Reusable widgets (PrimaryButton, CancelReasonDialog,
                ChangePickupDialog, ChangeDestinationDialog, SosDialog)
```

## Prerequisites

- Flutter SDK (`environment.sdk` in `pubspec.yaml` pins the constraint).
- The VISTAAR backend running locally (`apps/backend`) — see its own
  README/`infrastructure/docker/docker-compose.dev.yml`.

## Running against the backend

By default the app calls `http://127.0.0.1:8000`. Override with
`--dart-define` if that doesn't reach your backend:

```bash
# Android emulator (can't reach the host machine via 127.0.0.1):
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000

# iOS simulator / desktop / web (same machine as the backend):
flutter run
```

## MapTiler Cloud API key (never committed)

Copy `dart_define.example.json` to `dart_define.json` (already
git-ignored) and fill in a real `MAPTILER_API_KEY`, then run with:

```bash
flutter run --dart-define-from-file=dart_define.json
```

`AppConfig.mapTilerApiKey`/`AppConfig.hasMapTilerApiKey`
(`lib/core/config/app_config.dart`) read it. An empty key is a real,
supported state — every map-dependent screen must degrade rather than
crash when `hasMapTilerApiKey` is `false` (the same "wired, real
credential arrives later" pattern this codebase's backend already
follows for MSG91/Sentry/S3).

## Sentry DSN (never committed)

Same `dart_define.json` as above — add a real `SENTRY_DSN` from this
app's own Sentry project (a separate project from the backend's, so
mobile crashes don't mix into its error feed; org `vistaar-3j`,
2026-09-08). `AppConfig.sentryDsn` (`lib/core/config/app_config.dart`)
reads it; `main.dart` passes it straight to `SentryFlutter.init`. An
empty DSN is a real, supported state — the SDK simply stays disabled,
same pattern as the MapTiler key above and the backend's own
`SENTRY_DSN` handling (ADR-0053).

## Commands

```bash
flutter pub get       # install dependencies
flutter analyze       # static analysis
flutter test          # unit + widget tests (mocked HTTP, no backend needed)
flutter run           # run on a connected device/emulator/simulator
```

## Known gaps / deliberately deferred

- **No live driver-location tracking on the map** (item 19 above closed
  the rest of this line — pickup/destination picking and a static
  ride-preview map are both real now) — verified directly against the
  backend, there is no `/tracking` endpoint at all (api-contracts.md
  §14 documents a route name and a WebSocket, neither implemented). A
  real backend gap, not a mobile-side or maps-provider one, and outside
  this task's own explicit scope (map UI only, no backend distance/
  tracking changes) — `RideStatusScreen`/`RideExecutionScreen` show
  where the ride starts and ends, never where the driver currently is.
- **No "no driver found" retry/fare-increase UI** — api-contracts.md
  §21 documents `GET .../no-driver-options`/`POST .../fare-increase`;
  neither exists anywhere in the live backend (verified by grepping the
  whole backend source). A ride that finds no driver simply stays
  SEARCHING indefinitely today; `RideStatusScreen` shows that honestly.
- **No cash-payment confirmation** — api-contracts.md §33 documents
  `POST .../cash-payment/confirm`, but its own text already says "Not
  built today"; verified by grepping the whole backend source that no
  `cash-payment` route exists anywhere. `RideExecutionScreen` shows no
  UI for this since there is nothing it could call.
- **Destination change can't show the fare before confirming** — §25's
  request response never includes the computed fare for a
  BEYOND_ORIGINAL/DIFFERENT_ROUTE case, only §26's confirm response
  does, after the customer has already answered `confirmed` — verified
  directly against the live router. BR-082 requires the customer to see
  the fare *before* deciding. This app does not build a "confirm blind"
  screen around it: a fare-changing case is auto-rejected instead (see
  `RideStatusScreen._changeDestination()`), with an honest message
  rather than a broken confirmation flow. The free WITHIN_ROUTE case
  works normally. Not a client-side gap to fix — the backend response
  shape itself needs to change first.
- **Background location** — Sarthi's location updates only run while the
  app is in the foreground (an ordinary `Timer.periodic`). True
  background operation needs an Android foreground service (its own
  manifest declaration + persistent notification) and iOS's `location`
  background mode — neither is built yet, and background/"Always"
  location permission is deliberately not requested until they are.
- **`flutter_secure_storage` on web** does not encrypt (a documented
  limitation of the package itself) — acceptable since web is not this
  app's primary target; revisit if/when web becomes a real deployment
  target.
- **State management** — `provider` was chosen deliberately light for a
  login-only slice. Reconsider once more screens exist.
- **No customer-facing wallet / outstanding-charges view** — `WalletScreen`
  only exists for Sarthi. `GET /api/v1/customers/me` doesn't return
  `outstanding_penalty`/`total_payable` despite ADR-0026 documenting
  that as a target shape (verified directly against
  `modules/customer/router.py`) — there is no endpoint yet for a
  User-side wallet screen to call.
- **No support case history** — `SupportApi` only has Create and
  Get-by-id (verified directly against `modules/support/router.py` —
  no "list my cases" endpoint exists anywhere in the backend). This app
  can show a case right after `ContactSupportScreen` creates it, but
  cannot show a customer/driver any past cases; there is also no way to
  post a follow-up message into an existing case (Assign/Resolve/
  PostMessage are all undocumented at the HTTP layer too, ADR-0022
  Decision 6) — a case is create-once, view-once from this app.
- **No way to check an SOS incident's status after triggering it** —
  Acknowledge/Escalate/Resolve (state-machines.md §45) have no
  documented HTTP endpoint anywhere either (same ADR-0022 Decision 6),
  so the confirmation `SafetyApi.triggerSos()` shows is the last thing
  this app can ever tell the caller about that incident.
- **Push notifications work on Android; iOS is not yet configured** —
  `PushNotificationManager` wires real `firebase_messaging` on top of
  `NotificationApi` against the owner's Firebase project, and Android's
  `google-services.json`/Gradle wiring was generated by the owner's
  FlutterFire run. iOS is still genuinely incomplete: no
  `GoogleService-Info.plist` or `Podfile` exists yet (iOS has never
  been built once for this project), the Xcode "Push Notifications"
  capability has not been enabled, and no APNs Authentication Key has
  been uploaded to Firebase Console — all four need a real Mac, Xcode,
  and Apple Developer Program access this environment doesn't have. The
  backend's own `PUSH_PROVIDER` still defaults to `dev`.
- **Contacts picker works on Android; iOS is untested here** — a real
  debug APK was built (`flutter build apk --debug`) to confirm
  `flutter_contacts`'s native Android code actually compiles and links
  and `READ_CONTACTS` is wired correctly, but no physical Android
  device or emulator was available in this environment to tap through
  the live permission dialog and native picker themselves (`flutter
  devices`/`flutter emulators` confirm none connected or configured) —
  that interaction is covered by widget tests against injected fakes
  instead. iOS is entirely untestable here — no Mac/Xcode exists in
  this environment (the same standing limitation push notifications
  have, above) — `NSContactsUsageDescription` was added correctly by
  inspection against Apple's and the plugin's own documented
  requirements, not verified against a real prompt.
- **No reschedule for a scheduled ride** — only cancel-and-rebook.
  Rescheduling itself was never asked about or designed (ADR-0057);
  this app doesn't assume it exists.
