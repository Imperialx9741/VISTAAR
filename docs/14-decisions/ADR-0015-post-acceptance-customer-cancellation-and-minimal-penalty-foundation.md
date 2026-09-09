ADR-0015 — Post-Acceptance Customer Cancellation (ACCEPTED/ARRIVED) and
Minimal Penalty Foundation

Status: Accepted
Note (2026-09-04, ADR-0069): §3 and §6's references to a 30-day
`expires_at`/EXPIRED penalty status are superseded — BR-049 was
corrected: customer penalties never expire, `expires_at` was dropped
from the schema, and `EXPIRED` is no longer a valid `PenaltyStatus`
value. Every other decision in this ADR (penalty record created even
for the free ₹0 cancellation, fee-refund-from-original-transaction,
the standalone `penalty` module) is unaffected. See ADR-0069.
Date recorded: 2026-08-23
Deciders: Approved under the owner's phase-level autonomy grant (VISTAAR
session, 2026-08-23) — the owner authorized continuous implementation
within a roadmap phase without a per-task plan/approval pause, while
"mandatory stop conditions" (roadmap §0.3 — genuine TBD values, missing
providers/credentials) still force a stop. This ADR follows the same
"flag before implementing" governance ADR-0010 through ADR-0014 used
for every prior task (implementation-readiness.md §74) — the owner's
autonomy grant changes who reviews the plan and when, not whether
flagged ambiguities get resolved via an ADR before code is written.

1. Context

Task 3.4 (Accept Offer) made ACCEPTED a reachable ride state. ADR-0012
(Task 3.3) deliberately left ACCEPTED/ARRIVED → CANCELLED unimplemented,
since it needs a driver to actually be assigned first. That precondition
now holds. state-machines.md §11/§12, business-rules.md §15
(BR-046–049), and technical-architecture.md §34 together fully specify
the customer-cancellation-after-acceptance rules — none of the values
this task needs are TBD. What's missing is a place to persist a
cancellation charge (`penalty.penalties`, database-design.md §26.1 /
technical-architecture.md §33 — documented, not yet built) and a wallet
credit primitive (only `debit()` exists — Minimal Wallet Foundation,
ADR-0013).

technical-architecture.md §69's recommended build order puts
Cancellation/Penalty after Payment (Phase 5, not yet built). This task
pulls forward only the minimum Penalty foundation needed to make
post-acceptance customer cancellation work — the same "minimal X
foundation" pattern ADR-0013 established for Wallet — not the full
Cancellation & Penalty domain (5.12: also owns driver cancellation
penalties, no-show charges, and penalty expiry/collection, none of
which this task builds).

2. Decision 1 — A grace-period cancellation does not create a penalty
   record and does not count toward the qualifying-cancellation counter

state-machines.md §12 lists "Within 2-minute grace → ₹0" and "First
qualifying cancellation → ₹0" as two separate branches, not one —
implying the grace-period case is evaluated and resolved *before* the
qualifying-cancellation history is even considered, not as its own kind
of "qualifying" event. Treating a grace-period cancellation as consuming
the customer's one free qualifying slot would be counter-intuitive (a
customer who changes their mind within 2 minutes is not the behavior
BR-047/048's "qualifying cancellation" progression is meant to
penalize-on-repeat) and no document states otherwise. No `penalty.
penalties` row is created for a grace-period cancellation; the
qualifying-cancellation count used to decide "first" vs. "second+" is
the count of *existing* `penalty.penalties` rows with
`penalty_type = 'CUSTOMER_CANCELLATION'` for this customer, which a
grace-period cancellation never adds to.

3. Decision 2 — A penalty record is created for the free first
   qualifying cancellation too (amount 0, status SETTLED)

BR-047 says the first qualifying cancellation's penalty is ₹0 — not
that no record exists. A record is required precisely so the *second*
qualifying cancellation can determine it isn't the first. The row is
created with `amount = 0` and `status = 'SETTLED'` (nothing owed, so
immediately settled) rather than inventing a fourth status value beyond
the three the schema documents (`OUTSTANDING`, `SETTLED`, `EXPIRED` —
database-design.md §26.1's default and its partial index on
`status = 'OUTSTANDING'`). state-machines.md §12's "Event: penalty.
applied, only when a penalty actually exists" is read as governing
*event publication*, not row creation — moot either way, since no
Kafka producer infrastructure exists yet (same gap every prior task has
left; see modules/ride, modules/matching, modules/wallet's own
docstrings).

4. Decision 3 — The driver's platform-fee refund amount is read from
   the original debit transaction, not re-derived from BR-011

BR-046: "The driver's platform fee is refunded when the customer
cancels" — for *every* post-acceptance cancellation (grace, first, or
second+ qualifying alike; only the customer's own charge differs
between these three). The refunded amount is looked up from the
specific `wallet.transactions` row this ride's original `PLATFORM_FEE`
debit produced (a new `WalletRepository.get_debit_for_ride()` query),
not re-computed from `_PLATFORM_FEE_BY_CATEGORY` (modules/matching/
router.py) a second time. This is strictly more correct if that
constant is ever changed later — the refund must always match what was
actually taken, not what the current rule says the fee would be today —
and it is the natural reading of "refunded," which describes reversing
a specific transaction, not recomputing a fee.

`WalletService.credit()` is added (mirrors `debit()` — row-locked,
idempotent on a caller-supplied key, immutable ledger entry — but with
no insufficient-balance concern, since crediting can never make the
balance invalid). The refund's idempotency key is deterministic
(`ride:{ride_id}:platform-fee-reversal`), and `reference_type`/
`reference_id` on the new `FEE_REVERSAL` ledger row point back at the
original `PLATFORM_FEE` transaction's id — an explicit audit link,
using the two nullable columns `wallet.transactions` already has for
exactly this purpose (database-design.md §17.2).

5. Decision 4 — New `penalty` module, not folded into `wallet` or `ride`

technical-architecture.md §5.12 documents Cancellation & Penalty as its
own bounded domain. `wallet` stays financial-primitive-only (debit/
credit a balance, immutable ledger) with zero dependency on ride/
matching, exactly as ADR-0013 established; `penalty.penalties` is a
distinct concern (a pending charge record with its own expiry/status
lifecycle, not a wallet balance movement — the customer has no wallet
in this system at all, only drivers do, per database-design.md §17).
A new `modules/penalty/` is added, mirroring every other module's
domain/ports/models/repositories/service layering, composed at
`modules/ride/router.py`'s cancel endpoint the same one-directional way
`modules/ride` already composes `modules.matching`.

6. Item 5 — Explicitly out of scope (not this task's decision)

- How an `OUTSTANDING` `penalty.penalties` charge is ever actually
  collected from the customer (a future wallet-recharge-style flow, a
  deduction from a future ride, or something else — undocumented
  anywhere; not invented here).
- `penalty.strikes` and driver-cancellation penalties — a separate task
  (Driver Cancellation, `POST /api/v1/rides/{ride_id}/driver-cancel`),
  its own ADR.
- No-show charges, penalty expiry background processing (BR-049's
  30-day expiry is stamped onto `expires_at` at creation time; nothing
  yet reads or acts on an expired-but-unsettled row — same "lazy
  evaluation, no background worker" gap this codebase has left
  everywhere a scheduled job would otherwise be needed, e.g. ADR-0011
  Decision 2 for offer expiry).
- BR-069/BR-119's "repeated abuse → warning → temporary suspension"
  escalation — thresholds are explicitly TBD (business-rules.md §20);
  not built.

7. Consequences — documents updated alongside this ADR

- `api-contracts.md` §19 annotated with the current implementation
  status.
- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: this task marked
  complete once implemented and verified.
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `database-design.md` —
  `penalty.penalties` is implemented exactly as already documented;
  none of the decisions above required a schema or business-rule
  change.
