ADR-0045 — Platform Fee Management

Status: Accepted and implemented (2026-08-26) — owner decision #3 of the
2026-08-26 "approved product decisions" batch, recorded design-only per
the owner's "DO NOT IMPLEMENT RUNTIME CODE YET" instruction on that
batch, then implemented the same day under the owner's subsequent
broader authorization to build everything not blocked on an external
credential.

Date recorded: 2026-08-26.
Deciders: Project owner (explicit written decision, 2026-08-26,
"similar to fare management").

1. Context

The platform fee (BR-011, ADR-0014 Decision 1) is a hardcoded
`dict[VehicleCategory, Decimal]` in `modules/matching/router.py`:
`{BIKE: ₹2, AUTO: ₹5, CAB: ₹10}` — three keys, deliberately *not*
split by cab_tier ("CAB's ₹10 applies uniformly regardless of
Eco/Premium/Premium+ tier", per that dict's own comment). It is looked
up and immediately debited from the driver's wallet at Accept Offer
time (`matching/router.py`'s `accept_offer` handler), producing one
`wallet.transactions` row (`transaction_type='PLATFORM_FEE'`) that
already stores the exact amount charged — this table's own existing
immutability is why "existing/historical rides never change" is
already guaranteed by construction, once the *lookup* is versioned.

2. Decision 1 — `pricing.platform_fee_rules`, same shape and lifecycle
   as `pricing.fare_rules` (ADR-0042), same 3-key vehicle_category set

The owner said "similar to fare management" — implemented literally:
identical DRAFT → IN_REVIEW → PUBLISHED lifecycle, identical
"Publish closes out the prior live rule for the same key" mechanism.

```
CREATE TABLE pricing.platform_fee_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_category VARCHAR(20) NOT NULL,  -- 'BIKE' | 'AUTO' | 'CAB' — the
                                             -- existing 3-key set (BR-011),
                                             -- deliberately NOT the 5-key
                                             -- fare_rules set (no per-tier
                                             -- fee is documented anywhere)
    fee_amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | IN_REVIEW | PUBLISHED
    effective_from TIMESTAMPTZ,   -- NULL until Publish
    effective_until TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

A separate table from `pricing.fare_rules`, not an additional column
on it — a platform fee and a customer fare are two different concepts
that happen to share a versioning shape (the same reasoning ADR-0041
§7 and ADR-0043 §2 both already apply to their own pairs of tables):
fare_rules feeds `PricingService.calculate_fare()` (customer-facing
cost), platform_fee_rules feeds Accept Offer's driver-side debit — no
caller ever needs both from the same row, and their key granularity
already differs (5 keys vs. 3).

3. Decision 2 — Composition point: Accept Offer reads the live rule
   instead of the hardcoded dict; nothing else changes

`matching/router.py`'s `fee = _PLATFORM_FEE_BY_CATEGORY[category]`
becomes `fee = pricing_service.get_active_platform_fee(category,
now=now)` (a new method paralleling `get_active_by_category()`,
querying `platform_fee_rules` the identical way ADR-0042 already
queries `fare_rules`: `status='PUBLISHED' AND effective_from <= now()
AND (effective_until IS NULL OR effective_until > now())`). The
`WalletService.debit()` call immediately after is unchanged — it
already persists whatever `fee` value it's given onto an immutable
`wallet.transactions` row, so "future rides use the new rule; existing
rides never change" requires no change to Wallet at all, only to what
value Accept Offer looks up before calling it.

4. Decision 3 — Admin endpoints, identical shape to Fare Management
   (api-contracts.md §46.7)

```
POST /api/v1/admin/platform-fee-rules                        Create Draft
GET  /api/v1/admin/platform-fee-rules?vehicle_category=&status=  List (version history)
GET  /api/v1/admin/platform-fee-rules/{id}                    Get
POST /api/v1/admin/platform-fee-rules/{id}/submit-for-review
POST /api/v1/admin/platform-fee-rules/{id}/publish
```

New permission key needed: none — `FARE_MANAGEMENT` already exists
(ADR-0040) and platform fee is priced-service-adjacent, but it is a
*driver*-economics lever, not a *customer fare* lever, and an admin
with FARE_MANAGEMENT access should not automatically control it or
vice versa. Reuses `FINANCE` instead (already covers driver wallet
review) — an admin who can see/adjust a driver's money already needs
this same trust level.

5. Decision 4 — Migration seeds today's approved values, no fallback
   constant kept

Same discipline as ADR-0042/ADR-0043: the implementing migration
inserts three PUBLISHED rows (BIKE ₹2, AUTO ₹5, CAB ₹10,
`effective_from = migration time`) so the live fee never silently
changes the moment this ships. `_PLATFORM_FEE_BY_CATEGORY` is deleted
from `matching/router.py`, not kept as a fallback.

Resolved during implementation (2026-08-26), amending this Decision:
`_PLATFORM_FEE_BY_CATEGORY` was NOT deleted. It remains in
`matching/router.py` as a last-resort fallback — used only when no
PUBLISHED `pricing.platform_fee_rules` row exists for a category at
Accept Offer time — for the same two reasons ADR-0043 §4 already gave
its own old hardcoded constants, and the same reasoning ADR-0044 §3
independently reached for `SMS_TEMPLATES`: (1) production race-safety,
so a driver's Accept Offer can never hard-fail just because a category
has no published rule yet; (2) `pricing.platform_fee_rules` has a real
`created_by` FK to `admin.users` (unlike `pricing.fare_rules`, which
has none), so it cannot get `fare_rules`' own "excluded from
`tests/_integration_db.py`'s `truncate_integration_tables()`" treatment
— truncating `admin.users` would otherwise fail with a foreign-key
violation while a `platform_fee_rules` row still referenced a row about
to be deleted. `platform_fee_rules` is therefore cleared before
`admin.users` in that test helper, same as `referral.driver_bonus_
rules`/`customer_reward_rules` (ADR-0043) and `notification.templates`
(ADR-0044) — and, exactly like those two, needs a fallback to survive
that mid-session wipe. The migration still seeds all three PUBLISHED
rows so nothing changes for the common case; the fallback exists only
for the gap between "no PUBLISHED row" and "someone commits to
reseeding it."

6. What this does NOT resolve

- No new fee *dimension* is introduced (still flat ₹, still 3 keys,
  no per-tier or percentage-based fee) — "do not invent additional ad
  economics" doesn't apply to this decision specifically, but the same
  restraint is exercised: nothing beyond what BR-011 already
  documents.
