ADR-0066 — Customer Outstanding Penalty Settlement via Driver Wallet

Status: Accepted and implemented (2026-09-03) — owner decision
("FINAL BUSINESS DECISIONS FOR REMAINING OPEN ITEMS", item 2)

Note (2026-09-04, ADR-0069): §8's "30-day expiry" reference below is
superseded — BR-049 was corrected the same day: customer penalties
never expire. Every mechanism this ADR actually builds (attach →
release-on-cancellation → settle-on-completion) is unaffected; only the
one sentence describing what happens to a penalty attached to a ride
that never completes or cancels is out of date. See ADR-0069.
Date recorded: 2026-09-03
Deciders: Project owner (explicit written decision).
Supersedes: ADR-0026's settlement mechanism (rules 2, 5, 8 — "VISTAAR
does not immediately collect... a separate VISTAAR charge... no new
payment gateway"). ADR-0026 rules 1, 3, 4, 6, 7, 9 are unchanged — see
§4 below for exactly what survives.

1. Context

ADR-0026 (2026-08-26) established that a customer's outstanding
cancellation/no-show penalty is shown at their next ride booking
(implemented as ADR-0059, 2026-09-02) but never resolved how it gets
*collected* — that was explicitly left open ("the actual payment
mechanism/provider for 'Customer → VISTAAR' penalty collection is
undocumented and unbuilt... a future ADR must select it"). The owner's
2026-09-03 instruction resolves it: rather than building a second
customer-facing payment flow (which would have needed a real provider
decision, same category of gap as driver wallet recharge), the
customer pays the combined fare-plus-penalty amount to the Sarthi
directly, and VISTAAR recovers its own share through the existing
driver-wallet-debit mechanism — the same shape the ride's own platform
fee already uses.

2. Decision

1. **Attach, don't just display.** `POST /api/v1/rides` (Create Ride)
   still shows `outstanding_penalty`/`total_payable` exactly as
   ADR-0059 built it, but now also durably attaches every OUTSTANDING,
   not-yet-attached penalty this customer has to the new ride
   (`penalty.penalties.settlement_ride_id`, a new column distinct from
   the existing `ride_id`, which stays the ride the penalty was
   originally *incurred* on). "The User's next applicable ride" is now
   a real, traceable relationship, not a live recomputation that could
   drift between booking and completion.
2. **Release on cancellation.** If that specific ride is cancelled
   before it completes (`POST .../cancel` or `.../driver-cancel`), the
   attachment releases back to unattached-OUTSTANDING, so the
   customer's next *actual* ride picks it up instead. A penalty must
   never be silently stranded on a ride that never happened.
3. **Settle on completion.** `POST .../complete` (Ride Completion) —
   once the ride genuinely reaches COMPLETED — marks every penalty
   attached to it SETTLED and debits the driver's wallet for the total,
   via `TransactionType.CASH_SETTLEMENT` and
   `WalletService.debit_or_record_as_debt()` (never blocks completion
   on insufficient balance — see §3).
4. Example, matching the owner's own worked case exactly: ride fare
   ₹200 + outstanding penalty ₹30 → the customer pays the Sarthi ₹230
   directly; the Sarthi's wallet is separately debited ₹30
   (CASH_SETTLEMENT) once the ride completes, recovering VISTAAR's
   share the same way the platform fee already does for the ride fare
   itself.
5. Auditable chain, exactly as instructed ("outstanding penalty →
   attached to ride → settlement → accounting entry"): `issued_at`
   (penalty created OUTSTANDING) → `settlement_ride_id` set (attached,
   at booking) → `status = SETTLED`/`settled_at` set (at completion) →
   a real `wallet.transactions` CASH_SETTLEMENT row referencing the
   same ride. Four distinct, dated, queryable steps, not one opaque
   flag.

3. Never blocks anything

Matching the owner's explicit "do not block" instructions elsewhere in
the same decision set:
- Attaching a penalty never blocks or fails ride creation — best-effort
  past the point of no return, same pattern
  `matching_service.dispatch_offer()` already uses at the same call
  site; a failure here just means the penalty isn't attached to this
  particular ride and a future one attaches it instead.
- Releasing on cancellation never blocks the cancellation itself —
  same best-effort pattern, run after the cancellation is already
  durably committed.
- Settling on completion never blocks completion, and the wallet debit
  it triggers never blocks it either: `debit_or_record_as_debt()`
  (ADR-0062's mechanism, reused here for a second purpose — see that
  method's own updated docstring) means a driver whose balance can't
  cover the settlement amount still has the ride complete normally,
  with the shortfall recorded in the same `wallet.wallets.
  outstanding_debt` bucket ADR-0062 already introduced, recovered from
  a future recharge exactly the same way. One outstanding-debt bucket
  per driver covers both an unpaid cancellation penalty and an unpaid
  customer-penalty settlement — not two separate mechanisms.

4. What survives from ADR-0026, unchanged

- Rule 1: a valid cancellation/no-show penalty still creates an
  OUTSTANDING liability exactly as `penalty.penalties`/
  `PenaltyStatus.OUTSTANDING` already worked (BR-047/048/052,
  ADR-0015).
- Rule 4: the ride fare itself is still P2P, Customer → Sarthi
  (ADR-0025) — this ADR does not touch fare collection, only how the
  *penalty* portion is recovered.
- Rule 6/7 (driver wallet debited only for VISTAAR's own charges, never
  the customer's ride fare): still true — CASH_SETTLEMENT debits
  exactly the penalty amount, never the fare.
- Rule 9: every already-approved wallet/debit/credit/penalty rule is
  preserved — this ADR adds a new *reason* for a wallet debit
  (CASH_SETTLEMENT), reusing the exact mechanism ADR-0062 already
  built, not inventing a new one.
- BR-047/048/052-057's penalty amounts, expiry, and qualification
  rules: entirely unchanged.

5. What changes from ADR-0026

- Rule 2 ("VISTAAR does not immediately collect... through a separate
  customer payment gateway"): still true in letter (no gateway is
  built), but the *spirit* changes — VISTAAR now collects its share
  automatically at ride completion, just through the driver's wallet
  rather than a customer-facing flow.
- Rule 5 ("the outstanding penalty is a separate VISTAAR charge:
  Customer → VISTAAR"): reversed. The customer never pays VISTAAR
  directly for this — they pay the Sarthi the combined amount, and
  VISTAAR recovers its share from the Sarthi's wallet instead.
- Rule 8 ("no new payment gateway is implemented"): still true, and
  now permanently so for this flow — no customer-facing penalty
  payment gateway will ever be needed, since the mechanism this ADR
  builds doesn't require one.
- ADR-0026 §5's "genuinely open" item (the collection provider/
  mechanism) is now closed — not by picking a provider, but by
  determining none is needed.

6. TransactionType.CASH_SETTLEMENT — dormant since ADR-0025, real again

`database-design.md` §17.2 already documented `CASH_SETTLEMENT` as
"concept superseded (ADR-0025)... modeled VISTAAR recovering its own
charge from cash the driver collected on its behalf... no longer a
scenario that can occur... reconsider whether this value is still
needed the next time wallet code is touched." That reconsideration is
this ADR: the exact scenario it was built for — the driver collecting
money on VISTAAR's behalf and VISTAAR recovering it via a wallet debit
— is real again, just for a different charge (the customer's
penalty, not the ride fare itself, which stays untouched per §4
above). No new `TransactionType` value was invented; the existing,
previously-dormant one is reused for real.

7. Verification

- Full backend test suite, `ruff`, `mypy` — see the completion report
  this ADR was delivered alongside for exact counts.
- Real migration round-trip (upgrade head → downgrade base → upgrade
  head) against a disposable Postgres container, confirming the new
  `penalty.penalties.settlement_ride_id` column's `upgrade()`/
  `downgrade()` both work cleanly.
- Real end-to-end HTTP test
  (`tests/test_ride_lifecycle_api.py::test_ride_completion_settles_carried_forward_penalty_and_debits_wallet`):
  a customer with a real ₹15 OUTSTANDING penalty (reached through two
  real cancellations, not a hand-crafted row) books a ride, the ride
  runs its full real lifecycle through HTTP (accept → arrived → start
  → complete), and completion settles the penalty and debits the
  driver's wallet by exactly ₹15 — confirmed against real Postgres rows
  in both `penalty.penalties` and `wallet.transactions`, not just the
  HTTP response.
- Real end-to-end HTTP test
  (`tests/test_ride_api.py::test_cancelling_a_ride_releases_its_attached_penalty_for_the_next_ride`):
  confirms the release-on-cancellation path for real — a penalty
  attached to a cancelled ride reappears as `outstanding_penalty` on
  the customer's next ride, backed by a real `settlement_ride_id`
  column change in Postgres.

8. What this ADR explicitly does not do

- Does not change any penalty amount, expiry, or qualification rule.
- Does not touch the ride fare's own P2P settlement (ADR-0025) —
  fare and penalty stay conceptually separate line items combined only
  in what the customer physically hands the Sarthi, never merged in
  the ledger.
- Does not handle the (currently already-existing, not newly
  introduced) gap of a ride that neither completes nor gets cancelled
  (e.g. an indefinitely SEARCHING ride with no matching driver) — a
  penalty attached to such a ride simply stays attached, indefinitely,
  with no automatic release (superseded 2026-09-04: BR-049 no longer
  has a 30-day expiry at all — see ADR-0069; the penalty remains
  OUTSTANDING and attached to this ride's `settlement_ride_id` until
  the ride is either cancelled, which releases it per §2 above, or
  completed, which settles it per §3, however long that takes).
- Does not add a retry mechanism if the wallet debit itself fails after
  the penalty is already marked SETTLED in the same transaction — both
  happen inside one atomic commit (see modules/ride/router.py's
  complete_ride()), so a failure rolls back both together, but a ride
  that already completed has no further trigger to retry settlement
  automatically; flagged as a known, low-probability gap, consistent
  with this codebase's existing treatment of other best-effort
  post-commit steps (e.g. a failed matching dispatch also has no
  automatic retry beyond the lazy-expiry-driven rematch path).
