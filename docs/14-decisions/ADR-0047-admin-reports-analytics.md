ADR-0047 — Admin Reports / Analytics (MVP)

Status: Accepted and implemented (2026-08-26) — owner decision #5 of the
2026-08-26 "approved product decisions" batch, recorded design-only per
the owner's "DO NOT IMPLEMENT RUNTIME CODE YET" instruction on that
batch, then implemented the same day under the owner's subsequent
broader authorization to build everything not blocked on an external
credential.

Date recorded: 2026-08-26.
Deciders: Project owner (explicit written decision, 2026-08-26).

1. Context

No Reports/Analytics domain exists at all — the Admin Web plan's own
§4.16 called this "not a partial gap, a from-scratch module... needs
its own scoping conversation before any endpoint is designed." The
owner's decision supplies that scoping: nine report areas (rides,
customers, drivers, financial/wallet, penalties, promotions/referrals,
safety/support, notification delivery, matching/operational), built
from data this codebase already has, explicitly not a separate data
warehouse.

2. Decision 1 — One endpoint per report area, each a fixed set of
   real aggregate numbers over an optional date range — not a generic
   query builder

A generic ad hoc report-builder (arbitrary group-by/filter
combinations) is the "separate data warehouse" the owner said not to
build — it would mean either a new analytical store or expensive
unindexed aggregate queries against the live operational tables on
every request. Instead: nine purpose-built endpoints, each computing a
small, fixed set of numbers already meaningful in this codebase's own
documented vocabulary (existing status enums, existing transaction
types), accepting `from`/`to` (defaulting to a sensible recent window,
e.g. last 30 days, if omitted — exact default is an implementation
detail, not a business rule). Every number is a `COUNT`/`SUM`/`AVG`
over an existing indexed or naturally-scoped column — no new
materialized view, no scheduled ETL, no new datastore.

```
GET /api/v1/admin/reports/rides?from=&to=
  rides_by_status: {SEARCHING: n, ACCEPTED: n, ..., CLOSED: n, CANCELLED: n}
  rides_by_vehicle_category: {BIKE: n, AUTO: n, CAB: n}
  average_fare: decimal        -- AVG(fare_quotes.total) for CLOSED rides in range
  completion_rate: decimal     -- CLOSED / (CLOSED + CANCELLED), 0 if no rides

GET /api/v1/admin/reports/customers?from=&to=
  total_customers: int
  new_customers_in_range: int  -- COUNT(created_at BETWEEN from AND to)

GET /api/v1/admin/reports/drivers?from=&to=
  total_drivers: int
  by_verification_status: {PENDING: n, APPROVED: n, REJECTED: n}
  by_operational_status: {OFFLINE: n, ONLINE: n, ON_RIDE: n, SUSPENDED: n, ...}
  new_drivers_in_range: int

GET /api/v1/admin/reports/financial?from=&to=
  platform_fee_collected: decimal    -- SUM(wallet.transactions.amount) WHERE
                                      -- transaction_type=PLATFORM_FEE, DEBIT, in range
  fee_reversals: decimal             -- same, transaction_type=FEE_REVERSAL, CREDIT
  driver_referral_bonuses_paid: decimal
  advertisement_payouts: decimal
  by_transaction_type: {PLATFORM_FEE: n, FEE_REVERSAL: n, ...}  -- counts, in range

GET /api/v1/admin/reports/penalties?from=&to=
  penalties_by_status: {OUTSTANDING: n, SETTLED: n, WAIVED: n, ...}
  penalties_by_type: {CUSTOMER_CANCELLATION: n, DRIVER_CANCELLATION: n, ...}
  total_amount_outstanding: decimal
  total_amount_settled_in_range: decimal

GET /api/v1/admin/reports/promotions-referrals?from=&to=
  entitlements_granted_in_range: {WELCOME: n, REFERRAL_REFERRED: n, REFERRAL_REFERRING: n, CAMPAIGN: n}
  entitlements_used_in_range: int    -- COUNT(promotion.usage WHERE status=CONSUMED, in range)
  total_discount_given: decimal      -- SUM(promotion.usage.discount_amount, in range)
  referrals_by_status: {ATTACHED: n, ACTIVATED: n}
  rewards_issued_in_range: decimal   -- SUM(referral.rewards.amount, in range)

GET /api/v1/admin/reports/safety-support?from=&to=
  incidents_by_status: {OPEN: n, ACKNOWLEDGED: n, IN_PROGRESS: n, RESOLVED: n}
  average_incident_resolution_minutes: decimal   -- AVG(resolved_at - created_at) where resolved, in range
  cases_by_status: {OPEN: n, ASSIGNED: n, RESOLVED: n, ...}
  average_case_resolution_minutes: decimal       -- same shape, support.cases

GET /api/v1/admin/reports/notifications?from=&to=
  deliveries_by_channel: {IN_APP: n, SMS: n, PUSH: n, WHATSAPP: n}
  deliveries_by_status: {PENDING: n, SENT: n, FAILED: n}
  delivery_success_rate: decimal   -- SENT / (SENT + FAILED)

GET /api/v1/admin/reports/matching?from=&to=
  offers_by_status: {PENDING: n, ACCEPTED: n, EXPIRED: n, DECLINED: n}
  offer_acceptance_rate: decimal   -- ACCEPTED / total offers in range
  average_time_to_accept_seconds: decimal   -- AVG(responded_at - created_at) where ACCEPTED
```

Field names above are illustrative of shape, not a final contract —
the implementing task finalizes exact key names against each domain's
own real enum values (e.g. `RideStatus`, `PenaltyStatus`) at build
time, the same "shape decided here, exact wire format at
implementation" split every other ADR in this codebase already uses.

3. Decision 2 — "Online drivers"/real-time operational state is
   explicitly NOT part of Reports either

Consistent with api-contracts.md §46.11's own dashboard-summary
decision (2026-08-26): a live Redis-derived count is unreliable today
(stale entries never removed on go_offline, ADR-0011) and stays out of
scope here too, for the identical reason — a "report" implies a number
someone can trust, and this one currently cannot be trusted. If the
owner wants it, the underlying go_offline-cleanup gap needs fixing
first (a separate, small ADR-0011 follow-up), not invented around here.

4. Decision 3 — New repository methods this needs; no new tables

Every report above composes a handful of new, narrowly-scoped
aggregate query methods added to each domain's own existing repository
(e.g. `RideRepository.count_by_status_in_range()`,
`WalletRepository.sum_by_transaction_type_in_range()`,
`SafetyIncidentRepository.average_resolution_minutes_in_range()`) —
the same `func.count()`/`func.sum()`/`func.avg()` SQLAlchemy pattern
already used throughout this session's admin work (e.g.
`WalletRepository.sum_debits_since()`, ADR-0045's own dashboard
predecessor). No new table, no new schema, no cross-service
composition beyond what `modules/admin/router.py` already does for
every other admin endpoint (one router composing several services'
read methods).

5. Decision 4 — Permission

`AdminModule.REPORTS` (already in the 20-module catalog, BR-126) —
VIEW only; nothing here mutates data, so no MANAGE-gated action exists
in this module.

6. What this does NOT resolve

- No CSV/PDF export — not requested, not built.
- No scheduled/emailed report delivery — same.
- No custom date-range presets beyond a plain `from`/`to` — no "last
  quarter"/"this fiscal year" business calendar exists anywhere in
  this codebase to build those against.
