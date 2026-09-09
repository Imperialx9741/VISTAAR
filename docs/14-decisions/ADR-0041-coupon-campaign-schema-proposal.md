ADR-0041 — Coupon/Campaign Schema

Status: Implemented (2026-08-26). Accepted per the owner's "ok continue"
confirmation of this design; implementation proceeded under the owner's
subsequent "do it by your own call" authorization (this specific task,
named explicitly), which supersedes the Admin Web spec's original
"DO NOT IMPLEMENT YET" instruction for this one backend schema/service/
API slice — that instruction otherwise still stands for the Admin Web
*frontend* itself, which remains unbuilt. BR-063's discount-cap-per-
campaign-type question stays open regardless (Decision Register,
unchanged by this ADR) — that's a rate/value question, not this
schema's shape.

**Clarified 2026-09-04**: BR-063 itself is resolved for the welcome/
referral entitlement types (ADR-0049, 2026-08-28 — 50% off, ₹100 cap).
The "per-campaign-type question" this ADR left open is a distinct,
still-genuinely-open question: campaigns (BR-128) are admin-configured
per campaign, each with its own `discount_value`/`max_discount_amount`
set by whoever authors it — there is no fixed platform-wide rate for
campaigns to inherit, by design. Nothing about ADR-0049 changes that;
this note only prevents the two being conflated.

Date recorded: 2026-08-26. Implemented: 2026-08-26.
Deciders: Project owner (confirmed this task's proposed schema shape,
"ok continue," after review; separately authorized implementation via
"do it by your own call").

1. Context

`promotion.entitlements` (database-design.md §24.1) is a per-customer
*grant* — one row already means "this specific customer holds this
promotion," created by `GrantWelcomePromotion`/`GrantReferralPromotion`
at the moment a customer becomes eligible (first access, driver-referral
qualification). There is no shared "coupon definition" concept anywhere:
no `code` column, no vehicle-tier eligibility, no minimum-fare
threshold, no cross-customer usage cap. The Admin Web spec's "Offers/
Coupons" module — a designer with a code, eligible tier, discount type/
value, minimum fare, eligible-user scope, ride-count limits, a
customer-use limit, a total usage limit, and active/paused control —
describes a materially different concept: a campaign definition many
customers redeem against, not a grant already assigned to one customer.
Building admin screens against `promotion.entitlements` as if it were
already that would mean either inventing fields with nowhere to store
them, or silently narrowing the spec to fit what exists — neither is
this task's call to make alone.

2. Decision 1 — A new `promotion.campaigns` table, additive to
   `promotion.entitlements`, not a replacement

```
CREATE TABLE promotion.campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(30) UNIQUE,  -- NULL for an auto-applied campaign with no
                               -- customer-entered code
    name VARCHAR(100) NOT NULL,
    vehicle_category VARCHAR(20),          -- NULL = every category
    discount_type VARCHAR(10) NOT NULL,    -- 'PERCENT' | 'FLAT'
    discount_value NUMERIC(12,2) NOT NULL,
    max_discount_amount NUMERIC(12,2),
    minimum_fare NUMERIC(12,2),
    eligible_scope VARCHAR(20) NOT NULL DEFAULT 'ALL',  -- 'ALL' | 'SELECTED'
    per_customer_use_limit INT NOT NULL DEFAULT 1,
    total_usage_limit INT,
    ride_count_limit INT,   -- e.g. "only a customer's first N rides ever"
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | ACTIVE | PAUSED | ENDED
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE promotion.campaign_eligible_customers (
    campaign_id UUID NOT NULL REFERENCES promotion.campaigns(id),
    customer_id UUID NOT NULL REFERENCES customer.customers(id),
    PRIMARY KEY (campaign_id, customer_id)
);  -- populated only when eligible_scope = 'SELECTED'
```

`promotion.entitlements` gains one additive, nullable column:
`campaign_id UUID REFERENCES promotion.campaigns(id)`. Existing rows
(welcome/referral grants) keep it `NULL` — nothing about the existing
`GrantWelcomePromotion`/`GrantReferralPromotion`/`ReservePromotion`/
`ConsumePromotion`/`RestorePromotion` commands changes. A coupon
redemption becomes a *new* command, `RedeemCampaignCode`, that creates
an entitlement the same shape those five already produce, with
`campaign_id` set and the discount fields *copied* from the campaign at
redemption time — not read live from `promotion.campaigns` at ride time.
This matters for the same reason Fare Management's own versioning
matters: editing a live campaign (pausing it, changing its discount)
must never retroactively change a discount a customer already redeemed
and is holding.

3. Decision 2 — A new customer-facing redemption endpoint, not just an
   admin one

The Admin Web spec covers the *authoring* side (create/pause/edit a
campaign) but redemption itself needs a customer-facing surface too —
`POST /api/v1/customers/me/promotions/redeem` (or similar; exact path
TBD at implementation time), taking a `code`, validating `status =
'ACTIVE'`, the date window, vehicle-category match, `eligible_scope`
(and membership in `campaign_eligible_customers` if `'SELECTED'`), the
per-customer-use limit (count of the caller's own entitlements with
this `campaign_id`), and the total usage limit (count across all
customers) — then creates the entitlement. Not documented anywhere in
api-contracts.md today; needs a new section, same as ADR-0040's admin
endpoints.

4. Decision 3 — Admin endpoints (Super-Admin or Offers/Coupons-MANAGE
   permission, per ADR-0040)

```
POST   /api/v1/admin/campaigns              Create (starts as DRAFT)
GET    /api/v1/admin/campaigns               List/search
GET    /api/v1/admin/campaigns/{id}          Get one
PATCH  /api/v1/admin/campaigns/{id}          Edit (DRAFT only — see Decision 4)
POST   /api/v1/admin/campaigns/{id}/activate  DRAFT/PAUSED → ACTIVE
POST   /api/v1/admin/campaigns/{id}/pause     ACTIVE → PAUSED
POST   /api/v1/admin/campaigns/{id}/end       → ENDED (terminal)
```

5. Decision 4 — Editing is DRAFT-only, matching Fare Management's own
   "never rewrite history" principle

Once a campaign has any real redemption (an entitlement referencing it
exists), its discount terms are frozen — `PATCH` only succeeds while
`status = 'DRAFT'`. An `ACTIVE`/`PAUSED` campaign can only change
`status` itself (pause/resume/end), never its discount value, minimum
fare, or eligibility — the same reasoning the Admin Web spec itself
already states for fares ("changing a fare must never rewrite historical
ride pricing"), applied consistently here rather than only where the
spec said it explicitly.

6. What this does NOT resolve

- BR-063's discount-cap question for welcome/referral entitlements is
  resolved (ADR-0049, 2026-08-28) and was always unrelated to this
  schema shape regardless. Whether campaign-type promotions should have
  any *additional*, campaign-independent cap logic beyond each
  campaign's own admin-set `max_discount_amount` remains open, but
  narrower than originally framed here — see this ADR's own §1 note,
  added 2026-09-04.
- Whether `promotion.entitlements`' existing `discount_percent`/
  `max_discount_amount` columns should be renamed/generalized, or a
  campaign-redeemed entitlement just reuses them as-is (this proposal
  assumes reuse — no entitlement schema change beyond the one additive
  `campaign_id` column).
- The exact customer-facing redemption endpoint's path/request shape —
  sketched above, not finalized.

6.1 Resolved during implementation — FLAT discounts need no entitlement
    schema change either

Decision 6's second bullet flagged this as genuinely open. Resolved:
`promotion.entitlements` has exactly one discount-shape pair,
`discount_percent` + `max_discount_amount` (a cap). The formula every
percent-based entitlement already implies is `min(fare * percent/100,
cap or infinity)`. A `FLAT` campaign's `discount_value` (say ₹50 off)
is represented at redemption time as `discount_percent=100,
max_discount_amount=<discount_value>` — `min(fare, 50)` is exactly
"₹50 off, or the whole fare if it's under ₹50," which is precisely what
a flat-₹50-off coupon means (a discount can never exceed the fare
itself, so there is no daylight between the two formulas). No new
entitlement column, matching Decision 1's own "no entitlement schema
change beyond `campaign_id`" assumption exactly — `discount_type`
selects *how a redemption computes* `discount_percent`/
`max_discount_amount` from the campaign's own `discount_value`, not a
new stored representation.

6.2 Resolved during implementation — what `ride_count_limit` bounds on
    the redeemed entitlement

Not previously nailed down: does `ride_count_limit` cap the *campaign*
(e.g. "only the first N redemptions across all customers" — which
`total_usage_limit` already covers) or the *redeemed entitlement itself*
(how many of that one customer's rides the discount applies to)? The
spec's own example — "only a customer's first N rides ever" — reads as
the latter, and `promotion.entitlements.total_uses` already exists to
express exactly that (it's what welcome's "first 3 rides" and referral's
"2 rides" already mean). Resolved: a redeemed entitlement's
`total_uses`/`remaining_uses` is set to `campaign.ride_count_limit`,
falling back to `1` (single-use per redemption) when unset — consistent
with the migration's own `per_customer_use_limit` default of 1. The
entitlement's `expires_at` is additionally capped at the campaign's own
`ends_at` when set, so a redemption can never outlive the campaign that
produced it, on top of the usual 30-day validity window (BR-062).

7. Alternative considered and rejected

Extending `promotion.entitlements` directly with all of the campaign
spec's fields (code, eligible_scope, limits, etc.) instead of a separate
table — rejected because it conflates two different lifecycles: a
campaign is authored once and redeemed many times by many customers; an
entitlement is one customer's one grant. Cramming both into one table
would mean either massive duplication (the same code/discount/limits
repeated on every redeeming customer's row) or nullable fields that only
make sense for one of the two cases — the same "don't conflate two real
concepts into one table" reasoning this codebase already applies
elsewhere (e.g. `ride.change_requests` unifying pickup/destination
change was the right call specifically because those *are* the same
concept; a campaign and a grant are not).

8. Implementation note (2026-08-26)

Built as designed, no further schema changes beyond what §2/§6.1/§6.2
already describe. Migration `92cda537e9c7` (revises `5150fb4352b4`) adds
`promotion.campaigns`, `promotion.campaign_eligible_customers`, and the
additive `promotion.entitlements.campaign_id` column — verified
`upgrade head` / `downgrade -1` / re-`upgrade head` clean on both the
dev and test databases before any application code was written.

Domain: `Campaign` entity (`modules/promotion/domain/entities.py`) with
`DiscountType`/`EligibleScope`/`CampaignStatus`, a shared
`_validate_campaign_fields()` helper used by both `Campaign.new()`
(create) and `Campaign.apply_edit()` (DRAFT-only PATCH) so the two
paths can never drift apart, `activate()`/`pause()`/`end()` enforcing
the transition table in §5/§6.2, `redemption_discount_fields()`
implementing §6.1's FLAT-as-capped-PERCENT formula, and
`Entitlement.new_campaign_redemption()` implementing §6.2's
`total_uses`/`expires_at` rules. Seven new error types
(`CampaignNotFoundError`, `InvalidCampaignInputError`,
`InvalidCampaignStateTransitionError`, `CampaignNotActiveError`,
`CampaignNotEligibleError`, `CampaignMinimumFareNotMetError`,
`CampaignUsageLimitExceededError`) were added to
`modules/promotion/domain/errors.py`,
reusing `RESOURCE_NOT_FOUND`/`VALIDATION_FAILED`/
`INVALID_STATE_TRANSITION` where they already fit and introducing four
new api-contracts.md §49 codes
(`CAMPAIGN_NOT_ACTIVE`/`CAMPAIGN_NOT_ELIGIBLE`/
`CAMPAIGN_MINIMUM_FARE_NOT_MET`/`CAMPAIGN_USAGE_LIMIT_EXCEEDED`) where
nothing existing fit, the same "PROMOTION_EXPIRED/
PROMOTION_ALREADY_USED were new too" precedent §1 already established.

Service: `PromotionService` gained `create_campaign`/`get_campaign`/
`list_campaigns`/`update_campaign`/`activate_campaign`/
`pause_campaign`/`end_campaign`/`redeem_campaign_code` — the last
validates campaign status/window, vehicle-category match, eligible-
scope membership, minimum fare, and both usage limits, in that order,
against a `get_by_code_for_update()`-locked campaign row (serializes
concurrent redemptions against `total_usage_limit`, same "lock, then
check, then act" shape `reserve_entitlement()` already established for
entitlements).

API: `POST/GET/PATCH /api/v1/admin/campaigns[/{id}]` plus `/activate`,
`/pause`, `/end` (all requiring `OFFERS_COUPONS` VIEW/MANAGE per
ADR-0040, all mutations audited) in `modules/admin/router.py`, and
`POST /api/v1/customers/me/promotions/redeem` in
`modules/promotion/router.py` — documented in api-contracts.md §37 and
new §46.2.

Docs updated: database-design.md §24.4/§24.5 (and the additive column
note on §24.1), domain-design.md §15.2/§15.3/§15.6, state-machines.md
§37.1, business-rules.md BR-128 (plus a Decision Register entry), and
api-contracts.md §37/§46.2/§49.

Testing: 32 tests in `tests/test_promotion_service.py` (up from 20 —
12 new, in-memory fakes, covering creation validation, the DRAFT-only
edit gate, the full activate/pause/end transition table, the FLAT-as-
capped-PERCENT representation, and every redemption failure mode), 6
new real-Postgres HTTP tests in `tests/test_admin_api.py` (campaign
CRUD/lifecycle, `OFFERS_COUPONS` permission gating), and 4 new
real-Postgres HTTP tests in `tests/test_promotion_api.py` (redeem
success/not-found/usage-limit/unauthenticated). Full suite: 997 passed,
5 skipped (Kafka-only, infra-unreachable in this environment), ruff and
mypy clean.

One real bug caught and fixed before any of this was committed: the
integration test suite's shared `_CLEAR_ORDER` table-wipe list
(`tests/_integration_db.py`) deletes `admin.users` before
`promotion.entitlements` did *not* yet know about the two new tables'
FK edges (`promotion.campaigns.created_by -> admin.users`,
`promotion.entitlements.campaign_id -> promotion.campaigns`) — the
first full-suite run after adding the new tables broke roughly 80
unrelated tests in other files (`test_ride_lifecycle_api.py`,
`test_verification_integration.py`, etc.) with a `ForeignKeyViolation`
on `DELETE FROM admin.users`, because campaign rows left over from this
feature's own tests still referenced it. Fixed by inserting
`promotion.campaign_eligible_customers`/`promotion.campaigns` into
`_CLEAR_ORDER` between `promotion.entitlements` and `admin.users` — the
same class of gap the file's own comment block already documents
happening repeatedly with every new FK-bearing table, not a new kind of
mistake.

9. Addendum — CSV bulk customer targeting (owner decision #8, 2026-08-26)

Design only — the owner's "DO NOT IMPLEMENT RUNTIME CODE YET"
instruction applies to this addendum too.

§4's `eligible_customer_ids` (create/edit body) already covers "all
eligible customers" (`eligible_scope='ALL'`, the field omitted/empty)
and "selected customers" (`eligible_scope='SELECTED'`, the field
populated by whatever search/select UI the Admin Web builds against
Search Customers, api-contracts.md §46.4 — already implemented). The
owner's decision adds a third input mode: bulk targeting via CSV
upload. Two design points this addendum resolves:

- **CSV format**: one column, header `phone`, one Indian phone number
  per row — the realistic shape of a marketing list an admin actually
  has on hand (not `customer_id`, which no admin-facing export
  produces anywhere in this codebase). Each row is resolved to a
  `customer_id` via the existing `identity.accounts` phone lookup +
  `customer.customers` existence check (the same two-step precondition
  Search Customers' own Customer Detail composition already performs);
  unmatched rows (no account, account not a customer, or no
  `customer.customers` row yet) are reported back to the caller, not
  silently dropped or hard-failed as a whole-request error — a
  100-row CSV with 3 typos should not force re-uploading the other 97.
- **Additive, not replacing**: unlike `eligible_customer_ids` on
  Create/Edit (which fully replaces the set, matching Update
  Permissions' own "PATCH replaces the whole set" precedent, ADR-0040),
  a CSV upload *adds* to the campaign's existing eligible-customer set.
  A marketing team re-uploading a refreshed list is the realistic
  workflow this serves, and replace-semantics would silently drop
  every individually-added customer the moment a bulk file is
  uploaded — a surprising, destructive default for what's meant to be
  an additive bulk-add tool. "Do not invent additional targeting
  rules" (owner instruction) is read as bounding the *targeting
  concept* (still just all/selected/bulk-selected, nothing fancier
  like tag-based or behavioral segments) — not as forbidding this one
  explicit, necessary choice between additive and replacing semantics,
  which the owner's own bullet list left open.

Endpoint:

```
POST /api/v1/admin/campaigns/{campaign_id}/eligible-customers/bulk
  multipart/form-data, one field: file (CSV, header "phone")

Response:
{
  "added": 97,
  "already_eligible": 2,
  "unmatched": [{"row": 14, "phone": "+91...", "reason": "no customer account"}]
}
```

Only valid while the campaign is DRAFT (same `Campaign.can_edit()` gate
§5/Decision 4 already enforces for the rest of a campaign's
eligibility) and only meaningful for `eligible_scope='SELECTED'`
(uploading against an `'ALL'`-scope campaign is a caller error,
`VALIDATION_FAILED` — the same "this field only means something for
SELECTED" rule Create/Edit already enforces for `eligible_customer_ids`).
Audited the same as every other campaign mutation.
