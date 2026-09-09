"""VISTAAR Referral module — Phase 12 (Growth).

Owns `referral.codes`/`referrals`/`rewards`, per
docs/04-database/database-design.md §25, implementing domain-design.md's
Referral commands (GetOrCreateReferralCode, AttachReferral,
QualifyCustomerReferral, QualifyDriverReferral, RecordReward —
RejectReferral is the one command excluded, ADR-0019 Decision 1: nothing
in this codebase yet drives a reject path).

See docs/14-decisions/ADR-0019-growth-minimal-promotion-and-referral-
foundation.md for the full scope reasoning. This module deliberately
does NOT:

- Expose a driver-facing `GET .../referral` HTTP endpoint.
  `get_or_create_code()` works identically for a driver owner, but
  api-contracts.md §38 documents only the customer-facing endpoint —
  inventing one would violate ADR-0019 Decision 5. A driver's referral
  code is provisioned instead the moment `qualify_driver_referral()` /
  `record_reward()` are composed at driver-approval time in
  `modules/admin/router.py`.
- Implement `POST /internal/referrals/qualify` as a literal HTTP
  endpoint. api-contracts.md §55 documents it as an internal service API
  requiring service authentication, a concept that doesn't exist in this
  codebase (ADR-0013 Decision 1's precedent, reused — ADR-0019
  Decision 3). `qualify_customer_referral()`/`qualify_driver_referral()`
  are plain in-process method calls instead.
- Import `modules.promotion` or `modules.wallet` anywhere in this
  module. Every cross-module effect a referral produces (a promotion
  grant, a wallet credit) is composed at the router/composition layer
  that calls into this module — `modules/referral/router.py` for the
  customer flow, `modules/admin/router.py` for the driver flow — the
  same one-directional-imports rule every other module in this codebase
  follows.

What it does do:

- `get_or_create_code()`: lazily provisions one referral code per owner
  on first request — no code is generated ahead of time.
- `attach_referral()`: BR-025 (self-referral must not generate a
  reward) rejected here; `uq_referrals_referred_id` (a referred party
  can only ever be referred once) enforced by the repository, which
  raises `AlreadyReferredError` on a genuine duplicate insert.
- `qualify_customer_referral()` / `qualify_driver_referral()`: two
  distinct commands for two genuinely different real-world trigger
  events — BR-060 (customer: activates on first login through the
  referral, no completed ride required) vs. BR-023 (driver: only after
  registration, onboarding, verification, AND approval all succeed).
- `record_reward()`: an idempotent (on `idempotency_key`) audit record
  of a reward already granted by the module that actually owns the
  effect (`modules.wallet` for BR-022's ₹100 driver credits,
  `modules.promotion` for BR-059/060's ride discounts) — this table
  never itself moves money or grants an entitlement.

Layering mirrors modules/promotion/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        ReferralCodeRepository, ReferralRepository,
                    RewardRepository Protocols
    models.py       SQLAlchemy ORM models for the three tables
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): ReferralService
    dependencies.py FastAPI DI wiring
    schemas.py      AttachReferralRequest (POST /api/v1/referrals/attach
                    is the only endpoint here with a request body)
    router.py       GET /api/v1/customers/me/referral,
                    POST /api/v1/referrals/attach (api-contracts.md
                    §38) — composes modules.promotion for the customer
                    flow's entitlement grants
"""
