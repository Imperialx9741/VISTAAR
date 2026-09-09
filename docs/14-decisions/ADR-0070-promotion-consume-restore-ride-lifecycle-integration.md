ADR-0070 — Promotion Consume/Restore Ride-Lifecycle Integration

Status: Accepted and implemented (2026-09-04)
Date recorded: 2026-09-04
Deciders: Resolved during a verification task the owner requested
("reconcile the current repository... verify whether the remaining
Phase 12 item — promotion consume/restore integration with the ride
lifecycle — is already fully implemented").
Supersedes: ADR-0019 §7 (Item 6, "deferred, not decided here") — only
the deferral itself; every other ADR-0019 decision is unaffected.

1. Context

The owner asked for a verification, not new work — with explicit
instructions not to change anything already correct (BR-063's discount
cap, referrals) and to implement only a piece found genuinely missing.
Inspecting the actual code against ADR-0019 §7 and the module's own
docstrings found two things, not one:

1. `ReservePromotion` **is** composed into `POST /api/v1/rides` (ride/
   router.py's create_ride(), reserving against the customer's soonest-
   expiring ACTIVE entitlement and feeding the discount into
   PricingService.calculate_fare()) — contradicting ADR-0019 §5's "not
   wired in" and the promotion module's own `__init__.py`/`service.py`
   docstrings, which still described it as undone. This composition was
   evidently added later (once the Pricing domain existed) without ever
   updating ADR-0019, the module docstrings, or ADR-0019's own §7
   reasoning, which depended on it.
2. `ConsumePromotion`/`RestorePromotion` were genuinely **not**
   composed anywhere — confirmed by a full-codebase search
   (`consume_reservation(`/`restore_reservation(` had zero callers
   outside their own definitions and direct unit/integration tests that
   call them manually, never through the real cancel/complete HTTP
   endpoints). A reservation created at Create Ride was therefore never
   resolved: cancelling the ride never gave the use back, and completing
   the ride never recorded it as actually used — `promotion.usage`
   would report zero real usage forever, even for rides that genuinely
   received a promotional discount, and a cancelled customer would
   permanently lose an entitlement use they never got to spend.

This is the genuinely missing piece. It is implemented here; nothing
about BR-063's discount cap or the referral domain was touched.

2. A second, independent gap found while verifying: no row lock on the
   Reservation itself

Verifying "protection against double-consume/double-restore" and
"behavior under concurrent/replayed requests" against the actual code
(not just reading the docstrings) found that `consume_reservation()`
and `restore_reservation()` both read the reservation via a plain
`get_by_id()` — no lock — then later acquired the *entitlement*'s lock
(restore only) before writing. Traced through with real Postgres
transaction semantics: two concurrent or replayed calls against the
*same* reservation_id could both read status=RESERVED before either
commits, then both proceed — for restore, both increment
`remaining_uses` (double-restore: entitlement locking serializes two
*different* reservations racing on the same entitlement, but does not
protect the *same* reservation's own status check, which happens before
that lock is acquired). Consume has a database-level backstop
(`uq_promotion_ride_use` makes a second INSERT fail), but restore had
none — `remaining_uses` is a plain mutable counter, not a unique-
constrained insert.

3. Decision

1. **Wire consume into ride completion, restore into both cancellation
   paths**, using two new ride_id-keyed `PromotionService` methods
   (`consume_reservation_for_ride()`, `restore_reservation_for_ride()`)
   that mirror the exact pattern `PenaltyService.
   settle_penalties_for_completed_ride()`/`release_penalties_from_
   cancelled_ride()` already established for the same "best-effort,
   ride_id-keyed, no-op when nothing applies" shape:
   - `complete_ride()` (modules/ride/router.py): after the ride is
     durably COMPLETED, consumes any reservation this ride made, with
     `discount_amount` read from the ride's own final fare quote
     (`FareQuote.promotion_discount` — the amount actually applied, not
     re-derived). Fires `promotion.consumed` (event-contracts.md §15.3).
   - `cancel_ride()` and `driver_cancel_ride()` (modules/ride/
     router.py): after the ride is durably CANCELLED, restores any
     reservation it made. Fires `promotion.restored` (event-contracts.md
     §15.4).
   - Both are best-effort, past the point of no return — the ride's own
     status change is never blocked or rolled back by a promotion-
     resolution failure, matching every other post-commit composition
     in these same two endpoints (penalty release/settlement, matching
     cleanup).
2. **BR-065/066's early/late-cancellation boundary stays genuinely
   TBD** (business-rules.md §18/§19) — no threshold is invented. Every
   cancellation of a ride carrying a RESERVED reservation restores it
   unconditionally. This implements BR-065 in full (a customer never
   wrongly loses a use to a cancellation) while leaving BR-066's "a
   late cancellation instead consumes it" case unenforced until the
   boundary is actually decided — flagged here, not guessed at, the
   same discipline this codebase applies to every other genuinely-TBD
   business value (e.g. the Pickup PROCEED additional-charge
   placeholder, testing-strategy.md's own checklist).
3. **Close the row-lock gap**: `ReservationRepository` gains
   `get_by_id_for_update()` (same `.with_for_update()` pattern
   `EntitlementRepository`/`CampaignRepository` already use);
   `consume_reservation()`/`restore_reservation()` now lock the
   reservation before checking and changing its status, so a concurrent
   or replayed call against the same reservation_id is rejected with
   the ordinary `PromotionAlreadyUsedError` instead of racing to
   double-resolve it.

4. What was changed

Backend:
- `promotion/ports.py` — `get_by_id_for_update()` added to
  `ReservationRepository`.
- `promotion/repositories.py` — implemented in
  `SqlAlchemyReservationRepository`.
- `promotion/service.py` — `consume_reservation()`/`restore_reservation()`
  now lock the reservation first; two new methods,
  `consume_reservation_for_ride()`/`restore_reservation_for_ride()`.
- `ride/router.py` — `cancel_ride()`, `driver_cancel_ride()`,
  `complete_ride()` each gained a `promotion_service` dependency (and
  `complete_ride()` a `pricing_service` one, to read the final fare
  quote's `promotion_discount`); each now calls the corresponding
  `..._for_ride()` method in its existing best-effort block and appends
  the matching outbox event.

Tests (all real HTTP + real Postgres, not just PromotionService called
directly — the exact gap this ADR closes):
- `tests/test_ride_lifecycle_api.py` — four new tests: completion
  consumes a reserved promotion and writes a matching Usage row
  (`test_ride_completion_consumes_reserved_promotion_and_writes_usage`);
  completion with no reservation is a silent no-op
  (`test_ride_completion_with_no_promotion_reservation_is_a_silent_no_op`);
  customer cancellation restores it
  (`test_cancelling_an_accepted_ride_restores_its_reserved_promotion`);
  driver cancellation restores it
  (`test_driver_cancelling_a_ride_restores_its_reserved_promotion`).
- `tests/test_promotion_api.py` — two new real-concurrency tests proving
  the row-lock fix: `test_concurrent_restores_of_the_same_reservation_
  never_double_restore`, `test_concurrent_consumes_of_the_same_
  reservation_never_double_consume` (two real threads, two real DB
  sessions, racing the *same* reservation_id — exactly one resolves,
  `remaining_uses`/Usage-row-count proven not to double-move).
- `tests/test_promotion_service.py` — `FakeReservationRepository` gained
  `get_by_id_for_update()` (aliased to `get_by_id`, matching the
  existing fake-repository convention for entities with no real
  concurrency to simulate).

Full relevant suite (`test_promotion_api.py`, `test_promotion_service.py`,
`test_ride_lifecycle_api.py`, `test_ride_api.py`, `test_matching_api.py`,
`test_scheduled_ride_api.py`): 161 passed. `ruff`/`mypy` clean on every
touched file.

5. Verification against the user's exact checklist

- **When a promotion is consumed**: at ride completion
  (`complete_ride()`), with the real fare-quote discount — proven by
  `test_ride_completion_consumes_reserved_promotion_and_writes_usage`.
- **When it is restored after cancellation**: at both customer and
  driver cancellation, unconditionally (BR-065; BR-066's TBD boundary
  not invented) — proven by the two cancellation tests above.
- **Whether completion keeps it consumed**: yes — `remaining_uses` was
  already decremented at reserve time (ADR-0019, unchanged); consume
  never touches it again, only marks the reservation CONSUMED and
  writes the Usage row — proven by the same completion test asserting
  `remaining_uses == 2` (unchanged from reserve time) after consume.
- **Protection against double-consume**: `uq_promotion_ride_use`
  (database-level, pre-existing) plus the new reservation row lock
  (application-level, this ADR) — proven by
  `test_concurrent_consumes_of_the_same_reservation_never_double_consume`.
- **Protection against double-restore**: the new reservation row lock —
  proven by
  `test_concurrent_restores_of_the_same_reservation_never_double_restore`
  (the one case that had no pre-existing database-level backstop at
  all before this ADR).
- **Idempotency under retries**: a retried cancel/complete HTTP call
  cannot reach the promotion step twice for the same ride, because
  `RideService`'s own row lock and state machine reject a second
  cancel/complete of an already-cancelled/-completed ride before this
  code runs; a genuine replay at the PromotionService level (e.g. a
  future consumer retrying) is covered by the row-lock fix above.
- **Behavior under concurrent/replayed requests**: see the two new
  concurrency tests — exactly one resolution wins, the other observes
  `PromotionAlreadyUsedError`.
- **Preservation of promotion redemption/audit records**: unaffected —
  `promotion.usage`/`promotion.reservations` rows are never deleted or
  rewritten by this change, only actually populated for the first time
  through the real ride lifecycle instead of staying permanently
  RESERVED/absent.

6. What this ADR explicitly does not do

- Does not touch BR-063's discount cap (ADR-0049) or its 50%/₹100
  implementation — verified already correct, not re-implemented.
- Does not touch the referral domain in any way.
- Does not decide BR-065/066's early/late-cancellation boundary — still
  genuinely TBD, still not invented.
- Does not add a literal `/internal/promotions/...` HTTP endpoint —
  ADR-0019 Decision 3's reasoning (no service-authentication concept
  exists) is unchanged and still applies.
