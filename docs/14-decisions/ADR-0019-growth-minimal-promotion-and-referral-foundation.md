ADR-0019 — Growth: Minimal Promotion & Referral Foundation

Status: Decisions 1-5 Accepted. Item 6 explicitly deferred, not decided
here.
Note (2026-09-04, ADR-0070): §5's "ReservePromotion is NOT wired into
POST /api/v1/rides" is superseded — it was wired in at some later point
(once the Pricing domain existed) without this ADR, or the module's own
docstrings, ever being updated to say so. §7's deferral of Consume/
RestorePromotion is now resolved (ADR-0070): both are composed into
ride cancellation/completion. Decisions 1-5 and Decision 4's other two
composition points (GrantWelcomePromotion, QualifyDriverReferral/
IssueReferralReward) are unaffected.
Date recorded: 2026-08-24
Deciders: Approved under the owner's phase-level autonomy grant (VISTAAR
session, 2026-08-24) — mandatory stop conditions (roadmap §0.3/§0.4)
still apply and are respected below where they genuinely bite.

1. Context

Phase 12 — Growth (14 roadmap tasks) covers the Promotion Domain
(domain-design.md §15) and Referral Domain (§16). Unlike Advertisement
(ADR-0018), both are fully specified end to end: exact business values
(BR-058-066, BR-022-025), exact schema (database-design.md §24-25), and
— unlike Advertisement — real documented customer-facing HTTP endpoints
(api-contracts.md §37-38: Get Promotions, Get Referral Code, Attach
Referral). One genuine gap remains: BR-063's promotional discount cap
is explicitly marked TBD ("determined through unit economics before
launch") — the same treatment ADR-0010 gave `fare: null` and ADR-0013
gave `outstanding_settlement: 0`, i.e. this ADR does not invent a
number where none is approved.

2. Decision 1 — Build the full domain/service/repository layer for
   both Promotion and Referral, matching the documented schema/commands
   exactly

`promotion.entitlements`/`usage`/`reservations` and `referral.codes`/
`referrals`/`rewards` (database-design.md §24-25), and all eleven
domain-design.md §15.3/§16.3 commands (GrantWelcomePromotion,
GrantReferralPromotion, ReservePromotion, ConsumePromotion,
RestorePromotion, ExpirePromotion, CreateReferralCode, AttachReferral,
QualifyCustomerReferral, QualifyDriverReferral, IssueReferralReward) —
`RejectReferral` is the one command not implemented, since nothing in
this task needs to reject a referral yet (self-referral is refused
before a `referral.referrals` row is ever created, not rejected after).

3. Decision 2 — `max_discount_amount` stays NULL; no cap is invented

`promotion.entitlements.max_discount_amount` (database-design.md §24.1)
is nullable. BR-063's cap is explicitly TBD. NULL here is genuinely
accurate — "no cap has been set" — not a placeholder standing in for an
unknown value, the same distinction ADR-0013 drew for
`outstanding_settlement: 0`.

**Superseded 2026-08-28 by ADR-0049** (owner decision, confirmed exactly
2026-09-04): BR-063 is resolved — 50% off, capped at ₹100/ride, for the
welcome/referral entitlement types this ADR built. `max_discount_amount`
is no longer NULL for those; see ADR-0049 and
`modules/promotion/domain/entities.py`'s `_WELCOME_REFERRAL_MAX_DISCOUNT_AMOUNT`.

4. Decision 3 — Internal domain commands are in-process Python methods,
   not literal `/internal/...` HTTP endpoints

api-contracts.md §55 documents `POST /internal/promotions/reserve`,
`/internal/promotions/restore`, `/internal/referrals/qualify` as
"internal service APIs" requiring "service authentication" — the exact
same shape §55-57 documented for wallet debit/credit, which ADR-0013
Decision 1 already resolved: no service-authentication concept exists
anywhere in this codebase, so these are in-process methods
(`PromotionService.reserve_entitlement()` etc.) other modules call
directly, composed at the router/composition layer like every other
cross-module call in this codebase. Reusing that decision here, not
re-deciding it.

5. Decision 4 — Two real composition points are wired in now; ride
   creation is not

Two of this task's commands have an existing, real, already-built
caller:

- `GrantWelcomePromotion`: composed into
  `CustomerService.get_profile()`'s existing auto-provision point
  (BR-058 — "A new customer receives 50% off the first 3 rides",
  unconditional on referral, so registration/first-access is the
  correct trigger, not the referral-attach flow).
- `QualifyDriverReferral`/`IssueReferralReward`: composed into
  `modules/admin/router.py`'s existing `POST /drivers/{driver_id}/
  approve` endpoint — domain-design.md §16.6 documents the activation
  trigger as exactly "Registration → Onboarding → Verification →
  Approval", i.e. the admin driver-approval action that already exists
  (Task 2.7A).

`ReservePromotion` is NOT wired into `POST /api/v1/rides` (ride
creation). api-contracts.md §72's documented flow is "Ride creation →
Promotion eligibility → Reserve entitlement → Fare quote → Ride
outcome" — a Fare Quote step sits between reservation and any
consumption/restoration decision, and the Pricing domain that produces
one does not exist yet (ADR-0010 Decision 1 — `fare` is always `null`).
Wiring a reservation into ride creation with no fare to apply a
discount against, and no consumer of the reservation once made, would
be exactly the speculative-infrastructure-with-no-real-caller pattern
ADR-0013 avoided for Wallet's `credit()`. `reserve_entitlement()`/
`consume_reservation()`/`restore_reservation()` are proven instead by
real-Postgres integration tests exercising the full lifecycle directly,
the same "prove the composition without inventing a live call site"
treatment ADR-0018 gave Advertisement's wallet-credit composition.

6. Decision 5 — HTTP surface built: exactly the three documented
   endpoints, nothing invented for drivers

`GET /api/v1/customers/me/promotions`, `GET /api/v1/customers/me/
referral`, and `POST /api/v1/referrals/attach` (api-contracts.md §37-38)
are implemented as documented. No parallel `GET /api/v1/drivers/me/
referral` is built — api-contracts.md documents no such endpoint, and
inventing one (even though `referral.codes.owner_type` is generic
enough to support it) would be the same "new public API contract"
§0.3 stop condition ADR-0018 flagged for Advertisement — a driver has
no documented way to fetch their own referral code yet. Driver referral
*qualification and reward* do not need this endpoint to work (they
trigger automatically at admin approval, Decision 4 above); only a
driver's ability to *discover* their own code is affected.

7. Item 6 — Promotion consumption/restoration on ride
   completion/cancellation: deferred, not decided here

`ConsumePromotion`/`RestorePromotion` are implemented and tested
directly, but not composed into `modules/ride/router.py`'s cancellation
endpoints or a future ride-completion endpoint — both require a real
fare to compute `discount_amount` against (event-contracts.md §15.3's
`promotion.consumed` payload), which does not exist until Pricing does.
Wiring the RESERVE side without a real ride-creation call site (Decision
4) makes this consistently out of scope for the same reason.

8. Consequences — documents updated alongside this ADR

- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: this task marked
  complete for the scope above, with Item 6 recorded as the reason the
  remaining roadmap tasks (which presuppose ride-creation composition
  and a real fare) are not done.
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, `state-machines.md`, or `database-design.md` —
  the domain/schema built matches what's documented exactly.
