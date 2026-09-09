VISTAAR — Authoritative Current Status

Date: 2026-09-04
Supersedes every completion claim in docs/roadmap.md (already marked
Superseded), docs/VISTAAR_IMPLEMENTATION_ROADMAP.md, and
docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md wherever they conflict with
this document — those remain as historical logs of what each task did
at the time (per this project's established "annotate, don't rewrite"
practice), but THIS document is the one to read for "is X done today."
Verified against actual current code, not against those documents'
own claims, for every phase below (backend: real router/service/test
inspection this session and prior sessions in this thread; mobile: real
file inventory this session; infra: real file inspection + YAML syntax
validation this session).

Five status categories, used consistently below:
- **COMPLETE** — built, tested, verified against real code.
- **AUTONOMOUS ENGINEERING REMAINING** — buildable without external
  input; not done yet, purely a matter of engineering time.
- **BLOCKED BY EXTERNAL CREDENTIAL/PROVIDER** — needs a real
  credential, account, or third-party API/contract not available here.
- **BLOCKED BY BUSINESS DECISION** — needs an owner decision (a
  business rule, a value, a scope call) not yet made.
- **INTENTIONALLY DEFERRED** — explicitly postponed by owner
  instruction, not a gap to close.

═══════════════════════════════════════════════════════════════════
PART 1 — PHASE-BY-PHASE STATUS (1–21)
═══════════════════════════════════════════════════════════════════

Phase 1 — Foundation: COMPLETE. Backend/mobile/admin-web scaffolding,
CI, migrations framework, base config.

Phase 2 — Identity & Auth: COMPLETE. Corrected 2026-09-07 — this line
previously listed Admin RBAC and Admin MFA as BLOCKED BY BUSINESS
DECISION; both were actually decided and fully built well before this
session even started. Admin RBAC (ADR-0009 Conflict 1, resolved
2026-08-26, built via ADR-0040, BR-126/BR-127): two roles
(`SUPER_ADMIN`, unlimited; `ADMIN`, an employee with per-module
`admin.permissions` rows, each `VIEW` or `MANAGE`) across a 20-module
catalog, with Admin Management and Settings permanently
Super-Admin-only — verified directly against
`modules/admin/domain/entities.py` (`AdminRole`/`AdminModule`/
`AccessLevel`), real and enforced on every admin endpoint. Admin MFA
(ADR-0051, 2026-08-28): Enroll/Confirm/Disable/Verify, api-contracts.md
§7.3, real. The one genuinely still-open item ADR-0009 itself names is
much narrower — `admin.audit_logs` is still missing the `actor_role`/
`ip_address` columns `security.md` §7 documents (a schema-vs-doc
mismatch, not a role-taxonomy question); see Part 5 below.

Phase 3 — Driver Operations: **Backend COMPLETE, extended this pass** —
profile, document submission (`POST /api/v1/drivers/me/documents`),
vehicle CRUD/activate/deactivate, admin driver/vehicle approve/reject
review flow, all tested. **New this pass (ADR-0072, closing
docs/14-decisions/ADR-0007's explicitly-flagged gap — the same
precedent ADR-0006 already set for the equivalent vehicle-endpoint
gap)**: `GET /api/v1/drivers/me/documents` (list my driver documents),
`POST`/`GET /api/v1/drivers/me/vehicles/{id}/documents` (submit/list
vehicle documents) — the service/repository layer for both already
existed and was already tested; only the HTTP route was missing. 16 new
backend tests. VAHAN/SARATHI government API integration: BLOCKED BY
EXTERNAL CREDENTIAL/PROVIDER (no official API documentation supplied —
not invented, per explicit instruction). **Mobile — COMPLETE for
onboarding, built this pass**: `SarthiOnboardingScreen` (profile-name
creation, KYC document submission, vehicle registration, vehicle
document submission, real approval-status display, vehicle activation),
`DriverApi`/`VehicleApi` API clients (new — neither existed before this
pass), wired into `SarthiHomeScreen`. A Sarthi can now complete
onboarding end-to-end from the app. (Updated in a later same-day pass:
document submission's free-text-reference limitation noted here is now
CLOSED — `EvidenceUploadService`/`image_picker` added real Camera/
Gallery capture, see Part 2's own later item for the full account.
Strike/penalty history and the GPS-dispute/evidence flow, also
originally flagged here as remaining, are likewise now COMPLETE — see
Part 2.)

Phase 4 — Ride Matching & Lifecycle: COMPLETE — creation, matching
dispatch, accept/reject, cancellation (all variants), GPS-verified
arrival/start/completion, early drop, schedule-a-ride, book-for-
someone-else. Real-time push for offers: INTENTIONALLY DEFERRED
(polling instead — no WebSocket/push channel for this exists; a
documented, accepted architecture choice, not a gap).

Phase 5 — Pricing: COMPLETE. Fare calculation, promotion discount
composition, platform fees, minimum fare. Distance uses haversine
(interim) — Mapbox/OSM integration: BLOCKED BY EXTERNAL CREDENTIAL/
PROVIDER (no Maps credential in this environment).

Phase 6/7 — GPS Verification & Ride Lifecycle: COMPLETE — arrival/
completion radius checks, manual-review escalation, dispute-evidence
window (state-machines.md §69).

Phase 8/9 — Ride Modifications: COMPLETE for what's documented
(destination/pickup change, early drop). CreateFareRevision/pickup-
PROCEED-charge exact value: BLOCKED BY BUSINESS DECISION (business-
rules.md's own TBD placeholder, ₹10–₹20/km discussed, not approved —
unchanged by this pass, not touched, per this task's "do not invent a
business value" instruction).

Phase 10 — Payment: BLOCKED BY BUSINESS DECISION / EXTERNAL PROVIDER —
no real production payment-gateway decision exists (Razorpay stays
TEST-only per standing instruction; SBI named as the intended future
production gateway, no credential/contract yet). Ride fare stays P2P
(Customer -> Sarthi directly) per already-approved architecture — not
touched, not re-litigated.

Phase 11 — Financial/Wallet: **COMPLETE ✅ — verified this session,
not modified.** Wallet debit/credit, outstanding-debt recovery
(ADR-0062), customer-penalty settlement via driver wallet (ADR-0066),
Razorpay TEST recharge, transaction ledger, admin wallet view. Full
backend test suite (1,419 tests, see Part 4) passes with zero
regressions — confirms this phase is unaffected by this pass's changes.

Phase 12 — Growth (Promotions & Referrals): **COMPLETE ✅ — verified
this session, not modified.** 50%-off-capped-at-₹100/ride rule
(BR-063, ADR-0049) confirmed still implemented and tested exactly as
approved; promotion consume/restore ride-lifecycle integration
(ADR-0070, closed 2026-09-04, the prior task in this same session)
confirmed still composed and tested: cancellation before completion
restores the promotion, only successful completion consumes it,
double-consume/double-restore protected by a real row lock, proven by
real-concurrency tests. Referral domain untouched. Not re-implemented
or re-designed this pass, per explicit instruction — only regression-
verified (full suite green, see Part 4).

Phase 13 — Disputes: COMPLETE for what's documented (GPS-verification
dispute, penalty dispute via Dispute-as-Support, ADR-0028/0029).

Phase 14 — Safety & Support: **Backend COMPLETE, including new work
this pass** — SOS trigger/acknowledge/escalate/resolve; Support Case
create/get; **List My Support Cases (`GET /api/v1/support/cases`) —
the previously-missing endpoint, implemented this pass**, paginated,
authorized (customer/driver only, own-cases-scoped, 403 for admin),
tested (9 new backend tests). **Mobile: the list screen is now
integrated (`SupportCasesListScreen`, wired into both User and Sarthi
home screens, 5 new widget tests) — COMPLETE.** Support follow-up
messaging (`PostSupportMessage`): **BLOCKED BY BUSINESS DECISION** —
inspected ADR-0022 Decision 6 directly: no HTTP shape is documented
anywhere in api-contracts.md for this; building one means inventing a
new public API contract, the exact §0.3 stop condition this project
has consistently respected. Flagged, not built, per explicit
instruction not to invent behavior here. AI Support / emergency-
service providers: INTENTIONALLY DEFERRED (BLOCKED BY EXTERNAL
PROVIDER — no LLM credential; no emergency-service integration
contract).

Phase 15 — Notifications: COMPLETE, audited this pass with no
regressions needed. IN_APP/SMS/PUSH(FCM) all real and verified
end-to-end (a prior session's own real Google/FCM API call, real
Sentry/Slack integrations). Consumer idempotency, retry/backoff, and
DLQ for the *event pipeline* (Phase 18, below) already cover the
Kafka-consumption side. Audited `NotificationService.send()`,
`broadcast_dispatch.py`, `push.py` directly this pass: error handling
is solid (every provider exception caught, marked FAILED, never
crashes a batch or the consumer); idempotency is solid (DB dedup
constraint + Phase 18's processed_events). The one gap this audit found
— a FAILED SMS/PUSH send had no retry mechanism at all — is now CLOSED
(ADR-0075, same-day follow-up): a Celery Beat task, every 5 minutes,
gives every FAILED SMS/PUSH delivery exactly one bounded retry
(`notification.deliveries.retry_count`, new column; `retry_count = 0`
is the query's own exclusivity condition, so no row is ever retried
twice regardless of how often the task runs). WhatsApp: INTENTIONALLY
DEFERRED (BLOCKED BY EXTERNAL PROVIDER — no BSP/API docs supplied, per
explicit instruction not to build this).

Phase 16 — Admin: COMPLETE. Corrected 2026-09-07 — this line
previously claimed "~15 already-built capabilities" with "a live
driver-location map" and "Promotion/Referral admin authoring UI beyond
what's built" as AUTONOMOUS ENGINEERING REMAINING; that was stale,
inherited from a 2026-08-25 intermediate count without checking
`docs/15-admin-web/admin-web-implementation-plan.md`'s own later
closing declaration. That plan's own record (verified directly, not
assumed): all 20 original sidebar modules plus every NEW — SCOPED
sub-item (Driver Strike History, CSV Bulk Customer Targeting, GPS
Dispute frontend, Compose/Send Broadcast) were built by 2026-08-29,
ending in that document's own words, "No item from this plan's
original scope remains outstanding." Promotion/Referral admin
authoring is real and already built (`/offers-coupons`,
`/referrals/rewards/*`) — not a gap. The live driver-location map is
real but not an engineering gap either: that plan's §4.6 explicitly
frames it as **excluded by the owner's own decision, left for a
separate future ADR** (ADR-0054 §5) — BLOCKED BY BUSINESS DECISION
(a scoping call only the owner can make), not AUTONOMOUS ENGINEERING
REMAINING, and it would need a Maps/location-rendering provider
regardless (the same external-credential blocker Phase 5's own fare-
distance calculation already carries). Nothing in Phase 16 is
currently buildable without one of those two.

Phase 17 — Advertisements/Admoto: **ON HOLD — FUTURE SCOPE — NOT AN
INITIAL LAUNCH BLOCKER, per explicit instruction. Not implemented
this pass, and not touched.** Domain/service/repository layer was
already built in a prior session (ADR-0018); no HTTP endpoint exists
(inventing one means inventing a new API contract) and no Admoto
integration exists (no credential/contract) — both correctly left
alone.

Phase 18 — Event & Background Reliability: **COMPLETE ✅ — verified
this session, not modified.** Retry/backoff (exponential, configurable,
capped), Kafka DLQ (`vistaar.dlq.<domain>`, preserves original event +
metadata), and consumer idempotency (`shared.processed_events`) —
ADR-0071, closed 2026-09-04, the task immediately preceding this one in
the same session. Full backend suite green this pass confirms no
regression. One pre-existing, explicitly-scoped-out gap, unchanged:
`NotificationConsumer`'s own message-handling failures (as opposed to
the outbox publisher's) have no persistent per-message retry/DLQ of
their own — documented in that ADR's §5 and event-contracts.md §32 as
a deliberate scope boundary, not silently missing.

Phase 19 — Security: COMPLETE for HTTPS/TLS (infra-level, Ingress/ALB),
JWT security, rate limiting (ADR-0061), input validation, file-upload
security (ADR-0065, presigned POST). RBAC enforcement: see Phase 2 (
Admin RBAC specifically is the open piece, same business-decision
block).

Phase 20 — Testing: Unit/integration/E2E test suites COMPLETE (1,419
backend tests, 148 mobile tests, both green this pass — Part 4).
**Load-testing preparation — built this pass**: k6 scripts for all
five documented scenarios (driver polling, ride-status polling, full
ride lifecycle, wallet recharge, admin reporting), a safe test-account
provisioning/cleanup script pair (verified end-to-end against the real
local backend this pass, two real bugs found and fixed during that
verification), staged-ramp configuration (smoke/baseline/design/
target/soak), and a results-analysis script — all in
`infrastructure/load-testing/`, see that directory's own README for
exactly what has and hasn't been verified. **Execution against a real
target is BLOCKED BY EXTERNAL CREDENTIAL/PROVIDER** (no staging AWS
environment reachable from this environment) **and BLOCKED BY BUSINESS
DECISION** (the 20/30/50 user-mix traffic split is still an unconfirmed
working assumption, load-testing-plan-2026-09-03.md §1). k6 itself is
not installed in this development environment — scripts are syntax-
checked and endpoint-verified against real router source, not
executed.

Phase 21 — Deployment Preparation: Terraform (AWS EKS/RDS/ElastiCache/
Kafka/ECR/S3-state-backend, plus a separate admin-web stack),
Kubernetes manifests (backend deployment/HPA/Ingress/ConfigMap/Secret
templates, Celery worker, migration Jobs, Prometheus/Grafana/
Alertmanager monitoring stack), and GitHub Actions workflows (CI +
AWS/DigitalOcean deploy) all already exist from prior sessions.
**Validated this pass**: all 17 Kubernetes manifests + 3 GitHub Actions
workflow files parse as syntactically valid YAML (verified directly,
not assumed). Terraform HCL syntax validation (`terraform validate`)
was NOT run — the `terraform` CLI is not installed in this
environment; flagged rather than silently skipped. **Actual deployment
execution is BLOCKED BY EXTERNAL CREDENTIAL/PROVIDER** — no AWS
credentials exist in this environment; nothing has been deployed to a
real AWS account, and this document makes no claim that it has.

═══════════════════════════════════════════════════════════════════
PART 2 — WHAT WAS DONE THIS PASS (2026-09-04)
═══════════════════════════════════════════════════════════════════

1. Phase 14 backend: `GET /api/v1/support/cases` (List My Support
   Cases) — new port/repository/service method + router endpoint,
   paginated, own-cases-scoped, status-filterable, admin correctly
   rejected. 9 new backend tests, all passing.
2. Phase 14 mobile: `SupportCasesListScreen` — loading/error/empty
   states, pagination ("Load more"), tap-through to case detail (fresh
   GET, not the stale list-row data), wired into both User and Sarthi
   home screens. `SupportApi.listCases()` added. 5 new widget tests.
3. Phase 15 audit: read `NotificationService.send()`,
   `broadcast_dispatch.py`, `push.py` directly. Confirmed solid error
   handling and idempotency; found and documented (not fixed) one
   genuine gap — no retry for a FAILED send.
4. Mobile — Android background/foreground-service location (HIGH
   PRIORITY, explicit instruction): replaced the previous foreground-
   only `Timer.periodic` + `getCurrentPosition()` polling in
   `SarthiHomeScreen` with `Geolocator.getPositionStream()` using
   `AndroidSettings.foregroundNotificationConfig` — a real Android
   foreground service with a persistent notification, using the
   *already-approved* `geolocator` dependency (no new package added).
   `AndroidManifest.xml` updated with the required
   `FOREGROUND_SERVICE`/`FOREGROUND_SERVICE_LOCATION` permissions. One
   documented, non-silent limitation: this raises process priority and
   keeps location active while backgrounded/screen-locked, but does not
   guarantee survival under full Activity destruction — a dedicated
   background-isolate service package would close that specific
   remaining gap, noted as a possible future hardening step. 8 existing
   tests updated (stream-based fake) and re-passing.
5. Phase 20 — load-testing preparation (see Phase 20 above for detail):
   k6 scenario scripts, account provisioning/cleanup scripts (verified
   end-to-end, 2 real bugs found and fixed), staged-ramp config,
   results-analysis tooling, README.
6. Phase 21 — deployment prep validation: all Kubernetes manifests and
   GitHub Actions workflows confirmed syntactically valid YAML.
7. Phase 3 — Sarthi onboarding (backend + mobile): closed a real,
   explicitly-flagged backend gap (ADR-0072 — driver document
   retrieval + vehicle document endpoints, matching ADR-0006's own
   precedent for the equivalent earlier gap), then built
   `SarthiOnboardingScreen` end-to-end (profile creation, KYC document
   submission, vehicle registration, vehicle document submission,
   real approval-status display, vehicle activation) plus the
   `DriverApi`/`VehicleApi` clients neither of which existed before.
   16 new backend tests, 6 new mobile tests. A Sarthi can now complete
   onboarding from the app — previously impossible regardless of
   backend readiness.
8. Mobile — User (customer) screens: Profile, Ride History,
   Promotions, and Referrals, built 2026-09-04 as a same-day follow-up
   to item 7 — the next highest-priority gap by the same logic
   (highest-value, still-missing, no external blocker). All four
   backend endpoints (`GET`/`PATCH /api/v1/customers/me`,
   `GET /api/v1/rides` with no status filter, `GET`/`POST
   /api/v1/customers/me/promotions[/redeem]`,
   `GET /api/v1/customers/me/referral` + `POST
   /api/v1/referrals/attach`) already existed with zero mobile callers
   — this was pure mobile-side work, no backend changes. New
   `CustomerApi`/`PromotionApi`/`ReferralApi` clients (ride history
   reuses the existing `RideApi.listMyRides()`), four new screens
   (`ProfileScreen`, `RideHistoryScreen`, `PromotionsScreen`,
   `ReferralScreen`), wired into `UserHomeScreen`'s app bar and
   `main.dart`'s providers. 15 new mobile tests. Not in scope for this
   item, still remaining per Part 3 below: GPS-dispute/evidence
   submission. (Correction, made in a later same-day pass: this item's
   original text also claimed "wiring a redeemed promotion's discount
   into Book a Ride" as a remaining gap — that was wrong, based on a
   stale docstring in `modules/promotion/router.py` rather than the
   actual `ride/router.py` code. ADR-0070, closed earlier the same day,
   already auto-reserves a customer's soonest-expiring entitlement at
   `POST /api/v1/rides` with no client action needed — a redeemed
   promotion already applies to the next ride booked, in both the
   backend and this app, with nothing further to build. The stale
   docstring and this doc's own repetition of it have both been fixed.)
9. Mobile — Sarthi Strike History, built 2026-09-04 as a same-day
   follow-up to item 8, same priority logic. Unlike item 8, this closed
   a real *backend* gap first (ADR-0073, same precedent ADR-0072 set):
   `PenaltyService.list_strikes_for_driver()` and the admin-only
   `GET /api/v1/admin/drivers/{id}/strikes` (§46.18) already existed,
   but nothing let a driver read their own strikes — only the bare
   `strikes` counter was ever exposed to them. Added
   `GET /api/v1/drivers/me/strikes` (`modules/driver/router.py`,
   scoped to the caller, same item shape as the admin route), 6 new
   backend tests, then `StrikeHistoryScreen` + `DriverApi.listStrikes()`
   on the mobile side, wired into `SarthiHomeScreen`'s app bar. 4 new
   mobile tests. Does not add a dispute/appeal capability — none exists
   at any layer of this codebase, and none is invented here (see that
   ADR's own scope note).
10. Mobile — GPS Dispute/Evidence flow, built 2026-09-04 (ADR-0074),
    closing the last remaining shared User/Sarthi mobile gap. Backend
    gap found and closed: a dispute reaches the driver directly (their
    own failed Mark Arrived/Complete Ride call opens it), but nothing
    ever told the *customer* one existed on their ride —
    `GpsDisputeRepository` had no query to find a dispute by `ride_id`
    at all. Added `list_for_ride()` (repository + Protocol),
    `RideService.list_gps_disputes_for_ride()`, and
    `GET /{ride_id}/gps-disputes` (discovery only — the existing
    Get Dispute/Submit Evidence/upload-url endpoints, already COMPLETE,
    are unchanged), 8 new backend tests (4 HTTP + 4 unit). Mobile: new
    shared `GpsDisputeScreen` (status, evidence trail, submission form)
    reachable two ways — the driver is pushed to it directly when
    `RideExecutionScreen` catches a `GPS_VERIFICATION_FAILED` error's
    `dispute_id` (`ApiException` extended to carry the error envelope's
    `details` field for this), the customer sees a banner on
    `RideStatusScreen` once its new dispute-discovery poll finds an
    open one. `uri`-typed evidence uses the same free-text "evidence
    reference" convention `SarthiOnboardingScreen` already established
    — not a real file picker (none exists anywhere in this app); TEXT
    evidence needs no such reference and is fully real. 10 new mobile
    tests.
11. Mobile — real camera/gallery evidence capture, built 2026-09-04
    (`image_picker` dependency added), closing the free-text-reference
    limitation flagged in items 7 and 10. New `EvidenceUploadService`
    (`core/uploads/`) — the same "constructor-injected native call,
    real by default" pattern `ContactsApi` already established — picks
    a photo/video, requests a presigned target
    (`DriverApi.requestUploadUrl` — new; `RideApi.
    requestGpsDisputeEvidenceUploadUrl` — already existed), and POSTs it
    as real multipart form data (verified the `http` package's own
    `MultipartRequest` always encodes fields before files regardless of
    call order, satisfying S3's "file last" requirement without manual
    byte-level construction). Wired into `SarthiOnboardingScreen`'s
    document sections (driver + vehicle documents, both already using
    the one shared upload endpoint) and `GpsDisputeScreen`'s PHOTO/
    VIDEO evidence (DOCUMENT stays a plain text field — no separate
    raw-file picker exists; a real photo already covers the common
    case). No `AndroidManifest.xml` permission was needed
    (`image_picker_android`'s own AAR declares none — it delegates to
    the system camera/gallery app via intent); iOS `Info.plist` gained
    `NSCameraUsageDescription`/`NSPhotoLibraryUsageDescription` anyway,
    ahead of any iOS resume, so a future build doesn't inherit a
    missing-key crash. 8 new mobile tests (6 service-level in
    `evidence_upload_service_test.dart` + 1 each in
    `sarthi_onboarding_screen_test.dart`/`gps_dispute_screen_test.dart`
    — both needed a widget-test-safe seam around the real disk I/O
    `http.MultipartFile.fromPath` does; see `EvidenceUploadService`'s
    own doc comment on `_readFile`).
12. Backend — Notification FAILED-send retry, built 2026-09-04
    (ADR-0075), closing the one gap this same day's Phase 15 audit
    found and explicitly left unfixed: `NotificationService.send()`'s
    `mark_failed()` was terminal — a transient SMS/FCM outage meant
    that delivery never got a second chance. New
    `notification.deliveries.retry_count` column (migration
    `b7353a942bf3`, real upgrade/downgrade round-trip verified);
    `DeliveryRepository.get_by_id_for_update()` (the Protocol had no
    single-row lookup before this); `NotificationService.
    retry_delivery()` — one bounded attempt, `retry_count` stamped to 1
    regardless of outcome so the same row is never retried twice; new
    Celery Beat task `notification.retry_failed_notifications` (every 5
    minutes, same cadence `send-scheduled-broadcasts`/
    `promote-due-scheduled-rides` already use), scanning
    `status='FAILED' AND retry_count=0` directly (raw SQL, matching
    this file's own existing style) and re-looking-up the *current*
    phone number for SMS (deliberately never persisted at original send
    time). Also exposed `retry_count` on the existing admin Notification
    History endpoint (`GET /api/v1/admin/notifications/deliveries`) —
    it existed in the database from this same change but wasn't
    actually serialized in the response until this fix, so it's now
    genuinely the "admin can observe this working" mechanism the ADR
    itself claims. 10 new backend tests (7 service-level unit + 3 real-
    Postgres integration). Does not add backoff, a configurable retry
    limit, or a dead-letter concept — a single bounded retry was this
    gap's own stated scope; does not add an admin-facing "retry now"
    button.
13. Mobile — Token Refresh, built 2026-09-07 (ADR-0076), after Phase 16
    turned out to have nothing further buildable (corrected item 12's
    own note above — admin-web's original scope was already fully
    closed as of 2026-08-29, a stale intermediate count had been cited
    instead). Closes this app's own long-documented gap (`AuthSession`/
    `ApiClient`'s doc comments and the app's README all explicitly said
    "no token-refresh logic exists"): the backend's `POST /api/v1/auth/
    refresh` was always real and fully tested, just never called.
    `AuthApi.refresh()` (new); `ApiClient.onAuthInvalid` — every one of
    `get`/`post`/`patch`/`delete` now transparently refreshes and
    retries once on an expired-access-token (`AUTH_INVALID`) failure;
    `AuthSession` wires itself onto it at construction, single-flight
    (concurrent callers share one real refresh, since refresh tokens
    are rotated single-use server-side — a real correctness detail, not
    an edge case skipped), and `restore()` now attempts a refresh
    before forcing re-login on a cold start whose access token has
    expired (a refresh token typically far outlives it). Pure mobile-
    side work, no backend changes — the backend was already correct.
    9 new mobile tests (7 in a new `api_client_test.dart` covering the
    retry/no-retry cases directly; in `widget_test.dart`, replaced one
    now-inaccurate "expired session is cleared" `AuthSession` test with
    two — refresh-fails-so-clears and refresh-succeeds-so-restores —
    plus one new single-flight concurrency test; every other existing
    `AuthSession`/provider-tree test updated only for the constructor's
    two new required parameters, no behavior change).
14. Mobile — Dark theme, built 2026-09-07, closing the one real gap a
    concrete accessibility check (same day, see the corrected "Shared
    mobile UX" note above) found: `AppTheme` only ever defined `light`,
    and `main.dart`'s `MaterialApp` had no `darkTheme` at all, so a
    device set to system dark mode was silently forced into the light
    theme regardless. Verified first, not assumed, that this was safe
    to fix with no other changes: every screen in this app already
    reads its colors from `Theme.of(context).colorScheme` rather than
    a hardcoded literal (grepped the whole `lib/` tree for
    `Colors.white`/`Colors.black`/explicit `backgroundColor:`/
    `Color(0x...)` — none found outside the theme file itself and one
    themed dialog; a handful of low-opacity semantic status tints —
    green/orange/blue for online/warning/decorative — read fine
    unchanged against either scheme). New `AppTheme.dark`
    (`ColorScheme.fromSeed(..., brightness: Brightness.dark)`, same
    seed color as `light`); `MaterialApp` now sets `darkTheme` +
    `themeMode: ThemeMode.system`. 3 new tests (`app_theme_test.dart`).
15. Mobile — Map rendering, built 2026-09-07 (owner-requested: "Build
    the MapTiler map-rendering functionality now using the existing
    MAPTILER_API_KEY... do NOT assume MapTiler should replace the
    backend's current Haversine distance calculation... Do not change
    fare calculation or backend distance logic in this task"). Closes
    the gap the owner's own question that same day surfaced: a real
    MapTiler Cloud key had been provided and stored on 2026-08-29 —
    before this whole session even started — but nothing had ever been
    built to use it. Verified first, not assumed: confirmed the key was
    genuinely present and non-empty in `apps/mobile/dart_define.json`
    without ever printing it, and confirmed the backend's haversine-
    interim fare distance calculation was scoped against a *different*
    provider (Mapbox, per `api-contracts.md`) — this task touched zero
    backend files, verified via a file-mtime check after the fact, not
    just intent.

    Package: `flutter_map` + `latlong2` (not Google Maps or the Mapbox
    SDK — neither matches the credential actually provided), consuming
    MapTiler's `streets-v2` raster XYZ tiles. New
    `lib/shared/map/maptiler_tile_layer.dart` is the *only* file that
    ever reads the real key — every map screen goes through it instead,
    plus MapTiler's own required attribution overlay. New
    `LocationPickerScreen` (tap-to-place-pin, defaults to the device's
    own current position via `Geolocator`, falls back to a fixed
    central-India view if that fails) — wired into `BookRideScreen`
    (pickup + destination) and both Change Pickup/Change Destination
    dialogs as a **Pick on Map** button that fills the same manual
    lat/lng fields those screens already had, so validation/submission
    needed no changes at all. New `RouteMapPreview` (static pickup +
    optional destination pins, auto-fit bounds) — wired into
    `RideStatusScreen`, `RideExecutionScreen`, and `RideOfferScreen`
    (offers only ever carry `pickup`, api-contracts.md §16.1's own
    documented shape, not a client omission — handled as a genuine
    single-point case, not padded with an invented destination).

    Explicitly **not** built, flagged rather than silently implied:
    live driver-location tracking on any of those three ride screens —
    there is still no `/tracking` endpoint anywhere in the backend
    (unaffected by this task); these show where a ride starts/ends, not
    where the driver currently is. Turn-by-turn navigation is likewise
    out of scope — MapTiler renders map imagery here, it doesn't
    compute a route, and none was requested.

    Every map-touching screen degrades to a plain `MapUnavailableNotice`
    (or, for the pick-on-map buttons, simply doesn't show them) when no
    maps key is configured for a build — proven by the test suite
    itself, which runs with no `--dart-define` and so never sees a
    real key. 9 new mobile tests (3 for `RouteMapPreview`'s fallback
    behavior, 4 for `LocationPickerScreen`'s own interaction logic —
    genuinely testable independent of real tile loading — plus 2 more
    proving the map-or-fallback wiring inside `BookRideScreen`/
    `RideStatusScreen`, with two more existing tests in
    `RideExecutionScreen`/`RideOfferScreen` extended with the same
    assertion rather than duplicated as new tests).
16. This document.

═══════════════════════════════════════════════════════════════════
PART 3 — AUTONOMOUS ENGINEERING REMAINING (buildable, not done here)
═══════════════════════════════════════════════════════════════════

Given the true scope of this request (effectively "complete every
buildable gap across the whole product"), the mobile app in
particular has substantial real work remaining beyond what a single
pass could responsibly complete without producing shallow, undertested
code. Listed precisely rather than glossed over:

**Mobile — User (customer) screens**: profile, ride history, promotions
view, referrals view, and GPS-dispute/evidence (banner on
`RideStatusScreen` -> shared `GpsDisputeScreen`, Part 2 item 10) are
now COMPLETE. Nothing remaining here — a redeemed promotion's discount
already applies to the customer's next booked ride automatically
(ADR-0070, `POST /api/v1/rides` server-side), no app-side wiring
needed; a stale claim to the contrary earlier in this document has been
corrected (see item 8's own note).

**Mobile — Sarthi (driver) screens**: KYC/document submission, vehicle
registration, vehicle document submission (`SarthiOnboardingScreen`,
Part 2 item 7), strike history (`StrikeHistoryScreen`, Part 2 item 9 —
required a new backend endpoint too, ADR-0073), and GPS-dispute/
evidence (pushed to directly from a terminal Mark Arrived/Complete
Ride failure, Part 2 item 10) are now COMPLETE. Nothing remaining
here — the real camera/gallery picker this section previously listed
as still missing is now built (`EvidenceUploadService`, Part 2 item
11) and wired into both document submission and GPS-dispute evidence.

**Shared mobile UX**: token refresh is now CLOSED (ADR-0076, see Part
2's own later item — the README's "no token-refresh logic exists" line
this section used to cite is gone). Audited 2026-09-07: cancellation
dialogs need no consistency fix — only two entry points exist
(`ride_execution_screen.dart`, `ride_status_screen.dart`) and both
already call the same shared `showCancelReasonDialog`. A concrete
accessibility check (not just "not performed," an actual pass) found a
solid baseline already — every `IconButton` in the app has a
`tooltip`, no custom `GestureDetector` bypasses Flutter's built-in
widget semantics, no `textScaleFactor` override blocks the system font-
size setting, status is always shown as text not color-only, and the
Material 3 seeded color scheme generates WCAG-safe contrast pairs by
construction. The one real gap that check found — no dark theme — is
now CLOSED too, same day (see Part 2's own later item). Consistent
empty/error/loading states
retrofitted onto every screen built later in this session, not
independently re-audited across the handful of screens that predate it.

**Phase 15**: nothing remaining — FAILED-notification retry (the one
gap this phase's own audit found) is now CLOSED, ADR-0075, see Part 2's
own later item.

**Phase 16**: nothing remaining — see Phase 16's own corrected entry
above (2026-09-07). The one item ever really outstanding, the live
driver-location map, is BLOCKED BY BUSINESS DECISION (a future ADR
only the owner can scope), not autonomous engineering.

**Phase 2**: `admin.audit_logs` is still missing the `actor_role`/
`ip_address` columns `security.md` §7 documents (ADR-0009 Conflict 2,
still open) — a schema-vs-doc mismatch, genuinely buildable (add the
columns, populate them at write time from the already-authenticated
admin's own role and the request's own IP), not a business decision.

═══════════════════════════════════════════════════════════════════
PART 4 — VERIFICATION (this pass)
═══════════════════════════════════════════════════════════════════

Full details and exact commands are in this session's own record; the
headline results:

- **Backend**: 1,459 tests passed (1,410 before this pass + 9 new
  support-list tests + 16 new driver/vehicle-document tests + 6 new
  strike-history tests + 8 new GPS-dispute-discovery tests: 4 HTTP + 4
  unit + 10 new notification-retry tests: 7 unit + 3 real-Postgres
  integration), 0 failed, 0 skipped (real Postgres + real Kafka, the
  latter started via `infrastructure/docker/docker-compose.dev.yml` for
  this pass). `ruff check` and `mypy` clean on every touched file
  (`mypy` run across the full `src/` tree: 217 files, 0 errors). A real
  migration upgrade/downgrade round-trip verified for
  `b7353a942bf3` (`notification.deliveries.retry_count`).
- **Mobile**: `flutter test` — all 210 tests (154 from the previous
  pass + 15 from Profile/Ride History/Promotions/Referrals: 3 + 5 + 4 +
  3, + 4 from Strike History, + 8 from GPS Dispute/Evidence: 6 in the
  new screen's own test file + 1 in `ride_status_screen_test.dart` + 1
  in `ride_execution_screen_test.dart`, + 8 from real camera/gallery
  capture: 6 in `evidence_upload_service_test.dart` + 1 each in
  `sarthi_onboarding_screen_test.dart`/`gps_dispute_screen_test.dart`,
  + 9 from Token Refresh: 7 in a new `api_client_test.dart` + 2 net new
  in `widget_test.dart`, + 3 from Dark Theme in a new
  `app_theme_test.dart`, + 9 from Map Rendering: 3 in
  `route_map_preview_test.dart` + 4 in
  `location_picker_screen_test.dart` + 2 new in `book_ride_screen_test.
  dart`/`ride_status_screen_test.dart`) passed. `flutter analyze` — 0
  issues. Zero backend files touched this task — verified by file-mtime
  check, not just intent, per the owner's own explicit instruction not
  to change fare/distance logic.
- **Sarthi onboarding end-to-end, verified against the real local
  backend** (not just unit tests): 5 concurrent synthetic Sarthi
  accounts provisioned via the same document-submission/vehicle-
  registration/activation sequence the new mobile screen itself calls,
  all 5 successfully reached `ONLINE` — direct proof the new backend
  endpoints (ADR-0072) and the mobile screen calling them are wired
  correctly end to end, not just individually. Found and fixed a real
  concurrency bug in the verification tooling itself during this check
  (see `infrastructure/load-testing/README.md`).
- **Migrations**: no new migrations in this pass (Phase 14/15/Android/
  Phase 3 work is all application-code-only — the new document/vehicle
  endpoints compose existing tables). Phase 18's own two migrations
  (`c2e6a9f4d7b1`, `d8f1c3a6e9b2`) remain verified from the immediately
  preceding task in this session (upgrade/downgrade round-trip,
  including with real data present).
- **Regression check on Phase 11/12/18** (explicitly required not to
  be modified): the full 1,435-test backend suite, which includes every
  wallet, promotion, and event-reliability test, passed with zero
  failures — direct evidence none of the three were altered or broken.

═══════════════════════════════════════════════════════════════════
PART 5 — WHAT THE OWNER NEEDS TO PROVIDE OR DECIDE
═══════════════════════════════════════════════════════════════════

**External credentials/providers** (nothing invented, per standing
instruction):
- AWS account access (Phase 20 execution, Phase 21 actual deployment).
- Maps/geocoding credential (Mapbox/OSM, Phase 5 — haversine stays
  interim without it).
- Real payment gateway (SBI or otherwise) for Phase 10 — Razorpay
  stays TEST-only.
- VAHAN/SARATHI government API documentation (Phase 3) — not invented.
- WhatsApp BSP + API docs (Phase 15) — not built without them.
- LLM provider credential (AI Support, Phase 14) — not built without
  one.
- Admoto credential/contract (Phase 17) — correctly on hold regardless.

**Business decisions**:
- Pickup-PROCEED additional-charge exact value (Phase 8/9) —
  business-rules.md's own TBD.
- Support follow-up messaging (`PostSupportMessage`) HTTP contract
  (Phase 14) — genuinely no documented shape; needs either an approved
  contract or an explicit decision to add one.
- Load-test traffic-mix split confirmation (20/30/50 or a correction,
  Phase 20).
- Live driver-location map for Admin Web (Phase 16) — explicitly
  excluded from ADR-0054's own scope, left for a separate future ADR;
  needs an owner scoping call before any engineering starts. (Note,
  2026-09-07: a maps-rendering credential — MapTiler Cloud — now
  exists and is proven working on the mobile side, so a rendering
  credential is no longer this item's blocker; the owner's own scoping
  decision is.)

═══════════════════════════════════════════════════════════════════
PART 6 — INTENTIONALLY DEFERRED (owner instruction, not a gap)
═══════════════════════════════════════════════════════════════════

- Phase 17 (Advertisements/Admoto) — explicit "ON HOLD — FUTURE SCOPE
  — NOT AN INITIAL LAUNCH BLOCKER" this pass.
- WhatsApp notification channel — explicit "do not implement... until
  a BSP/provider and API documentation are supplied."
- AI Support / emergency-service providers — explicit "do not
  implement... without an approved external contract."
- iOS — explicit "remains postponed and must not block Android";
  unaffected by this pass's Android-specific location work.
- Real-time push for ride offers/location (WebSocket) — an earlier,
  still-standing architectural choice (polling instead), not reopened
  here.

═══════════════════════════════════════════════════════════════════
PART 7 — PROJECT PAUSED HERE (2026-09-09)
═══════════════════════════════════════════════════════════════════

**The owner is putting VISTAAR on hold for several months.** This
section is the resume point: what changed since the 2026-09-04 status
above, what's genuinely unresolved, and exactly how to get everything
running again. Read this section first on resume, then the rest of
this document for feature-level status.

### What happened between 2026-09-04 and this pause (admin-web focus)

- **Mobile UI/UX redesign** (Forest Green → later corrected to exact
  admin-web brand parity, `#003314`/`#EFBF04`) — Rapido-benchmarked
  information hierarchy, map-first booking/driver screens, boxed OTP
  input, a real `VistaarLogoMark`/`VistaarWordmark`, and a regenerated
  Android/iOS launcher icon from that same mark. 267 mobile tests
  passing, `flutter analyze` clean.
- **Sentry error tracking wired for all three apps** — three separate
  Sentry projects (org `vistaar-3j`): backend (`.env`'s `SENTRY_DSN`,
  now actually loaded via `python-dotenv`, added this pass —
  `core/config.py` never sourced `.env` before), mobile
  (`dart_define.json`'s `SENTRY_DSN`), admin-web
  (`.env.local`'s `NEXT_PUBLIC_SENTRY_DSN`, wired via Next.js 16's
  current `instrumentation-client.ts`/`instrumentation.ts` convention,
  not the older wizard-generated pattern). All three redact
  OTP/bearer-token-shaped substrings before sending. Backend tests
  force `SENTRY_DSN=""` (`tests/conftest.py`) so `pytest` never spams
  the real Sentry project.
- **Admin Web login screen built** — phone + OTP + conditional MFA
  step (`src/components/auth/LoginPage.tsx`), the same identity
  endpoints every account type uses (`account_type: "ADMIN"`). Closes
  the gap where no self-service way existed to get a real
  `vistaar_admin_token` other than pasting one in by hand. Sign
  in/out wired into `TopBar`. `scripts/provision_admin.py` remains the
  only way to create the *first* Super Admin (no self-registration, by
  design — BR-127).
- **Auto-refresh on expired access token** (`lib/api/client.ts`) —
  mirrors the mobile app's own proven ADR-0076 design exactly
  (single-flight refresh shared across concurrent 401s, retried once).
  Previously every admin session dead-ended in a full re-login every
  `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (30 by default).
- **Backend error responses unified** — `modules/identity/dependencies.py`'s
  auth-layer 401/403s (`AUTH_REQUIRED`/`AUTH_INVALID`/`ACCOUNT_SUSPENDED`/
  `FORBIDDEN`/`RATE_LIMITED`) used to bypass this app's own
  `{data, error, request_id}` envelope entirely (a raw FastAPI
  `HTTPException`) — found while diagnosing a confusing "UNKNOWN_ERROR"
  admin-web report. Fixed with one central exception handler in
  `main.py` (`_enveloped_http_exception_handler`); health-check
  endpoints' own free-form messages are untouched.
- **Admin dashboard's hardcoded sample-data fallback removed** —
  `mock-data.ts`/`SampleDataBanner.tsx` deleted outright.
  `getDashboardSummary`/`getAdminProfile`/`getRecentAuditLog` now
  propagate real errors instead of substituting fake numbers on any
  failure (no session, network error, backend rejection). Since
  `getAdminProfile` is shared by every admin-web page, this fixed the
  same latent fallback everywhere, not just the Dashboard. Driver/
  Vehicle list rows now show a distinct "Review →" affordance for
  PENDING records instead of a plain "View" link, so the existing
  Approve/Reject workflow (already fully built on the detail pages) is
  actually discoverable from the list.
- **Development-database cleanup, approved and executed in stages** —
  traced ~1,800 `identity.accounts` rows (and their full FK-dependent
  graph — sessions, driver/vehicle/customer profiles, documents,
  verification cases, admin users/audit-logs) to a real, historical,
  already-self-documented bug (`tests/_integration_db.py`'s own
  docstring): every DB-backed test ran against the *development*
  database before `tests/conftest.py`'s isolation fix existed, in two
  bursts on 2026-08-21/22. Backed up (`pg_dump`, validated with
  `pg_restore --list`) before deleting; deleted 6,934 rows across 13
  tables inside one transaction with a pre-commit count re-check
  against the approved report; verified after. The backup file itself
  is gitignored, not committed — see "Restoring the dev database" below
  if it's still needed after the pause.
- **`apps/driver-mobile`/`apps/customer-mobile` removed for real** —
  these were the pre-ADR-0027 separate mobile apps, abandoned on disk
  once `apps/mobile` (the unified app) replaced them, but that removal
  had never actually been committed until this pause-cleanup commit.
  `apps/mobile` is the only mobile app going forward.
- **`.env.example`'s `DATABASE_URL` corrected** (`5432` → `5433`) — it
  had been silently wrong since long before this session; harmless
  while nothing loaded `.env` locally, but a real trap for whoever
  copies this template to bootstrap a fresh `.env` now that the
  backend does load it (see next item).
- **`.env` is now actually loaded on local backend startup** —
  `core/config.py` gained a `load_dotenv()` call (`python-dotenv`).
  Every setting already had a safe default before this, so nothing
  needed `.env` loaded locally until a real `SENTRY_DSN` did. `uv.lock`
  needs regenerating (`uv lock`, not run this session — `uv` isn't
  installed here) before the production Docker build, which is
  otherwise unaffected (it already injects real env vars directly).

### Known, NOT resolved — read this before assuming the app "should just work"

**Backend process stability on this development machine was never
root-caused, only worked around repeatedly.** Across this pause's own
session, the backend (`uvicorn --reload`) went from healthy to
completely unreachable — no listening socket, no process at all —
multiple times, including once in the middle of being directly
diagnosed. Two real, confirmed *contributing* factors, neither proven
to be the *whole* explanation:
1. **`uvicorn` with no `--host` flag defaults to `127.0.0.1`
   (localhost) only** — confirmed directly (`Get-NetTCPConnection`
   showed only `127.0.0.1:8000`, and the backend's own LAN address was
   unreachable even from the same machine). This alone fully explains
   "the mobile app on a physical device can never reach the backend"
   regardless of any IP configured client-side. **Start it with
   `uvicorn src.main:app --reload --host 0.0.0.0` if a phone or any
   other device needs to reach it** — this was identified but not yet
   confirmed as a full fix by the owner at pause time.
2. **The laptop's LAN IP drifts** (confirmed twice this session alone:
   `192.168.100.217` → `192.168.1.5` → `192.168.101.223`) — every
   Wi-Fi reconnect/DHCP renewal is a candidate to break
   `apps/mobile/dart_define.json`'s `API_BASE_URL` again. Check
   `ipconfig`/`Get-NetIPAddress` against that file's current value
   before assuming anything else is wrong.
3. **Not ruled out**: Windows Firewall blocking inbound connections
   to port 8000 from other LAN devices even once bound to `0.0.0.0` —
   flagged as the next thing to check if `--host 0.0.0.0` alone
   doesn't fix device connectivity, never actually checked this
   session.

None of this is a code or database problem — every backend endpoint
answered correctly, with real data, every time it was actually
reachable and given a valid token. It is purely "is the process up,
and is it listening on the right interface."

### Resuming: exact commands

```powershell
# 1. Infra (Postgres, Redis, Kafka) — from the repo root
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d

# 2. Backend — apps/backend, venv active
#    --host 0.0.0.0 if a phone/other device needs to reach it (see above)
uvicorn src.main:app --reload --host 0.0.0.0

# 3. Admin Web — apps/admin-web
npm run dev
# then http://localhost:3000/login — provision the first Super Admin
# first if none exists yet:
#   cd apps/backend && python scripts/provision_admin.py --phone +91XXXXXXXXXX --role super_admin

# 4. Mobile — apps/mobile
#    Check dart_define.json's API_BASE_URL against `ipconfig`/
#    Get-NetIPAddress FIRST — it has drifted before and will again.
flutter run --dart-define-from-file=dart_define.json
```

**Before any of this works, these local-only files need real values
again** (all gitignored, none committed, none restored by `git pull`):
`.env` (repo root — `DATABASE_URL`, `SENTRY_DSN`, `JWT_SECRET`, SMS/
storage credentials, etc.), `apps/mobile/dart_define.json`
(`API_BASE_URL`, `MAPTILER_API_KEY`, `SENTRY_DSN`), `apps/admin-web/
.env.local` (`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SENTRY_DSN`). Each
has a checked-in `.example`/`.local.example` sibling documenting every
key — copy and fill in real values, don't guess the shape.

### Restoring the dev database, if still needed

The pre-cleanup backup (`apps/backend/db_backups/vistaar_db_pre_cleanup_
20260908T083907Z.dump`, gitignored, still on disk as of the pause) has
every row from before the 6,934-row cleanup, including the confirmed
test-pollution this pass removed. Only restore it if there's a real
reason to want that pollution back (there almost never is) —
otherwise the cleaned database this pause leaves behind is the correct
starting point.
