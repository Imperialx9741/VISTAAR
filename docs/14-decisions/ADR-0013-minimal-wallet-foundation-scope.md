ADR-0013 — Minimal Wallet Foundation Scope and Open Items

Status: Decisions 1–2 Accepted. Items 3–5 explicitly out of scope, not
decided here.
Date recorded: 2026-08-23
Deciders: Approved via the "Minimal Wallet Foundation" planning and
decision-resolution exchange, following the same "flag before
implementing" governance ADR-0010 through ADR-0012 used for every prior
task (implementation-readiness.md §74).

1. Context

The next ride task (Accept Offer / Ride ACCEPTED) is blocked:
state-machines.md §5 requires "Required platform fee secured" to enter
`ACCEPTED`, and technical-architecture.md §18's atomic accept transaction
debits a wallet row that doesn't exist in this codebase yet. Per
docs/VISTAAR_IMPLEMENTATION_ROADMAP.md §2.0 ("Actual next engineering
dependency"), the correct response is to pull forward only the minimum
Wallet foundation needed to make offer acceptance atomic and safe — not
the entire Phase 11 (Financial) module. This ADR records the scope
boundary and two implementation-shape decisions that boundary required.

2. Decision 1 — `WalletService.debit()` is an in-process method, not a
   literal `POST /internal/wallet/debit` HTTP endpoint

api-contracts.md §55–57 documents wallet debit/credit as `POST /internal/
wallet/debit` and `POST /internal/wallet/credit`, described as "internal
service APIs" requiring "service authentication." No such internal-
service-authentication concept exists anywhere in this codebase, and
every other cross-module composition built so far (ride → matching,
driver → vehicle, ride → matching's rematch composition) is a plain
in-process Python service call at the router/composition layer, matching
implementation-readiness.md §45–47's explicit "modular monolith first"
guidance (roadmap.md §46: reduces network complexity, distributed-
transaction problems, and deployment complexity while preserving domain
boundaries).

`WalletService.debit()` is implemented as an in-process method other
modules can call directly (the next task, Accept Offer, will call it
inside its own transaction, the same way modules/ride/router.py already
calls into modules.matching). §55–57 remain the documented target shape
for a future microservice extraction — not something this task builds
literally. If/when this backend is ever split into real services, that
extraction is the point at which `/internal/wallet/debit` would become a
real HTTP boundary with real service authentication; nothing in this
decision precludes that later.

3. Decision 2 — `GET /api/v1/drivers/me/wallet` is included

Not strictly required to unblock the next task (which only needs
`debit()`), but small, fully documented (api-contracts.md §34), safe
(read-only), and leaves the wallet unobservable to a driver if omitted.
Included as part of this task rather than deferred.

`outstanding_settlement` in the response is hard-coded to `0` — not a
placeholder standing in for an unknown value (contrast ADR-0010
Decision 1's `fare: null`), genuinely accurate: `wallet.
outstanding_settlements` doesn't exist yet (Decision 4 below), so
nothing can ever create one.

Item 3 — Recharge, credit paths, and `wallet.outstanding_settlements`/
`wallet.recharges`: explicitly out of scope

`POST /api/v1/drivers/me/wallet/recharge` (api-contracts.md §35) needs
the payment gateway, which is TBD (external service & credential plan) —
BR-016 requires "Payment must be successfully verified before the wallet
is credited," and no verification mechanism exists. No credit path is
implemented either (joining bonus BR-020/021, driver referral bonus
BR-022-024, advertisement payout, admin adjustment, fee/penalty
reversal) — none of it is needed to unblock the next task, and building
a `credit()` method now with nothing calling it would be speculative.
Tests seed a wallet balance directly via SQL to exercise `debit()`'s
success path instead — the same pattern already used throughout this
codebase to reach states no endpoint produces yet (e.g.
tests/test_driver_availability_api.py's `_mark_driver_document_
approved`). `wallet.outstanding_settlements` (database-design.md §18) and
`wallet.recharges` (§19) are not created by this task's migration.

Item 4 — The platform-fee *amount* lookup: not this task's decision

`debit()` takes `amount` as a caller-supplied parameter. Where the
Accept Offer task reads "the applicable platform fee" from (a hard-coded
constant reflecting the already-approved BR-011 table — Bike ₹10 / Auto
₹20 / Cab ₹20 — vs. a new server-side config table
technical-architecture.md §17 recommends but database-design.md doesn't
document) is that task's decision, not this one's.

Item 5 — `GET .../wallet/transactions` (ledger history): out of scope

Not needed to unblock the next task; `wallet.transactions` rows exist
and are queryable directly (e.g. by tests, or a future admin view) even
without this endpoint.

4. Consequences — documents updated alongside this ADR

- `api-contracts.md` §34 annotated with the current implementation
  status (this ADR) and confirmation `outstanding_settlement` is
  genuinely `0`, not a placeholder.
- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` §2.0/§34 updated: this task
  marked complete, next task is Task 3.4 — Accept Offer (no longer
  blocked on Wallet not existing — still has its own scope to plan,
  including Item 4 above).
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `database-design.md` —
  `wallet.wallets`/`wallet.transactions` are implemented exactly as
  already documented; none of the decisions above required a schema or
  business-rule change.
