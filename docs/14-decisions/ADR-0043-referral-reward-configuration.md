ADR-0043 — Referral Reward Configuration

Status: Accepted and implemented (2026-08-26) — owner decision #1 of the
2026-08-26 "approved product decisions" batch, recorded design-only per
the owner's explicit "DO NOT IMPLEMENT RUNTIME CODE YET" instruction on
that batch, then implemented the same day under the owner's subsequent
broader authorization to build everything not blocked on an external
credential.

Date recorded: 2026-08-26.
Deciders: Project owner (explicit written decision, 2026-08-26).

1. Context

Two structurally different "referral reward" values are hardcoded today:

- Driver referral (BR-022/023): a flat ₹100 wallet credit to both the
  referred and referring driver, paid at driver-approval time —
  `_DRIVER_REFERRAL_BONUS_AMOUNT = Decimal("100")` in
  `modules/admin/router.py`.
- Customer referral (BR-059/060): a promotion grant — 3 rides at 50%
  off (referred customer) or 2 rides at 50% off (referring customer) —
  `_REFERRAL_CUSTOMER_TOTAL_USES`/`_REFERRAL_CUSTOMER_DISCOUNT_PERCENT`/
  `_REFERRING_CUSTOMER_TOTAL_USES`/`_REFERRING_CUSTOMER_DISCOUNT_PERCENT`
  in `modules/promotion/domain/entities.py`.

The owner's decision: both become admin-editable, versioned/effective-
dated, with historical issued rewards immutable and every change
audited. BR-058 (WELCOME — 50% off the first 3 rides, unconditional on
any referral) is explicitly NOT a referral reward and is out of this
ADR's scope — see ADR-0048 (Settings) §"Promotion defaults" for it.

2. Decision 1 — Two tables, not one: driver bonus and customer reward
   configuration are different shapes, same "don't conflate two
   concepts" reasoning ADR-0041 already established

```
CREATE TABLE referral.driver_bonus_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referred_amount NUMERIC(12,2) NOT NULL,   -- credited to the referred driver
    referrer_amount NUMERIC(12,2) NOT NULL,   -- credited to the referring driver
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | IN_REVIEW | PUBLISHED
    effective_from TIMESTAMPTZ,   -- NULL until Publish (ADR-0042 Decision 2 pattern)
    effective_until TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE referral.customer_reward_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reward_type VARCHAR(30) NOT NULL,  -- 'REFERRAL_REFERRED' | 'REFERRAL_REFERRING'
                                        -- (matches promotion.entitlements.
                                        -- promotion_type exactly, BR-059/060)
    discount_percent NUMERIC(5,2) NOT NULL,
    total_uses INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    effective_from TIMESTAMPTZ,
    effective_until TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Both tables reuse the exact DRAFT → IN_REVIEW → PUBLISHED lifecycle and
"Publish closes out the prior live row" mechanism ADR-0042 established
for `pricing.fare_rules` — a single, already-proven pattern for
"versioned/effective-dated, future values apply going forward, history
untouched." `referral.customer_reward_rules` keys on `reward_type` the
same way `pricing.fare_rules` keys on `vehicle_category`: one
independent config stream per type (REFERRED and REFERRING already
differ today — 3 uses vs. 2 — so they must be edited/published
independently). `referral.driver_bonus_rules` has no key column — BR-022
is a single global policy, not per-category.

3. Decision 2 — Values are copied at qualification time, never read
   live later

`referral.rewards` (the existing audit/idempotency table) already
records `amount`/`promotion_uses` per issued reward — nothing about
that table changes. The only change is *where* `qualify_driver_referral()`
(admin/router.py's Approve Driver composition) and the customer-referral
attach/qualify path (modules/referral/router.py) source their
amount/discount_percent/total_uses from: the currently-PUBLISHED-and-
live config row at the moment of qualification, instead of the module-
level Python constants — copied onto the `WalletService.credit()`
call, the `referral.rewards` row, and (customer side) the
`promotion.entitlements` row created at that exact moment. Editing or
publishing a new config row afterward never touches an already-issued
reward, the same "coupon redemption copies fields at redemption time"
principle ADR-0041 §6.1 already established, and the same "a fare
quote freezes its values at creation" principle this codebase has used
since ADR-0020.

This mirrors an already-real precedent for the *timing* itself: ADR-0019
Decision 4 already established that a driver referral qualifies at
Approve Driver, not at Attach — reading config live at that same,
already-existing moment adds no new timing question.

4. Decision 3 — The migration seeds a PUBLISHED row; the old constants
   become a defensive last-resort fallback, not deleted

The migration inserts one PUBLISHED row per table/type carrying
today's approved values (₹100/₹100; 50%/3 uses; 50%/2 uses) — the same
backfill discipline ADR-0042's migration used for
`pricing.fare_rules.active → status`. This is the sole source of truth
in ordinary operation; every qualification reads it live.

Resolved during implementation (2026-08-26), amending this Decision's
original "no fallback, deleted" stance: the Python-level constants
(`_DRIVER_REFERRAL_BONUS_AMOUNT`,
`_REFERRAL_CUSTOMER_TOTAL_USES`/`_DISCOUNT_PERCENT`,
`_REFERRING_CUSTOMER_TOTAL_USES`/`_DISCOUNT_PERCENT`) are kept, but
demoted to a defensive last-resort default used only when no PUBLISHED
row exists at all for a given key — logged as a warning, not silently
absorbed, and never the normal path. Two reasons this is safer than a
hard failure: (a) production — if an admin's Publish action races with
another End/replace in a way that briefly leaves no row live (should
not happen given the "close out the prior rule" mechanism in Decision
2, but a defensive backstop costs little), a driver-approval or
referral-attach flow should degrade to a known-good value rather than
502 every qualification platform-wide; (b) the migration's own seed
step depends on an `admin.users` row already existing to satisfy
`created_by`'s FK — a fresh/test database has none yet, so the
migration additionally provisions a fixed-UUID synthetic system admin
account when no real Super Admin exists (mirroring
`scripts/provision_admin.py`'s own "ops-only, same trust as `alembic
upgrade head`" precedent) purely so seeding never depends on migration
ordering relative to the first real admin's creation — and that seeded
row can still be legitimately absent in an isolated test database that
never ran this migration's seed path (e.g. a fake in-memory repository
in a unit test). The fallback exists for exactly that class of
situation, not as permission to skip building the real config path.

5. Decision 4 — Admin endpoints, mirroring Fare Management exactly
   (ADR-0042, api-contracts.md §46.7)

```
POST   /api/v1/admin/referral-config/driver-bonus              Create Draft
GET    /api/v1/admin/referral-config/driver-bonus               List (version history)
GET    /api/v1/admin/referral-config/driver-bonus/{id}           Get
POST   /api/v1/admin/referral-config/driver-bonus/{id}/submit-for-review
POST   /api/v1/admin/referral-config/driver-bonus/{id}/publish

POST   /api/v1/admin/referral-config/customer-rewards            Create Draft
GET    /api/v1/admin/referral-config/customer-rewards?reward_type=  List
GET    /api/v1/admin/referral-config/customer-rewards/{id}       Get
POST   /api/v1/admin/referral-config/customer-rewards/{id}/submit-for-review
POST   /api/v1/admin/referral-config/customer-rewards/{id}/publish
```

Permission key `REFERRALS` (already exists, ADR-0040) — no new
`AdminModule` value needed. Every mutation audited, same shape as
every other admin action in this codebase.

6. What this does NOT resolve

- BR-058's WELCOME promotion values are out of scope (see §1) —
  tracked as "promotion defaults" under ADR-0048 (Settings) instead.
- No new reward *types* or qualification rules are introduced — "do
  not invent arbitrary reward rules beyond the existing policy" (owner
  instruction) is read literally: only the two already-existing
  reward shapes (driver wallet bonus, customer promotion grant) become
  editable; nothing about *when* a referral qualifies changes.
