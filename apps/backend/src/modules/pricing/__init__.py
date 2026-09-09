"""VISTAAR Pricing module — Phase 04's "Initial fare quote" task.

Owns `pricing.fare_rules`/`fare_quotes`, per
docs/04-database/database-design.md §15, implementing domain-design.md
§11.4's CalculateFare (with ApplyPromotionDiscount folded in).

See docs/14-decisions/ADR-0020-pricing-foundation-and-cab-tiers.md for
the full scope reasoning. This module deliberately does NOT:

- Use a real road-routing distance. `calculate_fare()` uses a straight-
  line haversine distance between pickup and destination — technical-
  architecture.md names Mapbox+OSM as the approved Maps choice, but no
  Mapbox credential exists in this environment (§0.4). Flagged in code
  (`domain/entities.py::haversine_distance_km()`), not silently
  invented — same treatment ADR-0018 gave Admoto.
- Implement CreateFareRevision, CalculatePickupChangeCharge, or
  CalculateDestinationChangeFare. All three need Phase 09 (Ride
  Modifications, not started) as a real caller — no live endpoint
  changes a ride's pickup/destination yet.
- Compute a non-zero time_charge/waiting_charge/parking_charge/
  toll_charge/tax_amount. None has a live composition point yet (no
  waiting-time tracking, no parking-proof-to-fare composition, no toll
  integration, no tax engine) — domain-design.md §11.3's formula is
  still implemented exactly, with these terms genuinely 0, not omitted.
- Expose any HTTP endpoint. No `GET /api/v1/rides/{id}/fare` or similar
  is documented anywhere; the only consumer is the internal composition
  in `modules/ride/router.py::create_ride()`.

What it does do:

- `calculate_fare()`: BR-005/006's now-resolved rates (ADR-0020), keyed
  by `pricing.fare_rules.vehicle_category` (`BIKE`/`AUTO`/`CAB_ECO`/
  `CAB_PREMIUM`/`CAB_PREMIUM_PLUS` — see `domain/entities.py::
  fare_rule_key()`). `total = max(minimum_fare, base_fare + per_km ×
  distance) - promotion_discount`, composed into
  `modules/ride/router.py::create_ride()` right after the ride itself is
  created (`pricing.fare_quotes.ride_id` is a NOT NULL FK) — see
  ADR-0020 Decision 6, which also closes ADR-0019 Item 6 by reserving
  and applying an eligible promotion in the same call.

Layering mirrors modules/promotion/ and modules/advertisement/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        FareRuleRepository, FareQuoteRepository Protocols
    models.py       SQLAlchemy ORM models for the two tables
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): PricingService
    dependencies.py FastAPI DI wiring

No schemas.py/router.py — this module has no HTTP surface (see above).
"""
