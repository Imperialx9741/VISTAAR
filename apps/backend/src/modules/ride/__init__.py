"""VISTAAR Ride module — Ride Booking / Create Ride Request
(Phase 3 / Task 3.1), extended by Task 3.2 for matching dispatch,
Task 3.3 for SEARCHING-only customer cancellation, and Task 3.4 for
SEARCHING -> ACCEPTED (AssignDriver, via RideService.accept_ride()).

Owns ride records, per docs/04-domain-design/domain-design.md §9 (Ride
Domain) and docs/04-database/database-design.md §9.1/§9.2 (ride.rides,
ride.state_history).

Implements these endpoints, docs/05-api/api-contracts.md §12, §13, §19:

    POST /api/v1/rides                     Create Ride Request
    GET  /api/v1/rides/{ride_id}           Get Ride (Phase 04, ADR-0024)
    POST /api/v1/rides/{ride_id}/cancel    Customer Cancellation (SEARCHING only)

See docs/14-decisions/ADR-0010-ride-creation-scope-and-open-items.md,
ADR-0011-matching-scope-and-open-items.md,
ADR-0012-searching-cancellation-scope-and-open-items.md, and
ADR-0014-accept-offer-fee-and-vehicle-source.md for every scope
decision made so far — this module deliberately does NOT:

- Calculate a fare, or apply a promotion (Pricing/Promotion domains
  don't exist yet — Phases 5/6). The response always returns
  `"fare": null` (ADR-0010 Decision 1). `active_fare_quote_id` stays
  NULL on every ride this module creates.
- Accept a `payment_method` field at all — removed 2026-09-03 (owner
  decision, no user-facing payment-method selection in the app; see
  modules/ride/domain/entities.py's own docstring). It was previously
  accepted-but-unpersisted (ADR-0010 Decision 2).
- Implement any other ride-lifecycle command beyond AssignDriver and
  the two cancellation paths (MarkArrived, StartRide, ... —
  domain-design.md §9.4).

ride.requested/ride.accepted/ride.cancelled ARE published now (Phase 3
/ Event & Outbox Foundation, ADR-0017) — router.py writes each to
shared.outbox_events in the same transaction as the domain change it
describes (event-contracts.md §2/§27); see shared/outbox.py. ACCEPTED/
ARRIVED cancellation and Driver Cancellation (state-machines.md
§11/§13, BR-046-049's real 2-minute-grace/₹15 logic, BR-067-071) are
ALSO implemented now (Tasks 3.5/3.6, ADR-0015/0016) — see router.py's
own docstring for the full composition (wallet refund, penalty
recording, driver strike). Cancelling a ride that isn't in a
cancellable state, or charging anything beyond what BR-046-049/BR-067
document, remains out of scope.

What it does do:

- Creates `ride.rides` directly in SEARCHING (state-machines.md §4),
  including `requested_vehicle_category` (added by Task 3.2, ADR-0011
  Decision 1; Task 3.1 validated but couldn't persist it — ADR-0010 §8
  Addendum).
- Writes one `ride.state_history` row (NULL -> SEARCHING) in the same
  transaction as the ride insert (ADR-0010 Decision 3), another
  (SEARCHING -> CANCELLED, with the customer's `reason`) when a ride is
  cancelled (Task 3.3), and another (SEARCHING -> ACCEPTED, no reason)
  when a ride is accepted (Task 3.4, ADR-0014) — `RideService.
  accept_ride()` is the one place `driver_id`/`vehicle_id`/`accepted_at`
  get written (domain-design.md §9.6: "Only the Ride Domain may
  transition the authoritative ride state"). Composed at
  `modules/matching/router.py`'s accept-offer endpoint, not here — this
  module has no dependency on modules.matching or modules.wallet.
- Enforces `Idempotency-Key` against `shared.idempotency_keys`
  (ADR-0010 Decision 5) via shared/idempotency.py on ride creation only —
  no Idempotency-Key header is documented for Cancel (api-contracts.md
  §19 lists none, unlike §12), so none is required there either. Ride
  creation's dedup is not a "one active ride" business rule — none is
  documented, and none is invented (see ADR-0010 Decision 5's full
  reasoning).
- Validates pickup/destination as standard-range coordinates only (no
  invented geofence/service-area/same-location restriction) and
  `vehicle_category` against the existing `VehicleCategory` enum
  (reused from `modules.vehicle.domain.entities` — no new enum; a
  narrow, one-directional ride -> vehicle dependency, same shape as
  vehicle -> verification elsewhere in this codebase).
- Establishes the caller's `customer.customers` row first (via
  `modules.customer.service.CustomerService.get_profile`, which
  auto-provisions) to satisfy `ride.rides.customer_id`'s foreign key —
  same API-layer composition pattern `modules/vehicle/router.py`
  already uses for `driver.drivers`.
- Ownership is always enforced (`ride.customer_id == authenticated
  customer` — `RIDE_NOT_FOUND` either way it isn't, same IDOR-masking
  pattern used throughout this codebase) before any cancellation, and
  the same pattern gates Get Ride (Phase 04, ADR-0024): a customer sees
  only their own ride, a driver only a ride assigned to them.
- After the ride is durably created or cancelled, router.py makes a
  best-effort call into `modules.matching` (dispatch the first offer on
  creation; cancel any outstanding PENDING offer on cancellation) — a
  one-directional ride -> matching dependency at the router/composition
  layer only (this module's domain/service/repositories never import
  modules.matching). Neither call can fail or roll back the ride's own,
  already-successful response — see router.py's docstring for why.

Layering mirrors modules/vehicle/ and modules/driver/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        RideRepository Protocol
    models.py       SQLAlchemy ORM models (infrastructure), including
                    the PostGIS geometry columns (shared/geometry.py)
    repositories.py SQLAlchemy-backed implementation of the port
    service.py      application service (use cases): create_ride(),
                    cancel_ride(), get_ride()
    schemas.py      Pydantic request/response DTOs
    dependencies.py FastAPI DI wiring (reuses modules.identity's
                    require_customer/require_customer_or_driver as-is —
                    no new auth code here)
    router.py       FastAPI routes under /api/v1/rides
"""
