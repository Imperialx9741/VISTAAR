"""VISTAAR Promotion module — Phase 12 (Growth).

Owns `promotion.entitlements`/`usage`/`reservations`, per
docs/04-database/database-design.md §24, implementing domain-design.md
§15.3's commands (GrantWelcomePromotion, GrantReferralPromotion,
ReservePromotion, ConsumePromotion, RestorePromotion — ExpirePromotion
is lazy, evaluated on read, not a separate stored command).

See docs/14-decisions/ADR-0019-growth-minimal-promotion-and-referral-
foundation.md for the full scope reasoning, and
docs/14-decisions/ADR-0070-promotion-consume-restore-ride-lifecycle-
integration.md (2026-09-04) for the ride-lifecycle composition below —
ADR-0019 originally deferred `ConsumePromotion`/`RestorePromotion`
composition (its Item 6); ADR-0070 closes that gap. This module
deliberately does NOT:

- Invent BR-063's promotional discount cap — resolved by the owner
  instead (ADR-0049, 2026-08-28): ₹100/ride, applied via
  `max_discount_amount` on every welcome/referral entitlement
  (`Entitlement.new_welcome()`/`new_referral_referred()`/
  `new_referral_referring()`, modules/promotion/domain/entities.py).
  Before ADR-0049 this stayed `NULL` — genuinely accurate (no cap had
  been set), not a placeholder (ADR-0019 Decision 2).
- Invent BR-065/066's early/late-cancellation boundary — genuinely TBD
  (business-rules.md §18/§19). `restore_reservation_for_ride()` below
  restores unconditionally on every cancellation rather than guessing
  at a threshold (ADR-0070 §3).
- Implement `POST /internal/promotions/reserve`/`/restore` as literal
  HTTP endpoints — api-contracts.md §55 documents them as internal
  service APIs requiring service authentication, a concept that
  doesn't exist in this codebase (ADR-0013 Decision 1's precedent,
  reused here — ADR-0019 Decision 3).

What it does do:

- `grant_welcome_promotion()`: composed into
  `modules.customer.service.CustomerService.get_profile()`'s existing
  auto-provision point (BR-058 — unconditional on referral, so
  registration/first-access is the trigger, not the referral-attach
  flow).
- `grant_referral_promotion()`: composed into
  `modules.referral.router.attach_referral()` (the same
  router/composition-layer pattern `modules/ride/router.py` established
  for cross-module calls — `modules.referral.service` never imports
  `modules.promotion`) — BR-059/060, both the referred and referring
  customer's entitlements, granted at the moment attachment succeeds.
- `reserve_entitlement()`: composed into `POST /api/v1/rides` (ride
  creation) — reserves against the customer's soonest-expiring ACTIVE
  entitlement, feeding the discount into
  `PricingService.calculate_fare()`. Row-locked
  (`EntitlementRepository.get_by_id_for_update()`, database-design.md
  §44), concurrency-safe. The use is decremented at *reserve* time, not
  consume time — BR-065's "early cancellation restores" only makes
  sense if a use was already provisionally taken.
- `consume_reservation()`/`restore_reservation()`: also row-locked, now
  on the reservation itself too (`ReservationRepository.
  get_by_id_for_update()`, added by ADR-0070 — closing a real double-
  consume/double-restore race a plain `get_by_id()` left open).
  `consume_reservation_for_ride()`/`restore_reservation_for_ride()`
  (ADR-0070) are the ride_id-keyed wrappers composed into
  `modules/ride/router.py`'s `complete_ride()`/`cancel_ride()`/
  `driver_cancel_ride()`, mirroring the exact best-effort,
  no-op-when-nothing-applies shape `PenaltyService.
  settle_penalties_for_completed_ride()`/`release_penalties_from_
  cancelled_ride()` already established.
- `list_entitlements()`: lazily expires (BR-062, 30 days) any entitlement
  past its `expires_at` on read — same "no background worker" pattern
  ADR-0011 Decision 2 established for offer expiry.

Layering mirrors modules/wallet/ and modules/penalty/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        EntitlementRepository, UsageRepository,
                    ReservationRepository Protocols
    models.py       SQLAlchemy ORM models for the three tables
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): PromotionService
    dependencies.py FastAPI DI wiring

No schemas.py — `GET /api/v1/customers/me/promotions` (api-contracts.md
§37) has no request body. `router.py` implements it, composing
`modules.customer.service.CustomerService.get_profile()` first (same
precondition-check pattern `modules/wallet/router.py` established for
`GET /api/v1/drivers/me/wallet`).
"""
