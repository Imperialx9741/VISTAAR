ADR-0049 — Promotion Discount Cap (BR-063)

Status: Accepted and implemented (2026-08-28) — owner decision, resolving
business-rules.md §18's "Promotion discount cap (BR-063) — still
genuinely TBD" Decision Register entry.

Date recorded: 2026-08-28.
Deciders: Project owner (explicit written decision, 2026-08-28).

1. Context

BR-063 states "50% promotional discounts are subject to a maximum
per-ride discount. The exact cap is: TBD — determined through unit
economics before launch." The 50% figure itself was never in question
(BR-058/059/060 already fixed it for welcome/referral entitlements); only
the rupee ceiling was open. `Entitlement.max_discount_amount` (database-
design.md §24.1) has existed as a nullable column since the promotion
domain's own foundation (ADR-0019) specifically to hold this value once
supplied — welcome/referral entitlements have always passed `None` for
it, with `modules/promotion/domain/entities.py`'s own code comment
documenting that as "genuinely accurate here, not a placeholder standing
in for an unknown value," the same treatment ADR-0013 gave
`outstanding_settlement` before its own resolution.

2. Decision

The cap is ₹100 per ride, applied to every 50%-off welcome/referral
entitlement (`PromotionType.WELCOME`, `REFERRAL_REFERRED`,
`REFERRING_REFERRING`) — all three share the same 50% figure and now the
same cap; no source document or owner instruction distinguishes them.

`Entitlement._new()`'s existing `max_discount_amount` parameter is
supplied a real value for these three grant paths instead of `None`.
`PricingService`'s fare calculation already accepts and applies
`promotion_max_discount_amount` (built for campaign-redeemed
entitlements, ADR-0041 §6.1, ADR-0020 Decision 6's ApplyPromotionDiscount)
— capping a welcome/referral discount is the same mechanism, not new
code. No migration: the column already exists and already allows a
non-NULL value; only the domain-layer default changes, and only for
entitlements activated after this change (existing already-activated
entitlements keep whatever `max_discount_amount` they were created
with — never rewritten retroactively, the same never-rewrite-history
principle BR-128 states for published Campaign terms).

Campaign-redeemed entitlements (`PromotionType.CAMPAIGN`) are
unaffected — their cap is whatever the admin who authored that campaign
set (BR-128), independent of this ₹100 welcome/referral figure.

3. What this does NOT resolve

- Any cap on Campaign/Coupon discounts — BR-128's own admin-authored cap
  mechanism is untouched.
- BR-064's "cannot stack two 50% discounts on the same ride" rule —
  unrelated to the cap value itself, already enforced elsewhere.
