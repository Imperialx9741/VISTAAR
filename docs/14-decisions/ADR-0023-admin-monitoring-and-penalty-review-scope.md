ADR-0023 — Admin Monitoring & Penalty Review Scope (Phase 16)

Status: Accepted
Date recorded: 2026-08-24
Deciders: Autonomous implementation (phase-level owner authorization —
see the standing execution agreement), reconciling roadmap Phase 16
("Admin," 17 tasks) against docs/05-api/api-contracts.md §46-48, the
only canonical source of the Admin HTTP surface.

1. Context

Phase 16 in docs/VISTAAR_IMPLEMENTATION_ROADMAP.md lists 17 admin
capabilities: Admin dashboard, Customer management, Driver management,
Vehicle management, Ride monitoring, Payment monitoring, Wallet
monitoring, Penalty administration, Promotion administration, Referral
administration, Dispute dashboard, GPS evidence review, Pricing
configuration, Safety dashboard, Support dashboard, Advertisement
management, Audit viewer.

This list is PRD/roadmap-level ("Admin capabilities should include...",
PRD.md §54; domain-design.md §23.2) — an intent list, not itself an API
contract. Per this project's own source-of-truth hierarchy
(business-rules.md §45: PRD → Business Rules → Architecture → API
Contracts → Database/Events/State Machines → Tests → Implement), the
question of what to actually build is answered by api-contracts.md, not
by the roadmap bullet list. api-contracts.md's entire Admin surface is
§46 (Admin APIs), §47 (Admin Financial Review), §48 (Admin Penalty
Review) — 12 routes total. Cross-referencing each of the 17 roadmap
bullets against those 12 routes (plus what Task 2.7A already built in
Phase 2, before Phase 16 existed as a checkpoint) gives the scope below.

2. Decision 1 — What is already built (no new work)

Driver management and Vehicle management (mutations) are COMPLETE from
Phase 2 / Task 2.7A (ADR-0009): `GET /api/v1/admin/drivers/{driver_id}`
(Driver Review), `POST .../drivers/{id}/approve`, `POST
.../drivers/{id}/reject`, `POST /api/v1/admin/vehicles/{id}/approve`,
`POST .../vehicles/{id}/reject`. Nothing in this ADR changes them.

3. Decision 2 — What Phase 16 adds: Ride monitoring

`GET /api/v1/admin/rides` (Search Rides) and `GET
/api/v1/admin/rides/{ride_id}` (Get Ride) are documented with real query
parameters (`status`, `driver_id`, `customer_id`, `page`, `page_size` —
§46, §51) but no response body shape. Built:

- `RideRepository.search()` (new port method) — allow-listed filters
  only (§51: "Clients cannot inject arbitrary SQL fields into
  sorting/filtering"), backed by a real SQL query with `LIMIT`/`OFFSET`
  and a paired `COUNT(*)` for `pagination.total`.
- `RideService.search_rides()` composes it. `RideService.get_ride()`
  (added Phase 3 / Task 3.2, previously unexposed via HTTP) is reused
  as-is for Get Ride — no new service method needed there.
- Response shape (filled in, since none is documented — same precedent
  Phase 14 set for GET Support Case): `ride_id`, `status`, `customer_id`,
  `driver_id`, `vehicle_id`, `requested_vehicle_category`,
  `requested_cab_tier`, `pickup`/`destination` (current, not original —
  matches what's operationally relevant to a monitoring admin), `fare`
  (same shape modules/ride/router.py's `_fare_data()` already produces,
  when `active_fare_quote_id` is set), and the full lifecycle timestamp
  set (`requested_at` through `cancelled_at`/`closed_at`). This requires
  one new, narrow read: `FareQuoteRepository.get_by_id()`, looked up via
  the ride's own `active_fare_quote_id` (not a ride_id lookup —
  `pricing.fare_quotes` can hold more than one version per ride, so
  fetching by the specific id the ride already points to is the only
  unambiguous read; the only other fare-quote lookup that exists,
  `create()`, doesn't serve a re-fetch at all).
- Pagination follows §50 exactly. Since no list endpoint existed
  anywhere in this codebase yet, a shared `shared/pagination.py` helper
  (`PageParams`, `paginate()`, `pagination_envelope()`) is added rather
  than a one-off in modules/ride — Search Penalties (Decision 4 below)
  reuses it immediately, and it is the natural shared home for every
  future list endpoint (same "first module to need it belongs in
  shared/" reasoning shared/api_envelope.py's own docstring already
  states). Max page size is server-configured (§50) via a new
  `ADMIN_MAX_PAGE_SIZE` setting (default 100), following
  core/config.py's existing `MATCHING_SEARCH_RADIUS_KM`-style pattern.
- Both routes live on `modules/admin/router.py`, composing
  `modules.ride`'s service/repository — NOT on `modules/ride/router.py`
  (customer/driver-scoped, prefix `/api/v1/rides`, unauthenticated for
  arbitrary ride ids). This mirrors exactly how Driver/Vehicle Review
  already compose modules.driver/modules.vehicle at the admin layer.
  Read-only: no audit log is written (matching the existing precedent
  that GET /api/v1/admin/drivers/{driver_id} writes none either — only
  admin *mutations* are audited).

This is distinct from and does not build roadmap item 10 (Phase 04's
customer/driver-facing `GET /api/v1/rides/{ride_id}`, api-contracts.md
§13) — a separate, still-open, small unblocked task noted in
VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's execution order.

4. Decision 3 — What Phase 16 adds: Wallet monitoring (partial Admin
   Financial Review)

`GET /api/v1/admin/wallets/{driver_id}` (§47) is built: `WalletService.
get_wallet()` already exists (used by the driver-facing `GET
/api/v1/drivers/me/wallet`) and is reused unchanged, just called with an
admin-supplied `driver_id` instead of the caller's own. Response shape
is exactly `_wallet_data()`'s existing shape (`balance`, `currency`,
`outstanding_settlement`) — no transaction history is folded in here:
`GET /api/v1/drivers/me/wallet/transactions` (§34) is a separate,
still-undocumented-response, still-unbuilt, driver-facing endpoint, not
part of what §47 names for this route. No `WalletDomainError` this
endpoint can raise requires a new error code — an unknown `driver_id`
surfaces via `RESOURCE_NOT_FOUND` the same way it would for any other
admin lookup (wallet auto-creation on first access, per
`get_or_create_for_update`'s existing contract, means this route never
404s for a driver that exists — only for a `driver_id` with no
`driver.drivers` row, checked via the existing account lookup pattern
Driver Review already uses).

`GET /api/v1/admin/payments/{payment_id}` and `GET
/api/v1/admin/settlements` (also §47) are NOT built — flagged, not
invented. No `modules/payment` exists anywhere in this codebase (Phase
10, payment gateway selection, remains fully blocked — no domain, no
table, nothing to query). "Settlements" has no backing concept in
database-design.md or domain-design.md at all under any module. Building
either would mean inventing both a data model and a response shape with
zero source-of-truth grounding — the same §0.3/§0.4-class gate this
session has hit repeatedly (Advertisement HTTP, Driver Suspend HTTP,
Safety/Support command HTTP). "Payment monitoring" (the roadmap bullet)
stays entirely blocked for the same reason.

5. Decision 4 — What Phase 16 adds: Penalty administration (Admin
   Penalty Review)

§48 documents both routes with a concrete request example for resolve
but no response shapes and no filter query params for the list route.
Built:

- `PenaltyRepository.get_by_id_for_update()` (new port method, same
  row-locking shape as every other exclusive-transition repository in
  this codebase) and `.search()` (filters: `status`, `user_id`,
  paginated — modeled on Search Rides' shape, since §48 names no
  filters explicitly).
- `PenaltyStatus.WAIVED` — a real fourth status. state-machines.md §40
  documents it as a direct sibling of SETTLED/EXPIRED under OUTSTANDING
  ("OUTSTANDING → WAIVED"), a DIFFERENT case from ADR-0015 Decision 2's
  "a ₹0 penalty is created already SETTLED, no fourth status needed" —
  that decision was about penalty *creation*, not admin resolution; it
  does not preclude WAIVED as a distinct outcome of a later admin
  action. The stale-sounding overlap is called out here so a future
  reader does not mistake the two for a contradiction.
- `Penalty.waive()` (domain method) and `PenaltyService.resolve_penalty()`
  (service method, row-locked via `get_by_id_for_update()`) — requires
  `status == OUTSTANDING`; SETTLED/EXPIRED/already-WAIVED raise
  `PenaltyNotOutstandingError` → `INVALID_STATE_TRANSITION` (reusing the
  existing error code, same as Approve/Reject Driver's "not PENDING"
  case — no new code invented).
- `action` in the request body is validated to equal exactly `"WAIVE"` —
  the only value api-contracts.md's example shows and the only outcome
  state-machines.md's Penalty State Machine documents an admin action
  reaching (OUTSTANDING → WAIVED). Any other value is a
  `VALIDATION_FAILED`, not silently accepted — no canonical `action` enum
  exists to validate more permissively against.
- "The original penalty remains immutable. A reversal/waiver record is
  created" (§48): `amount`/`issued_at`/`expires_at` are never rewritten
  (only `status`, and NOT `settled_at` — WAIVED is not "settled," and no
  separate `waived_at` column is documented, so that field stays NULL
  for a waived penalty). The "reversal/waiver record" is the
  `admin.audit_logs` row this mutation writes in the same transaction
  (`action="RESOLVE_PENALTY"`, `before_state`/`after_state` capturing the
  status transition, `reason` from the request body) — reusing the
  existing audit-log mechanism every other admin mutation already uses,
  rather than inventing a second, undocumented table for the same
  purpose. `database-design.md` §33.2's `admin.audit_logs` schema
  (`before_state`/`after_state` JSONB, `reason` TEXT) already satisfies
  what §48 asks for.
- No outbox event is published — event-contracts.md documents no
  `penalty.waived`/`penalty.resolved` event anywhere (only
  `penalty.applied`/`penalty.strike_recorded`/`penalty.expired`, none of
  which describe this transition), and no other admin mutation in this
  codebase publishes one either (Approve/Reject Driver/Vehicle are
  audit-logged only, not outboxed) — consistent, not a gap specific to
  this task.
- Both routes live on `modules/admin/router.py`, composing
  `modules.penalty`'s service/repository — `modules/penalty/` itself
  still has no router.py of its own (its `__init__.py`'s "implements no
  HTTP endpoint of its own" note is updated to mention this second
  composition point, alongside the existing ride-cancellation one).

6. Decision 5 — What stays explicitly BLOCKED/flagged (not invented)

The remaining roadmap bullets have zero HTTP shape anywhere in
api-contracts.md — building any of them would mean inventing a new
public API contract, the same §0.3 mandatory-stop condition this session
has applied to Advertisement (ADR-0018), Driver Suspend/Reactivate
(ADR-0021), and Safety/Support's non-HTTP commands (ADR-0022):

- Admin dashboard (aggregate view) — no route, no shape, anywhere.
- Customer management — api-contracts.md has no
  `/api/v1/admin/customers*` route of any kind; PRD.md §54/domain-design
  §23.2 name it as an intent, api-contracts.md never operationalized it.
- Vehicle Review (`GET /api/v1/admin/vehicles/{id}`) and any
  driver/vehicle pending-review list/search endpoint — already flagged
  as not-documented by ADR-0009/Task 2.7A; unchanged by this ADR (a
  vehicle can still only be approved/rejected sight-unseen).
- Promotion administration / Referral administration — no
  `/api/v1/admin/promotions*` or `/api/v1/admin/referrals*` route
  documented anywhere, despite domain-design.md §23.2 naming "Promotion
  review"/"Referral review" as intents.
- Dispute dashboard / GPS evidence review — both depend on the Dispute
  domain question ADR-0002 explicitly left unresolved (no schema, no
  API, no state machine anywhere for GPS-verification disputes);
  building either here would resolve that ADR by implementation
  accident, which ADR-0002 itself says must not happen.
- Pricing configuration — no admin-facing CRUD endpoint over
  `pricing.fare_rules` is documented anywhere (ADR-0020/pricing/ports.py
  already notes "no admin-facing CreateFareRule/rate-change endpoint
  exists yet"); unchanged here.
- Safety dashboard / Support dashboard — beyond the 3 real endpoints
  ADR-0022 already built (SOS, Create/Get Support Case), no admin-facing
  list/aggregate-view route is documented for either domain.
- Advertisement management — ADR-0018 already established this is fully
  blocked at the HTTP layer (§0.3); unchanged.
- Audit viewer — `admin.audit_logs` is a real, populated table, but no
  `GET` route to read it back exists anywhere in api-contracts.md. This
  is worth calling out explicitly because
  VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's own working notes had grouped
  "the audit viewer" together with the genuinely-buildable items
  (customer/driver/vehicle/ride/wallet monitoring) as "backed by
  already-complete domains" — that phrasing conflated "the data exists"
  with "an endpoint to read it is documented." api-contracts.md, the
  actual source of truth, settles it: no route, so not built. This
  ADR's own roadmap-doc updates correct that earlier phrasing.

7. Consequences

Of Phase 16's 17 roadmap bullets: 2 were already complete (driver/vehicle
mutation management, Task 2.7A), 3 are newly built here (ride monitoring,
wallet monitoring, penalty administration), and 12 remain flagged as
having no documented HTTP contract to build against — not unbuilt
through lack of effort, but because api-contracts.md itself does not
describe them. Any of the 12 becomes buildable the moment a real route
and response shape is added to api-contracts.md (or, for the Dispute-
coupled two, once ADR-0002 is resolved).
