ADR-0056 — Pickup Change Simplification: 100m Hard Threshold, No Driver
Decision, No Paid Path

Status: Accepted — owner confirmed via "continue," 2026-08-31.
Documentation was reconciled first (business-rules.md, state-machines.
md, api-contracts.md, event-contracts.md, domain-design.md, database-
design.md, technical-architecture.md — see §6), then backend
implementation followed (see §7, added after acceptance): §5's design
below is now live.

Date recorded: 2026-08-31.
Deciders: Project owner, via a direct instruction during the VISTAAR
mobile build session, 2026-08-31 (owner declined the previously
mobile-planned "wire the existing PROCEED/PASS flow into the driver
app" approach and specified a different rule instead — see §1).

1. Context

PRD.md §34-35 and business-rules.md §22 (BR-071 through BR-078)
document VISTAAR's original pickup-change design: a customer may change
pickup after booking; within 250m the change applies immediately; more
than 250m away, the *driver* is offered a choice — PROCEED (an
additional per-km charge is calculated, shown to the customer, and
applied only after the customer confirms it) or PASS (the driver is
released with no ₹30 penalty and no strike, and the ride is rematched
to a new driver near the changed pickup). ADR-0033 (2026-08-25) resolved
the one remaining open item in that design (BR-076's TBD rate) and
recorded the full implementation: `POST /api/v1/rides/{ride_id}/
pickup-change` (api-contracts.md §22), `.../pickup-change/driver-
decision` (§23), and `.../pickup-change/confirm` (§24) are all live in
`apps/backend/src/modules/ride/router.py`, backed by `RideService.
request_pickup_change()`/`decide_pickup_change()`/
`confirm_pickup_change()`, `PricingService.
calculate_pickup_change_charge()`, and the shared `ride.change_requests`
table (database-design.md §11.1, `request_type=PICKUP_CHANGE`). This is
real, tested, already-shipped backend functionality — Phase 09's own
milestone.

No mobile screen calls any of these three endpoints yet — the mobile
build order's own step 6b (docs/16-mobile/mobile-app-implementation-
plan.md) had proposed building against this existing PROCEED/PASS
design next. Before that happened, the owner gave a different,
significantly simpler rule for pickup change and explicitly asked for
this reconciliation-and-ADR step, with implementation deferred pending
review. Nothing in `apps/mobile` needs undoing — no pickup-change UI
was ever built. What this ADR reconciles is entirely on the
already-shipped *backend* side, plus the product/business-rule
documents that describe it.

2. Decision — the new rule, verbatim from the owner's instruction

1. After a User books a ride, the User may request a pickup-location
   change.
2. The new pickup location is allowed only if it is within 100 metres
   of the last confirmed pickup location.
3. If the new pickup is more than 100 metres away, the change must be
   rejected completely.
4. There is no Sarthi (driver) approval / Proceed / Pass flow for this
   case.
5. If the change is more than 100 metres, the User must cancel the
   current ride and book a new ride.
6. The existing cancellation penalty rules (BR-046-049, Customer
   Cancellation, api-contracts.md §19) apply normally to that
   cancellation — no special exemption, no new penalty rule.
7. The system must not silently move the ride, rematch it to a
   different driver, or increase the fare as a consequence of a pickup
   change.

This replaces the driver-mediated, chargeable >250m path with a flat
binary rule with no financial or matching consequence beyond the
threshold: within threshold, free and immediate, exactly as today;
beyond threshold, rejected outright, full stop — the customer's only
path to a genuinely-far pickup is to cancel and create a new ride
(under the ride's own already-existing, unrelated cancellation-penalty
rules).

3. What this supersedes

- **BR-074** (Pickup More Than 250m Away — "driver gets a choice") —
  superseded. There is no driver choice; the change is rejected.
- **BR-075** (Driver Accepts Changed Pickup) — superseded, no longer
  reachable. No path exists where a pickup change beyond the threshold
  is ever accepted by anyone.
- **BR-076** (Additional Pickup Charge, resolved by ADR-0033 to "the
  ride's own base per-km rate") — superseded. There is no longer any
  scenario in which a pickup change carries a charge; the rate this
  business rule resolved is now unused.
- **BR-077** (Customer Must See Charge) — superseded for pickup change
  specifically (the general "no fare change may be silently applied"
  principle it embodies still holds everywhere else it already applies,
  e.g. destination change, BR-082 — this ADR does not touch that).
- **BR-078** (Driver Passes Changed Pickup) — superseded, no longer
  reachable.
- **BR-071** (Driver Changed-Pickup Pass, the ₹0-penalty/no-strike
  cancellation exemption for a driver passing a >250m pickup change) —
  superseded. Since no driver ever decides on a pickup change anymore,
  this exemption's trigger condition can never occur.
- **BR-073** (Pickup Within 250m) — the *shape* of this rule
  (within-threshold changes apply immediately) is kept; only the
  numeric threshold changes, 250m → 100m.
- **BR-072** (Pickup Change — "customers may change their pickup
  location after booking") is unchanged in substance, now qualified by
  the new threshold/rejection rule.
- **state-machines.md §14-16** ("Changed Pickup: Driver Pass,"
  "...Driver Proceed," "...Customer Rejects Charge") — all three
  superseded. Replaced by a single, much shorter transition: request →
  (≤100m: applied) or (>100m: rejected, ride unchanged).
- **state-machines.md §62's "Changed Pickup >250m" flow summary** —
  superseded, replaced with the new binary outcome.
- **api-contracts.md §23 (Driver Pickup-Change Decision)** and **§24
  (Customer Pickup-Change Confirmation)** — both superseded/removed.
  Neither endpoint has a reachable pending request to act on anymore.
  §22 (Pickup Change) itself is kept, with an updated threshold and
  response shape for the beyond-threshold case (§5 below).
- **PRD.md §34-35** — left as-is (this project's established
  convention: the PRD is kept as the original historical requirement;
  business-rules.md is the corrected, living derived-rules document —
  see ADR-0033's own "Consequences" list, which updated business-rules.
  md but not PRD.md for its own, smaller BR-076 correction). PRD.md
  §34-35 should be read as superseded by this ADR, same as any other
  now-outdated PRD passage a later owner decision overrides.

4. What is explicitly NOT decided here, flagged rather than assumed

- **`driver_cancel_ride()`'s `CHANGED_PICKUP_OVER_250M` reason
  exemption** (ADR-0016/ADR-0033, `_CHANGED_PICKUP_PASS_REASON` in
  `modules/ride/router.py`) is a *normal driver-cancellation*-endpoint
  mechanism, not the pickup-change endpoints this ADR covers. With this
  ADR's rule in effect, nothing will ever legitimately submit that
  reason again (no pickup-change flow produces it) — the code path
  becomes dead, but is not itself broken or incorrect by continuing to
  exist. Whether to remove that dead exemption from
  `driver_cancel_ride()` as follow-up cleanup, or leave it as an inert
  reason string a driver could still type into a free-text
  cancellation reason (the pre-existing "no canonical reason enum"
  behavior this session's own build already relies on for ordinary
  cancellation), is a separate implementation-cleanup decision this ADR
  does not make. Flagged for the owner/reviewer, not assumed.
- **The exact new error code** for the beyond-threshold rejection is
  proposed in §5 below (`PICKUP_CHANGE_TOO_FAR`) but not yet
  implemented — naming is part of what review is for.
- **Whether `ride.change_requests`/`PICKUP_CHANGE` as a
  `request_type` becomes entirely unused** — yes, under this rule nothing
  ever creates a `PICKUP_CHANGE` row again (both the ≤100m and >100m
  paths bypass the table entirely, exactly as the ≤250m path already
  does today per ADR-0033 Decision 5). The table itself is not
  proposed for removal — `DESTINATION_CHANGE` still uses it, and
  database migrations are not undone for a now-unused enum value.

5. New behavior, precisely (as implemented — see §7)

`POST /api/v1/rides/{ride_id}/pickup-change` remains the only
pickup-change endpoint. Request shape unchanged
(`{"latitude": ..., "longitude": ...}`). Customer-only, same
ownership/state checks `RideService.request_pickup_change()` already
performs.

- Distance from the ride's current confirmed pickup ≤
  `RIDE_PICKUP_CHANGE_THRESHOLD_METERS` (new default: `100`, down from
  `250`) → applied immediately, identical response shape to the
  original immediate-apply path: `{"applied": true, "distance_meters":
  <float>}`. No `ride.change_requests` row, no driver involvement —
  unchanged from prior behavior at the (now smaller) threshold.
- Distance > threshold → the request is rejected outright. No `ride.
  change_requests` row is created (the ≤threshold branch already
  skipped this; the >threshold branch now does too, since there is no
  longer a pending decision for a row to represent). The ride's
  `current_pickup`, `status`, and `driver_id`/`vehicle_id` are all left
  completely unchanged — no state transition, no `ride.state_history`
  row, no rematch dispatch, no fare-quote version bump. The response is
  a new domain error/code `PICKUP_CHANGE_TOO_FAR` (409, matching this
  codebase's convention for a business-rule rejection rather than a
  validation failure), with a message telling the customer the new
  pickup is too far and that they should cancel this ride and book a
  new one. No `distance_meters`/`applied` fields are needed in an error
  response — the existing error envelope (`{code, message}`) is
  sufficient.
- `POST /api/v1/rides/{ride_id}/pickup-change/driver-decision` and
  `POST /api/v1/rides/{ride_id}/pickup-change/confirm` are removed —
  both routes return FastAPI's default `404` (route not found), not a
  domain error, since nothing can ever legitimately call them again.
- `PricingService.calculate_pickup_change_charge()` (service method and
  the underlying pure domain function) is deleted — its only caller was
  the now-removed driver-decision endpoint.
- Cancelling instead: unaffected by this ADR. `POST /api/v1/rides/
  {ride_id}/cancel` (api-contracts.md §19, already implemented and
  already shipped in the mobile app, build order step 6a) already
  handles exactly the "customer cancels and can book a new ride" path
  point 5/6 of the owner's rule describes, with its existing
  grace-period/first-qualifying/subsequent penalty rules applying
  unchanged. This ADR does not add, remove, or special-case any
  cancellation behavior.

6. Consequences — documents updated (reconciliation pass, before
   implementation)

- business-rules.md: BR-071/074/075/076/077/078 each annotated
  SUPERSEDED with a pointer to this ADR (not deleted — same
  in-place-correction convention ADR-0033 already used for BR-076's own
  TBD resolution); BR-073's threshold corrected to 100m; BR-072 gains a
  brief qualifying note.
- state-machines.md: §14-16 replaced with a single simplified
  transition; §62's "Changed Pickup >250m" flow summary replaced with
  the new binary outcome.
- api-contracts.md: §22 updated (100m threshold, new error response for
  the beyond-threshold case); §23-24 marked SUPERSEDED/removed, kept
  for historical record (same treatment §29-33's superseded Payment
  sections already received).
- event-contracts.md: §10.5 (`ride.pickup_changed`) marked REMOVED —
  its only publisher (`.../pickup-change/confirm`) no longer exists;
  §44's flow diagram and the event consumer registry both corrected to
  match; §10.6 (`ride.destination_changed`) is unaffected.
- domain-design.md: §9.4 (RequestPickupChange/ConfirmPickupChange),
  §9.5 (RidePickupChanged), and §11.4 (CalculatePickupChangeCharge)
  annotated to reflect the removal.
- database-design.md: §11.1 (`ride.change_requests`) gained an
  implementation-status note — table/columns unmodified, but no
  PICKUP_CHANGE row is ever created by new code anymore, either branch.
- technical-architecture.md: §26 (Pickup Change Architecture) rewritten
  with the new binary flow, original kept below as historical record;
  §27 (Destination Change) unaffected.
- docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md: item 18's own entry gained
  a pointer to this ADR.
- PRD.md: left unmodified, per this project's established convention —
  see §3 above.

7. Implementation (2026-08-31, after owner acceptance via "continue")

Backend implemented exactly as §5 describes:

- `core/config.py`: `RIDE_PICKUP_CHANGE_THRESHOLD_METERS` default
  changed `250` → `100`.
- `modules/ride/domain/errors.py`: added `PickupChangeTooFarError`
  (code `PICKUP_CHANGE_TOO_FAR`, mapped to HTTP 409 in
  `shared/api_envelope.py`); removed `PickupChangeNotFoundError`,
  `PickupChangeNotAwaitingDriverDecisionError`,
  `PickupChangeNotAwaitingConfirmationError`,
  `InvalidPickupChangeDecisionError` (all now-unreachable).
  `PickupChangeAlreadyRequestedError` is kept, purely as a defensive
  guard against a pending request row that predates this ADR — new
  code never creates one.
- `modules/ride/service.py`: `request_pickup_change()` now raises
  `PickupChangeTooFarError` instead of creating a pending request for a
  >threshold change; `get_pending_pickup_change()`,
  `decide_pickup_change()`, `confirm_pickup_change()` deleted entirely.
- `modules/ride/router.py`: `.../pickup-change/driver-decision` and
  `.../pickup-change/confirm` routes deleted; `.../pickup-change`
  simplified to match the new two-outcome service method.
- `modules/ride/schemas.py`: `DecidePickupChangeBody`,
  `ConfirmPickupChangeBody` deleted.
- `modules/pricing/service.py` and `modules/pricing/domain/entities.py`:
  `calculate_pickup_change_charge()` (service method and pure domain
  function) deleted.
- `ChangeRequestStatus.AWAITING_DRIVER_DECISION`/`.PASSED` and
  `ChangeRequestDriverDecision` are kept in the domain entity/schema —
  not removed — solely for backward compatibility with any request row
  that predates this ADR; new code never sets them.

Tests: the dedicated `tests/test_pickup_change_api.py` integration
suite was rewritten for the new behavior (a single rejection test
replacing the old PROCEED/PASS/reject tests; two new tests confirming
the removed routes 404), and the pickup-change-specific unit tests in
`tests/test_pricing_service.py` were deleted along with the code they
tested. Full backend suite: **1244 passed, 5 skipped (Kafka-
connectivity-only, unrelated), 0 failed** — including the real-Postgres
integration tests for this change, not skipped.

No mobile code changed by this implementation pass — the mobile Pickup
Change UI (build order step 6b) is separate, subsequent work.
