ADR-0059 — Outstanding Customer Penalty Display: Implementation

Status: Accepted — owner directive, delivered as part of "VISTAAR —
Consolidated Decisions, Remaining Implementation & Integration
Instructions," 2026-09-02. Implemented the same day.
Date recorded: 2026-09-02
Deciders: Project owner (explicit written instruction to implement the
already-approved ADR-0026 rule 3, using existing business rules only —
no new penalty amount or collection rule invented).

1. Decision

Implements exactly what ADR-0026 (2026-08-26) already approved but left
unbuilt: `POST /api/v1/rides` (Create Ride) now returns
`outstanding_penalty`/`total_payable` in the shape `api-contracts.md`
§12 already documented as the target — no new business rule, no new
penalty amount, no new collection mechanism. This closes a real gap
between an approved decision and the running system, not a new decision
of its own.

2. What was built

- `PenaltyRepository.sum_amount_outstanding_for_user()` /
  `SqlAlchemyPenaltyRepository` — the same aggregate query
  `sum_amount_outstanding()` (Admin Web's all-drivers dashboard total)
  already used, scoped to one customer via `user_id`.
- `PenaltyService.get_outstanding_penalty_total(customer_id=...)` — thin
  pass-through, `0` for a customer with no OUTSTANDING row.
- `modules/ride/router.py`'s `create_ride()` — composes the above (a
  plain informational read, no lock, never blocks or fails ride
  creation — the ride is already durably committed by the time this
  runs) and `_ride_data()` (Create Ride's own response builder, not
  shared with any other endpoint) now returns `outstanding_penalty`
  (`null` or `{amount, currency}`) and `total_payable`
  (`{ride_fare, outstanding_penalty, total, currency}`), exactly the
  shape already documented.
- Mobile: `RideCreationResult` gained `outstandingPenalty`/
  `totalPayable` fields (`lib/core/api/ride_api.dart`).
  `BookRideScreen` shows a dialog immediately after a successful
  booking whenever `outstandingPenalty` is non-null, before navigating
  to `RideStatusScreen` — the earliest real point available, since no
  separate "preview before booking" endpoint exists; booking itself is
  never blocked on it (BR-057, unchanged).

3. What this does not do

- Does not create a payment/collection flow for the outstanding
  penalty — `total_payable.total` remains informational only, per
  ADR-0026: the ride fare is still paid P2P, directly to the Sarthi
  (ADR-0025). **Superseded 2026-09-03 by
  [ADR-0066](ADR-0066-customer-penalty-settlement-via-driver-wallet.md):**
  the "genuinely undecided" collection mechanism this bullet pointed
  to is now resolved — the penalty is settled automatically at the
  ride's completion (no customer-facing payment flow ever needed) and
  this same `outstanding_penalty` value this ADR computes is now also
  durably *attached* to the ride at the moment this endpoint runs, not
  just displayed. The display behavior this ADR built is otherwise
  unchanged — ADR-0066 extends it, doesn't replace it.
- Does not change any penalty amount, expiry, or qualification rule
  (BR-047/048/052-057, all unaffected).
- Does not add this field to any other endpoint (e.g. `GET /rides/
  {ride_id}` or `GET /customers/me`) — scoped exactly to "the
  customer's next eligible ride booking" moment ADR-0026 rule 3 names,
  which is Create Ride specifically.

4. Testing

Backend: 3 new real-HTTP/real-Postgres integration tests
(`tests/test_ride_api.py`) — no outstanding penalty (the common case,
fields `null`/`0`), a real ₹15 OUTSTANDING penalty correctly surfaced
(reached through the real domain service — two real cancellations
against two real rides, since BR-047/048's first-qualifying-cancellation
is free and only the second produces an OUTSTANDING row), and
confirming one customer's outstanding penalty never leaks into another
customer's booking response. Full backend suite: 1312 passed, 5
skipped, 0 failed (was 1309), ruff/mypy clean.

Mobile: 1 new widget test
(`test/features/rides/book_ride_screen_test.dart`) confirming the
dialog appears with the correct amount and that `RideStatusScreen` is
not pushed until it's dismissed. Full suite: 131/131 passed (was 130),
`flutter analyze` clean.
