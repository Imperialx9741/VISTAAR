ADR-0033 — Ride Modifications: Pickup Change, Destination Change, and the
Pickup-Change-PASS Rematch Design

Status: Accepted.
Date recorded: 2026-08-25.
Deciders: Project owner (rate decisions, rematch design), via
AskUserQuestion — VISTAAR session, 2026-08-25. Everything else decided
under the owner's phase-level-autonomy grant; the specific items below
were real mandatory-stop conditions (roadmap §0.3), not guessed past.

1. Context

Phase 09 (Ride Modifications) was blocked on one specific gap: BR-076's
pickup-change rate was explicitly marked TBD (range discussed:
₹10–₹20/km, never approved). Re-reading business-rules.md §22-23 while
scoping this task found the *other* half of the phase was never actually
blocked the way the roadmap's own summary implied — BR-080 (destination
extension) already has a ratified, documented flat rate (₹8/km, with a
worked numeric example), no TBD marker anywhere near it. The roadmap's
"core value blocked — roughly half the phase needs a TBD rate" verdict
conflated the two; this ADR corrects that on the record (see also the
roadmap/execution-plan doc updates alongside this ADR).

Everything else this phase needs — the 250m pickup-change threshold, the
driver PROCEED/PASS decision, the customer-confirmation-required gate on
any fare increase, the three destination-change cases (within route /
beyond original / different route) — is already fully documented across
business-rules.md §22-23, state-machines.md §14-18, technical-
architecture.md §26-27, domain-design.md §9.4/§11.4/§11.6, api-
contracts.md §22-26, and event-contracts.md §10.5-10.6, down to exact
endpoint paths, request/response shapes, and event payloads. This ADR
resolves the two remaining real gaps and records the implementation
design; it does not restate what those documents already settle.

2. Decision 1 — Pickup-change rate: reuse the ride's own base per-km fare

The owner resolved BR-076's TBD rate as "the same rate as the base
per-km fare" — i.e., not a new flat number, but the vehicle category's
own `pricing.fare_rules.per_km` value already loaded for CalculateFare.
This needs no new configuration value at all: `PricingService.
calculate_pickup_change_charge()` looks up the ride's own fare rule (by
`fare_rule_key(vehicle_category, cab_tier)`, the same helper CalculateFare
already uses) and multiplies its `per_km` by the extra distance beyond
250m. business-rules.md BR-076 updated from TBD to this resolution.

3. Decision 2 — Destination-extension rate: unchanged, ₹8/km flat

BR-080's already-ratified ₹8/km flat rate is kept exactly as documented
— not replaced with a per-category rate, and not touched by Decision 1
above. `PricingService.calculate_destination_change_fare()`'s "Case B —
beyond original destination" branch uses a single new config constant,
`RIDE_DESTINATION_EXTENSION_RATE_PER_KM` (default `"8.00"`), matching
this codebase's existing convention for every other numeric business
constant (`RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW`, `MATCHING_SEARCH_RADIUS_KM`,
etc. — a `core/config.py` setting, not a new generic rules table). The
documented `pricing.additional_charge_rules` config table
(database-design.md §16.1) stays unbuilt — genuinely unneeded scope
beyond what these two now-decided values require, the same "don't build
what nothing calls yet" discipline ADR-0013 applied to Wallet's
`credit()` before Task 3.5 gave it a caller.

4. Decision 3 — Pickup-change PASS: same ride resets to SEARCHING,
   re-dispatched near the new pickup

state-machines.md §14 ("Changed Pickup: Driver Pass") documents the
result as "current driver → released, ride → rematching" — descriptive
prose, not a literal `RideStatus` value, and genuinely ambiguous the same
way ADR-0016 Item 2 already found BR-070's driver-cancellation rematch
language ambiguous (same ride resets vs. cancel-and-transparently-
recreate). This is the identical mechanic, so it was surfaced as the
identical class of stop condition rather than resolved independently.

The owner decided: the same ride row resets — `driver_id`/`vehicle_id`
cleared, `status: ACCEPTED -> SEARCHING`, a fresh `ride.state_history` row
(`reason: CHANGED_PICKUP_OVER_250M`, `actor_type: DRIVER`), and the
router composes a fresh `MatchingService.dispatch_offer()` call against
the *new* pickup location — same best-effort, separately-committed
pattern `POST /api/v1/rides`' own post-creation dispatch already uses (a
dispatch failure must never undo the already-durable state change).

This decision is scoped to the pickup-change-PASS path only.
`RideService.driver_cancel_ride()` (Task 3.6, ADR-0016) is NOT changed by
this ADR — it still transitions ACCEPTED -> CANCELLED unconditionally,
exactly as state-machines.md §13 literally documents, with no rematch
dispatch. Extending "same ride resets to SEARCHING" to *that* endpoint
too would be a larger, backward-incompatible change to already-shipped,
tested behavior (`ride.state_history` semantics, any future `ride.
cancelled` consumer's expectations) that the owner's answer did not
unambiguously request changing — ADR-0016 Item 2 stays open for normal
driver cancellation specifically. If the owner does want
`driver_cancel_ride()`'s behavior changed to match, that's a follow-up
decision, not assumed here.

The PASS branch of `RideService.decide_pickup_change()` implements this
inline (not a separate method — the same call already holds the request
row lock and needs to decide PROCEED vs. PASS, so splitting the ride-side
transition into its own method would just add an extra round trip) — same
row-lock/ownership-check shape as `driver_cancel_ride()`, different
terminal transition and no penalty/strike, matching BR-071/078's
exemption, which `driver_cancel_ride()` already implements for its own
`CHANGED_PICKUP_OVER_250M` reason path (that existing exemption logic is
mirrored here, not duplicated as a shared helper — the ride-side
transition itself differs enough, SEARCHING vs. CANCELLED, that a shared
helper would need its own conditional branching anyway).

5. Decision 4 — Request tracking: the already-documented
   `ride.change_requests` table, not a new one

**Correction, recorded after initial implementation**: this ADR's first
draft (and initial code) invented a new `ride.pickup_change_requests`
table, having missed that database-design.md §11 ("Ride Change
Requests") already documents `ride.change_requests` — one shared table
for both PICKUP_CHANGE and DESTINATION_CHANGE, discriminated by
`request_type`, with `old_location`/`new_location`,
`old_fare_quote_id`/`new_fare_quote_id`, and separate
`driver_decision`/`customer_decision` columns. The project owner was
asked directly (mid-session) whether to keep the invented table or
rework to match the documented one, and chose the rework — this section
now describes what was actually shipped, not the superseded first draft.

`ride.change_requests` (database-design.md §11.1, unmodified from what
was already documented): id, ride_id, request_type (PICKUP_CHANGE —
DESTINATION_CHANGE is documented but not yet implemented by this ADR),
requested_by, old_location/new_location (GEOMETRY(Point,4326), reusing
the same DDL-only type every other geometry column in this codebase
uses), old_fare_quote_id (the ride's `active_fare_quote_id` captured at
request time, for audit reference — never read back by any service
method in this ADR's scope), new_fare_quote_id (nullable — set only once
the driver's PROCEED decision computes one), status
(AWAITING_DRIVER_DECISION — only reached when >250m; ≤250m never creates
a row, see Decision 5 — AWAITING_CUSTOMER_CONFIRMATION, CONFIRMED,
REJECTED, PASSED — this codebase's own choice of vocabulary; the
documented schema only fixes `request_type`'s two values and a `PENDING`
column default, not the full status enum), driver_decision (NULL/
PROCEED/PASS), customer_decision (NULL/CONFIRMED/REJECTED, set at the
confirm step), created_at, resolved_at. No `distance_meters` column
exists in the documented schema — `RideService`/the router recompute it
from `old_location`/`new_location` via `haversine_distance_meters()`
wherever needed rather than persisting a derived value.

The repository port (`ChangeRequestRepository.get_pending_for_update()`)
takes `request_type` as an explicit filter, so a pending PICKUP_CHANGE
request and a pending DESTINATION_CHANGE request on the same ride (once
the latter is implemented) can never collide on the same "one pending
request" lookup.

6. Decision 5 — ≤250m pickup change and Case A destination change never
   create a request row

Both apply immediately: `ride.rides.current_pickup`/`current_destination`
updated in place, a `ride.state_history` row recorded, the documented
event published — no driver decision and no customer confirmation gate
exists for these paths (BR-073, technical-architecture.md §27 Case A),
so persisting a transient request row for them would be unused
ceremony. This mirrors how `mark_arrived()`'s PASS-path GPS verification
doesn't create a dispute row either — only the paths that actually need
multi-step state get one.

7. Decision 6 — Fare-quote versioning: `FareQuoteRepository.
   get_latest_for_ride()` added

`pricing.fare_quotes.version` is unique per `(ride_id, version)`; every
ride created so far only ever has version 1 (`CreateFareRevision` was
never called — ADR-0020). A pickup-change PROCEED or a destination-change
Case B/C needs the *next* version number for that ride, so a new
repository method (`get_latest_for_ride(ride_id) -> FareQuote | None`) is
added; `PricingService` computes `next_version = (latest.version if
latest else 0) + 1`. The new quote's `reason` is `"PICKUP_CHANGE"` or
`"DESTINATION_CHANGE"` (matching the existing `"INITIAL_QUOTE"`
convention); `additional_charge` carries the new amount, `total` is the
previous quote's total plus it — its id is what `ride.change_requests.
new_fare_quote_id` (Decision 4) stores once computed. `FareQuoteStatus`
stays `DRAFT`-only, unchanged from ADR-0020 — "activation" is still
purely the `ride.rides.active_fare_quote_id` pointer swap on customer
confirmation, the same mechanism the initial quote already uses; no new
status value is invented for this ADR either.

8. Decision 7 — Endpoints, exactly as api-contracts.md §22-26 already
   document

    POST /api/v1/rides/{ride_id}/pickup-change                (customer)
    POST /api/v1/rides/{ride_id}/pickup-change/driver-decision (driver)
    POST /api/v1/rides/{ride_id}/pickup-change/confirm         (customer)
    POST /api/v1/rides/{ride_id}/destination-change            (customer)
    POST /api/v1/rides/{ride_id}/destination-change/confirm    (customer)

No new endpoint invented; no documented shape changed.

9. Decision 9 — Destination-change case classification: a route-
   deviation tolerance, engineering judgment not a business value

BR-079/080/081 name three cases (along the original route / beyond the
original destination / a different route) but no document anywhere
specifies the geometric test for telling them apart — unlike the
pickup-change threshold (250m, an explicit owner-approved number), no
tolerance value was ever discussed for this. Classifying a case wrong
does have a real billing consequence (Case A charges nothing, Case B
charges a flat ₹8/km, Case C recalculates the whole fare), but the
*tolerance value itself* is a geometric-classification implementation
detail, not a new business rule the way a rate or a penalty amount is —
the same distinction ADR-0020 Decision 5 already drew when it chose
straight-line haversine distance over real road routing without asking
the owner. This is decided here as an engineering judgment call, stated
plainly so it can be revisited:

`CalculateDestinationChangeFare` treats `new_destination` as "along the
original route" (BR-079/080) when its perpendicular distance from the
straight line between `original_pickup` and `original_destination` is
within `RIDE_DESTINATION_ROUTE_DEVIATION_METERS` (new config constant,
default 200 — the same order of magnitude as the owner-approved 250m
pickup threshold, not a monetary value). Within that tolerance, the
point is projected onto the line; a projection at or before the original
destination is Case A (BR-079, original fare unchanged, no request row
created — same "nothing changed, no ceremony" treatment as pickup
change's own ≤threshold case, ADR-0033 Decision 5), a projection beyond
it is Case B (BR-080, ₹8/km × the straight-line distance from the
*original* destination to the *new* one — matching BR-080's own worked
example's framing of "additional distance"). Outside the tolerance
entirely is Case C (BR-081) — full `CalculateFare` recalculation from the
ride's *current* location (not the original pickup) to the new
destination, exactly as BR-081/technical-architecture.md §27 Case C
state.

"Current location" for Case C has no real data source anywhere in this
codebase, and this needed resolving before Case C could be implemented
at all: `POST /api/v1/drivers/me/location` (modules.matching) is a
driver-global, Redis-ephemeral geo-index update for dispatch purposes
only — not ride-scoped, not persisted, not queryable after the fact.
The destination-change request body itself (api-contracts.md §25)
carries only the new destination, no location field. No per-ride live-
GPS-tracking mechanism exists (out of scope to build here — a genuinely
separate, larger feature). `ride.current_pickup` is therefore used as
"current location": it is the only "confirmed current state" location
concept `Ride` actually has, and for a STARTED ride it holds the
driver's confirmed arrival point (frozen since `mark_arrived()`,
ADR-0028) — the closest available approximation to "where the ride
currently stands" without inventing new infrastructure this task was
never asked to build. Recorded here explicitly as an engineering
interpretation, not a literal reading of "current location," so it can
be revisited if real per-ride live tracking is ever built.

Case A never creates a `ride.change_requests` row (no confirmation
needed, BR-082 only requires one when the fare changes) or a fare quote
— it updates `ride.rides.current_destination` directly via the existing
`update_current_destination()` port method (ADR-0033 Decision "Request-
tracking tables" above). Cases B and C both create a request row
(`request_type=DESTINATION_CHANGE`, `status=AWAITING_CUSTOMER_
CONFIRMATION` immediately — no driver-decision step exists for
destination change anywhere in the documented flow, unlike pickup
change's PROCEED/PASS) and a new fare quote via `PricingService.
calculate_destination_change_fare()`; the ride's destination/active fare
quote only change once the customer confirms.

10. Decision 10 — Events

`ride.pickup_changed` and `ride.destination_changed` (event-contracts.md
§10.5/§10.6) are published on confirmation, exact documented payload
shapes. Outbox rows written regardless of whether a real consumer exists
yet — same "no consumer, still published" treatment every other event
this session has added gets. Case A's destination update (no fare
change) is not itself a documented event — `ride.destination_changed`'s
own payload always carries `additional_charge`, implying it fires only
when a charge exists (Cases B/C), the same reading BR-082 supports
("if destination change causes the fare to change").

11. Consequences — documents updated alongside this ADR

- business-rules.md BR-076 updated from TBD to "same as the ride's own
  base per-km fare rate," with a note pointing at this ADR. BR-080 is
  unchanged (already correct).
- docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's Phase 09 entry and summary
  bucket corrected — it previously described "roughly half the phase
  needs a TBD rate" as if both rates were open; only BR-076 was.
- api-contracts.md §22-26 annotated with implementation status (no shape
  changed).
- database-design.md §11.1 gains an implementation-status note — the
  table itself is unmodified from what was already documented (see
  Decision 4's correction note).
- domain-design.md §9.4/§11.4/§11.6 commands/rules marked implemented.
- state-machines.md unchanged in substance — §14-18 already document the
  literal, unambiguous transitions this ADR implements; only an
  implementation-status note is added.
- ADR-0016 Item 2 (normal driver-cancellation rematch) is explicitly NOT
  resolved by this ADR — see Decision 4's own scoping note.
