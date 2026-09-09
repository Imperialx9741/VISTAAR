ADR-0062 — Sarthi Unpaid Cancellation-Penalty Recovery From Next Wallet Recharge

Status: Accepted — owner decision, delivered via clarifying questions
after the owner's own "Keep unchanged" wording didn't match the real
running code (verified against it directly, not assumed), 2026-09-03.
Implemented the same day.
Date recorded: 2026-09-03
Deciders: Project owner (explicit written decision, in response to a
clarifying question this session asked before implementing anything).

1. Decision

Resolves the oldest open item in
`docs/02-business/known-functional-gaps-2026-09-02.md` §1: what happens
when a Sarthi (driver) cancels an ACCEPTED ride but their wallet balance
can't cover the ₹30 driver-cancellation penalty (BR-011's
`_DRIVER_CANCELLATION_PENALTY`).

1. The cancellation is **never blocked** by an insufficient balance —
   the ride transitions to CANCELLED and the driver strike is recorded
   exactly as it would with a sufficient balance.
2. If the balance covers the penalty, it's debited normally — no
   behavior change from before.
3. If it doesn't, **no partial deduction happens** — the wallet balance
   is left completely untouched, and the full ₹30 becomes a tracked
   `wallet.wallets.outstanding_debt`.
4. The debt is recovered automatically from the driver's **next
   WALLET_RECHARGE credit** — the recharge pays down the debt first (up
   to the full recharge amount), and only any remainder is credited to
   the spendable balance. Not scoped to any other credit type (a bonus
   or fee-reversal credit never triggers this).
5. An outstanding debt does **not**, by itself, block ride acceptance —
   that remains governed solely by the pre-existing ₹20 low-balance
   grace-ride rule (ADR-0058), completely independent of this debt
   concept. A driver with debt but ≥₹20 available balance can keep
   accepting rides normally.

2. Why a clarifying question was asked before building this

The owner's original instruction described this as something to "keep
unchanged." Checked directly against the real running code and this
session's own earlier E2E findings
(`docs/10-testing/e2e-findings-2026-09-02.md` §2.3): that was not
accurate. The actual behavior was the opposite — `WalletService.debit()`
raised `InsufficientWalletBalanceError` outright, and
`driver_cancel_ride()`'s single `try` block caught it as a
`WalletDomainError` and rolled back the *entire* cancellation, including
the ride-status transition that had already happened moments earlier in
the same call. A driver with an insufficient balance could not cancel a
ride at all before this ADR. Rather than silently build against the
owner's description or silently build against the old code's real
behavior, this was flagged back to the owner directly — the answer
above is their explicit confirmation of the intended new behavior, not
an assumption.

3. Design

`wallet.wallets` gains one new column,
`outstanding_debt NUMERIC(12,2) NOT NULL DEFAULT 0` (migration
`f2a9c6e18b3d`, `CHECK (outstanding_debt >= 0)`) — deliberately a
separate field from `balance`, not folded into it, so "what a driver
can actually spend" and "what a driver owes VISTAAR from a past
cancellation" are never conflated in the same number.

**Incurring the debt** — `WalletService.debit_or_record_as_debt()`
(new method, used only by `modules/ride/router.py`'s
`driver_cancel_ride()`; every other debit in this codebase — the
accept-offer platform fee in particular — still goes through the
existing `debit()`, unchanged, and still hard-fails on insufficient
balance, since that must never silently become a debt):

- Balance covers the amount: debits normally, identical to `debit()`.
- Balance doesn't: debits nothing, adds the full amount to
  `outstanding_debt`. Still creates a real `WalletTransaction` row
  (`transaction_type: DRIVER_PENALTY`, `direction: DEBIT`,
  `balance_before == balance_after` since nothing was actually paid,
  `metadata: {"outstanding_debt_incurred": "30.00", "reason":
  "insufficient_balance_at_cancellation"}`) — this is what makes the
  existing `idempotency_key` UNIQUE-constraint guarantee protect a
  retried cancellation request from double-incurring the debt, the same
  mechanism every other wallet write in this codebase already relies
  on. No new idempotency mechanism was invented for this.

**Recovering the debt** — `WalletService.credit()` (extended, not a new
method): when `transaction_type == WALLET_RECHARGE` and the wallet has
`outstanding_debt > 0`, the recharge amount is split —
`debt_recovered = min(recharge_amount, outstanding_debt)` reduces the
debt, and only `recharge_amount - debt_recovered` is credited to
`balance`. This is recorded as a **single** ledger row, not two:
`amount` always holds the full amount actually verified/paid (audit-
accurate against the payment gateway's own record — see ADR-0060),
while `balance_after` reflects only what actually landed in the
spendable balance. When the two differ,
`metadata.outstanding_debt_recovered`/`outstanding_debt_remaining`
explain exactly why in the same row — the one place in this codebase
where a transaction's `amount` doesn't equal its own balance delta, and
deliberately marked as such rather than left silently inconsistent.

4. Independence from the ₹20 low-balance rule (ADR-0058)

Confirmed explicitly with the owner: the two mechanisms never interact.
`enforce_low_balance_policy()` (accept-offer's gate) reads only
`wallet.balance` against `LOW_BALANCE_THRESHOLD` — it has no awareness
of `outstanding_debt` at all, and this ADR does not add any. A driver
who owes ₹30 in debt but has ₹25 in spendable balance can still accept
rides normally (₹25 > ₹20 threshold); a driver who owes nothing but has
₹15 in balance is still blocked by the existing low-balance rule exactly
as before. Neither rule was weakened or strengthened by the other's
existence.

5. API surface

`GET /api/v1/drivers/me/wallet` — `outstanding_debt` added to the
response (always `0` before this ADR could ever produce a nonzero
value; genuinely real now, unlike `outstanding_settlement`, a
permanently-`0` superseded ADR-0025 concept the same response already
carries).

`POST /api/v1/drivers/me/wallet/recharge/confirm` — `debt_recovered`/
`outstanding_debt_remaining` added to the response, present only when a
debt was actually paid down by this recharge, so a driver isn't left
guessing why their credited balance is less than what they just paid.

6. Testing

Backend: 8 new `WalletService` unit tests (`tests/test_wallet_service.py`
— fake repository) covering both branches of
`debit_or_record_as_debt()` (normal debit vs. debt-only), its
idempotency guarantee on the debt-only branch specifically, its
independence from the low-balance grace flag, and `credit()`'s debt-
recovery arithmetic (full recovery, partial recovery when the recharge
is smaller than the debt, non-WALLET_RECHARGE credits never triggering
recovery, and a plain recharge with no debt behaving exactly as
before). 2 real-HTTP/real-Postgres E2E tests rewritten in
`tests/test_e2e_wallet_penalty_journey.py`: the test that used to assert
the old (blocking) behavior on purpose now asserts the cancellation
succeeds with the debt recorded; a second test exercises the full real
journey end to end — cancel with insufficient balance, then recharge
through the real `POST /recharge` + `/recharge/confirm` HTTP endpoints
(Razorpay TEST-mode gateway faked, matching
`tests/test_wallet_recharge_api.py`'s own convention) — confirming the
debt is recovered first and the response correctly reports both the
recovered amount and the final spendable balance. Full backend suite:
1368 passed, 5 skipped, 0 failed (was 1360), ruff/mypy clean.

7. What this ADR does not do

- Does not touch the ₹20 low-balance rule (ADR-0058) — confirmed
  independent, per §4 above.
- Does not touch the customer outstanding-penalty display (ADR-0059) or
  its collection mechanism (still genuinely undecided, ADR-0026 §5) —
  the owner explicitly confirmed that stays a Customer→VISTAAR display-
  only concept, unrelated to this ADR's Sarthi-side debt.
- Does not change the P2P ride-fare model, Razorpay's TEST-only status,
  or any other business rule not named in this document.
- Does not add a new notification for debt being incurred or recovered
  — not requested; the driver can see `outstanding_debt` on the wallet
  screen and `debt_recovered` in the recharge confirmation response, but
  no push/SMS was invented for this event.
