"""VISTAAR Penalty module — Minimal Penalty Foundation.

Pulled forward from Phase 13's "5.12 Cancellation & Penalty Domain"
(technical-architecture.md) specifically to unblock post-acceptance
customer cancellation and driver cancellation (Phase 3 / Tasks 3.5-3.6)
— not the full Cancellation & Penalty domain. See
docs/14-decisions/ADR-0015-post-acceptance-customer-cancellation-and-
minimal-penalty-foundation.md for the full reasoning, following the same
"minimal X foundation, pulled forward" precedent ADR-0013 established
for Wallet.

Owns `penalty.penalties` and `penalty.strikes`, per
docs/04-database/database-design.md §26.

Implements no HTTP endpoint of its own — composed at
modules/ride/router.py's cancellation endpoints (record_customer_
cancellation()/record_driver_strike()) and, since Phase 16 (ADR-0023),
at modules/admin/router.py (search_penalties()/resolve_penalty(), the
documented `GET /api/v1/admin/penalties` / `POST .../resolve` routes) —
the same one-directional composition shape every other cross-module
call in this codebase uses.

This module deliberately does NOT implement:

- No-show charges (BR-050-052) — a different penalty_type this task
  doesn't need; not built until its own task exists.
- Penalty expiry — **not a gap, a deliberate non-feature (BR-049,
  corrected 2026-09-04, ADR-0069, owner decision): customer penalties
  in VISTAAR never expire.** A charge remains OUTSTANDING indefinitely
  until actually paid; there is no validity window, no `expires_at`
  column, and no expiry-enforcement job — none will ever be built for
  this. (Distinct from Sarthi cancellation-penalty debt,
  `wallet.wallets.outstanding_debt` — ADR-0062 — which has never had an
  expiry concept either; the two are separate mechanisms, see ADR-0069.)
- How an OUTSTANDING `penalty.penalties` charge is ever actually
  collected from the customer (a future wallet-recharge-style flow, a
  deduction from a future ride, or something else) — undocumented
  anywhere, not invented here (ADR-0015 Item 5).
- BR-069/BR-119's "repeated abuse → warning → temporary suspension"
  progressive-enforcement escalation — thresholds are explicitly TBD
  (business-rules.md §20); not built.
`penalty.applied`/`penalty.strike_recorded` ARE published now (Phase 3
/ Event & Outbox Foundation, ADR-0017) — composed at
modules/ride/router.py's cancellation endpoints (the same place
PenaltyService itself is composed), not inside this module. `penalty.
applied` is only published for a real (>0) charge — state-machines.md
§12's "Event: penalty.applied, only when a penalty actually exists"
(ADR-0015 §3) — even though the ₹0 first-qualifying case still gets a
`penalty.penalties` row.

What it does do:

- `PenaltyService.record_customer_cancellation()`: BR-047/048 — creates
  a `penalty.penalties` row for a post-acceptance customer cancellation
  that is NOT within the 2-minute grace period (the caller decides
  that; a grace-period cancellation never calls this at all — ADR-0015
  Decision 1). ₹0 for the first qualifying cancellation (created already
  SETTLED — ADR-0015 Decision 2), ₹15 from the second onward (created
  OUTSTANDING, remaining so indefinitely until paid — BR-049,
  corrected 2026-09-04). Idempotent
  per ride via `uq_penalties_ride_penalty_type` (migration
  383b55c70732) — a retried/racing call for the same ride returns the
  same row rather than creating a second one.
- `PenaltyService.record_driver_strike()`: BR-068 — records a behavioral
  strike for a driver cancellation, independent of and in addition to
  the ₹30 financial penalty (which is a plain `WalletService.debit()`
  call the caller makes separately — technical-architecture.md §36:
  "the penalty is processed through the Wallet domain," not through
  this module).
- `PenaltyService.search_penalties()`/`resolve_penalty()` (Phase 16,
  ADR-0023): admin-only Search/Resolve, composed at
  modules/admin/router.py. `resolve_penalty()` implements `ResolvePenalty`
  (domain-design.md §17.3) for the one documented `action: "WAIVE"` case
  — OUTSTANDING -> WAIVED (state-machines.md §40), row-locked, original
  `amount`/`issued_at` left untouched. The "reversal/waiver
  record" api-contracts.md §48 asks for is the `admin.audit_logs` row
  the router writes in the same transaction — no second table exists for
  this. `resolve_penalty()`'s `action: "WAIVE"` is ALSO how `DisputePenalty`
  (also §17.3) is decided in the customer's favor now (Phase 13,
  ADR-0029, 2026-08-25): the dispute itself is filed as an ordinary
  Support Case (modules/support/, `category: "PENALTY_DISPUTE"`,
  `ride_id` = the disputed penalty's own ride), not a command on this
  module — this module gained no new code for it, only
  modules/ride/router.py's cancellation response gained `charge.
  penalty_id` so the customer has something to reference. See the ADR
  for why no `PenaltyStatus.DISPUTED` state or dedicated endpoint was
  invented.

Layering mirrors modules/wallet/ and modules/matching/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        PenaltyRepository, StrikeRepository Protocols
    models.py       SQLAlchemy ORM models for penalty.penalties/strikes
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): PenaltyService
    dependencies.py FastAPI DI wiring

No schemas.py, no router.py — this module has no request/response DTOs
and no HTTP surface of its own; see "Implements no HTTP endpoint" above.
"""
