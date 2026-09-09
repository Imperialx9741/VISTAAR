VISTAAR Mobile App — Implementation Plan

Status: build authorized and underway, 2026-08-29 (same day as the
draft below). Owner final decisions (role labels, MapTiler as maps
provider, keep the existing `apps/mobile` architecture, defer Schedule
a Ride/Book for Someone Else, "continue implementation and verification
according to existing VISTAAR governance") — see the third decision
block below. Everything below §11's original "Status: Draft... STOP FOR
REVIEW" framing is now the approved design record this build follows,
not an open proposal. As of 2026-09-01, every build-order item is
either shipped (through real FCM push notifications, §6.3, and the
native Contacts picker, §6.2) or blocked on an external decision or
credential (payment gateway, WhatsApp BSP, or the iOS-side Xcode/APNs
steps §6.3 details — the same class of gap §6.2 has for iOS testing).

Build order step 1 (§8) is IMPLEMENTED and verified, 2026-08-29:

- **Role rename applied throughout `apps/mobile`** — `AppRole.user`/
  `AppRole.sarthi` (`lib/features/auth/app_role.dart`), display labels
  "User"/"Sarthi"; wire `account_type` values unchanged (`CUSTOMER`/
  `DRIVER`). `CustomerHomeScreen`/`DriverHomeScreen` renamed to
  `UserHomeScreen`/`SarthiHomeScreen` (files renamed to match). No
  "Guest" label exists anywhere in the app or this plan (the owner's
  clarifying answer confirmed there was nothing to rename there).
- **MapTiler Cloud wired, key received and stored securely** —
  `AppConfig.mapTilerApiKey`/`hasMapTilerApiKey`
  (`lib/core/config/app_config.dart`), read via `--dart-define-from-
  file=dart_define.json` (git-ignored; `dart_define.example.json` is
  the committed template). **Updated 2026-09-07 — no longer accurate**:
  every map-rendering screen this note originally deferred is now
  built (`flutter_map` + MapTiler tiles) — pickup/destination picking
  in Book a Ride and the Change Pickup/Destination dialogs, and a
  static pickup/destination preview on `RideStatusScreen`/
  `RideExecutionScreen`/`RideOfferScreen`. See `docs/VISTAAR_STATUS.md`
  for the authoritative, current account; this line is kept as a
  historical record of the original config-only step, not a live
  status claim anymore.
- **App-launch location permission (§6.1) — IMPLEMENTED as designed**,
  including the staging this plan proposed (minimal "when in use" now,
  background deferred to the Sarthi go-online screen, not yet built).
  `lib/features/location/location_permission_screen.dart`, inserted
  between role selection and phone entry. iOS
  `NSLocationWhenInUseUsageDescription` and Android
  `ACCESS_FINE_LOCATION`/`ACCESS_COARSE_LOCATION` added. Denial never
  blocks login. 6 new widget tests
  (`test/features/location/location_permission_screen_test.dart`)
  against `geolocator`'s own documented testing seam
  (`GeolocatorPlatform.instance`), plus the existing login-flow suite
  updated for the new screen in the middle of that flow — full suite
  `flutter analyze` clean, `flutter test` 17/17 passed.

Build order step 2 (§5.2) is IMPLEMENTED and verified, 2026-08-30:

- **Go Online/Offline** — `lib/features/home/sarthi_home_screen.dart`,
  no longer a placeholder. Calls `POST /api/v1/drivers/me/online`/
  `.../offline` (api-contracts.md §10) via a new `DriverAvailabilityApi`
  (`lib/core/api/driver_availability_api.dart`) — this app's first
  authenticated calls past login, which required extending `ApiClient`
  itself to attach a Bearer access-token header (it had none before;
  every prior call was the unauthenticated OTP flow).
- **Periodic location updates while online** —
  `POST /api/v1/drivers/me/location` (api-contracts.md §15), sent
  immediately on going online and then every 5 seconds (PRD §15's own
  target interval) via `Timer.periodic`, stopped on going offline or
  leaving the screen. A missed update is swallowed, not surfaced as an
  error — a transient GPS/network hiccup must not interrupt a driver
  trying to stay online; the next tick simply retries.
- **Scope actually shipped — foreground only, flagged, not silently
  implied:** this uses an ordinary in-app timer, which only runs while
  `SarthiHomeScreen` is alive and the OS hasn't suspended the app.
  Genuine background operation (updates continuing after the app is
  minimized or the screen locks) needs an Android foreground service
  (its own manifest declaration + persistent notification) and iOS's
  `location` background mode — real, distinct native platform work not
  included in this step. Background/"Always" location permission is
  therefore deliberately NOT requested yet either — declaring it with
  no real background service behind it risks the exact "unjustified
  permission" rejection both app stores flag. This is a genuine
  remaining task, not a decision needing the owner's input.
- 5 new widget tests
  (`test/features/home/sarthi_home_screen_test.dart`) against a
  `MockClient` (same convention as the login-flow tests) and a fake
  `GeolocatorPlatform.getCurrentPosition()` — full suite `flutter
  analyze` clean, `flutter test` 22/22 passed.

Build order step 3 (§5.3) is IMPLEMENTED and verified, 2026-08-31:

- **Incoming ride offers, while online** — `SarthiHomeScreen` polls
  `GET /api/v1/drivers/me/ride-offers` (api-contracts.md §16.1) every 4
  seconds while online, via a new `RideOfferApi`
  (`lib/core/api/ride_offer_api.dart`). There is no push/websocket
  channel (a documented gap), so polling is the only mechanism — picked
  faster than the offer's own PENDING window (PRD §17) so little of it
  is lost to poll latency. Polling starts/stops with Go Online/Offline,
  same lifecycle as the location-update timer.
- **`RideOfferScreen`** (`lib/features/rides/ride_offer_screen.dart`) —
  pushed the moment a PENDING offer is found. Shows the pickup
  coordinates and a locally-computed one-second countdown to
  `expires_at`; back navigation is disabled (`PopScope(canPop: false)`)
  so a driver can't swipe the request away without an explicit choice.
  Accept and Reject are real backend calls
  (`POST .../{offer_id}/accept`, `.../reject`, api-contracts.md
  §16.2-16.3); once the local countdown reaches zero, both buttons are
  replaced with a single "Close" — the backend's own expiry is the
  actual source of truth, this is just the client not pretending a
  clearly-expired offer can still be actioned.
- **Idempotency-Key for Accept** — required by the backend (ADR-0014):
  `ApiClient.post()` gained an `extraHeaders` parameter for this, and a
  `uuid` v4 key is generated once per Accept *attempt* and reused across
  retries of that same attempt (a network-error retry replays
  idempotently instead of risking a double accept).
- **Scope actually shipped, flagged, not silently implied:** accepting
  an offer currently just confirms ("Ride accepted — head to pickup")
  and returns to `SarthiHomeScreen` — there is no ride-execution screen
  yet (arrival, pickup OTP, in-progress, completion); that is the next
  build-order step, not this one.
- 6 new widget tests (`test/features/rides/ride_offer_screen_test.dart`)
  plus 1 more added to `sarthi_home_screen_test.dart` covering the
  poll-to-navigation path — full suite `flutter analyze` clean, `flutter
  test` 28/28 passed.

Build order step 4 (§4.1-4.2) is IMPLEMENTED and verified, 2026-08-31:

- **Book a Ride** (`lib/features/rides/book_ride_screen.dart`) — pickup/
  destination as plain latitude/longitude entry (no maps/geocoding
  provider is selected anywhere in this project, roadmap §25.0), a
  vehicle category picker (cab tier shown only for CAB), and a "pay the
  driver via" picker (BR-035's UPI/CASH examples). Submits to
  `POST /api/v1/rides` (api-contracts.md §12) via a new `RideApi`
  (`lib/core/api/ride_api.dart`) — this app's first customer-side
  authenticated calls past login. No pre-booking fare estimate is shown
  (GAP-1, no such endpoint exists) — the real fare comes back the
  instant the ride is created, shown on the next screen.
- **Ride Status/Tracking** (`lib/features/rides/ride_status_screen.dart`)
  — polls `GET /api/v1/rides/{ride_id}` (api-contracts.md §13) every 4
  seconds, showing the current status, driver/vehicle info once
  assigned, and fare. Once ARRIVED, a "Show pickup code" button calls
  `POST .../otp/refresh` (api-contracts.md §18) to reveal the plaintext
  OTP — gated on ARRIVED specifically (not ACCEPTED), matching
  `RideService.refresh_otp()`'s own state check, found by reading the
  live service code rather than assuming from the plan's own less
  precise wording.
- **Two real backend gaps found and corrected in this plan while
  building, not assumed from the docs:** api-contracts.md §14 (Ride
  Tracking) documents only a route name and an unimplemented WebSocket —
  verified against `modules/ride/router.py` that **no `/tracking`
  endpoint exists in the live backend at all**, not just "needs a maps
  SDK to render." And api-contracts.md §21 (No Driver Found) documents
  `GET .../no-driver-options`/`POST .../fare-increase` — verified by
  grepping the entire backend source that **neither endpoint exists
  anywhere**; a ride that finds no driver simply stays SEARCHING
  indefinitely today. Both §4.2 and §5.4's tables below are corrected
  from their prior "EXISTS"/"needs a maps provider only" status to
  reflect this. `RideStatusScreen` shows SEARCHING honestly (a spinner,
  no retry/increase-fare buttons the backend can't answer) rather than
  building UI against a contract that doesn't exist.
- **Scope actually shipped, flagged, not silently implied:** no
  cancellation button (build order step 6), no pickup/destination change
  (step 6), no map rendering anywhere (blocked on the same unselected
  maps provider as before).
- 4 new widget tests (`test/features/rides/book_ride_screen_test.dart`)
  and 5 new widget tests (`test/features/rides/ride_status_screen_test.dart`)
  — full suite `flutter analyze` clean, `flutter test` 37/37 passed.

Build order step 5 (§5.4) is IMPLEMENTED and verified, 2026-08-31:

- **`RideExecutionScreen`** (`lib/features/rides/ride_execution_screen.dart`)
  — pushed the moment a ride offer is accepted (replacing the old "just
  confirm and go home" behavior from step 3). Polls
  `GET /api/v1/rides/{ride_id}` every 4 seconds and shows the action for
  the current status: **Mark Arrived** (ACCEPTED, GPS-gated —
  `POST .../arrived`, api-contracts.md §17), **Start Ride** (ARRIVED —
  the driver types in the code the customer reads aloud,
  `POST .../start`, §18), **Complete Ride** (STARTED, GPS-gated —
  `POST .../complete`, §28). `RideApi` gained `markArrived()`/
  `startRide()`/`completeRide()`; its doc comment was broadened from
  "Customer (User) ride endpoints" to cover both roles, since
  `getRide()` was already ownership-checked for either side
  (`require_customer_or_driver`) and is now genuinely reused by both
  `RideStatusScreen` and `RideExecutionScreen`.
- **Offer polling pauses during ride execution.** `SarthiHomeScreen`'s
  `RideOfferScreen` now pops with the new ride's id on Accept (`null`
  otherwise); `SarthiHomeScreen` uses that to stop its offer-poll timer
  while `RideExecutionScreen` is showing and resume it only once that
  ride is done and the driver is still online — location updates keep
  running throughout (the driver is still on the move). Whether the
  *backend* itself already excludes a driver with an active ride from
  new dispatches is unverified (not found in
  `modules/matching/service.py`); this is a client-side safeguard
  either way, not a substitute for checking that.
- **A third real backend gap found and corrected while building, not
  assumed from the docs:** api-contracts.md §33 (Driver Confirms Cash
  Payment) already read, on its own text, as "Not built today; kept
  here as the corrected target shape" — confirmed 2026-08-31 by
  grepping the entire backend source: no `cash-payment`-anything route
  exists anywhere. §5.4's table below is corrected from "EXISTS" to
  reflect this; `RideExecutionScreen` shows no cash-confirmation UI
  since there is nothing it could call.
- **Scope actually shipped, flagged, not silently implied:** no
  navigation to pickup/destination (same unselected maps provider every
  other map-dependent screen is blocked on), no parking proof (no
  backend module, GAP-3), no cancellation from this screen (driver
  cancellation exists at the API level, §20, but is build-order step 6,
  not bundled into this one).
- 8 new widget tests (`test/features/rides/ride_execution_screen_test.dart`)
  plus 1 more added to `sarthi_home_screen_test.dart` covering the
  accept → ride-execution → resume-polling handoff — full suite
  `flutter analyze` clean, `flutter test` 46/46 passed.

Build order step 6a (§4.4, §5.4 cancellation rows) is IMPLEMENTED and
verified, 2026-08-31 — split from the full step 6 scope, see below:

- **Cancel Ride** on `RideStatusScreen` (User) — Customer Cancellation
  (api-contracts.md §19), offered while SEARCHING/ACCEPTED/ARRIVED
  (matching `RideService.cancel_ride()`'s own allowed-status set, read
  directly from the service code). A shared
  `lib/shared/widgets/cancel_reason_dialog.dart` collects a free-text
  reason — the backend enforces no canonical reason enum for either
  cancellation endpoint (`validate_cancellation_reason()`: just
  non-blank, ≤100 chars), so this is a plain text field, not an invented
  category picker. On success, shows the resulting charge (`₹0` for a
  grace-period/first-qualifying cancellation, the real amount
  otherwise) — `RideApi` gained `cancelRide()`.
- **Cancel** on `RideExecutionScreen` (Sarthi) — Driver Cancellation
  (§20), offered only while ACCEPTED. Confirmed by reading
  `RideService.driver_cancel_ride()` directly that ARRIVED is
  deliberately excluded (state-machines.md §13's driver-cancel
  transition is ACCEPTED-only, unlike the customer side's
  SEARCHING/ACCEPTED/ARRIVED) — the button does not appear once the
  driver has already marked arrival. Reuses the same reason dialog.
  `RideApi` gained `driverCancelRide()`, which deliberately does not
  expose `"CHANGED_PICKUP_OVER_250M"` as a selectable reason — that
  ₹0-penalty/no-strike exemption belongs to the pickup-change decision
  flow (§23), not a plain cancellation, and isn't reachable from this
  screen.
- **Split, not silently narrowed:** the plan's own step 6 bundled
  "Cancellation + pickup/destination change (both sides)" as one step.
  Cancellation (one endpoint per side, a reason, and a result) shipped
  in full here. Pickup/destination change is a genuinely separate,
  larger piece of work — a multi-actor async flow (customer requests →
  driver decides PROCEED/PASS → customer confirms, §22-26) needing its
  own screen design, not a button on an existing one — so it's carried
  forward as its own increment rather than rushed into this one.
- 5 new widget tests (`test/features/rides/ride_status_screen_test.dart`)
  and 4 new widget tests
  (`test/features/rides/ride_execution_screen_test.dart`) — full suite
  `flutter analyze` clean, `flutter test` 55/55 passed.

Business-rule change, backend, 2026-08-31 — ADR-0056 (Pickup Change
Simplification): before starting step 6b, the owner replaced the
original >250m driver-PROCEED/PASS pickup-change design (ADR-0033)
with a flat 100m hard threshold and no driver decision at all. Per the
owner's explicit instruction, this was reconciled against every
affected document first (business-rules.md, state-machines.md,
api-contracts.md, event-contracts.md, domain-design.md, database-
design.md, technical-architecture.md) and recorded as a new ADR, then
implemented on the backend once accepted:
`RideService.request_pickup_change()` now either applies a ≤100m
change immediately or raises `PickupChangeTooFarError` for anything
farther — the driver-decision and customer-confirmation endpoints
(§23-24) are deleted, along with `PricingService.
calculate_pickup_change_charge()` (no chargeable path remains). Full
backend suite: 1244 passed, 5 skipped (Kafka-connectivity-only), 0
failed — including the real-Postgres pickup-change integration tests.

Build order step 6b, pickup change only (§4.3's "Change pickup" row),
is IMPLEMENTED and verified, 2026-08-31:

- **Change Pickup** on `RideStatusScreen` (User), while ACCEPTED —
  `RideApi.changePickup()` calls the simplified endpoint above. A ≤100m
  change shows "Pickup updated."; a >100m one surfaces the backend's
  own `PICKUP_CHANGE_TOO_FAR` message as-is (already tells the customer
  to cancel and rebook — no second explanation added). A new shared
  `lib/shared/widgets/change_pickup_dialog.dart` collects the new
  lat/lng — same plain-coordinate fallback Book a Ride already uses, no
  maps provider needed. No driver-facing screen exists for this at
  all — ADR-0056 removed the only reason one would have been needed.
- 5 new widget tests added to
  `test/features/rides/ride_status_screen_test.dart` — full suite
  `flutter analyze` clean, `flutter test` 60/60 passed.

Build order step 6b's remaining half — Destination Change (User side;
§4.3's "Change destination" row) — is IMPLEMENTED and verified,
2026-08-31:

- **Change Destination** on `RideStatusScreen`, while STARTED —
  `RideApi.changeDestination()` calls the endpoint above. A WITHIN_
  ROUTE result (no fare impact, BR-079) shows "Destination updated."
  and refreshes. A BEYOND_ORIGINAL/DIFFERENT_ROUTE result is
  automatically rejected (`RideApi.rejectDestinationChange()`, always
  `confirmed: false`) rather than shown to the customer for a "blind"
  confirm — **GAP-8** (found while building this): the request
  response never carries the computed fare, only the confirm
  response does, after the decision is already made, so there is no
  way to satisfy BR-082's "customer sees the fare, then confirms"
  ordering with the API as it stands. Rejecting automatically (instead
  of leaving the request pending) matters because the backend allows
  only one pending DESTINATION_CHANGE request per ride — without this,
  a customer who hit the fare-changing case would be locked out of
  trying any destination change again, including a free one.
- No driver-facing UI — destination change has no driver-decision step
  in the documented flow either (unlike pickup change's original,
  now-removed one).
- 5 new widget tests added to
  `test/features/rides/ride_status_screen_test.dart` — full suite
  `flutter analyze` clean, `flutter test` 66/66 passed.

Step 6 (Cancellation + Pickup/Destination Change, both sides) is now
fully complete for the User side. Driver-side pickup/destination-change
UI was never in scope (no driver-decision step exists for either,
post-ADR-0056) — nothing further to build there.

Build order step 7 — Wallet views (§5.5, minus Recharge) — is
IMPLEMENTED and verified, 2026-08-31:

- New `lib/core/api/wallet_api.dart` — `Wallet.fromJson()` (§34
  `GET /api/v1/drivers/me/wallet`), `WalletTransaction.fromJson()` +
  `WalletTransactionPage` (§34/§50 `GET
  /api/v1/drivers/me/wallet/transactions`, the shared pagination
  envelope), `WalletApi`.
- New `lib/features/wallet/wallet_screen.dart` — balance card (with
  outstanding settlement shown only when nonzero — always `0` on the
  wire today, see the field's own doc comment) and a paginated
  transaction ledger (`Load more`, pull-to-refresh), reached from a
  new wallet icon in `SarthiHomeScreen`'s AppBar.
- **Sarthi-side only** — flagged, not silently assumed complete: both
  backend wallet routes require `require_driver`
  (`modules/wallet/router.py`), and `GET /api/v1/customers/me` does
  not return `outstanding_penalty`/`total_payable` despite ADR-0026
  documenting that as a target shape (**GAP-6**, already tracked below
  before this step began) — there is no customer-facing wallet
  endpoint yet for a User-side wallet screen to call. Recharge (§35)
  remains BLOCKED — external, same payment-gateway gap as §4.5.
- 5 new widget tests added in a new
  `test/features/wallet/wallet_screen_test.dart` — full suite
  `flutter analyze` clean, `flutter test` 71/71 passed.

Build order step 8 — Safety/SOS + Support (§4.9/§5.7, both sides) — is
IMPLEMENTED and verified, 2026-08-31:

- New `lib/core/api/safety_api.dart` — `SafetyApi.triggerSos()`
  (§41). New `lib/shared/widgets/sos_dialog.dart` — a confirmation
  dialog with four presets (no canonical `incident_type` enum is
  documented anywhere, same treatment `document_type`/cancellation
  reasons already get) that requires picking one before the confirm
  button enables, so a stray tap can't fire a real safety escalation.
  Wired as an SOS AppBar action on both `RideStatusScreen` and
  `RideExecutionScreen`, shown while the ride isn't terminal, using the
  device's live GPS position (`Geolocator.getCurrentPosition()`, same
  pattern as Mark Arrived/Complete Ride). The dialog's own copy is
  explicit that this escalates to VISTAAR's internal safety team
  (ADR-0050), not to police or an ambulance directly.
- New `lib/core/api/support_api.dart` — `SupportApi.createCase()` +
  `getCase()` (§44). New `lib/features/support/contact_support_screen.dart`
  (category + message form, `rideId` optional) and
  `support_case_screen.dart` (shows the created case and its message
  thread — fetched via a follow-up `getCase()` call, since the create
  response doesn't echo the thread back). Reachable from both home
  screens (general contact) and, pre-filled with the ride id, from both
  ride screens (BR-121/domain-design.md §17.3's "Dispute-as-Support" —
  fare and penalty disputes are filed through this same endpoint,
  ADR-0028/ADR-0029). There is no "list my cases" endpoint anywhere
  (verified directly against `modules/support/router.py` — only Create
  and Get-by-id exist) — this app can only ever show a case it just
  created in the same session, not a support history; flagged in the
  README rather than silently promising one.
- 14 new widget tests across
  `test/features/rides/ride_status_screen_test.dart`,
  `test/features/rides/ride_execution_screen_test.dart`, and a new
  `test/features/support/contact_support_screen_test.dart` — full suite
  `flutter analyze` clean, `flutter test` 85/85 passed.

Build order step 9 — push notifications, the device-token-registration
half only (§6.3) — is IMPLEMENTED and verified, 2026-08-31:

- New `lib/core/api/notification_api.dart` — `NotificationApi.
  registerDevice()` (`POST /api/v1/notifications/me/devices`) and
  `unregisterDevice()` (`DELETE .../devices/{token}`), ADR-0052.
  Required adding `ApiClient.delete()` (this app's first DELETE call) —
  same shape and error handling as `get()`/`post()`.
- **Deliberately not wired into any screen.** Registering a *real*
  device needs the `firebase_messaging` Flutter SDK, a real Firebase
  project, and its generated `google-services.json`/
  `GoogleService-Info.plist` — none of which exist yet (confirmed: no
  Firebase project has been created; the backend's own `PUSH_PROVIDER`
  still defaults to `dev`, ADR-0052's own open item). Calling this
  class with a fabricated placeholder token would register a device
  nothing could ever deliver a push to, worse than not registering —
  so this app doesn't invent a screen to do that. `NotificationApi` is
  registered in `main.dart`'s provider tree now so the actual SDK
  integration is the only thing left to build once a Firebase
  credential exists.
- 5 new unit tests in a new `test/core/api/notification_api_test.dart`
  — a plain-Dart `test()` suite rather than `testWidgets()`, since
  there is no screen to pump yet; covers request shape, response
  parsing, and both the `AUTH_REQUIRED` and backend-validation error
  paths. Full suite `flutter analyze` clean, `flutter test` 90/90
  passed.

Step 9's other half (§6.3, actually receiving and displaying a push)
stays entirely blocked until that same Firebase credential exists —
nothing to build there yet.

Step 10, Schedule a Ride & Book for Someone Else — fully IMPLEMENTED
2026-08-31, backend and mobile (ADR-0057, status: Accepted,
owner-confirmed via "continue"): a structured two-round clarification
exchange resolved every remaining open question from §4.10/§4.11; the
ADR was written and every affected document reconciled first
(business-rules.md §48, state-machines.md §3.9, api-contracts.md
§12.1/§13/§19, database-design.md §9.1/§15.2/§26.1, domain-design.md
§9.4/§9.5, event-contracts.md §10.12), per this project's standing
governance, before any code was written.

Backend: new `SCHEDULED` ride state, `linked_contact` fields, a new
`GET /api/v1/rides` list endpoint (plus `scheduled_for` added to `GET
/rides/{ride_id}`'s own response, found needed once the mobile detail
screen was being built), and a Celery Beat task
(`modules/ride/tasks.py`) — turned out to need zero new matching
engineering (ADR-0057 §6). 35 new backend tests — full suite 1279
passed, 5 skipped, 0 failed (was 1244), ruff/mypy clean.

Mobile: `BookRideScreen` gained a **Schedule for later** date/time
picker (`showDatePicker`/`showTimePicker`, no new package) and a
**Book for someone else** name/phone form (plain text entry, not a
native Contacts picker — that's real, separately-scoped native-
permission work this increment doesn't add; manual entry is
`mobile-app-implementation-plan.md` §6.2's own documented "if denied"
fallback, used here as the primary path). New `ScheduledRidesScreen`
(`GET /api/v1/rides?status=SCHEDULED`, paginated), reached from a new
icon on `UserHomeScreen`. `RideStatusScreen` already handled
`SCHEDULED` once its status-label map and cancel gate were extended —
opening a scheduled ride from the list, cancelling it (BR-135's
≥3h/₹0-<3h/₹30 rule), and seeing its `scheduled_for` time all reuse
that one screen unchanged otherwise. 11 new mobile tests — full suite
`flutter analyze` clean, `flutter test` 101/101 passed (was 90).

Step 9's other half — real FCM integration (§6.3) — is IMPLEMENTED
and verified, 2026-09-01, once the owner set up the Firebase project
and ran FlutterFire configure themselves:

- Owner-supplied: **VISTAAR Production** (project ID
  `vistaar-production-3a79a`), ONE Firebase project registered against
  the existing single `apps/mobile` Flutter app for both User and
  Sarthi roles (no separate per-role app or project, per ADR-0052).
  FlutterFire generated `lib/firebase_options.dart` and
  `android/app/google-services.json`; both are git-ignored (new
  `.gitignore` entries alongside `ios/Runner/GoogleService-Info.plist`
  and its macOS counterpart), same never-in-git discipline as
  MSG91/S3/Sentry.
- `pubspec.yaml` gained `firebase_core`/`firebase_messaging`.
  `main.dart` now calls `Firebase.initializeApp()` before `runApp()`
  and registers a top-level `firebaseMessagingBackgroundHandler` via
  `FirebaseMessaging.onBackgroundMessage()`.
- New `lib/core/notifications/push_notification_manager.dart` —
  `PushNotificationManager.start()`/`stop()` wrap permission request,
  real token fetch, registration/unregistration through the existing,
  **unmodified** `NotificationApi` (`registerDevice()`/
  `unregisterDevice()` from step 9's first half), token-refresh
  re-registration, and foreground/background message listening
  (deliberately just a debug log — no notification content/target
  screen has ever been designed for any push this backend sends). Every
  actual Firebase call is constructor-injected as a closure, defaulting
  to the real `FirebaseMessaging.instance` calls — the same DI pattern
  `RideApi`'s `accessToken` closure already established — which is what
  makes it unit-testable without touching the native SDK.
- Wired at `HomeRouter` (`initState`, both the cold-start-restore path
  and the live-login path) so it covers both roles from one hook point;
  `UserHomeScreen`/`SarthiHomeScreen`'s `_signOut()` now `await`s
  `PushNotificationManager.stop()` — which unregisters the device while
  the access token is still valid — **before** `AuthSession.signOut()`
  clears it.
- Android manifest gained `POST_NOTIFICATIONS`; iOS `Info.plist` gained
  `UIBackgroundModes: remote-notification`. Genuinely still open,
  outside what a non-Xcode/non-macOS environment can do: iOS has no
  `GoogleService-Info.plist` or `Podfile` yet (FlutterFire only
  generated the Android side so far), the Xcode "Push Notifications"
  capability has not been enabled, and no APNs key has been uploaded to
  Firebase Console — all four need a real Mac, Xcode, and Apple
  Developer Program access.
- 13 new tests: 12 in a new
  `test/core/notifications/push_notification_manager_test.dart`
  (permission/token/refresh/register/unregister/error-swallowing, all
  against injected fakes) plus 1 regression test in
  `sarthi_home_screen_test.dart` verifying the unregister-before-
  sign-out ordering against a real `NotificationApi` call. Full suite
  `flutter analyze` clean, `flutter test` 114/114 passed (was 101).

The native Contacts picker for Book for Someone Else — owner-approved
2026-09-01, previously deferred as real, separately-scoped
native-permission work — is IMPLEMENTED and verified the same day. See
§6.2 above for the full write-up: `flutter_contacts: ^2.3.1`, a new
`ContactsApi` (`lib/core/contacts/contacts_api.dart`) wrapping the
native OS contact picker (not an in-app list, so no bulk contacts read
ever happens), a new "Choose from Contacts" button on `BookRideScreen`
next to the existing manual fields, and `READ_CONTACTS`/
`NSContactsUsageDescription` declared in the platform manifests. 14 new
tests, full suite `flutter analyze` clean, `flutter test` 128/128
passed (was 114). A real `flutter build apk --debug` also confirmed the
native Android side actually compiles and links — this surfaced and
fixed one real, unrelated pre-existing bug (`compileSdk` needed pinning
to 37 for `flutter_secure_storage` 11.x). No physical Android device or
emulator was available in this environment to interact with the live
permission dialog; iOS is entirely untestable here (no Mac/Xcode) —
both gaps are the same class already flagged for push notifications
(§6.3).

Nothing further is buildable in this build order without new owner
input — every item is now either shipped or genuinely blocked on an
external decision (payment gateway, WhatsApp BSP, or the iOS
Xcode/APNs steps above, none of which are completable from this
environment).

Owner decisions confirmed in a third round, same day:

- **Role labels, final:** Customer → **User**, Rider → **Sarthi**. No
  "Guest" label anywhere — confirmed nothing needed renaming there.
- **Maps provider, final: MapTiler Cloud.** API key received and
  stored per the codebase's standing secrets discipline (never in git).
- **Architecture, final:** stay on the existing `apps/mobile` (one
  Flutter app, two role-based experiences) — do not create or revive
  `customer-mobile`/`driver-mobile`.
- **Schedule a Ride and Book for Someone Else stay deferred** — not
  implemented until their remaining product/ADR questions (§4.10/§4.11)
  are resolved.
- **"Continue implementation and verification according to existing
  VISTAAR governance"** — the same standing authorization pattern this
  project has used before (e.g. Admin Web's own "continue and complete
  the whole"): proceed through the approved build order, verify each
  step for real, report progress, without re-confirming every
  individual screen first.

Owner decisions confirmed in the second round, 2026-08-29:

- **Tech stack: hybrid (single codebase, cross-platform iOS + Android),
  not native.** This matches `apps/mobile`'s existing Flutter
  foundation exactly — no rebuild needed, this ratifies the choice
  already made rather than changing anything.
- **One app, two login roles (Customer / Rider).** Matches ADR-0027
  exactly — no change needed.
- **Two new Customer features added to scope: Schedule a Ride and Book
  for Someone Else.** Neither exists in the PRD, business-rules.md, or
  any ADR — both are genuinely new requirements. §4.10/§4.11 below
  scope what's already decidable and flag the real open questions each
  one raises before a backend contract (and, for Schedule a Ride, its
  own ADR) can be written. Nothing past those questions is invented.

Owner decisions confirmed in a second round, same day:

- **Role label: "Rider" → "Sarthi."** Everywhere the app currently says
  "VISTAAR Rider" (role selection, driver-facing copy) becomes
  "Sarthi." One point sent back for confirmation rather than guessed:
  the accompanying instruction that "customer will replace the word
  guest" wasn't clear enough to act on directly — see the question
  list at the end of this document.
- **Book for Someone Else — two real design questions resolved.** The
  ride-start OTP goes to *both* the booker and the linked contact (the
  actual rider); the actual rider is picked from the booker's phone
  contacts, not required to be a registered VISTAAR account. This adds
  a new required permission (Contacts) — scoped in §6.2 below. See
  §4.11's own updated status.
- **Schedule a Ride — cancellation policy resolved.** Cancelling ≥3
  hours before the scheduled ride time: ₹0 penalty. Cancelling <3
  hours before: ₹30 penalty. See §4.10's own updated status. The
  remaining open questions there (matching timing, fare lock, offer
  mechanism, no-driver-found handling, scheduling window) are
  unaffected and still need answers.
- **Maps provider: a real API key is being supplied.** Once it arrives
  (with which provider it's for), the map-entry/navigation/live-
  tracking rows across §4.1, §4.2, and §5.4 move from blocked to
  buildable. Not yet reflected as EXISTS below — the key hasn't arrived
  in this document yet, and per this codebase's own standing "never
  pick a vendor on the owner's behalf" rule, no specific provider is
  assumed here either.

0. How to read this document

Mirrors the Admin Web plan's own convention exactly. Every screen below
states one of three things: **EXISTS** (a real backend endpoint is
already there to build against), **NEW — SCOPED** (this plan specifies
the exact new endpoint needed, ready to build once approved), or
**NEW — NEEDS SCOPING** (the screen is named in the PRD but what it
should show/do isn't fully decided by any document, or depends on a
business rule the PRD itself marks TBD — flagged, not guessed past).
Nothing in this plan invents a fare rate, a threshold, or a business
rule PRD.md §62/§60 lists as still TBD.

1. Current state of `apps/mobile` (verified directly against the code)

`apps/customer-mobile` and `apps/driver-mobile` are dead — leftover
Flutter scaffolds from Phase 01's original "Customer mobile skeleton"/
"Driver mobile skeleton" tasks, superseded by ADR-0027's "one app, two
roles" decision. Neither has a `lib/` directory or a `pubspec.yaml`;
they are IDE/build artifacts only and should eventually be deleted
(not this plan's job).

`apps/mobile` is the real, current app (ADR-0027). What exists today,
confirmed by reading the actual source, not just its own README:

- Role selection (Customer / VISTAAR Rider) — `features/auth/role_
  selection_screen.dart`.
- Phone entry — `POST /api/v1/auth/otp/request`.
- OTP verify, with resend — `POST /api/v1/auth/otp/verify`.
- Session persistence to the platform keychain/keystore
  (`SecureTokenStorage`), restored on cold start
  (`SessionBootstrapper`); an expired session falls back to role
  selection rather than silently failing.
- One placeholder home screen per role (`CustomerHomeScreen`/
  `DriverHomeScreen`) — confirmed by reading both files directly: each
  is a static "Signed in as X" card with a sign-out button. No ride
  booking, no driver go-online/offer screens, no wallet, nothing else.
- `provider` for state, `http` for the API client, `flutter_test` for
  unit/widget tests (mocked HTTP, no backend required to run them) —
  the established pattern this plan continues rather than replaces.

Everything below this line is new work.

2. Backend readiness — verified module by module, not assumed

Before proposing any screen, the actual backend surface it would call
was checked directly (`api-contracts.md`'s customer/driver-facing
sections §6-§45, cross-referenced against the real routers in
`apps/backend/src/modules/`). Three real gaps surfaced that the PRD
names but the backend does not yet have any module for — these are
called out once here and referenced by number wherever they block a
screen below, rather than repeated in full each time:

- **[GAP-1] No standalone fare-estimate endpoint.** PRD §12 asks for
  "View estimated fare" as its own step before "Request a ride." The
  backend only computes a real fare as part of `POST /api/v1/rides`
  (ride creation itself) — there is no `GET`-style quote endpoint. The
  Admin Web's own Fare Management screens read published `pricing.
  fare_rules` rows, so the *rate table* a client-side estimate would
  need is real and queryable, but no endpoint exposes "here's roughly
  what this trip will cost" without actually creating a ride yet.
- **[GAP-2] No Rating module anywhere.** PRD §46 (two-way 1-5 star
  ratings after a completed ride) has zero backing — no `modules/
  rating/`, no table, no endpoint, confirmed by grepping every backend
  module directly.
- **[GAP-3] No Parking Proof / parking-charge composition.** PRD §45's
  upload-proof→AI-verify→charge-approved flow has no backend at all —
  `pricing.fare_quotes.parking_charge` is a real column but is always
  `0`; `modules/pricing/__init__.py`'s own docstring says so explicitly
  ("no parking-proof-to-fare composition").
- Also confirmed unbuilt, matching the PRD's own §4 Non-Goals framing
  for one and a real but separate gap for the other: **Ride Sharing**
  (§48, no `ride.share`/similar anywhere) and **Lost and Found** (§49,
  no module anywhere).
- **[GAP-4] No Ride Tracking endpoint at all** (found 2026-08-31, while
  building step 4). api-contracts.md §14 documents `GET .../tracking`
  and a WebSocket stream; neither exists anywhere in
  `modules/ride/router.py` or the rest of the backend. Previously this
  plan (incorrectly) treated §14 as "the API exists, only rendering on a
  map is blocked" — it does not exist at either layer.
- **[GAP-5] No No-Driver-Found retry/fare-increase endpoints**
  (found 2026-08-31, while building step 4). api-contracts.md §21
  documents `GET .../no-driver-options` and `POST .../fare-increase`;
  grepping the entire backend source finds neither anywhere. A ride
  that finds no driver simply stays SEARCHING indefinitely today —
  previously this plan (incorrectly) marked this row "EXISTS."
- **[GAP-6] `outstanding_penalty`/`total_payable` not implemented**
  (found 2026-08-31, while building step 4). ADR-0026 documents this as
  the target shape for both `POST /api/v1/rides` (§12) and
  `GET /api/v1/customers/me` (§8); reading `_ride_data()` and
  `_profile_data()` directly confirms neither field is actually
  returned by either live endpoint yet.
- **[GAP-7] No Driver Confirms Cash Payment endpoint** (found 2026-08-31,
  while building step 5). api-contracts.md §33 documents
  `POST .../cash-payment/confirm` but says, in its own text, that it is
  "Not built today; kept here as the corrected target shape" —
  confirmed by grepping the entire backend source for any
  `cash-payment` route: none exists. This plan previously (incorrectly)
  marked §5.4's "Cash payment confirmation" row "EXISTS."
- **[GAP-8] Destination Change can't show the fare before confirming**
  (found 2026-08-31, while building the mobile UI for step 6b).
  BR-082 requires "Customer sees revised fare → Customer confirms," in
  that order — verified directly against `modules/ride/router.py` that
  `POST .../destination-change`'s response never includes the computed
  fare for a BEYOND_ORIGINAL/DIFFERENT_ROUTE case; only `POST
  .../destination-change/confirm`'s response does, *after* the customer
  has already answered `confirmed`. Unlike GAP-1 through GAP-7, this
  isn't a missing endpoint — §25/§26 both exist and work — it's a
  response-shape gap that makes the endpoint unable to satisfy its own
  documented business rule. Not resolved as a backend fix; `apps/mobile`
  does not build a "confirm blind" screen around it (see below).

Real-time tracking is polling, not push: `api-contracts.md` §64
documents a WebSocket events shape, but no WebSocket server exists
anywhere in this codebase (grepped directly) — `GET /api/v1/rides/
{ride_id}` is the only mechanism today. api-contracts.md §14's own
"Ride Tracking" endpoint does not exist at all in the live backend
(verified 2026-08-31 while building step 4, by reading
`modules/ride/router.py` directly — no `/tracking` route anywhere) —
§14 documents only a route name and the same unimplemented WebSocket,
not a real, separate mechanism. A mobile client polls Get Ride; it does
not subscribe, and there is no live driver-location feed for a ride at
all today, not just an unrendered one.

Every other customer/driver-facing capability the PRD's MVP scope
(§56) names — registration/login, ride creation, matching/offers,
driver location updates, arrival, ride-start OTP, pickup/destination
change, early drop, completion, cancellation (both sides), wallet +
recharge (gateway-blocked, see §5 below), promotions, referrals,
outstanding charges, offline payment confirmation, SOS, support — has
a real, tested backend endpoint today. This plan's screens reuse those
directly; nothing new is proposed for them beyond the mobile UI itself.

3. Design system

No mobile brand spec exists beyond what `apps/mobile/lib/core/theme/
app_theme.dart` already establishes (a single shared Material theme,
used by both roles today). Proposed: extend that same theme file with
the VISTAAR Gold/Deep Green brand pair the Admin Web plan already
established (`--vistaar-gold: #EFBF04`, `--vistaar-deep-green:
#003314`) rather than inventing a second palette for the same product
— flagged for owner confirmation the same way the Admin Web plan
flagged its own supporting palette, not treated as decided.

4. Customer flow

4.1 Home / Book a Ride — permission: authenticated Customer role

| Screen | API | Status |
| :--- | :--- | :--- |
| Pickup/destination entry | client-side only (no geocoding backend exists) | IMPLEMENTED (2026-08-31) as the fallback this row itself proposed — plain latitude/longitude fields, no maps provider. Upgrading to map/address entry once one is selected is a UI change only, not a new backend contract |
| Vehicle category + fare display | `POST /api/v1/rides` (§12) computes the real fare; nothing shows it *before* the ride is created | IMPLEMENTED (2026-08-31) using this row's own second fallback — category picked before submitting, the real fare shown immediately after on `RideStatusScreen`, no pre-booking estimate. GAP-1 (a dedicated estimate endpoint) stays open if that UX is ever wanted instead |
| Outstanding charges / applicable promotions shown pre-booking | `GET /api/v1/customers/me` (§8, outstanding_penalty/total_payable, ADR-0026) | **NEW — NEEDS SCOPING** (real backend gap, not just undocumented): verified 2026-08-31 by reading `modules/customer/router.py`'s `_profile_data()` directly — `outstanding_penalty`/`total_payable` are ADR-0026's documented *target* shape, never implemented; the live endpoint returns neither field |
| Request ride | `POST /api/v1/rides` (§12) | IMPLEMENTED (2026-08-31 — `BookRideScreen`, `RideApi.createRide()`) |

4.2 Ride Status / Tracking — permission: the ride's own customer only
(IDOR-safe, same ownership check the backend already enforces)

| Screen | API | Status |
| :--- | :--- | :--- |
| Live ride status (SEARCHING→ACCEPTED→ARRIVED→STARTED→COMPLETED→CLOSED) | `GET /api/v1/rides/{ride_id}` (§13), polled every 4s | IMPLEMENTED (2026-08-31 — `RideStatusScreen`, `RideApi.getRide()`) — polling only, no push-on-change (no WebSocket server exists, see §2) |
| Driver/vehicle info once assigned | same response, `driver`/`vehicle` sub-objects | IMPLEMENTED (2026-08-31) |
| Map view of driver location | Ride Tracking (§14) | **NEW — NEEDS SCOPING, and a real backend gap, not just a missing SDK**: verified 2026-08-31 by reading `modules/ride/router.py` directly — there is no `/tracking` route in the live backend at all. §14 documents only a route name and an unimplemented WebSocket (see §2 above) — this row was previously (incorrectly) treated as "the API exists, only rendering is blocked"; it does not exist at either layer |
| Ride-start OTP display | `POST /api/v1/rides/{ride_id}/otp/refresh` (§18) | IMPLEMENTED (2026-08-31) — gated on the ride being ARRIVED specifically (`RideService.refresh_otp()`'s own state check, confirmed by reading the service code, not just this plan's earlier looser wording); SEARCHING/ACCEPTED/STARTED all reject it |
| No-driver-found retry / fare increase | `GET .../no-driver-options` + `POST .../fare-increase` (§21) | **NEW — NEEDS SCOPING, and a real backend gap**: verified 2026-08-31 by grepping the entire backend source — neither endpoint exists anywhere. A ride that finds no driver simply stays SEARCHING indefinitely today; `RideStatusScreen` shows that state honestly rather than a retry/increase-fare UI the backend can't answer. PRD §18's custom-increase maximum (§62, TBD) is moot until the endpoints themselves exist |

4.3 Pickup / Destination Change — permission: ride's own customer

| Screen | API | Status |
| :--- | :--- | :--- |
| Change pickup | `POST .../pickup-change` (§22) | **IMPLEMENTED, 2026-08-31** (`RideStatusScreen`, `RideApi.changePickup()`) — ADR-0056 (owner decision) replaced the old >250m driver-decision/customer-confirmation design with a hard 100m threshold — within it, applies immediately (unchanged shape); beyond it, rejected outright (`PICKUP_CHANGE_TOO_FAR`), no driver involved, customer must cancel + rebook instead. §23-24 (driver decision, customer confirmation) are removed. Backend: `RideService.request_pickup_change()`/`router.py` simplified, full test suite 1244 passed; mobile: `flutter test` 60/60 passed. See the ADR for the full reconciliation (business-rules.md BR-071/074-078, state-machines.md §14) |
| Change destination | `POST .../destination-change` (§25), confirmation (§26) | IMPLEMENTED, 2026-08-31 (`RideStatusScreen`, `RideApi.changeDestination()`), while STARTED — the free WITHIN_ROUTE case applies cleanly; a fare-changing case (BEYOND_ORIGINAL/DIFFERENT_ROUTE) is auto-rejected with an honest message rather than confirmed blind — see **GAP-8** below, a real response-shape gap that makes §26's documented "customer sees the fare, then confirms" order unbuildable as the API stands today |

4.4 Cancellation — permission: ride's own customer

| Screen | API | Status |
| :--- | :--- | :--- |
| Cancel ride | Customer Cancellation (§19) | IMPLEMENTED (2026-08-31 — `RideStatusScreen`, `RideApi.cancelRide()`) — real penalty/grace-period rules already enforced server-side |

4.5 Payment — permission: ride's own customer

| Screen | API | Status |
| :--- | :--- | :--- |
| Payment breakdown (fare + outstanding, before confirming) | `GET` Payment Breakdown (§30) | EXISTS |
| Select online payment | Customer Payment (§29) — real gateway integration is blocked (Phase 10, SBI clarification pending) | **BLOCKED — external** (payment gateway) |
| Select offline (cash) payment | Offline Payment (§32) — confirmation itself is a *driver*-side action (§33) | EXISTS on the API side; this screen is display-only for the customer |

4.6 Wallet-adjacent: Outstanding charges — permission: own account

| Screen | API | Status |
| :--- | :--- | :--- |
| View outstanding penalty/settlement total | `GET /api/v1/customers/me` (ADR-0026) | EXISTS |
| Pay down outstanding balance directly (not via next ride) | no such endpoint exists | **NEW — NEEDS SCOPING**, and transitively blocked on the same payment gateway as §4.5 regardless |

4.7 Promotions / Referrals — permission: own account

| Screen | API | Status |
| :--- | :--- | :--- |
| View active promotions | no dedicated customer-facing "my promotions" read endpoint found in §37 beyond what auto-applies at booking | **NEW — NEEDS SCOPING**: `promotion.entitlements` exists and is populated (ADR-0019), but no documented `GET` surfaces it to the owning customer directly — worth a small scoping pass, likely EXISTS-adjacent (a thin new read endpoint over an already-real table, the same shape Driver Strike History was earlier this project) |
| View/share referral code | Referral (§38) | Referral code generation exists; confirm the exact `GET` shape before building — not fully traced in this pass |

4.8 Rating — permission: ride's own customer, post-COMPLETED

| Screen | API | Status |
| :--- | :--- | :--- |
| Rate the driver | none | **NEW — NEEDS SCOPING** (GAP-2) — no Rating domain exists at all; needs its own ADR (schema, one rating per completed ride, retaliation-risk timing per PRD §46) before any screen |

4.9 Safety / Support — permission: ride's own customer or general account

| Screen | API | Status |
| :--- | :--- | :--- |
| SOS | `POST /api/v1/rides/{ride_id}/sos` (§41) | IMPLEMENTED (2026-08-31 — an AppBar action on `RideStatusScreen`/`RideExecutionScreen`, offered while the ride isn't terminal) |
| Support case (create + view conversation) | Support (§44) | IMPLEMENTED (2026-08-31 — `ContactSupportScreen`, `SupportCaseScreen`) — no "list my cases" endpoint exists (verified against the live router), so a case is only ever reachable right after this app creates it |
| AI-assisted support | AI Support (§45) | **BLOCKED — external** (no LLM provider/credential, same gap Phase 14 already named) |
| Ride sharing (share status with a third party) | none | **NEW — NEEDS SCOPING** — no backend module exists |
| Lost and found | none | **NEW — NEEDS SCOPING** — no backend module exists |

4.10 Schedule a Ride — owner-added 2026-08-29, permission: authenticated
Customer role

Not in PRD §56's MVP scope — PRD §57 (V2 Scope) explicitly lists
"Scheduled rides" as *not required for MVP unless separately
approved*. The owner has now separately approved it, so it moves into
this plan's scope, but the design itself isn't decided anywhere yet.
`POST /api/v1/rides` today creates a ride that enters `SEARCHING`
immediately — there is no concept anywhere in `ride.rides`,
`state-machines.md`, or `domain-design.md` of a ride that exists but
isn't searching yet. This is a real new ride-domain state/flow, not a
UI-only addition on top of an existing endpoint, so it needs its own
ADR before any backend contract is written — the same gate every other
new capability in this project has gone through (most recently
Compose/Send Broadcast, ADR-0055). Real open questions that ADR would
need to resolve:

| Screen | API | Status |
| :--- | :--- | :--- |
| Pick a future date/time for the ride | none | **IMPLEMENTED — ADR-0057** (2026-08-31); `scheduled_for` on Create Ride (§12.1), a date/time picker on `BookRideScreen` (`showDatePicker`/`showTimePicker`, no new package) |
| Confirm/view a scheduled ride ahead of time | none | **IMPLEMENTED — ADR-0057**; `GET /api/v1/rides?status=SCHEDULED`, a new `ScheduledRidesScreen` reached from `UserHomeScreen` |
| Cancel/reschedule a scheduled ride | none | **IMPLEMENTED — ADR-0057** for cancellation (₹0/₹30, BR-135) — `RideStatusScreen`'s existing Cancel Ride button, extended to also offer while `SCHEDULED`; reschedule itself still not designed — not asked, and this plan does not assume it exists (cancel-and-rebook is the only path today) |

All open questions below are RESOLVED — owner decision, 2026-08-31,
via a structured two-round clarification exchange, recorded as
ADR-0057 (status: Accepted) and fully implemented on the backend the
same day (1277 backend tests passed, 5 skipped, 0 failed — was 1244).
The mobile app's own screens for this feature are the only remaining
work:

- **Matching timing — RESOLVED: reserve a driver in advance.** A new
  `SCHEDULED` ride state (state-machines.md §3.9) holds the ride until
  a fixed window before pickup, then re-enters the *existing*,
  unmodified `SEARCHING` flow — no new offer type. See ADR-0057
  Decision 1 for why this turned out to need zero new matching
  engineering.
- **Fare — RESOLVED: locked at booking time.** Reuses the existing
  `pricing.fare_quotes` mechanism (already built for destination-change
  quoting) rather than a new domain concept — a quote is created and
  locked the moment the ride is scheduled.
- **Driver assignment lead time — RESOLVED: 30 minutes before pickup.**
  An engineering default (not an independently re-derived business
  value) for how close to `scheduled_for` matching actually begins.
- **Cancellation boundary/strike — RESOLVED:** a strict `≥`/`<` 3-hour
  boundary; no strike recorded either way (BR-135) — the ≥3h/₹0,
  <3h/₹30 fee split itself was already decided 2026-08-29.
- **No-driver-found handling — RESOLVED: same as an immediate ride.**
  Reuses §21's retry/fare-increase flow once it exists — no
  scheduled-specific version.
- **Scheduling window — RESOLVED: 1 hour minimum, 24 hours maximum**
  (BR-137).

4.11 Book for Someone Else — owner-added 2026-08-29, permission:
authenticated Customer role

Not named anywhere in the PRD or business-rules.md. `ride.rides.
customer_id` today implicitly means "the person actually in the
vehicle" — folded into the same ADR-0057 as §4.10 (both were decided in
the same session), per that ADR's own Decision 2. Two design questions
were already resolved 2026-08-29, restated here for continuity:

- **Who gets the OTP — RESOLVED.** The ride-start OTP (§18) is sent to
  *both* the booker and the linked contact (the actual rider) — not
  just one or the other. Whoever is physically in the vehicle (the
  actual rider, in the normal case) is the one the driver asks for it,
  and now has it even if the booker isn't present.
- **Registered rider or guest — RESOLVED, guest.** The actual rider is
  picked from the booker's own phone contacts (name + phone number) —
  not required to be a registered VISTAAR account. This is the reason
  the app needs a new permission it didn't need before: **Contacts**
  (scoped in §6.2 below, the same treatment §6.1 gave Location). Since
  the rider isn't necessarily a VISTAAR account, their copy of the OTP
  most plausibly arrives by SMS (the existing MSG91 channel, already
  built) rather than in-app — this plan assumes that delivery mechanism
  but flags it, since it wasn't stated explicitly.

All remaining questions are RESOLVED (owner decision, 2026-08-31,
ADR-0057 — Accepted and fully implemented on the backend the same day):

| Screen | API | Status |
| :--- | :--- | :--- |
| Enter the actual rider's details when booking | none | **IMPLEMENTED — ADR-0057**; `linked_contact` on Create Ride (§12.1), a name/phone form on `BookRideScreen`, either typed by hand or filled in via the native Contacts picker (§6.2, owner-approved and IMPLEMENTED 2026-09-01) — manual entry remains §6.2's own documented "if denied" fallback |
| The actual rider's own view of the ride (if any) | none | **RESOLVED — booker-only for now** (BR-139); deferred to whenever Ride Sharing (§4.9) exists |

- **Who is billed — RESOLVED: the booker by default**, with cash-on-
  the-spot as a fallback the owner also approved — but §33's cash-
  payment-confirmation endpoint still doesn't exist anywhere in the
  backend (an already-tracked, unrelated gap), so only the booker-
  billed path actually ships until that's built (BR-138).
- **Rider visibility — RESOLVED: booker-only** for this first version
  (BR-139) — no shared-link view yet.
- **Promotions/referral eligibility — RESOLVED: the booker's account**
  (BR-140) — proposed as a reasonable default rather than asked
  directly, since the booker is billed and is `ride.rides.customer_id`
  for every other purpose; flagged in ADR-0057 as open to override.
- **Contact storage — RESOLVED: both name and phone.** Also a proposed
  default, not asked directly — costs nothing beyond what the Contacts
  permission already grants access to, and lets the driver's own app
  eventually show "picking up Priya" instead of a bare number.

5. Driver flow

5.1 Onboarding / Profile — permission: authenticated Driver role

| Screen | API | Status |
| :--- | :--- | :--- |
| Profile creation (name required on first write, ADR-0004) | `PATCH /api/v1/drivers/me` (§9) | EXISTS |
| Document submission (Government ID, Driving Licence) | Driver document endpoints (§9) | EXISTS |
| Verification status view | same profile read | EXISTS — review/approval itself is admin-side (Admin Web, already built) |
| Vehicle registration + documents (RC, Insurance) | Vehicle APIs (§11) | EXISTS |
| Vehicle activation (one active vehicle rule, BR-122) | `POST .../vehicles/{id}/activate` (§11) | EXISTS |

5.2 Online / Offline + Location — permission: own driver session

| Screen | API | Status |
| :--- | :--- | :--- |
| Go online/offline | Driver Availability (§10) | IMPLEMENTED (2026-08-30 — `SarthiHomeScreen`, `DriverAvailabilityApi`) |
| Location updates while online (~5s interval, PRD §15) | `POST /api/v1/drivers/me/location` (§15) | IMPLEMENTED for the foreground case (2026-08-30 — `Timer.periodic`, stopped on going offline/leaving the screen). Genuine background operation (Android foreground service, iOS background location mode) is real remaining client engineering, not yet built — flagged above, not a backend gap either way |

5.3 Ride Offers — permission: own driver session

| Screen | API | Status |
| :--- | :--- | :--- |
| Incoming offer (countdown to `expires_at`) | `GET /api/v1/drivers/me/ride-offers` (§16), polled every 4s | IMPLEMENTED (2026-08-31 — `RideOfferApi`, `RideOfferScreen`, polling driven from `SarthiHomeScreen`), same "no push, poll" caveat as §4.2 |
| Accept | Accept Offer (§16) | IMPLEMENTED (2026-08-31) — the wallet-lock atomic accept transaction (ADR-0014); requires the `Idempotency-Key` header (`ApiClient.post()`'s new `extraHeaders`, a `uuid` v4 per attempt). An old, now-stale "not implemented, blocked on Wallet" note still sits in this section of api-contracts.md from Phase 5 — the live backend code fully implements it |
| Reject | Reject Offer (§16) | IMPLEMENTED (2026-08-31) |

5.4 Ride Execution — permission: assigned driver only

| Screen | API | Status |
| :--- | :--- | :--- |
| Navigate to pickup | none — needs the same unselected maps/routing provider as §4.1/§4.2 | **NEW — NEEDS SCOPING** (external) |
| Mark arrived (GPS-gated) | Driver Arrival (§17) | IMPLEMENTED (2026-08-31 — `RideExecutionScreen`, `RideApi.markArrived()`) |
| Enter customer's OTP to start | Ride Start OTP (§18) | IMPLEMENTED (2026-08-31 — `RideApi.startRide()`) |
| Pickup-change decision (Proceed/Pass) | Driver Pickup-Change Decision (§23) | **REMOVED under ADR-0056** (owner decision, 2026-08-31) — no driver decision exists for pickup change anymore; a change beyond 100m is rejected outright at the customer's own request endpoint, never reaching the driver. Nothing for `RideExecutionScreen` to wire in |
| Destination-change handling | same as customer side, driver reads the updated route/fare | EXISTS (not yet wired into this screen — build order step 6b) |
| Early-drop handling | Early Drop (§27) | EXISTS (not yet wired into this screen) |
| Complete ride (GPS-gated) | Ride Completion (§28) | IMPLEMENTED (2026-08-31 — `RideApi.completeRide()`) |
| Fare summary at completion | same response | IMPLEMENTED (2026-08-31) |
| Cash payment confirmation | Driver Confirms Cash Payment (§33) | **NEW — NEEDS SCOPING, and a real backend gap**: confirmed 2026-08-31 by grepping the entire backend source — no `cash-payment`-anything route exists anywhere. §33's own text already read "Not built today; kept here as the corrected target shape" — this plan previously (incorrectly) marked it "EXISTS" |
| Cancel (with strike/penalty rules) | Driver Cancellation (§20) | IMPLEMENTED (2026-08-31 — `RideExecutionScreen`, `RideApi.driverCancelRide()`), ACCEPTED-only per the live service's own gate |
| Parking proof upload | none | **NEW — NEEDS SCOPING** (GAP-3) |

5.5 Wallet — permission: own driver session

| Screen | API | Status |
| :--- | :--- | :--- |
| Balance + outstanding settlement | Wallet (§34) | IMPLEMENTED (2026-08-31 — `WalletApi`, `WalletScreen`, reached from a new AppBar icon on `SarthiHomeScreen`) |
| Transaction history | `GET /api/v1/drivers/me/wallet/transactions` (ADR-0024) | IMPLEMENTED (2026-08-31 — paginated, "Load more") |
| Recharge | Wallet Recharge (§35) | **BLOCKED — external** (same payment gateway as §4.5) |
| Joining bonus / referral bonus visibility | reflected as real wallet transaction rows, no separate screen needed | IMPLEMENTED (2026-08-31 — shown via `WalletTransaction`'s `transactionType`/`isCredit`, no separate screen needed, as this row already anticipated) |
| Customer-side wallet / outstanding-charges view | none — no customer-facing wallet endpoint exists (GAP-6) | **BLOCKED — backend gap**, unchanged by this step |

5.6 Advertisements — permission: assigned driver only, if any campaign

| Screen | API | Status |
| :--- | :--- | :--- |
| View assigned ad campaign, submit installation proof | Advertisement HTTP surface exists (ADR-0046) but is documented as the **admin** surface only — no driver-facing submission endpoint | **NEW — NEEDS SCOPING**, matching the Admin Web plan's own note that "a driver-facing proof-submission endpoint remains unbuilt (ADR-0046 is the admin surface only)" |

5.7 Rating / Safety / Support — mirrors §4.8/§4.9's driver-side halves
exactly (rate the customer — same GAP-2; SOS, Support — IMPLEMENTED
2026-08-31, same `RideExecutionScreen`/`ContactSupportScreen` wiring).

6. Cross-cutting

6.1 App-launch location permission — owner-added 2026-08-29. Not a
new backend contract — permission handling is entirely client-side
(Flutter's OS-level permission APIs); the coordinates it unlocks
already have a real destination once granted: `POST /api/v1/drivers/
me/location` (§15, already EXISTS) for the driver's periodic updates,
and client-side pickup pre-fill for the customer (reading the device's
own current position needs no backend call). **Status: NEW — SCOPED**
— no business-rule ambiguity, ready to build once the one real
placement decision below is confirmed.

Proposed design:

- Prompted right after role selection, before or during login — after
  role selection specifically (not a blanket prompt shown before the
  app even knows which role is signing in), so the system prompt's
  context ("VISTAAR needs your location to match you with nearby
  drivers" vs. "...to show you nearby ride requests") is
  role-appropriate.
- iOS: request `NSLocationWhenInUseUsageDescription` at this point for
  both roles. `NSLocationAlwaysAndWhenInUseUsageDescription`
  (background location) is requested separately, only when a Driver
  actually goes online (§5.2) — not upfront. Apple's own App Store
  review guidelines penalize requesting background location before a
  feature that actually needs it is reached, and a Customer never
  needs background location at all.
- Android: runtime `ACCESS_FINE_LOCATION` at this point. `ACCESS_
  BACKGROUND_LOCATION` is a distinct, separately-requestable
  permission on Android 10+ and cannot be bundled into the same
  prompt — requested only when a Driver goes online, same staging as
  iOS.
- Denial handling: the app must stay usable if location is denied. A
  Customer can still type a pickup address manually (§4.1's own entry
  screen already allows for this — it doesn't require a device
  location). A Driver cannot go online without location granted; that
  screen shows a clear explanation and a button linking to the OS
  settings screen, not a dead end.
- Re-prompt logic: if denied once, the app does not re-prompt on every
  launch — it checks permission status and offers a way to grant it
  later from account/profile settings, the standard platform-guidance
  pattern (repeatedly re-prompting after a denial is itself flagged by
  both app stores' review guidelines).

The staging above (minimal "while using" first, background permission
only once a Driver actually goes online) is this plan's own engineering/
UX recommendation, not a decision already on record anywhere — confirm
or override at review.

6.2 Contacts permission — owner-added 2026-08-29 (second round), a
consequence of Book for Someone Else's §4.11's own resolved design: the
actual rider is picked from the booker's phone contacts. **Status:
IMPLEMENTED and verified, 2026-09-01** (owner-approved the same day) —
the proposed design below was built essentially as scoped, with one
refinement found once a real package was actually evaluated.

Design, mirroring §6.1's own pattern:

- **When:** requested when the User taps a new "Choose from Contacts"
  button — shown only once "Book for someone else" is toggled on, not
  at app launch alongside Location. Mirrors this same screen's own
  "Schedule for later" pattern exactly: the toggle reveals a section,
  a dedicated button performs the actual native action, so the
  permission dialog only ever appears in direct response to that one
  explicit tap, never merely from flipping the toggle.
- **Package:** `flutter_contacts: ^2.3.1` (QuisApp, actively maintained,
  resolves cleanly against this app's `sdk: ^3.13.0`/Flutter 3.47.0).
- **Picker, refined from the original proposal:** rather than this app
  fetching the full contacts list itself (`FlutterContacts.getAll()`)
  and rendering its own in-app list/search screen, `ContactsApi`
  (`lib/core/contacts/contacts_api.dart`) calls
  `FlutterContacts.native.showPicker()` — the OS's own native contact
  picker UI (Android's system Contacts app in picker mode /
  iOS's `CNContactPickerViewController`). This app never receives more
  than the one contact the User actually picks; there is no bulk
  contacts list ever held in this app's memory at all, which makes the
  "reads only the selected contact's name and phone number" scope line
  below literally true by construction, not just a policy this app
  chooses to follow.
- **iOS:** `NSContactsUsageDescription` (`ios/Runner/Info.plist`),
  requested at that point via `FlutterContacts.permissions.request()`.
  Native note: iOS's own picker doesn't strictly require a granted
  permission to return picked-contact data (Apple's picker mediates
  access itself) — this app requests permission before opening it
  anyway, so both platforms go through the identical gated,
  testable flow.
- **Android:** runtime `READ_CONTACTS` (`AndroidManifest.xml`),
  requested at that point. Unlike geolocator/firebase_messaging,
  `flutter_contacts`'s own AAR manifest declares no permission at all
  (verified directly against the plugin's package contents) — this app
  must, and does, declare it explicitly. `WRITE_CONTACTS` is
  deliberately not declared — this app only ever reads, never
  creates/edits/deletes a contact. Android's native picker specifically
  throws unless `READ_CONTACTS` is already granted when asked for the
  phone-number property, which is exactly why `ContactsApi.pickContact()`
  must only be called after `requestPermission()` returns `true`.
- **Scope:** the app only ever reads a contact's name + phone number
  to prefill the booking form — nothing is uploaded to VISTAAR's
  backend or stored server-side beyond what the booker explicitly
  submits with that one booking (no bulk contact sync, no address-book
  upload).
- **If denied, cancelled, or no phone number on the picked contact:**
  the booker can still type the rider's name and phone number by hand
  — the manual fields were never removed, only a new button was added
  above them; a denied permission additionally shows a one-line
  SnackBar pointing at that fallback.
- **Testing:** `flutter analyze` clean; 10 new unit tests
  (`test/core/contacts/contacts_api_test.dart`, injected fakes — no
  real `FlutterContacts` call is reachable from a widget/unit test,
  same reasoning as `PushNotificationManager`'s own tests) plus 4 new
  widget tests in `book_ride_screen_test.dart`; full suite 128/128
  passed (was 114). A real `flutter build apk --debug` was also run to
  confirm `flutter_contacts`'s native Android code actually compiles
  and links, not just that the Dart side type-checks — this surfaced
  one real, pre-existing, unrelated bug: `flutter_secure_storage` 11.x
  now requires `compileSdk 37`, but `android/app/build.gradle.kts` was
  still deriving `compileSdk` from Flutter's own bundled default (36).
  Fixed by pinning `compileSdk = 37` explicitly (Gradle's own
  recommended fix; doesn't change `minSdk`/`targetSdk`, so no runtime
  behavior or device-compatibility change) — this had silently blocked
  *any* real Android build in this project, not just this feature's;
  it was only ever caught because this task specifically asked for a
  real build. No physical Android device or emulator was available in
  this environment (`flutter devices`/`flutter emulators` both confirm
  none connected or configured, and no Android system image is
  installed to create one) — the interactive permission-dialog and
  native-picker UI itself was therefore verified through the widget
  tests' injected fakes, not a live tap-through; the real Android build
  and permission/manifest wiring were verified for real. **iOS is
  untestable here entirely** — same standing limitation as push
  notifications (§6.3): no Mac/Xcode exists in this environment, so
  neither a real iOS build nor `NSContactsUsageDescription`'s actual
  runtime prompt has been exercised, only written correctly by
  inspection against Apple's and the plugin's own documented
  requirements.

6.3 Push notifications — device-token registration (ADR-0052) is
already built on the backend (`POST/DELETE /api/v1/notifications/me/
devices`) and is identity-agnostic (works for both roles). This app's
`NotificationApi` (build order step 9, 2026-08-31) calls both
endpoints and is tested against them, and is now fully wired to the
real `firebase_messaging` SDK via `PushNotificationManager`
(2026-09-01) — permission prompt, real token registration on login,
token-refresh re-registration, and unregistration on sign-out, against
the owner's real Firebase project (`vistaar-production-3a79a`). Only
the Android side is fully configured end-to-end; iOS still needs its
own `GoogleService-Info.plist`/`Podfile`, the Xcode "Push
Notifications" capability, and an APNs key uploaded to Firebase
Console — none completable without a real Mac/Xcode/Apple Developer
account (see the build order's step 9 write-up above for the full
list). `PUSH_PROVIDER` locally now runs as `fcm` (a git-ignored root
`.env`, ADR-0052 §8, 2026-09-01) once the owner supplied the backend's
own Firebase Admin SDK credential; production/Kubernetes deployment is
unaffected and still defaults to `dev` (a separate deployment step, not
completable from this environment — see ADR-0052 §8 for why).

6.4 Localization — PRD §6 requires English/Hindi from the start. No
work has been done on this in `apps/mobile` yet (login screens are
English-only today, confirmed by reading them). Flutter's built-in
`intl`/ARB-file localization is the standard approach; this plan
proposes it but treats exact string translations as a content task,
not an engineering blocker.

7. What this plan does NOT propose inventing

- A maps/routing provider selection — reserved externally (roadmap
  §25.0), blocks pickup/destination map entry, driver navigation, and
  live map tracking specifically (screens above name each instance).
- A payment gateway — reserved externally (Phase 10/ADR-0025/ADR-0026),
  blocks online customer payment and wallet recharge specifically.
- Rating, Parking Proof, Ride Sharing, Lost and Found — no backend
  module exists for any of the four; each needs its own scoping pass
  (and likely ADR, per this codebase's §0.3 new-public-API-contract
  gate) before a screen can be designed against a real contract, the
  same treatment Compose/Send Broadcast got before ADR-0055.
- AI Support — blocked on an LLM provider/credential, unaffected by
  anything mobile-side.
- A standalone fare-estimate endpoint (GAP-1) — flagged as a real
  product-behavior question (show a number before booking vs. show the
  real fare the instant the ride is created), not assumed either way.

8. Recommended build order (a sequencing suggestion, not a decision)

Everything below is buildable today against a real, already-tested
backend, in rough dependency order:

1. App-launch location permission (§6.1) — comes before everything
   else below, since Driver Online/Offline (step 2) and Customer Book a
   Ride (step 3) both read from it (with the manual-entry/denied-
   permission fallbacks §6.1 already specifies).
2. Driver: Online/Offline + location updates (§5.2) — the shortest
   path to a real, testable feature loop, and a prerequisite for every
   later driver screen ever receiving an offer.
3. Driver: Ride Offers — incoming/accept/reject (§5.3).
4. Customer: Book a Ride (§4.1, minus the map-entry/fare-estimate
   NEEDS-SCOPING items — a plain lat/lng or address-text input and a
   "fare shown after you request" flow can ship without either) and
   Ride Status/Tracking (§4.2, polling, no map rendering).
5. Driver: Ride Execution (§5.4, minus navigation and parking proof) —
   arrival, start OTP, completion, cash confirmation.
6. Both: Cancellation (§4.4/§5.4's own row) and Pickup/Destination
   Change (§4.3/§5.4).
7. Both: Wallet views (§5.5, minus Recharge) and outstanding-charge
   display (§4.5/§4.6, minus online payment).
8. Both: Safety/SOS and Support (§4.9/§5.7's EXISTS rows).
9. Push notifications (§6.3) once a real Firebase credential exists;
   device-token registration itself can be wired earlier and simply do
   nothing until then, the same "wired, real credential arrives later"
   pattern every other provider integration in this codebase follows.

Everything flagged NEW — NEEDS SCOPING or BLOCKED above is deliberately
excluded from this ordering — each needs its own decision first, the
same gate every prior new-contract feature in this project has gone
through (ADR-0054, ADR-0055, etc.). Schedule a Ride (§4.10) and Book
for Someone Else (§4.11) are additive at the end (step 10), once their
own open questions are answered and an ADR records the design — they
don't block anything in steps 1-9, and nothing in steps 1-9 blocks
them either, since both are new ride-entry-point features layered on
top of a `POST /api/v1/rides`-shaped flow that step 4 already builds
the ordinary version of.

9. Testing

Continues `apps/mobile`'s own established pattern (its README already
states this): `flutter test` — unit + widget tests against a mocked
HTTP client, no real backend required to run them, mirroring this
backend's own "fake repository" unit-test convention. A smaller set of
tests against the real local backend (the same "skip, don't fail, if
Postgres/the backend is unreachable" convention `apps/backend/tests/`
already uses) is proposed for the handful of genuinely stateful flows
(offer accept, ride lifecycle) once those screens exist.

10. Open questions, consolidated (as of this update, 2026-08-31)

Everything the owner has answered so far is folded into the relevant
section above and not repeated here. Role label clarity and Maps
provider identification (both listed as open in an earlier version of
this section) were resolved in the "Owner decisions confirmed in a
third round" narrative above — Sarthi/User, MapTiler Cloud — and are
not restated here.

**Schedule a Ride (§4.10) and Book for Someone Else (§4.11) — RESOLVED
and backend-IMPLEMENTED, 2026-08-31, ADR-0057.** Every question this
section previously listed for both features now has an answer,
recorded in that ADR and cross-referenced from §4.10/§4.11 above.
Nothing open here — what's left is the mobile screens themselves,
tracked in §4.10/§4.11's own tables, not a further question.

11. Next step

Superseded repeatedly since 2026-08-29 as build order steps 1-9 shipped
(see the dated status entries near the top of this document, the
authoritative current-state record — this section is left as historical
scaffolding, not updated per-step). As of 2026-08-31: steps 1-9 are
done; step 10 (Schedule a Ride & Book for Someone Else)'s backend is
fully implemented (ADR-0057) — its mobile screens are next.
