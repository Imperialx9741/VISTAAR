"""VISTAAR Wallet module — Minimal Wallet Foundation.

Pulled forward from Phase 11 (Financial) specifically to unblock the next
ride task (Accept Offer / Ride ACCEPTED — state-machines.md §5 requires
"Required platform fee secured" to enter ACCEPTED, and
technical-architecture.md §18's atomic accept transaction debits a
wallet that must exist first). Not a new business rule — see
docs/VISTAAR_IMPLEMENTATION_ROADMAP.md §2.0 ("Actual next engineering
dependency") and ADR-0013.

Owns `wallet.wallets` and `wallet.transactions`, per
docs/04-database/database-design.md §17.

Implements these endpoints, docs/05-api/api-contracts.md §34:

    GET /api/v1/drivers/me/wallet                 Get Wallet
    GET /api/v1/drivers/me/wallet/transactions     Wallet Transactions
                                                    (Phase 11, ADR-0024)

This module deliberately does NOT implement:

- Wallet recharge (`POST .../wallet/recharge`, api-contracts.md §35) —
  needs the payment gateway, which is TBD (external service &
  credential plan). BR-016: "Payment must be successfully verified
  before the wallet is credited" — no verification mechanism exists.
- Any credit path at all (joining bonus BR-020/021, driver referral
  bonus BR-022-024, advertisement payout, admin adjustment, fee/penalty
  reversal) — none of it is needed to unblock the next task. Building a
  `credit()` method now with nothing calling it would be speculative;
  ADR-0013 records this explicitly. Tests seed a wallet balance directly
  via SQL to exercise `debit()`'s success path, the same pattern already
  used throughout this codebase to reach states no endpoint produces yet
  (e.g. tests/test_driver_availability_api.py's `_mark_driver_document_
  approved`).
- `wallet.outstanding_settlements` (§18) / `wallet.recharges` (§19) —
  neither table is created by this task's migration. Offline
  cash-settlement recovery is unrelated to making offer acceptance
  atomic and safe.
- `POST /internal/wallet/debit` / `POST /internal/wallet/credit` as
  literal HTTP endpoints (api-contracts.md §55-57 documents them as
  "internal service APIs" requiring "service authentication," a concept
  that doesn't exist anywhere in this codebase). ADR-0013 Decision 1:
  `WalletService.debit()` is an in-process Python method instead — the
  same shape every other cross-module composition in this codebase
  already uses (e.g. modules/ride/router.py calling into
  modules.matching directly), consistent with this project's
  modular-monolith-first architecture
  (implementation-readiness.md §45-47). §55-57 remain the documented
  target shape for a future microservice extraction, not something this
  task builds literally.
- The platform-fee *amount* itself — `debit()` takes `amount` as a
  parameter; the ₹10/₹20/₹20 (BR-011) constant lookup lives at
  modules/matching/router.py's accept-offer endpoint, not here
  (ADR-0014 Decision 1 — a hard-coded constant, not a new config
  table).
- Any composition with modules.ride or modules.matching — this module
  still has zero dependency on either. `WalletService.debit()` is now
  called (Phase 3 / Task 3.4), but only from
  modules/matching/router.py's accept-offer endpoint, which imports
  *this* module — never the reverse.

What it does do:

- Auto-provisions a zero-balance `wallet.wallets` row on first access
  (`get_wallet()`), same pattern as
  `modules.customer.service.CustomerService._get_or_provision()`.
  Requires `driver.drivers` to already have a row for the caller
  (`wallet.wallets.driver_id`'s foreign key) — `router.py` establishes
  this first, same precondition-check pattern
  `modules/vehicle/router.py` already uses for `driver.drivers`.
- `debit()`: atomic, concurrency-safe (`SELECT ... FOR UPDATE` row lock,
  database-design.md §42), refuses an insufficient balance
  (`InsufficientWalletBalanceError`, BR-012), and writes an immutable
  ledger entry in the same operation (database-design.md §41's "both
  records must succeed or both must fail" rule — BR-013). Idempotent on
  a caller-supplied key via `wallet.transactions.idempotency_key`'s own
  `UNIQUE` constraint — a domain-level guard distinct from
  `shared.idempotency_keys` (which dedupes whole HTTP requests, not
  individual financial operations).
- `list_transactions()` (Phase 11, ADR-0024): this driver's own
  paginated ledger — every `debit()`/`credit()` row ever written for
  them, newest first, optionally filtered by `transaction_type`. This is
  the roadmap's "Financial audit trail" task; the ledger itself was
  already immutable and complete, only the read path was missing.

`wallet.debited`/`wallet.credited` (event-contracts.md §56) are
published by this module's callers (Phase 3 / Event & Outbox
Foundation, ADR-0017 — modules/matching/router.py's accept-offer
endpoint and modules/ride/router.py's cancellation endpoints), not by
`WalletService` itself — this module still has zero dependency on
`shared.outbox`/Kafka, consistent with staying a pure, Fake-testable
financial primitive.

Layering mirrors modules/ride/ and modules/matching/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        WalletRepository Protocol
    models.py       SQLAlchemy ORM models for wallet.wallets/transactions
    repositories.py SQLAlchemy-backed implementation of the port
    service.py      application service (use cases): get_wallet(), debit(),
                    credit(), list_transactions()
    dependencies.py FastAPI DI wiring (reuses modules.identity's
                    require_driver as-is — no new auth code here)
    router.py       FastAPI routes under /api/v1/drivers/me/wallet

No schemas.py — every endpoint here is a GET with no request body, so
there's no request DTO to define; not omitted by oversight.
"""
