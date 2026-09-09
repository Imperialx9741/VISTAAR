ADR-0057 — Schedule a Ride & Book for Someone Else: Design and Scope

Status: Accepted — owner confirmed via "continue," 2026-08-31
Date recorded: 2026-08-31
Deciders: Owner, via a structured two-round clarification exchange in
the VISTAAR session, 2026-08-31 (this is a genuinely new ride-domain
capability — a ride that exists before it enters `SEARCHING`, and a
ride whose rider isn't its own customer — so it needs its own ADR
before any backend contract is written, the same gate every other new
capability in this project has gone through, most recently ADR-0056).

1. Context

Both features were added to scope by the owner on 2026-08-29 (PRD §57
separately approves "Scheduled rides" beyond MVP; "Book for Someone
Else" isn't named anywhere in the PRD or business-rules.md at all).
`docs/16-mobile/mobile-app-implementation-plan.md` §4.10/§4.11 scoped
what was already decidable that day and flagged the rest as open
questions, deliberately not guessed past. Two rounds of owner-supplied
answers, 2026-08-31, resolve nearly all of them; this ADR records those
answers as the authoritative design and reconciles them against
`ride.rides`'s actual schema, `state-machines.md`'s actual FSM, and
`api-contracts.md`'s actual Create Ride / Customer Cancellation
contracts — not a new domain invented from scratch.

2. Decision 1 — Schedule a Ride: a new `SCHEDULED` ride state, matched
   close to pickup time, fare locked at booking

`RideStatus` (`modules/ride/domain/entities.py`) gains `SCHEDULED`,
entered instead of `SEARCHING` when a customer's Create Ride request
names a future pickup time. `state-machines.md` §3.1/§3.2 gain:

    SCHEDULED → SEARCHING   (automatic, driver lock-in window reached)
    SCHEDULED → CANCELLED   (customer cancels before lock-in)

Once a `SCHEDULED` ride transitions to `SEARCHING`, it re-enters the
existing SEARCHING → ACCEPTED → ... lifecycle completely unchanged —
no new offer type, no new matching logic. This directly delivers the
owner's "lock in close to pickup time, with automatic rematch if the
driver can't make it" answer for free: SEARCHING's existing matching
loop already re-offers to the next eligible driver if one rejects or
lets an offer expire, and already has no upper bound on how long it
stays SEARCHING if nobody accepts — which is also exactly the owner's
"same retry/fare-increase flow as an immediate ride" answer for
no-driver-found. Nothing new needs to be built for either; both are
consequences of "become an ordinary SEARCHING ride" being the entire
mechanism.

Schema additions (`ride.rides`, additive, non-breaking):

- `scheduled_for TIMESTAMPTZ NULL` — the customer-chosen future pickup
  time. `NULL` for every ride created today (an immediate ride) —
  zero behavior change to the existing flow.
- `lock_in_at TIMESTAMPTZ NULL` — computed at creation as
  `scheduled_for - 30 minutes` and stored (not computed on read), so
  the polling task below can index and query it cheaply. 30 minutes is
  an engineering choice for "close to pickup time," not a value the
  owner specified — flagged as such, easy to change later without a
  schema migration.
- `linked_contact_name`, `linked_contact_phone` — see Decision 2;
  listed here only because both features touch the same table.

New Celery Beat task (`modules/ride/tasks.py`, registered in
`shared/celery_app.py`'s `beat_schedule`), the same shape as ADR-0055's
`send_scheduled_broadcasts` — polling every 5 minutes
(`crontab(minute="*/5")`) for `SCHEDULED` rides where `lock_in_at <=
now()`, transitioning each to `SEARCHING` and calling the same
`MatchingService` composition `POST /api/v1/rides` already calls today.
A 5-minute poll granularity against a 30-minute lock-in window means a
ride could start matching up to ~5 minutes later than the window's own
edge — accepted for the same "correct first, not the fastest possible"
reason ADR-0055 accepted it for broadcasts.

Fare locked at booking time — reuses the existing `pricing.fare_quotes`
table (`database-design.md` §15.2) exactly as it already exists, no new
domain object, and no new `reason` value either: `modules/ride/
router.py`'s Create Ride endpoint already calls
`PricingService.calculate_fare()` unconditionally right after the ride
is created, regardless of status, always producing `reason =
'INITIAL_QUOTE'`. A SCHEDULED ride's quote is simply that same,
already-unconditional call happening at scheduling time instead of at
an immediate ride's own `SEARCHING` entry — `ride.rides.
active_fare_quote_id` is set the same way either way. The locked total
is what's returned in Create Ride's response and is never recomputed,
even if `pricing.fare_rules` changes between booking and pickup.

Scheduling window: 1 hour minimum lead time, 24 hours maximum —
`VALIDATION_FAILED` outside that range. Both are engineering defaults
the owner approved as a starting point, not independently re-derived
business values; revisit if real usage shows they're wrong.

Cancellation (`POST /api/v1/rides/{ride_id}/cancel`, `modules/ride/
service.py`'s `cancel_ride()`): the existing SEARCHING/ACCEPTED/ARRIVED
gate (`api-contracts.md` §19) gains `SCHEDULED`. A `SCHEDULED`
cancellation is charged against `scheduled_for` (not `accepted_at` —
there is no driver yet), with its own rule, distinct from BR-046-049
(which presuppose a driver was already assigned, per ADR-0012's own
clarification):

- `>=` 3 hours before `scheduled_for`: ₹0.
- `<` 3 hours before `scheduled_for`: ₹30.
- No `penalty.strikes` row either way — this is a different (advance-
  notice) failure mode than an ordinary last-second cancellation or a
  driver-side cancellation, and the owner's answer explicitly chose not
  to conflate the two.

New `PenaltyType.SCHEDULED_RIDE_LATE_CANCELLATION` value
(`modules/penalty/domain/entities.py`), parallel to the existing
`CUSTOMER_CANCELLATION` — a `penalty.penalties` row is created only for
the `<3h`/₹30 case (mirroring ADR-0015 Decision 1's "no row at all for
a ₹0 charge" treatment already given to the grace-period case). Once a
`SCHEDULED` ride has already transitioned to `SEARCHING` (past
lock-in), this rule no longer applies — an ordinary SEARCHING
cancellation is free per the existing, unchanged rule, since a driver
still hasn't been assigned yet either way.

A genuinely new gap this surfaces, in scope for this ADR to name (not
silently build around): there is no `GET /api/v1/rides` "list my
rides" endpoint anywhere in the backend today (verified — `modules/
ride/router.py` has only `GET /{ride_id}`, never a collection route).
"Confirm/view a scheduled ride ahead of time" is only actually usable
if the customer can browse their upcoming scheduled rides without
independently remembering a `ride_id` — booking a ride and immediately
being shown its detail (today's mobile flow) covers the moment of
booking, but not coming back later. This ADR's scope therefore includes
one new endpoint: `GET /api/v1/rides?status=SCHEDULED` (paginated,
`shared/pagination.py`'s existing envelope, the caller's own rides
only), the minimum needed to make this feature actually usable, not a
general-purpose ride-history browser.

3. Decision 2 — Book for Someone Else: a linked contact, booker-billed
   by default, no rider-facing view yet

`ride.rides` gains `linked_contact_name VARCHAR(200) NULL` and
`linked_contact_phone VARCHAR(20) NULL` — both `NULL` for an ordinary
self-booked ride (zero behavior change), both required together when
the booker names someone else. The contact is picked from the booker's
own phone contacts client-side (already resolved 2026-08-29) — VISTAAR
never receives more than the one name/phone pair submitted with that
booking (already-documented Contacts-permission scope,
`mobile-app-implementation-plan.md` §6.2). Storing the name alongside
the phone (not just the phone) was the smaller of two remaining
implementation choices this ADR resolves without a fresh owner
question: it costs nothing beyond what the Contacts permission already
grants access to, and lets the driver's own app show "picking up
Priya" instead of a bare phone number once that's wired in — a
reasonable default, flagged here rather than asked, open to override.

Ride-start OTP delivery (`modules/ride/service.py`'s OTP-generation
path, `api-contracts.md` §18): when `linked_contact_phone` is set, the
OTP is sent via the existing MSG91 SMS channel to both the booker and
the linked contact — already resolved 2026-08-29, restated here as
this ADR's authoritative record. No in-app delivery to the contact,
since the contact isn't required to have a VISTAAR account at all.

Billing: the booker's existing payment method (`api-contracts.md`
§4.5) is charged by default. The owner's answer also allows the rider
to pay the driver cash on the spot instead — but `POST .../cash-
payment/confirm` (`api-contracts.md` §33) does not exist anywhere in
the live backend today (confirmed by grepping the whole backend source
this same session, during mobile build order step 5) — §33's own text
already says "Not built today." This ADR does not invent that endpoint
just to unblock Book for Someone Else's cash path; until it's built
(its own separate, already-tracked gap), Book for Someone Else ships
with the booker-billed path only, and the cash-on-spot option is a
documented target, not something this app can offer yet.

Rider visibility: booker-only for this first version — the linked
contact receives only the pickup OTP by SMS, no read-only ride view.
Explicitly deferred to whenever Ride Sharing (`api-contracts.md` §42,
already a separate unbuilt row in the mobile plan) exists, rather than
building a one-off partial version of it here.

Promotions/referral eligibility (proposed default, not asked directly,
flagged as open to override): welcome/referral discounts apply against
the booker's own account, since the booker is billed and is `ride.rides
.customer_id` — the account of record for every other purpose this
feature touches. No schema change needed either way; this only affects
which `customer_id` `PromotionService` checks at ride-creation time,
already the booker's, unchanged.

4. api-contracts.md additions

`POST /api/v1/rides` (§12) gains two optional fields:

    {
      "pickup": {...}, "destination": {...},
      "vehicle_category": "CAB", "cab_tier": "ECO",
      "payment_method": "UPI",
      "scheduled_for": "2026-09-01T14:00:00Z",
      "linked_contact": {"name": "Priya Singh", "phone": "+91..."}
    }

Both independent of each other — a ride can be scheduled, booked for
someone else, both, or neither (today's behavior). When `scheduled_for`
is present, the response's `"status"` is `"SCHEDULED"` instead of
`"SEARCHING"`, and `"fare"` reflects the locked quote.

New `GET /api/v1/rides?status=SCHEDULED` (§12, new subsection) —
paginated, the caller's own rides only, same envelope shape
`shared/pagination.py` already establishes elsewhere.

`POST /api/v1/rides/{ride_id}/cancel` (§19) documents the new
`SCHEDULED`-sourced charge shape: `{"amount": 0 or 30, "currency":
"INR", "penalty_id": "uuid" or null}` (no `expires_at` field — BR-049,
corrected 2026-09-04, ADR-0069: customer penalties never expire), same
shape §19 already uses for the post-acceptance case, just sourced from
`scheduled_for` instead of `accepted_at`.

5. domain-design.md / event-contracts.md additions

New commands: `ScheduleRide` (composed into the extended `POST
/rides`), `PromoteScheduledRideToSearching` (the Beat task's own
composition point — not customer- or driver-triggered). New event:
`ride.schedule_promoted` (`{"ride_id", "promoted_at"}`), fired when a
`SCHEDULED` ride transitions to `SEARCHING`, mirroring
`ride.requested`'s existing shape for an immediate ride's own entry
into `SEARCHING`.

6. Consequences

- Zero new matching/offer engineering — the entire "reserve a driver
  in advance" behavior the owner asked for is delivered by re-entering
  the existing, unchanged SEARCHING flow at the right moment. This was
  the single biggest complexity reduction found while reconciling the
  owner's answers against the actual matching code, worth stating
  explicitly since the original open-questions list (mobile plan
  §4.10) implied this might need a genuinely new offer type.
- The `GET /api/v1/rides` list endpoint this ADR adds is a real, if
  small, new capability beyond what Decision 1 strictly requires —
  flagged rather than silently included, since it's the kind of thing
  a reviewer might reasonably want scoped out or built differently
  (filters, sort order, whether it should support immediate rides too)
  before implementation starts.
- Book for Someone Else ships without its own cash-payment path until
  `cash-payment/confirm` exists — an already-tracked, unrelated gap,
  not a new one this ADR creates.
- No change to any already-shipped behavior: every new column is
  nullable and defaults to the immediate-ride/self-booked case exactly
  as it works today.

7. Still open, deliberately not resolved here

- The exact wording/UX of the "1 hour minimum, 24 hour maximum"
  scheduling-window error message, and whether either bound should be
  admin-configurable later (matching this codebase's established
  pattern for fees/templates/platform-fee configurability) rather than
  a hard-coded constant — an engineering-scope call for implementation
  time, not a business-rule question.
- Whether `GET /api/v1/rides` should eventually grow into a general
  ride-history browser (all statuses, not just `SCHEDULED`) — out of
  scope for this ADR, which adds only what Schedule a Ride needs to be
  usable.

8. Implementation (backend), 2026-08-31

Migration `a3f7c8d1e2b4` (four additive/nullable `ride.rides` columns +
`idx_rides_lock_in_at`). `modules/ride/domain/entities.py` —
`RideStatus.SCHEDULED`, `validate_scheduled_for()`,
`validate_linked_contact()` (reuses `modules.identity.domain.
phone_number.PhoneNumber`, translated to `InvalidLinkedContactError` so
every error this module raises stays a `RideDomainError`), `Ride.new()`
extended. `modules/ride/domain/errors.py` — `InvalidScheduledForError`,
`InvalidLinkedContactError`, `ScheduledRideNotFoundError`.
`modules/ride/service.py` — `create_ride()` extended,
`promote_scheduled_ride_to_searching()` added, `cancel_ride()`'s status
gate extended. `modules/ride/ports.py`/`repositories.py` —
`list_due_scheduled()`. `modules/ride/router.py` — `GET ""` (List My
Rides), `POST ""` extended (skips matching dispatch for a `SCHEDULED`
ride — `calculate_fare()` already ran unconditionally, so fare-locking
needed no new code at all), `POST .../cancel` extended
(`_scheduled_ride_cancellation_charge()`), `POST .../otp/refresh`
extended (SMS to `linked_contact_phone` via the already-built
`SmsProvider.send_otp()`, composed into this endpoint for the first
time). New `modules/ride/tasks.py` (`promote_due_scheduled_rides`,
registered in `shared/celery_app.py`'s `beat_schedule`, polling every 5
minutes). `modules/penalty/domain/entities.py` —
`PenaltyType.SCHEDULED_RIDE_LATE_CANCELLATION`,
`Penalty.new_scheduled_ride_late_cancellation()`.
`modules/penalty/service.py` —
`record_scheduled_ride_late_cancellation()`.

One design detail resolved only once the actual OTP/pricing code was
read (not decided in the sections above, which is why this section
records it): fare-locking needed no new `pricing.fare_quotes.reason`
value — `calculate_fare()` already runs unconditionally right after
ride creation and always produces `reason = 'INITIAL_QUOTE'`; a
SCHEDULED ride's quote is simply that same call happening earlier.
`database-design.md` §15.2 was corrected to match (it briefly proposed
a new reason value before this was checked against the real code).

35 new tests (29 domain unit tests in `test_ride_domain.py`; 14
real-Postgres integration tests in a new `test_scheduled_ride_api.py`,
including `GET /rides/{ride_id}` now also returning `scheduled_for`
(§9 below); 4 real-Postgres+Redis integration tests in a new
`test_ride_tasks.py`; 2 in `test_ride_lifecycle_api.py` for the
linked-contact OTP SMS) — full backend suite 1279 passed, 5 skipped
(Kafka-connectivity-only, pre-existing), 0 failed (was 1244), ruff and
mypy clean across `src/`/`tests/`.

9. Implementation (mobile), 2026-08-31, same day

`RideApi.createRide()` extended with `scheduledFor`/`linkedContact`;
new `RideApi.listMyRides()` + `RideListItem`/`RideListPage`. Also
found needed once the ride-detail screen was actually being built (not
scoped in the sections above): `GET /rides/{ride_id}`'s own response
didn't carry `scheduled_for` at all — added to
`_ride_status_data()`/`RideStatusDetail` and documented in
api-contracts.md §13, with two more backend tests.

`BookRideScreen` gained a **Schedule for later** toggle (`showDatePicker`
+ `showTimePicker`, both already part of Flutter — no new package) and
a **Book for someone else** toggle (plain name/phone `TextFormField`s).
A native Contacts picker was deliberately not added: that's real,
separately-scoped work needing a new pub dependency
(`flutter_contacts` or equivalent) plus new native Android/iOS
permission entries this environment cannot verify against a real
device — `mobile-app-implementation-plan.md` §6.2 already documents
manual entry as this feature's own "if denied" fallback; it's used
here as the primary (and only) path for this increment, flagged rather
than silently built as if it were the full-picker version.

New `ScheduledRidesScreen` (paginated `GET /api/v1/rides?
status=SCHEDULED`), reached from a new icon on `UserHomeScreen`.
`RideStatusScreen` needed only its status-label map and cancel-status
set extended — SCHEDULED display, cancellation (BR-135's ≥3h/₹0-<3h/
₹30 charge, surfaced through the exact same `Cancel Ride` button and
response-shape handling ACCEPTED/ARRIVED already use), and Contact
Support/SOS gating all fell out of code that already existed for every
other ride status.

11 new mobile tests across `book_ride_screen_test.dart` (4),
`ride_status_screen_test.dart` (2), and a new
`scheduled_rides_screen_test.dart` (5) — `flutter analyze` clean,
`flutter test` 101/101 passed (was 90).

Both halves of this ADR — backend and mobile — are now fully shipped.
