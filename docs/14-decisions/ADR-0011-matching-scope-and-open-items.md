ADR-0011 — Driver Matching (Task 3.2) Scope and Open Items

Status: Decisions 1–4 Accepted. Item 5 (NO_DRIVER state conflict) —
Decision required, NOT decided by this record, carried forward from
ADR-0010 Item 6.
Date recorded: 2026-08-22
Deciders: Approved via the "VISTAAR — Ride Booking / Task 3.2 — Driver
Location Tracking & Ride Matching" planning and decision-resolution
exchange, following the same "flag before implementing" governance
ADR-0010 used for Task 3.1 (implementation-readiness.md §74).

1. Context

Task 3.2 implements roadmap.md's Phase 3 exit criteria for driver
matching: nearest-eligible-driver discovery, offer generation, 20-second
expiry, and offer rejection → next driver. Researching it against
api-contracts.md §15–16, event-contracts.md §11,
database-design.md §10, technical-architecture.md §13–18,
domain-design.md §10, state-machines.md §5, and business-rules.md
BR-026–034 surfaced four gaps that needed a decision before
implementation, plus one already-known unresolved conflict this task
still doesn't resolve.

2. Decision 1 — `ride.rides` gets a `requested_vehicle_category` column

ADR-0010 §8 (Addendum) found `ride.rides` has no column for the
customer's requested vehicle category, and deferred the question of
whether one needs to be added to "whichever task first builds Matching."
That's this task: Matching cannot pick a Redis GEO category-set
(`geo:drivers:BIKE/AUTO/CAB`) to search without it. `ride.rides` gains
`requested_vehicle_category VARCHAR(20) NOT NULL`, added via a new
migration and reflected in `database-design.md` §9.1. This is a genuine
schema addition, not something Task 3.1 or ADR-0010 already authorized —
recorded here per business-rules.md §44's change process (identify
affected domain → update database docs → migrate → implement).

`ride.rides.requested_vehicle_category` is set once, at ride creation,
from the same request field Task 3.1 already validates (`vehicle_category`
in `POST /api/v1/rides`) — no change to that endpoint's request contract,
only to what happens with the value after validation.

3. Decision 2 — Offer expiry and rematch are evaluated lazily, not by a
   background worker

No worker/scheduler/Kafka-consumer infrastructure exists anywhere in
this codebase yet (confirmed: nothing in `main.py`, no queue, no cron).
`database-design.md` §10.1 only requires "The application must enforce
the 20-second expiration" — it doesn't mandate a specific mechanism, and
this is an engineering choice, not a business one
(implementation-readiness.md §75).

Chosen mechanism: every code path that reads or acts on a `PENDING`
offer — `GET /api/v1/drivers/me/ride-offers`, `POST .../reject`, and
ride creation's own initial dispatch — first checks
`expires_at < now()` and, if expired, transitions that offer to
`EXPIRED` and advances to the next eligible driver (creating a new
offer) before doing anything else. This means a ride can sit with an
expired-but-not-yet-observed offer for longer than 20 seconds if nothing
polls it, which is an accepted limitation of this approach, not a
silent violation of BR-027's 20-second timer — the timer is enforced
relative to whenever the offer is next evaluated, and no driver can ever
successfully accept or have accepted-on-their-behalf an expired offer.
A future task may replace this with a real background sweep once worker
infrastructure exists (implementation-readiness.md §48); this decision
does not preclude that.

4. Decision 3 — Accept Offer / Ride ACCEPTED is out of scope for Task 3.2

`state-machines.md` §5's required conditions for `SEARCHING → ACCEPTED`
include "Required platform fee secured," and
`technical-architecture.md` §18's Accept-Ride Transaction debits a
wallet row that doesn't exist yet (Wallet is Phase 5). Task 3.2 ends at
a driver receiving, and being able to reject or let expire, a ride
offer — never at assignment. `matching.ride_offers.status` never
reaches `ACCEPTED` in this task's code; `PENDING → REJECTED` and
`PENDING → EXPIRED` are the only transitions implemented.
`POST /api/v1/drivers/me/ride-offers/{offer_id}/accept` is not
implemented at all in this task — calling it returns 404, same as any
undefined route, rather than a stubbed/partial implementation of a
financial operation ADR-0010's own precedent (never stub wallet debits)
argues against. This is a genuine, explicit task-boundary, not an
oversight — the next task depends on Wallet (Phase 5) being sequenced
first or alongside it, per roadmap.md's own dependency note for Phase 3.

5. Decision 4 — `GET .../ride-offers`, Reject Offer, and Driver Location
   Update response shapes

None of these three endpoints has a documented request/response JSON
example in api-contracts.md (unlike Create Ride / Accept Offer, which
do) — an under-specification gap, the same kind ADR-0007 flagged for
vehicle documents. This task fills all three in, following the same
envelope shape (`{"data": ..., "error": null, "request_id": ...}`)
every other endpoint in this codebase already uses. Driver Location
Update's response is a minimal `{"status": "OK"}` (api-contracts.md
§15); the two below:

    GET /api/v1/drivers/me/ride-offers
    {"data": {"offers": [{"offer_id", "ride_id", "status",
      "expires_at", "pickup": {"latitude","longitude"}}]}, ...}

    POST /api/v1/drivers/me/ride-offers/{offer_id}/reject
    {"data": {"offer_id", "status": "REJECTED"}, ...}

`api-contracts.md` §16 is updated with these shapes.

Item 5 — NO_DRIVER conflict: still not resolved here

Carried forward unchanged from ADR-0010 Item 6. Task 3.2's "expire →
next eligible driver" flow (BR-030) always finds either a next driver
(new `PENDING` offer) or exhausts the eligible-driver list — the latter
case is exactly where the documented `NO_DRIVER` state
(`domain-design.md` §9.3, `technical-architecture.md` §12) vs. its
absence from the authoritative `state-machines.md` §3.1 matters most.
Task 3.2 does not introduce a `NO_DRIVER` ride status and does not
implement BR-031's "no driver accepts → Retry/Increase Fare" customer
flow — when the eligible-driver list is exhausted, the ride simply stays
`SEARCHING` with no `PENDING` offer outstanding (a legitimate, already-
representable state: `SEARCHING` with zero active `matching.ride_offers`
rows). Whichever future task implements BR-031 must resolve the
NO_DRIVER conflict; this task does not pick a side for it.

6. Consequences — documents updated alongside this ADR

- `database-design.md` §9.1: `ride.rides` gains
  `requested_vehicle_category VARCHAR(20) NOT NULL`.
- `api-contracts.md` §12: the `vehicle_category` note is updated —
  Task 3.2 now persists it (superseding ADR-0010 §8's "not persisted by
  Task 3.1" language, which remains historically accurate for Task 3.1
  itself).
- `api-contracts.md` §16: Get Current Offers and Reject Offer response
  shapes added (Decision 4); a note documenting the lazy expiry
  mechanism (Decision 2) and that Accept Offer is not implemented by
  this task (Decision 3).
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, or `state-machines.md` — none of the decisions
  above require it. `event-contracts.md` §11's `matching.offer_created`/
  `offer_rejected`/`offer_expired` events remain the documented target
  shape for whenever Kafka publishing is actually wired up; Task 3.2
  does not publish them (no outbox/Kafka producer infrastructure exists
  yet — same reasoning as ADR-0010 Decision 3).
