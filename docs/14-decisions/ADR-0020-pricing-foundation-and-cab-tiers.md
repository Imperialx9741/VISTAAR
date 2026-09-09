ADR-0020 — Pricing Foundation, CAB Tiers, and the Ride-Creation Fare/Promotion Composition

Status: Accepted
Date recorded: 2026-08-24
Deciders: Approved via a real owner-supplied fare table plus a
three-round clarification exchange in the VISTAAR session, 2026-08-24
(the roadmap's own mandatory stop conditions, §0.3, were genuinely hit
three times below and resolved with the owner before any implementation
started — not guessed past).

1. Context

business-rules.md BR-005/006 mark exact fare rates as "TBD, determined
through unit-economics analysis" — the single blocker Phase 04's
"Initial fare quote" task, ADR-0010 Decision 1 (`fare` always `null`),
ADR-0019 Item 6 (promotion reservation not composed into ride creation),
and Phase 06/09's fare-dependent work have all been carrying since this
session began. The owner supplied a real, approved fare table:

|                  | 2W (🏍️) | Auto (🛺) | Eco (🚕) | Premium (🚘) | Premium+ (✨) |
| ---------------- | ------: | -------: | -------: | -----------: | ------------: |
| Minimum fare     |     ₹39 |      ₹59 |      ₹79 |          ₹99 |         ₹129 |
| Base fare        |     ₹29 |      ₹39 |      ₹55 |          ₹65 |          ₹85 |
| Per km           |      ₹7 |      ₹10 |      ₹12 |          ₹14 |          ₹18 |
| Free waiting     |   3 min |    5 min |    5 min |        5 min |        5 min |
| Waiting/min      |      ₹1 |       ₹2 |       ₹2 |           ₹2 |           ₹3 |
| Platform fee     |      ₹2 |       ₹5 |      ₹10 |          ₹10 |          ₹10 |

Three genuine ambiguities were surfaced against already-approved/already-
implemented decisions before any of this was built, each resolved
directly with the owner:

- The table's 5 columns don't match business-rules.md §2's documented 3
  vehicle categories (Bike, Auto, Cab).
- The table's platform fees (₹2/₹5/₹10/₹10/₹10) contradict BR-011's
  already-approved, already-implemented fees (Bike ₹10 / Auto ₹20 /
  Cab ₹20, ADR-0014 Decision 1).
- api-contracts.md §12 requires fare to be calculated *before* matching
  (no vehicle assigned yet); an initial "the assigned vehicle's tier
  decides the fare" answer would have made the quoted fare
  non-deterministic at request time, conflicting with BR-002 (pricing
  transparency) and BR-032/033 (no silent fare increases).

2. Decision 1 — Vehicle categories stay BIKE/AUTO/CAB; Eco/Premium/
   Premium+ are CAB sub-tiers, chosen by the customer at booking time

The owner confirmed: 2W/Auto map onto the existing BIKE/AUTO categories
1:1 (no schema change to `VehicleCategory`); Eco/Premium/Premium+ are
three fare/eligibility tiers *within* CAB, not new categories. The owner
also confirmed (reversing an intermediate answer, once the ride-creation-
timing conflict above was raised) that the *customer* selects the tier
when requesting a ride — the same way `vehicle_category` itself is
already selected — making the fare fully deterministic before matching
starts, consistent with api-contracts.md §12's documented flow and
BR-002/BR-032/BR-033.

Schema (additive, non-breaking):

- `vehicle.vehicles` gains `cab_tier VARCHAR(20) NULL` — set by the
  driver at vehicle creation (`POST /api/v1/drivers/me/vehicles`),
  required and validated when `category = CAB`, rejected (must be
  absent) otherwise. Self-declared, the same mechanism `category`
  itself already uses — no admin-assignment endpoint is invented.
- `ride.rides` gains `requested_cab_tier VARCHAR(20) NULL` — required
  and validated when `vehicle_category = CAB`, mirroring exactly how
  `requested_vehicle_category` was added (ADR-0011 Decision 1).
- Matching (BIKE/AUTO/CAB dispatch, the Redis geo-index in
  `shared/geo.py`, and `ComposedEligibilityChecker`) is entirely
  string-keyed already and never imports `modules.vehicle`/`modules.ride`
  directly (by design — see `modules/matching/service.py`'s own
  docstring). Tier-aware matching is implemented by building a composite
  key (`modules.vehicle.domain.entities.matching_category_key()`,
  e.g. `"CAB:ECO"`) at the three router-layer composition points that
  already import `modules.vehicle` (`modules/matching/router.py`'s
  location-update and accept-offer/rematch endpoints, `modules/ride/
  router.py`'s dispatch call) — zero signature changes inside
  `modules.matching` itself.

3. Decision 2 — This table supersedes BR-011's platform fee

The owner confirmed the new table is authoritative. Since Eco/Premium/
Premium+ all charge the identical ₹10 platform fee, this maps cleanly
onto the existing 3-category fee dict with no schema change: BIKE ₹2,
AUTO ₹5, CAB ₹10 (was ₹10/₹20/₹20). `business-rules.md` BR-011's table
is updated in the same change (source-of-truth precedence, §0.1: an
explicitly approved owner decision outranks a stale Business Rules
entry), and `modules/matching/router.py`'s existing
`dict[VehicleCategory, Decimal]` constant (ADR-0014 Decision 1) is
updated to match.

4. Decision 3 — No Time Charge component in v1; Minimum Fare is a floor
   on Base + Distance only

The owner confirmed the table's absence of a per-minute travel-time rate
means v1 pricing is `max(minimum_fare, base_fare + per_km × distance) -
promotion_discount` (waiting/parking/toll/tax stay `0` at the initial
quote — none of those have a live composition point yet either; see
Item 6 below). This still matches domain-design.md §11.3's documented
formula exactly (`Base + Distance + Time(0) + Waiting(0) + Parking(0) +
Toll(0) + Tax(0) - Promotion + Additional(0) = Final`) — no formula
term is removed, several are just genuinely `0` for now, the same
treatment `pricing.fare_quotes`' own schema already defaults every line
item to.

The floor is applied by adjusting `distance_charge` upward when
`base_fare + distance_charge < minimum_fare` (no new column is added for
it — `pricing.fare_quotes` has no `minimum_fare` line item documented,
and the existing `base_fare`/`distance_charge` pair already sums to the
right total either way).

5. Decision 4 — Distance is straight-line (haversine), not routed

`pricing.fare_rules` needs a real distance figure per ride. technical-
architecture.md's stack table names Mapbox + OSM as the approved Maps
choice (not TBD, unlike Payment gateway/Notifications in the same
table) — but no Mapbox credential exists in this environment, and live
routing-API integration is exactly the §0.4 external-provider gate every
other named-but-uncredentialed provider in this codebase has hit
(Admoto, the payment gateway, SMS/WhatsApp). `CalculateFare` uses a
pure haversine great-circle distance between pickup and destination
(both already stored as plain lat/lng — see `modules/ride/domain/
entities.py::Coordinates`) as an interim placeholder, clearly flagged
in code as not the real road-distance Mapbox would eventually provide.
This does not block anything else in this task — same "flag the
specific external-provider gap, build everything else" treatment
ADR-0018 gave Admoto.

6. Decision 5 — `pricing.fare_rules` is a real table, seeded via
   migration data, not a hard-coded constant

Unlike the platform fee (technical-architecture.md only *suggests* a
`platform_fee_rules` table database-design.md never defines — ADR-0014
Decision 1's reasoning for using a constant), `pricing.fare_rules` *is*
already fully defined by database-design.md §15.1, including
`effective_from`/`effective_until`/`active` columns built for exactly
this kind of rate update over time. Building the real, documented table
and seeding it with this task's 5 rows (keyed by `vehicle_category`:
`BIKE`, `AUTO`, `CAB_ECO`, `CAB_PREMIUM`, `CAB_PREMIUM_PLUS` — an
engineering choice for the string content of an already-generic
VARCHAR(20) column, not an invented business rule) is more faithful to
the documented schema than a shortcut constant would be, and matches
this session's "build the real documented schema, not a placeholder"
precedent (ADR-0019's Promotion/Referral tables). One additive column
beyond what §15.1 documents: `minimum_fare NUMERIC(12,2) NOT NULL` — no
other column expresses the table's own new "Minimum fare" line item.

7. Decision 6 — `CalculateFare` and `ReservePromotion` both compose into
   `POST /api/v1/rides`, closing ADR-0019 Item 6

api-contracts.md §12's documented flow is "Validate customer → Validate
coordinates → Calculate fare → Apply eligible promotion → Create ride →
Start matching." With a real fare now available, ADR-0019 Item 6's
deferred blocker (no Fare Quote step existed to reserve a promotion
discount against) is resolved. `modules/ride/router.py::create_ride()`
composes, in order: create the ride (so `pricing.fare_quotes.ride_id`'s
FK target exists) → `PricingService.calculate_fare()` → set `ride.rides.
active_fare_quote_id` → if the customer has any active, unexpired
entitlement (`PromotionService.list_entitlements()`, ordered
soonest-`expires_at`-first — an engineering choice to avoid an
entitlement quietly expiring unused while a later-expiring one keeps
getting picked, not a documented business rule), reserve it
(`PromotionService.reserve_entitlement()`) and recompute the quote's
`promotion_discount`/`total` before persisting — all within the same
already-established explicit-commit sequence this router uses (ride
creation still commits durably before the best-effort matching-dispatch
step, unchanged from ADR-0011).

`ConsumePromotion`/`RestorePromotion` on ride completion/cancellation,
and `CreateFareRevision`/`CalculatePickupChangeCharge`/
`CalculateDestinationChangeFare` (pickup/destination change, Phase 09,
not started), remain out of scope — no live caller exists yet for any
of them (same "no real caller yet" deferral this session has used
repeatedly), and `waiting_charge`/`parking_charge`/`toll_charge`/
`tax_amount` stay `0` for the same reason (no waiting-time tracking,
parking-proof-to-fare composition, toll integration, or tax engine
exists).

8. Consequences — documents updated alongside this ADR

- `business-rules.md` BR-005/006 updated with the resolved rates
  (superseding "TBD"); BR-011's fee table updated to ₹2/₹5/₹10.
- `database-design.md` §15.1 annotated with `minimum_fare`; §8.1/§9.1
  annotated with `cab_tier`/`requested_cab_tier`.
- `api-contracts.md` §11/§12 annotated: `cab_tier` in Add Vehicle and
  Create Ride Request; the `fare` response field's real
  `{base, discount, total, currency}` shape.
- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: Phase 04's "Initial
  fare quote" task marked complete; ADR-0019 Item 6 marked resolved.
- No change to `domain-design.md`, `event-contracts.md`, or
  `state-machines.md` — the domain built matches what they already
  specify (§11's commands/formula, §12.1's `pricing.fare_calculated`
  payload shape) with nothing contradicted.
