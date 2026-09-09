ADR-0012 — Customer Ride Cancellation (Task 3.3) Scope and Open Items

Status: Decisions 1–2 Accepted. Item 3 (ACCEPTED/ARRIVED cancellation,
driver cancellation, BR-046–049's real penalty framework) explicitly out
of scope, not decided here.
Date recorded: 2026-08-22
Deciders: Approved via the "VISTAAR — Ride Booking / Task 3.3 — Customer
Ride Cancellation" planning and decision-resolution exchange, following
the same "flag before implementing" governance ADR-0010/ADR-0011 used for
Tasks 3.1/3.2 (implementation-readiness.md §74).

1. Context

Task 3.3 implements `POST /api/v1/rides/{ride_id}/cancel`
(api-contracts.md §19) for the only ride state currently reachable:
`SEARCHING` (Task 3.4, Accept Offer, remains blocked on the Wallet domain
— roadmap.md §2/§3 — so `ACCEPTED`/`ARRIVED` are never reached yet).

business-rules.md BR-046–049 and api-contracts.md §19's "Server
determines: 2-minute grace → no charge / First qualifying cancellation →
₹0 / Second+ → ₹15" logic is written without explicitly restricting
itself to post-acceptance cancellations, but every individual rule's
content presupposes one:

- BR-046: "After driver acceptance, the customer receives a 2-minute
  cancellation grace period... The driver's platform fee is refunded when
  the customer cancels." A `SEARCHING` cancellation has no driver, no
  acceptance timestamp to measure 2 minutes from, and no platform fee to
  refund (Task 3.2's matching offers never debit one — that only happens
  at Accept, which doesn't exist).
- BR-047/048: "The driver's platform fee is returned" (first) / "is
  refunded" (subsequent) — same precondition.

No document states whether a `SEARCHING` cancellation is simply exempt
from this framework, or whether it should still count toward the
"first"/"second+" counter for future cancellations even though it can
never itself carry the ₹15 charge (since nothing was ever committed to
protect against). This is exactly the kind of ambiguity
implementation-readiness.md §74 requires stopping for rather than
assuming silently.

Separately: the Penalty domain (`penalty` module, Phase 5) does not exist
in code — there is nowhere to persist a ₹15 charge record even if one
were judged to apply here, which independently would block treating a
`SEARCHING` cancellation as chargeable regardless of the interpretation
question above.

2. Decision 1 — `SEARCHING` cancellation is unconditionally free and not
   counted

A cancellation while a ride is still `SEARCHING` is treated as `₹0`,
unconditionally, and does **not** increment whatever counter a future
task uses to track "first vs. second+ qualifying cancellation." Rationale:
BR-046–049's entire framework exists to discourage customers from
repeatedly wasting an *already-assigned* driver's time and an
*already-debited* platform fee — neither exists for a `SEARCHING`
cancellation, so there is nothing here for the penalty to be protecting
against. This is the most literal reading of BR-046–049's own stated
preconditions, not an invented business rule; it will need to be recorded
in `business-rules.md` as an explicit clarification (see §5) since it
resolves a real silence in the source documents, not merely a technical
detail.

`POST /api/v1/rides/{ride_id}/cancel`'s response returns `"charge": null`
for this transition — not a `{amount: 0, ...}` object — since there is no
concept of a chargeable event to represent, and no `penalty` table exists
yet to have created one against. This mirrors ADR-0010 Decision 1's
`"fare": null` precedent: a documented field standing in for "not
applicable to what this task builds," not a computed zero.

3. Decision 2 — Cancelling a `SEARCHING` ride cancels its outstanding
   matching offer, if any

If a `matching.ride_offers` row is `PENDING` for the ride being
cancelled, it transitions to `CANCELLED` (database-design.md §10.1 — the
one documented offer status Task 3.2 left entirely unused). Composed at
`modules/ride/router.py`, calling into a new `modules.matching` method,
the same best-effort, separately-committed pattern already established
for ride → matching composition (ADR-0011): a failure to cancel the
offer must never fail or roll back the ride's own cancellation, since the
ride's `CANCELLED` status is the fact of record regardless.

`modules.ride` still does not import `modules.matching`'s domain/service
internals directly — only the composition at the router layer, unchanged
in shape from Task 3.2.

Item 3 — Everything else about ride cancellation: explicitly out of scope

`ACCEPTED`/`ARRIVED → CANCELLED` (state-machines.md §11), Driver
Cancellation (§13, BR-070/071, ₹30 penalty + strike + automatic
rematching), and BR-046–049's real ₹15-charge/2-minute-grace logic for a
post-acceptance cancellation are **not** implemented by this task. They
require Task 3.4 (Accept Offer) and the Penalty domain (Phase 5) to exist
first — see roadmap.md §3, Tasks 3.4/3.5. This ADR's Decision 1 resolves
only the `SEARCHING` case; it does not pre-decide how the real ₹15/₹30
framework will be interpreted once those states are reachable.

4. Consequences — documents updated alongside this ADR

- `api-contracts.md` §19: annotated with the current implementation
  status — `SEARCHING` cancellation only, `charge` always `null`,
  `ACCEPTED`/`ARRIVED` cancellation and the real 2-minute-grace/₹15 logic
  remain the documented target for Task 3.4/3.5+.
- `business-rules.md`: a clarifying note added near BR-046 recording
  Decision 1 (a `SEARCHING` cancellation is free and not counted) as the
  resolution of that document's own silence on the pre-acceptance case —
  not a new rule invented outside the source-of-truth chain
  (business-rules.md §44/§45).
- No content changed in `database-design.md`, `domain-design.md`,
  `event-contracts.md`, or `state-machines.md` — `ride.state_history`
  already has the columns this task needs (`reason`, `actor_type`,
  `actor_id`), and `matching.ride_offers.status` already documents
  `CANCELLED` as a valid value.
