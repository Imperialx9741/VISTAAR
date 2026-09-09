VISTAAR — E2E Journey Test Findings

Date: 2026-09-02
Scope: real HTTP (FastAPI `TestClient`) + real local Postgres + real local
Redis, per testing-strategy.md §4.4 ("Test complete journeys"). New test
files, not duplicating existing per-endpoint integration coverage:

- `apps/backend/tests/test_e2e_customer_driver_journey.py` — the User +
  Sarthi ride journey (§82's Happy Path, plus Pickup Change and
  Destination Change composed into the same chain).
- `apps/backend/tests/test_e2e_wallet_penalty_journey.py` — the Sarthi
  wallet/penalty journey (§84's Insufficient Wallet Path).
- `apps/backend/tests/test_e2e_admin_journey.py` — the Admin operator
  journey (driver/vehicle approval, ride search, penalty resolution,
  audit logging). No dedicated Admin journey exists in
  testing-strategy.md §82-90; this file's scope is composed from
  api-contracts.md/ADR-0023/ADR-0040's real documented admin
  capabilities instead of inventing one.

All 9 tests pass — 3 of them pass *because* they assert the real current
(gap-containing) behavior on purpose, not despite it; see §2 below. Full
backend suite: 1296 passed, 5 skipped, 0 failed (was 1287), ruff/mypy
clean.

This pass used the existing roadmap, ADRs, and `testing-strategy.md`
only — no new business-rule or architecture decision was made to get
these tests to pass. Every place a documented scenario didn't match the
real code, the test was changed to match the real code (and the
mismatch recorded below), never the other way around.

1. Summary

| # | Scenario | Result |
| :-- | :-- | :-- |
| 1 | Full ride journey (book → accept → arrive → OTP → start → complete → close) | **Passes** — no payment gate needed by design (§2.1, corrected 2026-09-02) |
| 2 | Pickup Change | **Passes** — testing-strategy.md §85/§86 describe a superseded design (§2.2) |
| 3 | Destination Change (BR-080, ₹8/km) | **Passes** as documented |
| 4 | Driver cancellation, sufficient wallet balance | **Passes** as documented (once a real interaction was accounted for) |
| 5 | Driver cancellation, insufficient wallet balance | **Passes** — asserting a real blocker, not the documented behavior (§2.3) |
| 6 | Wallet recharge | **Passes** as documented |
| 7 | Admin driver/vehicle approval + audit log | **Passes** as documented |
| 8 | Admin ride search + penalty resolution + audit log | **Passes** as documented |

2. Real gaps found (not previously documented anywhere)

2.1 [CORRECTED, NOT A GAP] No payment step exists between ride
completion and closing — this is intentional, not missing

**Correction, 2026-09-02, after this finding was first written**: this
was originally logged as a gap against testing-strategy.md §82's Happy
Path ("Ride completes → **Payment succeeds** → Ride closes"). That
framing was wrong. `ADR-0025` (2026-08-25) already established VISTAAR's
approved payment model is peer-to-peer: the customer pays the driver
directly (cash/UPI) for the ride fare, and VISTAAR is never in that
path at all — no ride-fare gateway exists, was ever built, or is
supposed to exist. Under that approved model, a ride correctly closes
the moment GPS-verified completion happens, with no payment gate in
between, because there is nothing for VISTAAR's backend to verify — the
fare payment happens entirely outside its systems. `security.md`'s own
§27-32 ("Payment Gateway Security" etc.) described the pre-ADR-0025
model this test's first draft was measured against; those sections have
since been annotated superseded/corrected (2026-09-02) to match. See
`docs/02-business/known-functional-gaps-2026-09-02.md` for the real,
narrower payment-related gaps that this correction leaves standing —
they are not "no payment gate," they are specific, smaller pieces (an
undisplayed outstanding-penalty total, and two still-undecided gateway
integrations for driver recharge and penalty collection).

One real, smaller, still-accurate observation survives this correction:
`payment_method` (submitted on Create Ride as `"UPI"`/`"CASH"` — how the
customer intends to pay the *driver*, not a VISTAAR gateway selection,
per ADR-0025's own re-scoping of this field) is not even a column on
`ride.rides` — a real Postgres query for it fails with `UndefinedColumn`.
It is validated at the API boundary (`validate_payment_method()`) and
then discarded; the mobile app collects it but never displays it to the
driver either (checked directly against
`lib/features/rides/ride_offer_screen.dart`/`ride_execution_screen.dart`
— no reference anywhere). Whether this field is meant to inform the
driver what to expect, or is genuinely vestigial now, is not resolved
anywhere in the documentation set — flagged in
`known-functional-gaps-2026-09-02.md`, not decided here.

2.2 [DOCUMENTATION DRIFT] Pickup Change's testing-strategy.md scenarios
describe a design ADR-0056 already replaced

testing-strategy.md §85 ("Pickup Change PASS") and §86 ("Pickup Change
PROCEED") describe a driver PASS/PROCEED decision with a ₹10-20/km
charge for a >250m pickup change. ADR-0056 (2026-08-31, owner decision)
replaced this design before these tests were written — confirmed
directly against `modules/ride/router.py`'s `request_pickup_change()`
docstring: there is no driver decision step anymore at all. The real
current behavior, confirmed by running it: a change within the real
configured threshold (`RIDE_PICKUP_CHANGE_THRESHOLD_METERS`, 100m
default) applies immediately and free; beyond it, the request is
rejected outright (`PICKUP_CHANGE_TOO_FAR`) — the customer must cancel
and rebook.

This is not a code defect — ADR-0056 is a real, approved, intentional
change. It is `testing-strategy.md` that is now stale for §85/§86
specifically. **Not fixed here** (updating that document's own §85/§86
text is a small follow-up, not done in this pass, since this E2E pass's
job was building and running tests against the real system, not
auditing the rest of `testing-strategy.md` for other possible drift —
see §4).

2.3 [BLOCKER] A driver with an insufficient wallet balance cannot
cancel a ride at all — worse than either spec describes

Both `security.md` §25 ("Negative Wallet Protection") and
`testing-strategy.md` §84 ("End-to-End Insufficient Wallet Path")
describe the *same* intended behavior for this exact numeric scenario
("VISTAAR charge = ₹30, driver wallet = ₹10" → "₹10 debit, ₹20
outstanding"). Running the real equivalent scenario against real
Postgres shows this is not what happens:

- `WalletService.debit()` (`modules/wallet/service.py`) has no
  partial-debit/outstanding-balance code path at all. An insufficient
  balance raises `InsufficientWalletBalanceError` outright.
- `driver_cancel_ride`'s handler (`modules/ride/router.py`) wraps the
  ride-status transition *and* the penalty debit in a single `try`
  block. The debit failure is caught as a `WalletDomainError` and the
  entire cancellation — including the ride-status transition that had
  already succeeded moments earlier in the same call — is rolled back.

**Confirmed real, concrete consequence**: a driver whose wallet can't
cover the ₹30 cancellation penalty cannot cancel the ride at all. The
ride stays stuck ACCEPTED; no strike is recorded either, since the whole
call failed. This is worse than the documented "partial debit, track
the rest as outstanding" design — not merely a different implementation
of the same intent.

**Not fixed here.** Two real, materially different designs would both
satisfy the spirit of the two source documents, and choosing between
them is a genuine business-rule decision, not a bug with one obvious
fix:

- Keep blocking the cancellation entirely until the balance is
  sufficient (closer to today's real behavior, just made intentional
  and given a clearer error/UX instead of an opaque 409).
- Build the documented partial-debit-plus-outstanding-balance mechanism
  security.md §25/§26 actually describe (a real, non-trivial addition:
  `WalletService` would need a new method, `wallet.wallets` or a new
  table would need an "outstanding" concept to track and later recover
  from a recharge, and `driver_cancel_ride` would need to stop treating
  a partial debit as a failure).

`apps/backend/tests/test_e2e_wallet_penalty_journey.py::test_driver_cancellation_with_insufficient_balance_is_a_documented_blocker`
asserts the real, current (blocked) behavior on purpose — a future fix,
whichever design is chosen, will make this specific test fail, which is
the intended signal that it needs updating to match the new behavior,
not a silently-passing gap.

3. Real interactions discovered only by actually running the tests, not
   from reading code alone

- Accepting a ride offer already debits a real CAB platform fee (₹10,
  `_PLATFORM_FEE_BY_CATEGORY` in `modules/matching/router.py`) —
  independent of, and prior to, any later driver-cancellation penalty
  debit. The first draft of the wallet journey test's balance-arithmetic
  assumptions were wrong until this was accounted for (₹100 seeded →
  ₹90 after accept → ₹60 after a ₹30 cancellation penalty, not ₹70).
- `MatchingService`'s dispatch does not exclude a driver still marked
  ONLINE just because they already accepted a different ride — accepting
  an offer doesn't remove that driver from the Redis geo index. A test
  that creates two online drivers in sequence without explicitly taking
  the first one offline will nondeterministically have the second ride's
  offer routed to the wrong (already-busy) driver. This is the same
  class of issue `test_ride_lifecycle_api.py`'s own cleanup fixture
  already documents for stale drivers *across test runs*; this pass
  confirms it also applies *within* a single test that intentionally
  creates more than one online driver, which no existing test in this
  codebase happened to do before.
- The `pricing.fare_quotes`/`ride.change_requests` schema's real field
  and enum-value names differ from what a first-draft test guessed
  before checking (`new_fare_quote_id` not `fare_quote_id`,
  `DESTINATION_CHANGE` not `DESTINATION`,
  `AWAITING_CUSTOMER_CONFIRMATION` not `PENDING`) — all fixed by reading
  the real model/entity source rather than assumed from the response
  shape alone.

4. Not covered by this pass

- `testing-strategy.md` §83 ("End-to-End Offline Payment Path") and §88
  ("End-to-End Early Drop")/§89/§90 (GPS dispute paths) are not
  exercised here. §83 is not implementable at all (§2.1 — no payment/
  cash-confirmation module exists). Early Drop and GPS Dispute already
  have their own dedicated integration coverage
  (`test_early_drop_api.py`/`test_gps_dispute_api.py` — not duplicated
  here, per this document's own opening scope note).
- `testing-strategy.md` §85/§86's own text was not corrected in this
  pass (§2.2) — flagged, not silently left stale forever, but a
  documentation edit outside what "build and run E2E tests" covers.
- No browser-driven Admin Web UI journey — this project's testing
  strategy documents E2E as journeys through the API layer (§4.4's own
  wording: "Customer books → Driver accepts → ..."), and no browser
  automation framework (Playwright/Cypress/Selenium) is present anywhere
  in `apps/admin-web`'s own dependencies. Introducing one would itself
  be a new, undiscussed tooling decision — out of scope for this pass,
  which used only the existing roadmap and ADRs.
- Mobile app UI journeys — no physical Android device/emulator is
  available in this environment (already established during the native
  Contacts picker work), and no macOS/Xcode exists for iOS. The API
  layer both the User and Sarthi mobile apps actually call is the same
  layer these E2E tests exercise directly.
