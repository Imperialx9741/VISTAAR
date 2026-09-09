ADR-0058 — Sarthi Wallet Low-Balance Ride-Acceptance Rule

Status: Accepted — owner decision, delivered directly with an explicit
implementation directive ("VISTAAR — Consolidated Decisions, Remaining
Implementation & Integration Instructions"), 2026-09-02. Implemented the
same day.
Date recorded: 2026-09-02
Deciders: Project owner (explicit written decision).

1. Decision

When a Sarthi (driver)'s wallet balance is at or below ₹20:

1. The Sarthi is notified that their wallet balance is low and a
   recharge is required.
2. The Sarthi may accept exactly one more ride while in this state (the
   "grace ride").
3. After that one ride's acceptance, the Sarthi cannot accept another
   ride until the wallet balance is recharged back above ₹20.
4. No partial-debit mechanism is introduced — every wallet debit still
   either fully succeeds or fully fails, unchanged.
5. No new outstanding-balance/liability concept is introduced — this is
   a pure accept/reject gate on top of the existing balance, not a new
   ledger concept.

This is deliberately independent of, and layered on top of, the
pre-existing `InsufficientWalletBalanceError` check
(`WalletService.debit()`, BR-012) — that check still runs exactly as
before, for the specific platform fee a ride's acceptance would debit;
this rule adds an earlier, coarser gate that can block an acceptance
even when the fee itself would technically still fit.

2. Context

Related to, but distinct from, a blocker documented at the time this
ADR was written and later resolved separately
(`docs/02-business/known-functional-gaps-2026-09-02.md` §1, ADR-0062,
2026-09-03): a driver whose wallet balance is insufficient to cover the
₹30 driver-*cancellation* penalty could not cancel a ride at all. That
blocker was about the *cancellation* path, a different code path from
this ADR's own scope (`modules/matching/router.py`'s accept-offer
endpoint, ride-*acceptance* eligibility) — this ADR explicitly ruled out
a "partial debit + outstanding balance" design for *acceptance*
eligibility specifically, in favor of a simpler yes/no gate; ADR-0062
later built exactly that kind of outstanding-debt concept, but scoped
only to the cancellation-penalty debit, confirmed independent of this
ADR's own low-balance rule (ADR-0062 §4). The two remain separate
mechanisms today, not merged.

3. Enforcement point

`modules/matching/router.py`'s `accept_offer_endpoint()`, specifically
the wallet-row lock step (`technical-architecture.md` §18's Accept-Ride
Transaction, step 1) — already present before this ADR purely for its
row-lock side effect (`WalletService.get_wallet()`), now replaced with
`WalletService.enforce_low_balance_policy()`, which locks the row *and*
enforces this rule, raising a new `WalletRechargeRequiredError`
(`WALLET_RECHARGE_REQUIRED`, HTTP 409) before any offer/ride state
change if the driver is blocked. The pre-existing platform-fee debit
(and its own `InsufficientWalletBalanceError` check) runs unchanged,
immediately after.

4. Data model

One new column, `wallet.wallets.low_balance_grace_ride_used` (boolean,
default `false`, migration `d4e8f1a52c6b`) — tracks whether the current
"low balance window" has already consumed its one grace ride. Reset to
`false` by `WalletService.credit()` whenever a credit crosses the
balance back above ₹20 (keyed off the resulting balance, not the
credit's `transaction_type` — a recharge, a fee reversal, or a bonus
that happens to cross the threshold all have the same effect, since the
rule is about the balance level itself).

`LOW_BALANCE_THRESHOLD = Decimal("20")` is defined in
`modules/wallet/domain/entities.py`, the same "engineering constant,
not a configurable business value requiring its own settings-table
entry" treatment `_DRIVER_CANCELLATION_PENALTY`/`_PLATFORM_FEE_BY_CATEGORY`
already get elsewhere in this codebase — reasonable for a first
implementation; revisit if this ever needs to be admin-configurable.

5. Notification

A new SMS/IN_APP template, `WALLET_LOW_BALANCE`
(`modules/notification/domain/templates.py`), sent via the existing
`NotificationService` (`Channel.IN_APP`, same best-effort,
never-blocks-the-response pattern the pre-existing `RIDE_ACCEPTED`
notification in the same endpoint already uses). Fires exactly once per
threshold crossing — the moment a platform-fee debit brings the balance
from above ₹20 to at-or-below it — computed from that debit's own
`WalletTransaction.balance_before`/`balance_after`, not on every
subsequent debit while already low.

Scoped specifically to the accept-offer platform-fee debit, not
extended to the driver-cancellation penalty debit (`ride/router.py`) or
any other wallet debit — the owner's instruction described one cohesive
rule tied to ride-acceptance eligibility, and extending the notification
trigger elsewhere risked conflating this rule with the separate,
still-pending cancellation blocker (§2 above).

6. Mobile

The generic error-message display `RideOfferScreen` already had
(`ApiException.message`) surfaces `WALLET_RECHARGE_REQUIRED` correctly
with no code change required. Added: a low-balance warning SnackBar
shown immediately after a successful Accept whose returned
`wallet_balance` is at or below ₹20 — chosen over waiting on the
backend's IN_APP notification because this app has no notification-
inbox screen at all yet, for any existing notification type (not a gap
this rule introduces). A "Recharge Wallet" action from this warning, and
from the `WALLET_RECHARGE_REQUIRED` error state, is deferred to the
Razorpay wallet-recharge work (this same instruction batch's item 3) —
wiring a call-to-action toward a screen that doesn't exist yet would be
premature.

7. Testing

Backend: 8 new `WalletService` unit tests (`tests/test_wallet_service.py`
— fake-repository, no real Postgres) covering the threshold boundary,
grace consumption, blocking, the no-partial-debit invariant, and the
credit-side reset in all three relevant states (crosses back above,
stays at/below, was never used). 5 new real-HTTP/real-Postgres
integration tests (`tests/test_matching_api.py`) covering the full
accept-offer flow end to end, including the specific case that
distinguishes this rule from plain insufficient-balance (blocked with a
balance well above the platform fee), the notification firing/not-
firing on crossing vs. already-low, and a real recharge (via
`WalletService.credit()`) unblocking a subsequent accept. Full backend
suite: 1309 passed, 5 skipped, 0 failed (was 1296), ruff/mypy clean.

One real bug was caught by the integration tests, not assumed away: the
new `WALLET_RECHARGE_REQUIRED` error code was not registered in
`shared/api_envelope.py`'s `_ERROR_CODE_HTTP_STATUS` table, so it fell
back to the generic `400` default instead of the intended `409` — fixed
by adding the mapping (matching `INSUFFICIENT_WALLET_BALANCE`'s
existing `409`).

Mobile: 2 new widget tests (`test/features/rides/ride_offer_screen_test.dart`)
covering the low-balance warning appearing/not appearing based on the
returned `wallet_balance`. Full suite: 130/130 passed (was 128),
`flutter analyze` clean.

8. What this ADR does not do

- Does not touch the separate, still-pending driver-cancellation
  insufficient-balance blocker (§2) — left completely unchanged, per
  explicit instruction, pending its own owner decision.
- Does not make `LOW_BALANCE_THRESHOLD` admin-configurable.
- Does not build a "Recharge Wallet" mobile entry point — that arrives
  with the Razorpay wallet-recharge work.
- Does not add a general in-app notification inbox — the mobile warning
  here is a targeted, narrow addition, not a new platform capability.
