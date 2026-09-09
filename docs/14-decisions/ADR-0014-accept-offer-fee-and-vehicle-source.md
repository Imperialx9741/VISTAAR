ADR-0014 — Accept Offer: Platform Fee Source and Assigned-Vehicle Source

Status: Accepted
Date recorded: 2026-08-23
Deciders: Approved via the Task 3.4 (Accept Offer) planning and
decision-resolution exchange, following the same "flag before
implementing" governance ADR-0010 through ADR-0013 used for every prior
task (implementation-readiness.md §74).

1. Context

Task 3.4 (Driver Offer Acceptance, SEARCHING → ACCEPTED) implements
technical-architecture.md §18's Accept-Ride Transaction. Two points in
that transaction were not fully pinned down by any existing document
and needed a decision before implementation: where the platform fee
amount comes from (ADR-0013 §4 Item 4, deferred from the Minimal Wallet
Foundation), and which vehicle_id gets written onto ride.rides when the
offer's originally-captured vehicle may no longer be the driver's
current active one.

2. Decision 1 — Platform fee amount is a hard-coded constant, not a
   database table

business-rules.md BR-011 already fixes the fee by category (Bike ₹10 /
Auto ₹20 / Cab ₹20) as an approved rule, not a TBD value.
technical-architecture.md §17 suggests a `platform_fee_rules` table as
a possible future convenience ("allows future pricing changes without
rewriting the wallet engine"), but database-design.md — the
authoritative schema document — does not define that table, and no
other approved document requires it to exist for this task.

A `dict[VehicleCategory, Decimal]` constant matching BR-011 exactly is
implemented at the composition layer (modules/matching/router.py, next
to the accept-offer endpoint), the same treatment already given to
other fixed, approved, non-schema values in this codebase (e.g.
core.config.settings.MATCHING_OFFER_TTL_SECONDS's 20-second constant).
Building platform_fee_rules now would be inventing schema no document
requires; if the fee ever needs runtime configurability, that is a
separate, later task with its own migration and its own decision.

3. Decision 2 — The assigned vehicle is re-derived at accept time, not
   trusted from the offer's dispatch-time snapshot

matching.ride_offers.vehicle_id records which vehicle was offered the
ride at dispatch time. state-machines.md §5 and technical-architecture.
md §18 both require re-validating "Vehicle eligible" (and "Driver
eligible") as part of the accept transaction itself — not merely
trusting a value captured up to 20 seconds earlier (BR-027's offer TTL).
A driver's ACTIVE vehicle (BR-122: at most one at a time) can change
between offer dispatch and acceptance.

Accept Offer re-runs the same ComposedEligibilityChecker used at
dispatch (modules/matching/dependencies.py) and assigns whatever
vehicle_id it currently returns to ride.rides.vehicle_id — not
offer.vehicle_id. In the overwhelming majority of cases these are the
same vehicle; when they differ, re-deriving is what actually satisfies
the documented "Vehicle eligible" requirement, rather than a check that
looks at eligibility but assigns a different, potentially-stale
vehicle. The offer row's own vehicle_id is left unmodified — it remains
an accurate historical record of what was offered, not what was
ultimately assigned.

4. Consequences — documents updated alongside this ADR

- api-contracts.md §16 (Accept Offer) annotated with the current
  implementation status and a pointer to this ADR.
- docs/VISTAAR_IMPLEMENTATION_ROADMAP.md updated: Task 3.4 marked
  complete once implemented and verified.
- No content changed in business-rules.md, domain-design.md,
  event-contracts.md, state-machines.md, or database-design.md — both
  decisions above operate strictly within what those documents already
  specify; neither required a schema or business-rule change.
