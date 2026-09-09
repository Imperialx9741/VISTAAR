ADR-0016 — Driver Cancellation Scope and Open Items

Status: Decision 1 Accepted. Item 2 explicitly deferred, not decided
here.
Date recorded: 2026-08-24
Deciders: Approved under the owner's phase-level autonomy grant (VISTAAR
session, 2026-08-24) — mandatory stop conditions (roadmap §0.3) still
apply; this ADR exists because one was triggered (a contradiction
between two authoritative documents) and is being flagged, not guessed
past.

1. Context

Task 3.6 (Driver Cancellation, `POST /api/v1/rides/{ride_id}/driver-
cancel`, api-contracts.md §20) is the second half of Phase 04's
remaining work, alongside Task 3.5 (ADR-0015). BR-067-069
(business-rules.md §20) and state-machines.md §13 together specify most
of what's needed: a normal driver cancellation costs a ₹30 wallet
penalty (BR-067) and records a behavioral strike (BR-068), and the
changed-pickup-pass reason (BR-071) is exempt from both.

2. Decision 1 — Implement exactly the documented ACCEPTED → CANCELLED
   transition; do not build BR-070's automatic rematch

state-machines.md §13 documents driver cancellation's transition as
"ACCEPTED → CANCELLED" — literally the same terminal ride state
customer cancellation produces, not a special "return to SEARCHING"
state. BR-070 separately says: "Driver cancellation → ₹30 penalty →
Driver removed from booking → VISTAAR searches next nearest eligible
driver. The customer does not need to create a new booking."

These two statements are not obviously reconcilable from the documents
alone. Two readings are both plausible: (a) the existing ride resets to
SEARCHING with driver_id/vehicle_id cleared and a new offer dispatched
against the same ride.rides row, or (b) the ride is genuinely CANCELLED
(matching state-machines.md §13's literal transition) and the system
transparently creates a brand-new ride row with the same trip details
and dispatches matching for it — satisfying "customer does not need to
create a new booking" without contradicting the documented state
transition. Nothing in domain-design.md, database-design.md, or
event-contracts.md describes a "resurrect a CANCELLED ride" pattern, and
no event (e.g. a `ride.rebooked`) documents option (b) either.

This is a genuine product/business-rule ambiguity (roadmap §0.3) — not
a values-are-TBD gap this ADR can safely resolve on engineering
judgment alone, the way ADR-0014's fee-source/vehicle-source decisions
were. This task implements only the literal, unambiguous part: the
ACCEPTED → CANCELLED transition itself, the ₹30 wallet penalty, the
strike, and the changed-pickup-pass exemption. BR-070's automatic-
rematch/no-new-booking behavior is explicitly NOT built.

3. Decision 2 — Insufficient wallet balance blocks the cancellation,
   same as it blocks acceptance

`wallet.wallets.balance`'s CHECK (balance >= 0) constraint means
`WalletService.debit()` cannot silently let the ₹30 penalty push a
driver's balance negative — no document says what should happen if a
driver cancels without ₹30 available. This mirrors BR-018 ("zero wallet
balance... cannot accept a ride requiring a platform fee... must
recharge") and ADR-0014's Accept Offer precedent (`InsufficientWalletBalanceError`
blocks the action, 409): a driver cancellation is refused with
`INSUFFICIENT_WALLET_BALANCE` if their wallet cannot cover the ₹30
penalty, rather than the ride being left half-cancelled or the penalty
silently waived. The changed-pickup-pass exemption (BR-071, Decision 1
above) is unaffected — that path never calls `debit()` at all.

4. Item 2 — BR-070's automatic rematch: deferred, not decided

Whether a driver-cancelled ride should reset to SEARCHING or be replaced
by a transparently-created new ride is a product decision, not an
engineering one — it changes what `ride.state_history` records, what a
future `ride.cancelled`/`ride.rebooked` event would carry, and whether
customer-facing ride tracking treats it as "still the same ride" or
"a new ride, same trip." Recorded here as an open item for a future
task; the driver-cancel endpoint returns a normal CANCELLED response
with no rematch dispatch until this is resolved.

5. Consequences — documents updated alongside this ADR

- `api-contracts.md` §20 annotated with the current implementation
  status and this open item.
- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: this task marked
  complete for the scope actually built, with the deferred item listed.
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `database-design.md` —
  the implemented scope matches state-machines.md §13 exactly; the
  deferred item is a genuine gap between two documents, not something
  this ADR resolves by editing either one.
