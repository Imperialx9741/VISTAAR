ADR-0024 — Get Ride Status and Wallet Transaction History Scope

Status: Accepted
Date recorded: 2026-08-25
Deciders: Autonomous implementation (phase-level owner authorization —
see the standing execution agreement).

1. Context

Two small, real, fully-documented-but-unbuilt endpoints remained
unblocked after Phase 16 (ADR-0023): Phase 04's "GET ride status"
(api-contracts.md §13, `GET /api/v1/rides/{ride_id}`) and Phase 11's
"Financial audit trail" — traced, via modules/wallet/__init__.py's own
explicit "does NOT implement" list, to api-contracts.md §34's "Wallet
Transactions" (`GET /api/v1/drivers/me/wallet/transactions`). Both were
listed together as execution-plan RECOMMENDED EXECUTION ORDER item 10.
Neither needed new domain/service logic — `RideService.get_ride()`
already existed internally (added Phase 3 / Task 3.2 for matching's own
use) and `wallet.transactions` rows already exist and are fully
populated by `debit()`/`credit()` — only the read paths and response
shapes needed building.

2. Decision 1 — Get Ride (customer/driver)

`GET /api/v1/rides/{ride_id}` lives on `modules/ride/router.py`
(`/api/v1/rides` prefix), authenticated via a new `require_customer_or_
driver` dependency (`require_account_type(CUSTOMER, DRIVER)` —
`require_account_type` already supported multiple allowed types; only a
named constant was missing). Ownership check per §13's own text
("Customer may access their own ride. Driver may access rides assigned
to them."): `ride.customer_id == account.id` for a CUSTOMER,
`ride.driver_id == account.id` for a DRIVER; anything else raises
`RideNotFoundError` — the same "same response for missing and
unauthorized" IDOR-safe pattern used everywhere else in this codebase
(cancel_ride, driver_cancel_ride, SOS, Support Case).

This is a DIFFERENT endpoint from the admin-only `GET
/api/v1/admin/rides/{ride_id}` ADR-0023 built (no ownership restriction,
admin-only, lives on modules/admin/router.py) — the two happen to share
a resource but not an audience, a route, or a response shape.

§13's documented response names `driver`/`vehicle`/`fare`/`payment`
sub-objects with empty placeholders (`{}`), no fields specified. Filled
in as implementation decisions:

- `driver`: `null` if `ride.driver_id` is unset (still SEARCHING),
  otherwise `{driver_id, full_name, profile_photo_uri}` — composed via
  `DriverService.get_profile()`. Deliberately excludes phone number: no
  source document anywhere describes a masked-calling feature or any
  other justification for exposing a driver's raw phone number to a
  customer, and this codebase has no telephony provider/credential to
  mask it through even if it did — the same "don't invent an
  undocumented, privacy-sensitive shape" discipline used throughout.
- `vehicle`: `null` if `ride.vehicle_id` is unset, otherwise
  `{vehicle_id, category, registration_number, make, model}` — composed
  via `VehicleService.get_vehicle(driver_id=ride.driver_id,
  vehicle_id=ride.vehicle_id)`. This reuses the existing
  ownership-checked method as-is (no new vehicle-lookup-by-id-alone
  method needed): the ride's assigned vehicle is owned by the ride's
  assigned driver by construction (`AssignDriver`/`accept_ride()` sets
  both together, ADR-0011 Decision 3), so this can never legitimately
  fail once `ride.driver_id`/`vehicle_id` are both set.
- `fare`: same shape and same `PricingService.get_fare_quote()`
  composition ADR-0023 already established for the admin Get Ride
  endpoint — `null` if `ride.active_fare_quote_id` is unset.
- `payment`: always `null`. No Payment domain/module exists anywhere in
  this codebase (Phase 10, payment gateway, fully blocked — no
  credential, no provider decision). This is the same class of decision
  ADR-0010 Decision 1 made for `fare: null` before Pricing existed
  (later resolved by ADR-0020) — an honest "genuinely unknown" value,
  not a fabricated shape.

3. Decision 2 — Wallet Transactions (driver, own wallet only)

`GET /api/v1/drivers/me/wallet/transactions` lives on
`modules/wallet/router.py`, `require_driver`-gated, no ownership
ambiguity (always the caller's own `driver_id`, same as Get Wallet).
Paginated per §50 (reusing `shared/pagination.py`, ADR-0023) with the
two documented filters: `page`/`page_size` and `type` — `type` is
validated against the documented `TransactionType` enum
(database-design.md §17.2), `VALIDATION_FAILED` for an unrecognized
value, same treatment ADR-0023 gave Search Rides'/Search Penalties'
`status` filters.

Response item shape (undocumented beyond the route + query params):
`transaction_id`, `ride_id`, `transaction_type`, `amount`, `direction`,
`balance_before`, `balance_after`, `reference_type`, `reference_id`,
`created_at`. `reference_type`/`reference_id` are included (unlike the
admin Penalty response, which omits internal plumbing) because they are
exactly what makes this "the audit trail": a driver seeing a
`FEE_REVERSAL` credit can see which original `PLATFORM_FEE` debit it
reverses. `idempotency_key` and `metadata` are excluded — the former is
request-deduplication plumbing with no meaning to a driver reading their
own ledger, the latter is currently never populated by anything in this
codebase (every `WalletService.debit()`/`credit()` call site passes
`metadata=None`).

`WalletRepository.list_transactions()` is a new, purely additive port
method (`ORDER BY created_at DESC`, offset/limit) — it does not touch
`debit()`/`credit()`/the existing `get_debit_for_ride()`/
`get_transaction_by_idempotency_key()` reads at all.

4. Consequences

Both endpoints are pure reads with no new domain logic, no new table,
no new migration, and no new outbox event (neither is a state
transition). Phase 04 has no remaining unblocked task after this (its
only other gap, Phase 06's `ACCEPTED → ARRIVED`, stays blocked on the
GPS radius). Phase 11's remaining gaps (Outstanding balance, Recharge,
Outstanding recovery, Penalty expiry collection) all still depend on the
Phase 10 payment gateway decision or a background-worker foundation
decision neither of which this task resolves.
