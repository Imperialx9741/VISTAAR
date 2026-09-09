"""VISTAAR Matching module — Driver Location Tracking & Ride Matching
(Phase 3 / Task 3.2).

Owns the driver geo index, ride-offer records, and dispatch —
docs/04-domain-design/domain-design.md §10 (Matching Domain) and
docs/04-database/database-design.md §10.1 (matching.ride_offers).

Implements four endpoints (paths, not module boundaries — see below):

    POST /api/v1/drivers/me/location                          (api-contracts.md §15)
    GET  /api/v1/drivers/me/ride-offers                        (api-contracts.md §16)
    POST /api/v1/drivers/me/ride-offers/{offer_id}/reject      (api-contracts.md §16)
    POST /api/v1/drivers/me/ride-offers/{offer_id}/accept      (api-contracts.md §16)

The location-update path lives here rather than in modules/driver/
because domain-design.md §10.2 explicitly assigns "driver geo index"
ownership to the Matching Domain, not Driver — router.py defines two
separate APIRouter instances (different URL prefixes) for this reason,
both included in main.py.

See docs/14-decisions/ADR-0011-matching-scope-and-open-items.md and
ADR-0014-accept-offer-fee-and-vehicle-source.md for the scope decisions
these tasks made. Accept Offer / Ride ACCEPTED (ADR-0011 Decision 3's
original blocker) is now implemented (Phase 3 / Task 3.4) — see
accept_offer_endpoint() in router.py and MatchingService.accept_offer()
in service.py. This module still deliberately does NOT implement:

- A background worker/scheduler for the 20-second offer expiry
  (ADR-0011 Decision 2) — evaluated lazily instead, at every read of a
  driver's pending offers (Get Current Offers, Reject Offer, and the
  ride-creation-triggered initial dispatch).
- Publishing matching.offer_created/offer_rejected/offer_expired
  (event-contracts.md §11) — the outbox/Kafka producer infrastructure
  now exists (ADR-0017, Phase 3 / Event & Outbox Foundation) and this
  module DOES publish ride.accepted/wallet.debited from its accept-offer
  endpoint (composed there, not here — see router.py), but the
  offer-lifecycle events themselves are still out of scope; not built
  because no consumer of them exists yet either (ADR-0017 §4's same
  "no speculative infrastructure" reasoning).
- BR-031's "no driver accepts -> Retry/Increase Fare" customer flow, and
  the NO_DRIVER ride state some other documents describe — ADR-0011
  Item 5, carried forward unresolved from ADR-0010 Item 6. When the
  eligible-driver candidate list is exhausted, a ride simply stays
  SEARCHING with zero active matching.ride_offers rows; no error, no new
  state.
- Ride cancellation itself (that's modules.ride's — see
  MatchingService.cancel_pending_offers_for_ride() below for this
  module's one-directional part in it, composed at
  modules/ride/router.py, Task 3.3 / ADR-0012 Decision 2).

What it does do:

- `POST /api/v1/drivers/me/location`: validates the driver is ONLINE
  (api-contracts.md §15's "Driver state" check — DRIVER_NOT_ONLINE if
  not) and coordinates, resolves the driver's current ACTIVE vehicle
  (composed here with modules.vehicle, same pattern
  modules/driver/router.py already uses for Go Online), and writes to
  Redis (shared/geo.py: geo:drivers:{category} + driver:online:{id}).
- Given a ride's requested category and pickup point, finds the nearest
  eligible driver not already offered this ride (Redis GEOSEARCH
  candidates, re-verified against Postgres for current eligibility —
  Redis is only ever a spatial index here, never authoritative — see
  shared/geo.py) and creates a PENDING matching.ride_offers row with a
  20-second (configurable, not a business value —
  MATCHING_OFFER_TTL_SECONDS) expiry (BR-026, BR-027).
- `GET /api/v1/drivers/me/ride-offers`: lazily expires any PENDING offer
  past its expires_at, dispatching a new offer to the next eligible
  driver for that ride before returning this driver's still-current
  PENDING offers (BR-030).
- `POST .../reject`: transitions PENDING -> REJECTED (or -> EXPIRED if
  it turns out to already be past expiry) and dispatches a new offer to
  the next eligible driver (BR-029). No platform fee is deducted — a
  fee is only ever debited on a successful Accept.
- `POST .../accept` (Task 3.4, ADR-0014): technical-architecture.md
  §18's Accept-Ride Transaction — validates PENDING/not-expired/driver
  eligible/vehicle eligible/wallet balance sufficient, then atomically
  debits the platform fee (BR-011/012/013, via modules.wallet), assigns
  the driver+vehicle, and transitions offer -> ACCEPTED and
  ride -> ACCEPTED. Composed directly in router.py (wallet + matching +
  ride) rather than inside MatchingService, which stays decoupled from
  both — see router.py's module docstring for the full locking design.
- `MatchingService.cancel_pending_offers_for_ride()` (Task 3.3): given a
  ride_id, transitions any PENDING offer for it to CANCELLED — the one
  documented offer status (database-design.md §10.1) this module hadn't
  used until now. No rematch follows. Not routed to HTTP directly;
  modules/ride/router.py's cancel endpoint calls it.

Layering mirrors modules/ride/ and modules/vehicle/:

    domain/         pure business logic — no FastAPI/SQLAlchemy/Redis imports
    ports.py        OfferRepository, NearbyDriverIndex, DriverEligibilityChecker
                    Protocols
    models.py       SQLAlchemy ORM model for matching.ride_offers
    repositories.py SqlAlchemyOfferRepository + RedisNearbyDriverIndex
                    (infrastructure implementations of the ports above)
    service.py      application service (use case): MatchingService
    schemas.py      Pydantic request/response DTOs
    dependencies.py FastAPI DI wiring, including ComposedEligibilityChecker
                    (the one place this module imports modules.driver/
                    modules.vehicle — a narrow, one-directional
                    dependency, same shape as modules/vehicle/router.py's
                    existing composition with modules.driver for Go
                    Online)
    router.py       FastAPI routes under the three paths listed above,
                    and the composition point modules/ride/router.py
                    calls into after creating a ride
"""
