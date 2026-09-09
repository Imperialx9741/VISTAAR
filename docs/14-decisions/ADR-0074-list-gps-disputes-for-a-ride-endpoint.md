ADR-0074 — List GPS Disputes for a Ride Endpoint

Status: Accepted and implemented (2026-09-04)
Date recorded: 2026-09-04
Deciders: Closes a real, previously-unflagged discovery gap found while
building the mobile GPS-dispute/evidence screen (owner-requested
autonomous engineering pass, 2026-09-04, "continue" — same priority
logic as ADR-0072/ADR-0073). Same shape of gap: a repository/service
layer built for one access pattern (admin search by status,
customer/driver read by a known `dispute_id`) with no query supporting
the one new caller actually needs.

1. Context

A GPS dispute (BR-124/BR-125, ADR-0032) is auto-opened by
`mark_arrived()`/`complete_ride()` — never created directly by a
client request. `dispute_id` reaches the **driver** directly, in the
`GPS_VERIFICATION_FAILED` error's `details` field (the same call that
just failed *is* the one that opened it). It never reaches the
**customer** by any channel: `GET /{ride_id}` (api-contracts.md §13)
does not surface an active dispute, `ride.gps_dispute_opened`
(event-contracts.md §10.10) has no consumer (Phase 15's own audit,
2026-09-04, already documented this notification gap without fixing
it — unaffected here), and `GpsDisputeRepository` had no query to find
a dispute by `ride_id` at all — only `get_by_id` (needs the id already)
and admin's `search` (status-filtered, no ride scoping, no ownership
check, so unsuitable for a customer/driver caller as-is).

Without this, a customer-side "GPS Dispute" screen would have nothing
to call — the driver could see and act on a dispute they personally
triggered, but the customer, an equally legitimate party to the same
dispute (`submit_gps_dispute_evidence()` already accepts either), would
have no way to discover it exists.

2. Decision — one new repository query, one new service method, one
   new endpoint, reusing every existing shape unchanged

- **`GpsDisputeRepository.list_for_ride(ride_id)`** — new Protocol
  method + `SqlAlchemyGpsDisputeRepository` implementation. Newest
  first (same ordering `search()` already uses). A ride has at most two
  GPS verifications (pickup, destination) and therefore at most two
  disputes ever, so this is always a tiny, unpaginated result — same
  "bounded, no pagination needed" reasoning `GET /me/documents`
  (ADR-0072) already used.
- **`RideService.list_gps_disputes_for_ride(ride_id, account_id,
  is_admin, now)`** — fetches the ride first and applies the exact
  ownership check `get_gps_dispute()` already uses
  (`account_id in (ride.customer_id, ride.driver_id)` unless
  `is_admin`), then lazily expires any OPEN-but-overdue result the same
  way `get_gps_dispute()` does per item, then returns each
  `(dispute, evidence)` pair — the identical shape `get_gps_dispute()`
  already returns for one, just for every dispute this ride has.
- **`GET /{ride_id}/gps-disputes`** — customer/driver, own ride only
  (404 otherwise, IDOR-safe, matching every sibling endpoint in this
  file). Response: `{"data": {"disputes": [...]}}`, each item the exact
  same shape `_gps_dispute_data()` already produces for
  `GET .../gps-disputes/{dispute_id}` — no new shape invented.

This is intentionally the *discovery* endpoint only — a client still
calls the existing `GET .../gps-disputes/{dispute_id}` (or acts
directly on the item already returned here, both being sufficient)
and the existing evidence endpoints to act on a specific dispute.
Nothing about those three endpoints changes.

3. What this ADR explicitly does not do

- Does not add a push/in-app notification for `ride.gps_dispute_opened`
  — that remains Phase 15's own already-documented, not-yet-fixed gap.
  This endpoint is a pull (poll-on-view) discovery mechanism, matching
  every other "no push channel exists yet" pattern already accepted
  elsewhere in this app (README's own documented gap).
- Does not change `GET /{ride_id}}`'s own response shape — an active
  dispute is not added there; the new endpoint is the one and only
  place a client looks for this.
- Does not change the admin `search` endpoint, `get_gps_dispute()`, or
  either evidence endpoint.
- Does not add resolution/decision capability for a customer or
  driver — `resolve_gps_dispute()` stays admin-only, unchanged.

4. Verification

Real HTTP + real Postgres tests (mirroring the existing GPS-dispute
test file's own conventions): a ride with one open dispute returns it
to both the customer and the driver who own that ride; a ride with none
returns an empty list, not an error; another account's ride returns 404
(IDOR-safe); unauthenticated rejection. Full backend suite run after —
see this task's own completion report for the exact count.
