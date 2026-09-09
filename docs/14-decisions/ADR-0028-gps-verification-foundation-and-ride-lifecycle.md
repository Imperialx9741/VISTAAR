ADR-0028 — GPS Verification Foundation, Ride Lifecycle (ACCEPTED →
CLOSED), and Dispute Domain Resolution

Status: Accepted
Date recorded: 2026-08-26
Deciders: Project owner (via structured decision picker — GPS radius
values and the Dispute-domain question), plus the standard engineering
fill-in-the-undocumented-shape decisions this ADR records per this
project's established discipline.

1. Decisions

1. **GPS radius**: arrival verification radius = 50 meters. Completion
   verification radius = 100 meters. A driver gets 3 attempts per
   verification type per ride before the ride is left in its current
   state pending manual review — see Decision 3.
2. **Dispute domain**: GPS-verification disputes are a Support/Admin
   capability, not a new domain. No new `dispute.*` schema, API surface,
   or state machine is introduced. This resolves ADR-0002's open
   question in favor of option B there ("an approved subdomain/
   capability" of Support/Admin), consistent with BR-121's existing
   "ride-fare disputes require a support/admin process" language, now
   extended to GPS-verification disputes by the same reasoning.
3. **This ADR's own implementation scope**: GPS Verification Foundation
   (Phase 07) and the Ride Lifecycle transitions Phase 06 needs it for
   (`ACCEPTED → ARRIVED → STARTED → COMPLETED → CLOSED`) are built now.
   The actual Dispute-as-Support-capability workflow (Phase 13 — evidence
   submission, admin APPROVE/REJECT, GPS override) is NOT built in this
   change — Decision 2 records the architecture the future work must
   follow, but building the full 16-task Phase 13 scope is deferred to
   its own task. What this change DOES do for that future work: every
   GPS check (pass or fail) is written to `ride.gps_verifications`
   (already exactly documented, database-design.md §14.1) as an
   immutable audit trail — the raw material a future Dispute-as-Support
   case would review — with zero schema invented ahead of that task.

2. Context

api-contracts.md §17/18/28 already fully document Driver Arrival, Ride
Start OTP, and Ride Completion. state-machines.md §6-8 already document
the state-machine shape (`ARRIVED` requires `GPS verification = PASS`;
`STARTED` requires a valid, unexpired, attempt-limited OTP; `COMPLETED`
requires `GPS verification = PASS`). database-design.md §13-14 already
fully specify `ride.ride_otps` and `ride.gps_verifications`. None of
this needed inventing — the only genuinely missing piece was the radius
values themselves (business-rules.md §43/PRD.md §9 explicitly marked
these TBD) and the Dispute-domain question (ADR-0002). Both are now
resolved.

3. What this change builds

- **Migration**: `ride.gps_verifications` and `ride.ride_otps`, exactly
  as database-design.md §13-14 specify. `ride.rides.arrived_at`/
  `started_at`/`completed_at`/`closed_at` already existed as unused
  nullable columns (present since Task 3.1's original migration) — no
  change needed there, only that `RideRepository.save()` (which
  previously only synced `status`/`driver_id`/`vehicle_id`/
  `accepted_at`/`cancelled_at`) now also syncs these.
- **GPS verification**: a pure `haversine_distance_meters()` helper in
  `modules.ride.domain` (duplicated from Pricing's own
  `haversine_distance_km()`, not imported — same "small pure domain
  helper duplicated per-domain" precedent Safety's `Coordinates`/
  `validate_coordinates` already established, rather than a cross-
  domain dependency for one formula). A verification either PASSes or
  FAILs against the ride's current pickup (`ARRIVAL`) or current
  destination (`COMPLETION`) point; every attempt is recorded in
  `gps_verifications`, pass or fail — this table IS the audit trail,
  not an afterthought.
- **Retry/manual-review split** (Decision 1's "3 attempts... manual
  review"): attempts 1-3 that fail return `NOT_WITHIN_PICKUP_RADIUS`/
  `NOT_WITHIN_DESTINATION_RADIUS` (api-contracts.md §17/§28's own
  documented codes) — retriable, the ride stays in its current state.
  The 4th+ attempt (i.e. once 3 failures are already on record) returns
  the more terminal `GPS_VERIFICATION_FAILED` (api-contracts.md §49) —
  still retriable at the HTTP layer (no code change stops a further
  call), but now understood as "past normal retry, needs human
  judgment" per the roadmap's own "before opening manual review"
  language. No manual-review queue/endpoint is built — Decision 3.
- **Ride-start OTP**: reuses `modules.identity.domain.otp`
  (`generate_numeric_otp`/`hash_otp`/`verify_otp`) rather than
  duplicating HMAC/CSPRNG code — the one deliberate exception to the
  "duplicate small pure domain helpers" precedent above, because this
  is security-sensitive cryptographic code where correctness-via-reuse
  matters more than domain-import purity. A new, ride-scoped pepper
  (`RIDE_OTP_HASH_SECRET`, falling back to `JWT_SECRET` the same way
  identity's own `OTP_HASH_SECRET` does) keeps it a distinct secret from
  both JWT signing and login-OTP hashing. New `core.config.Settings`
  values (all engineering/config choices per security.md §89's own
  "OTP expiry/attempt limits are configuration, not business rules"
  classification, the same authority identity's own OTP settings
  already rely on): `RIDE_OTP_EXPIRY_SECONDS` (900 — 15 minutes, longer
  than login's 5 since a driver may take a while to reach the pickup
  point after arrival before starting), `RIDE_OTP_MAX_ATTEMPTS` (5,
  matching login's own default), `RIDE_ARRIVAL_GPS_RADIUS_METERS` (50),
  `RIDE_COMPLETION_GPS_RADIUS_METERS` (100),
  `RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW` (3).
- **Who sees the OTP** (api-contracts.md §18 doesn't specify — "server
  generates," no documented "customer views it" endpoint): **revised
  from this ADR's original draft.** The OTP is only ever persisted as
  its HMAC (`ride.ride_otps.otp_hash`, via `modules.identity.domain.
  otp.hash_otp`) — the plaintext is never stored, matching that
  module's own "never stored in plaintext where avoidable" discipline.
  That rules out exposing it through a later, separate `GET
  /api/v1/rides/{ride_id}` call (ADR-0024): by the time such a request
  arrives, the plaintext no longer exists anywhere to return. Instead,
  the plaintext is revealed ONLY in the direct HTTP response of
  whichever call generated it. In practice that is always `POST
  .../otp/refresh` (§18, customer-only): the OTP is auto-generated the
  moment the ride reaches `ARRIVED` (inside `mark_arrived()`, whose own
  response goes to the driver and must never carry it), so the
  customer's first sight of any code is necessarily via calling
  `otp/refresh` themselves — which doubles as both "get my current
  code" and "invalidate + issue a new one" (e.g. if it expired or
  wasn't received), since no notification channel exists yet (Phase 15,
  blocked) to push the auto-generated code to the customer unprompted.
  The driver never sees the plaintext through any endpoint — only the
  customer can read it aloud.
- **`waiting_started_at`** (§17's documented response field): equals
  `arrived_at` — no separate column or free-waiting/no-show logic is
  built here. BR-050-053 (free waiting, no-show charges) stay exactly
  as unbuilt as `modules/penalty/__init__.py` already documented —
  genuinely out of this change's scope (a ride-lifecycle-transition
  task, not a penalty task).
- **`COMPLETED → CLOSED`**: state-machines.md §10 only says "entered
  after COMPLETED and the ride-closing workflow has completed," with no
  document anywhere specifying what that workflow consists of (Rating,
  §40, is a separate, independent, not-gating endpoint — confirmed by
  grep, nothing references it as a CLOSED precondition). Implemented as
  immediate/automatic in the same transaction as `COMPLETED`, since no
  further real precondition is documented anywhere to gate it on. No
  `ride.closed` outbox event is published — event-contracts.md
  documents no such event (only `ride.arrived`/`started`/`completed`/
  `cancelled`), and this codebase does not invent undocumented events.
- **Outbox events**: `ride.arrived`, `ride.started`, `ride.completed`
  published with exactly their documented payloads
  (event-contracts.md §10.3/10.4/10.8) — `ride.completed`'s
  `final_fare_quote_id` is the ride's `active_fare_quote_id`;
  `completion_location` is the ride's current destination.
- **Authorization**: Driver Arrival, Start Ride, and Ride Completion are
  all assigned-driver-only (`ride.driver_id == caller`) — same
  IDOR-safe "not found" response for a wrong driver as every other
  ownership check in this codebase. OTP refresh is customer-only
  (`ride.customer_id == caller`).

4. What this change explicitly does NOT do

- Does not build any part of Phase 13's Dispute-as-Support workflow
  (evidence upload, admin APPROVE/REJECT, GPS override) — Decision 3.
- Does not build no-show handling (BR-050-053) or free-waiting-period
  enforcement.
- Does not build Early Drop (Phase 08) — it depends on this same GPS
  verification primitive (`EARLY_DROP` is already a documented
  `gps_verifications.verification_type` value) but is a distinct task
  with its own confirmation/state-machine shape, not attempted here.
- Does not build Pickup Change / Destination Change (Phase 09) — those
  need their own ₹/km rate decision (business-rules.md §43, still TBD),
  unrelated to the GPS-radius decision this ADR resolves.
- Does not resolve BR-112 (emergency/police integration) or any other
  external-provider question.

5. Consequences

Phase 06 (Ride Lifecycle) and Phase 07 (GPS & Verification) close out
their genuinely buildable scope. Phase 08 (Early Drop) and Phase 09
(Ride Modifications) remain not started but are now unblocked in the
narrow sense that the GPS-radius question they also depend on is
resolved — they still need their own scoping work. Phase 13 (Disputes)
has an architecture decision (Decision 2) but no code yet — a real,
smaller, well-scoped next task once picked up.
