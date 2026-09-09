ADR-0073 — Driver Self-Service Strike History Endpoint

Status: Accepted and implemented (2026-09-04)
Date recorded: 2026-09-04
Deciders: Closes a real, previously-unflagged gap discovered while
completing the mobile Sarthi app's remaining screens (owner-requested
autonomous engineering pass, 2026-09-04, "continue" — same priority
logic as ADR-0072: highest-value, still-missing, no external blocker).
Follows the exact precedent ADR-0072 itself followed from ADR-0006: a
service/repository layer already fully built and tested, an admin-only
HTTP route already exposing it, and no HTTP route for the data's own
subject (here, the driver) to read it about themselves.

1. Context

api-contracts.md §46.18 documents `GET /api/v1/admin/drivers/{driver_id}
/strikes` (Driver Strike History), composed in `modules/admin/router.py`
over `PenaltyService.list_strikes_for_driver()` — a plain, already-
tested pass-through to `SqlAlchemyStrikeRepository.list_for_driver()`.
`driver.drivers.strikes` (the bare counter) is already returned on
`GET /api/v1/drivers/me` and shown in the Sarthi app today — but nothing
lets a Sarthi see the individual strikes behind that count: which ride,
what reason, when.

No document anywhere (business-rules.md, api-contracts.md, any ADR)
records a deliberate decision to withhold this from the driver — it
simply was never extended past the admin-only route, the same shape of
gap ADR-0072 closed for driver/vehicle documents. The closest analogue,
`GET /api/v1/drivers/me/wallet/transactions` (ADR-0024), already
established that a driver reading their own immutable penalty-adjacent
history back is the expected pattern in this codebase, not a new one.

2. Decision — one new endpoint, reusing the existing service unchanged

**`GET /api/v1/drivers/me/strikes?page=&page_size=`** — the caller's
own strikes, newest first, same pagination envelope and item shape
§46.18 already documents for the admin route
(`strike_id`/`driver_id`/`ride_id`/`reason`/`created_at`), scoped to
`account.id` instead of an admin-supplied `driver_id` path param — no
ownership check needed beyond that scoping (unlike the vehicle-document
endpoints, there is no possibility of asking for someone else's data,
since the id is never caller-supplied). `PenaltyService.
list_strikes_for_driver()` itself is untouched — this is a second
caller, not a modified one, matching ADR-0072's own "reuses the service
layer unchanged" restraint.

No new admin capability, no new business rule, no new `reason` value —
`reason` remains exactly the free-form string
`PenaltyService.record_driver_strike()` already writes: BR-068's
driver-cancellation strike passes through the driver's own free-text
cancellation reason (`CancelRideBody.reason`, supplied to
`POST /{ride_id}/driver-cancel`) unmodified and unvalidated against any
vocabulary — this ADR does not add one.

3. What this ADR explicitly does not do

- Does not add a way for a driver to dispute, appeal, or annotate a
  strike — no such capability exists anywhere in this codebase today at
  any layer, and none is invented here.
- Does not change the admin endpoint, `PenaltyService`, or the
  `penalty.strikes` table in any way.
- Does not add push/in-app notification when a new strike is recorded
  (a separate, real gap — Phase 15's own notification-gap audit already
  covers what is and isn't wired there; unaffected by this change).
- Does not add a driver-facing penalty (monetary) history endpoint —
  that is wallet transaction history (ADR-0024), already built and
  already surfaced in the app's Wallet screen; strikes and wallet
  penalties are separate concepts (BR-068 vs. BR-047/048) with separate
  histories by design.

4. Verification

Real HTTP + real Postgres tests (mirroring
`tests/test_driver_document_api.py`'s own conventions): a driver with
strikes sees exactly their own, newest first, paginated correctly; a
driver with none sees an empty page, not an error; another driver's
strikes never appear (scoping by `account.id`, not a path param, makes
cross-driver leakage structurally impossible rather than merely
checked); unauthenticated and wrong-account-type (customer) rejection.
Full backend suite run after — see this task's own completion report
for the exact count.
