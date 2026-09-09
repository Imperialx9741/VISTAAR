ADR-0030 — Early Drop Implementation Scope (Phase 08)

Status: Decided and implemented (2026-08-25)
Deciders: This record resolves a genuine documentation conflict found
while scoping the implementation — flagged rather than guessed past, per
this project's own "PRD → Business Rules → Architecture → API Contracts
→ Database/Events/State Machines → Tests → Implement" source-of-truth
hierarchy (business-rules.md §44/45).

1. Context

Phase 08 (Early Drop) was previously assessed as transitively blocked on
Phase 07's GPS radius decision (VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's
own Phase 08 entry, pre-ADR-0028). ADR-0028 resolved Phase 07's own
arrival/completion GPS radii (50m/100m), so this record re-examined
whether that same resolution carries over to Early Drop. It does not —
security.md §12 explicitly names all three together ("The final radius
(for arrival, completion, and early drop) requires an explicit
product/business decision") but the project owner was only ever asked
about, and only ever approved, arrival and completion (ADR-0028 §1's "ok
ask the queries you have doubt" round never mentioned early drop). state-
machines.md §63 independently lists "Exact early-drop GPS tolerance" and
"Exact behavior when early-drop GPS verification fails repeatedly" as
still-open TBD items, unresolved by ADR-0028.

Closer reading, however, finds this apparent blocker dissolves once the
actual source-of-truth documents are compared rather than assumed
consistent:

- business-rules.md BR-088 (Customer-Requested Early Drop): "Customer
  requests early drop → Driver records reason → Customer confirms →
  GPS/location + timestamp recorded → Ride can complete." GPS/location is
  RECORDED — there is no verification step, no PASS/FAIL outcome, and
  nothing gates ride completion on a distance/tolerance check.
- api-contracts.md §27 (Early Drop): "Server records: GPS / Timestamp /
  Customer confirmation / Driver confirmation." Again, recorded — no
  verification step, no PASS/FAIL field anywhere in the documented
  request/response shape.
- technical-architecture.md §43: "Customer requests early drop → Driver
  records request → Customer confirms → Capture GPS + timestamp →
  Complete ride." Same — capture, not verify.
- database-design.md §12.1 (`ride.early_drop_requests`) has no `result`/
  `status` column of any kind for a verification outcome — only
  `customer_confirmed`/`driver_confirmed` booleans and a `gps_location`
  point. There is nothing in this schema to record a PASS/FAIL against.

Only state-machines.md §19-21 introduces a verification GATE ("GPS
verification ↓ ... Only a successful verification allows the early-drop
completion flow to close," "GPS check ├── FAIL → REVIEW/retry ... └──
PASS → EARLY_DROPPED") — a requirement none of the three higher-ranked
documents (Business Rules, Architecture, API Contracts) establish. This
is the same shape of gap ADR-0002 already found and named for the
GPS-verification-dispute workflow: a downstream document (there,
security.md/testing-strategy.md; here, state-machines.md) adding a
mechanic the upstream chain never actually authorized. Unlike ADR-0002's
GPS-dispute case, this one is resolvable without a new owner decision —
the documented hierarchy already tells us which reading governs when
documents conflict, and three higher-ranked documents agree with each
other and disagree with the lower-ranked one.

2. Decision

Decision 1 — No GPS verification gate for Early Drop; recording only.
Per the source-of-truth hierarchy, business-rules.md/api-contracts.md/
technical-architecture.md govern over state-machines.md's added
verification-gate language. `gps_location`/`confirmed_at` are captured
as an evidence record on `ride.early_drop_requests` once both parties
confirm; no distance/tolerance check is performed, no PASS/FAIL is
computed, and `ride.gps_verifications` (which already reserves
`GpsVerificationType.EARLY_DROP` for exactly this possibility — ADR-0028
§3) is NOT written to by this task, since there is no verification result
to record there. This resolves state-machines.md §63's "Exact early-drop
GPS tolerance"/"Exact behavior when early-drop GPS verification fails
repeatedly" TBD items as N/A, not merely deferred — there is no tolerance
or failure-handling policy to be TBD once no threshold check happens at
all. `GpsVerificationType.EARLY_DROP` stays reserved/unused, exactly as
before.

Decision 2 — Two-sided confirmation, one endpoint, two callers.
domain-design.md's `ride.early_drop_requests` schema (`customer_confirmed`
+ `driver_confirmed` booleans), state-machines.md's explicit "Customer
confirms + Driver confirms" flow, and BR-089's own section title
("Two-Sided Confirmation") all agree both parties must confirm — read
against BR-089's body text ("the customer must confirm the early-drop
request") as establishing the customer's own requirement specifically,
not excluding the driver's, which the section title and schema both
corroborate. `POST /api/v1/rides/{ride_id}/early-drop/confirm`
(api-contracts.md §27, `{"confirmed": true}`) is called once by each
party — the caller's own account_type determines which boolean it sets,
never a client-supplied role field, matching every other actor-derivation
in this codebase. `confirmed: false` is how "Customer rejects → STARTED"/
"Driver rejects → STARTED" (state-machines.md §21) is realized — no
separate reject endpoint exists or is needed; it discards the pending
request row so a fresh one can be filed.

Decision 3 — GPS coordinates travel on the driver's own confirm call.
Neither api-contracts.md §27's Confirm request (`{"confirmed": true}`)
nor database-design.md's schema says who submits `gps_location` — engine
plumbing, not a business decision. Matching every other GPS-capture
endpoint in this codebase (Driver Arrival, Ride Completion — ADR-0028),
the location travels with the DRIVER's own confirm call (optional
`latitude`/`longitude`, required specifically when the caller is the
driver): the driver's device is the operationally relevant one, and the
customer may already be exiting the vehicle by the time they confirm.

Decision 4 — `reason` is an additive column. api-contracts.md §27's
documented Request body includes `reason` with nowhere in database-
design.md §12.1's original schema to store it — the identical shape of
gap ADR-0022 Decision 1 already fixed for `support.cases.ride_id`, fixed
the same way here (`ride.early_drop_requests.reason`, nullable VARCHAR).

Decision 5 — Ride transition reuses COMPLETED, not a new status.
state-machines.md §3.1's authoritative ride-status enum (SEARCHING/
ACCEPTED/ARRIVED/STARTED/COMPLETED/CANCELLED/CLOSED — exactly what
`RideStatus` already implements) has no `EARLY_DROPPED` value, and
technical-architecture.md §43's own flow diagram draws early drop feeding
into "Complete ride" directly. §19/§21's "EARLY_DROPPED" is read as a
label for this same COMPLETED outcome (reached via the early-drop path
rather than the normal destination-arrival path), not a literal eighth
`ride.rides.status` value — inventing one would contradict §3.1's own
"exactly these states" framing. Once both confirmations exist:
STARTED → COMPLETED → CLOSED in the same request, immediately/
automatically (ADR-0028 Decision 3's already-established precedent for
why no separate CLOSED trigger exists — the same reasoning applies here
verbatim). `active_fare_quote_id` is untouched (Decision 6).

Decision 6 — No fare change. BR-090: "The original fare remains payable
even when the customer requests an early drop." No recalculation, no new
charge, no composition with modules.pricing.

3. What this implements

- Migration: `ride.early_drop_requests` (id, ride_id FK, requested_by,
  reason [additive, Decision 4], customer_confirmed, driver_confirmed,
  gps_location [nullable, Decision 1/3], requested_at, confirmed_at).
- `POST /api/v1/rides/{ride_id}/early-drop` (customer-only; ride must be
  STARTED; only one pending request at a time per ride).
- `POST /api/v1/rides/{ride_id}/early-drop/confirm` (customer or driver,
  ownership-checked; `confirmed: true` sets the caller's own flag; once
  both are true, STARTED → COMPLETED → CLOSED and `ride.early_drop_
  confirmed` is published with event-contracts.md §10.7's exact
  documented payload; `confirmed: false` discards the pending request).
- No code touches `ride.gps_verifications`/`modules.pricing` for this
  feature (Decisions 1/6).

4. Consequences

- Phase 08 (Early Drop) is genuinely unblocked and implemented — not
  merely reclassified as VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's earlier
  correction (2026-08-25, pre-dating this record) assumed when it said
  "the GPS-proof step [is] independently buildable now": that assumption
  is corrected here — there never was a GPS-proof *step* to build, once
  the actual authoritative documents are compared against each other
  rather than state-machines.md read in isolation.
- state-machines.md §19-21's verification-gate language is now known to
  be unratified by the higher-authority documents, the same class of
  finding ADR-0002 made for the GPS-dispute workflow — flagged here
  rather than corrected in state-machines.md itself, since resolving a
  cross-document conflict is this ADR's job, not a silent doc edit.
