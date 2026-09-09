VISTAAR — State Machines

Document Version: 1.0
Status: Draft
API Version: v1
Database: PostgreSQL + PostGIS
Event Transport: Kafka

1. Purpose

This document defines the authoritative state machines for VISTAAR.

A state machine specifies:

Valid states

Allowed transitions

Transition actor

Required conditions

Side effects

Events emitted

Invalid transitions

The backend must enforce these transitions.

The mobile applications must never directly set authoritative state.

2. General State-Machine Rule

Every state-changing command follows:

Request
  ↓
Authenticate
  ↓
Authorize
  ↓
Read current state
  ↓
Validate transition
  ↓
Validate business rules
  ↓
Perform transaction
  ↓
Write state history
  ↓
Write outbox event
  ↓
Commit

Invalid transitions return:

409 INVALID_STATE_TRANSITION

3. Ride State Machine

3.1 States

SCHEDULED (IMPLEMENTED — ADR-0057, 2026-08-31 — see the note below)
SEARCHING
ACCEPTED
ARRIVED
STARTED
COMPLETED
CANCELLED
CLOSED

SCHEDULED is entered instead of SEARCHING when Create Ride (§12) names
a future pickup time (Schedule a Ride, mobile-app-implementation-plan.md
§4.10). It exists only for a ride that hasn't begun matching yet — a
ride never returns to SCHEDULED once it leaves it.

3.2 Main Lifecycle

SCHEDULED (optional — only for a scheduled ride)
    ↓
SEARCHING
    ↓
ACCEPTED
    ↓
ARRIVED
    ↓
STARTED
    ↓
COMPLETED
    ↓
CLOSED

Cancellation can occur only in permitted pre-completion states.

SCHEDULED ─────→ SEARCHING (automatic, driver lock-in window reached —
    ADR-0057 Decision 1; not customer- or driver-triggered)
SCHEDULED ─────→ CANCELLED
SEARCHING ─────→ CANCELLED
ACCEPTED ───────→ CANCELLED
ARRIVED ────────→ CANCELLED
STARTED ────────→ CANCELLED only through approved exceptional flows

3.9 Ride: SCHEDULED (IMPLEMENTED — ADR-0057, 2026-08-31)

Decimal-numbered to avoid renumbering §4-10 below, which predate this
state.

Entered when

Customer's Create Ride request (§12) names a future `scheduled_for`
pickup time, 1-24 hours ahead (BR-137).

Allowed transitions

SCHEDULED → SEARCHING (automatic, not customer- or driver-triggered —
see below)
SCHEDULED → CANCELLED

Not allowed

SCHEDULED → ACCEPTED
SCHEDULED → ARRIVED
SCHEDULED → STARTED
SCHEDULED → COMPLETED
SCHEDULED → CLOSED

Side effects

A `pricing.fare_quotes` row is created and locked at this point
(ADR-0057 Decision 1) — the fare shown for this ride never changes
after this, regardless of any later `pricing.fare_rules` change.

No matching begins yet. A scheduled Celery Beat task (polling every 5
minutes, mirroring ADR-0055's `send_scheduled_broadcasts`) transitions
the ride to SEARCHING once `scheduled_for - 30 minutes` (`lock_in_at`)
is reached — from that point on, this ride follows the ordinary
SEARCHING → ACCEPTED → ... lifecycle unchanged; no new offer type or
matching logic exists for it.

Cancelling while still SCHEDULED is charged against `scheduled_for`
itself (BR-135) — ≥3 hours before: ₹0; <3 hours before: ₹30; no
strike either way, distinct from BR-046-049 which only ever apply once
a driver has been assigned.

Event:

ride.requested (fired at SCHEDULED entry, same shape as an immediate
ride's own SEARCHING entry — ADR-0057)
ride.schedule_promoted (fired at SCHEDULED → SEARCHING,
`{"ride_id", "promoted_at"}`)

4. Ride: SEARCHING

Entered when

Customer successfully requests a ride — or, for a ride created as
SCHEDULED (§3.9, ADR-0057), automatically once its driver lock-in
window is reached. Both paths converge on the same SEARCHING state;
nothing below this point distinguishes how it was reached.

Allowed transitions

SEARCHING → ACCEPTED
SEARCHING → CANCELLED

Not allowed

SEARCHING → ARRIVED
SEARCHING → STARTED
SEARCHING → COMPLETED
SEARCHING → CLOSED

Side effects

Matching begins

Ride offer may be created

Customer sees searching state

Event:

ride.requested

5. Ride: ACCEPTED

Entered when

An eligible driver accepts a valid, unexpired offer.

Required:

Offer = PENDING
Offer not expired
Ride = SEARCHING
Driver eligible
Vehicle eligible
Required platform fee secured

Allowed

ACCEPTED → ARRIVED
ACCEPTED → CANCELLED

Not allowed

ACCEPTED → STARTED
ACCEPTED → COMPLETED
ACCEPTED → CLOSED

until the required intermediate transitions occur.

Event:

ride.accepted

6. Ride: ARRIVED

Entered when

Driver reaches the pickup area and server GPS verification succeeds.

Required:

Ride = ACCEPTED
Driver = assigned driver
GPS verification = PASS

Allowed

ARRIVED → STARTED
ARRIVED → CANCELLED

Event:

ride.arrived

7. Ride: STARTED

Entered when

Driver submits the correct ride OTP.

Required:

Ride = ARRIVED
OTP valid
OTP not expired
OTP attempt limit not exceeded

Allowed

STARTED → COMPLETED
STARTED → CANCELLED

Cancellation after STARTED is restricted to explicitly supported exceptional flows.

Event:

ride.started

8. Ride: COMPLETED

Entered when

Driver requests completion and destination GPS verification succeeds.

Required:

Ride = STARTED
GPS verification = PASS

Allowed

COMPLETED → CLOSED

Not allowed

COMPLETED → STARTED
COMPLETED → CANCELLED
COMPLETED → ARRIVED

Event:

ride.completed

9. Ride: CANCELLED

Terminal operational state.

No normal ride transition is allowed out of:

CANCELLED

Payment, penalty, promotion restoration, or settlement workflows may continue asynchronously.

10. Ride: CLOSED

Final ride state.

Entered after:

COMPLETED

and the ride-closing workflow has completed.

No ride state transitions are allowed after:

CLOSED

Financial corrections must use compensating transactions rather than changing the historical ride state.

Implementation status (§6-10, Phase 06/07, ADR-0028): COMPLETE —
api-contracts.md §17/§18/§28. "The ride-closing workflow" above is
implemented as automatic/immediate: a successful Ride Completion call
(§28) transitions STARTED → COMPLETED → CLOSED within the same request,
not as a separate later step or async process — ADR-0028 found no
documented precondition anywhere that would ever gate COMPLETED →
CLOSED on anything else, so none was invented. Two ride.state_history
rows are still written (one per step) even though both happen together.
No ride.closed event exists in event-contracts.md, so none is published.

11. Ride Cancellation State Rules

Customer cancellation

SEARCHING → CANCELLED
ACCEPTED → CANCELLED
ARRIVED → CANCELLED

subject to the applicable cancellation rules.

The system calculates the penalty.

The client cannot submit the penalty amount.

12. Customer Cancellation Logic

The backend evaluates:

Cancellation timestamp
+
Ride state
+
Customer cancellation history

Rules:

Within 2-minute grace
    → ₹0

First qualifying cancellation
    → ₹0

Subsequent qualifying cancellation
    → ₹15

The applicable penalty is stored as a penalty record.

Event:

penalty.applied

only when a penalty actually exists.

13. Driver Cancellation

Normal driver cancellation:

ACCEPTED → CANCELLED

Possible side effects:

₹30 penalty
Strike
Matching retry/rematch

Events:

ride.cancelled
penalty.applied
penalty.strike_recorded

14. Changed Pickup: Rejected Beyond Threshold

Implementation status: PROPOSED, not yet implemented — see
ADR-0056-pickup-change-simplification-hard-threshold.md (owner
decision, 2026-08-31). Supersedes this section's own original content
(below, "As originally implemented") and §15-16, and §62's "Changed
Pickup >250m" summary. No driver decision exists anywhere in this flow
anymore.

Customer requests pickup change
        ↓
Distance ≤ 100m
        ↓
Applied immediately — no driver or customer decision step

or:

Customer requests pickup change
        ↓
Distance > 100m
        ↓
Request rejected (PICKUP_CHANGE_TOO_FAR)
        ↓
Ride is left completely unchanged — no rematch, no fare change, no
driver involved

If the customer still needs a pickup farther than 100m away, they
cancel the current ride (§11, Customer Cancellation — existing
grace-period/penalty rules apply exactly as they do for any other
cancellation, no exemption) and book a new one.

As originally implemented (ADR-0033, 2026-08-25 — superseded 2026-08-31
by ADR-0056, kept below as historical record):

When the customer changes pickup by more than 250 meters:

Customer requests pickup change
        ↓
Distance > 250m
        ↓
Driver decision

Driver may choose:

PASS

Result:

Current driver → released
Ride → rematching

The driver receives:

No ₹30 cancellation penalty
No strike

This is a business-rule exception.

The system records the reason:

CHANGED_PICKUP_OVER_250M

15. Changed Pickup: Driver Proceed — SUPERSEDED

Superseded 2026-08-31 (ADR-0056) — there is no driver decision step
anymore; a pickup change beyond the threshold is rejected outright, not
offered to the driver. Kept below as the historical record of the
original design (ADR-0033, 2026-08-25).

If the driver chooses:

PROCEED

then:

Distance > 250m
        ↓
Pricing calculates additional charge
        ↓
Customer sees additional charge
        ↓
Customer confirms
        ↓
Pickup change applied

The additional amount must not be silently added.

16. Changed Pickup: Customer Rejects Charge — SUPERSEDED

Superseded 2026-08-31 (ADR-0056) — no charge is ever calculated for a
pickup change anymore, so there is nothing for the customer to reject.
Kept below as the historical record of the original design (ADR-0033,
2026-08-25).

If the additional charge is presented and the customer does not confirm:

Pickup change → NOT APPLIED

The existing ride remains valid unless the customer separately cancels.

No hidden charge is created.

17. Destination Change State Machine

Implementation status: IMPLEMENTED (§17-18, ADR-0033 Decision 9,
2026-08-25). The exact geometric test for classifying "along the
original route" vs. "a different route" (§18's boundary) is an
engineering judgment call, not a literal reading of any document — see
the ADR.

Destination change does not create a new ride.

Instead:

STARTED
   ↓
Destination change requested
   ↓
Pricing evaluates new destination

If no additional charge:

STARTED
   ↓
Destination updated

If additional charge:

STARTED
   ↓
Fare confirmation required
   ↓
Customer confirms
   ↓
Destination updated

If customer rejects:

Existing destination remains

18. Destination Extension Rule

If the changed destination extends beyond the applicable original destination:

Additional charge = ₹8/km

The final amount is calculated by the server.

The client cannot supply:

₹8

or the final payable amount.

19. Early Drop State Machine

Customer requests early drop:

STARTED
   ↓
EARLY_DROP_REQUESTED
   ↓
Customer confirms
+
Driver confirms
   ↓
GPS verification
   ↓
EARLY_DROPPED

The original fare remains payable under the approved business rule.

The driver must record that:

Customer requested the early drop

20. Early Drop GPS Verification

The backend records:

Ride ID
Customer ID
Driver ID
GPS coordinates
Timestamp
Customer confirmation
Driver confirmation

Verification result:

PASS
FAIL

Only a successful verification allows the early-drop completion flow to close.

21. Early Drop State Machine

STARTED
   ↓
EARLY_DROP_REQUESTED
   ├── Customer rejects → STARTED
   ├── Driver rejects   → STARTED
   └── Both confirm
          ↓
       GPS check
          ├── FAIL → REVIEW / retry according to policy
          └── PASS → EARLY_DROPPED

The exact manual-review policy remains configurable.

Implementation status (Phase 08, ADR-0030, 2026-08-25): §19-21's "GPS
verification"/"GPS check"/PASS-FAIL/REVIEW-retry language above is NOT
implemented and does not govern — it is not corroborated by business-
rules.md BR-088, api-contracts.md §27, or technical-architecture.md §43,
all three of which describe GPS/location as RECORDED evidence only, with
ride completion gated on confirmation (both parties), not on any
verification outcome. Per this documentation set's own source-of-truth
hierarchy (business-rules.md §44/45: Business Rules → Architecture → API
Contracts outrank State Machines), those three govern instead — see the
ADR for the full reconciliation. What IS implemented: STARTED →
EARLY_DROP_REQUESTED → (both confirm) → COMPLETED → CLOSED, with
`EARLY_DROPPED` above read as a label for that same COMPLETED outcome
(state-machines.md §3.1's authoritative ride-status enum has no eighth
value), not the outcome of a verification step that never runs. "Customer
rejects"/"Driver rejects → STARTED" IS implemented, via `confirmed:
false` on the Confirm endpoint discarding the pending request.

22. Driver Availability State Machine

States

OFFLINE
ONLINE
OFFER_PENDING
ON_RIDE
SUSPENDED

23. Driver Offline → Online

Allowed:

OFFLINE → ONLINE

Requirements:

Driver approved
Required documents valid
Vehicle approved
Vehicle active
No suspension

Event:

driver.online

24. Driver Online → Offline

Allowed:

ONLINE → OFFLINE

A driver should not become offline while:

ON_RIDE

If a ride offer is pending, the driver must:

REJECT

or allow the offer timer to expire before going offline, according to the approved flow.

25. Driver Offer State Machine

States

PENDING
ACCEPTED
REJECTED
EXPIRED
CANCELLED

Lifecycle:

PENDING
 ├── ACCEPTED
 ├── REJECTED
 ├── EXPIRED
 └── CANCELLED

26. Offer Timer

Offer duration:

20 seconds

If the driver does nothing:

PENDING
   ↓
EXPIRED

The system then:

Requests next eligible driver

The driver must not be charged a cancellation penalty merely because an offer expired.

27. Offer Acceptance

Allowed:

PENDING → ACCEPTED

Only if:

Current time < expires_at
Ride still SEARCHING
Driver still eligible
Vehicle still eligible

After acceptance:

Driver → ON_RIDE
Ride → ACCEPTED

28. Offer Rejection

Allowed:

PENDING → REJECTED

Result:

Next driver matching attempt

No cancellation penalty.

29. Payment State Machine (SUPERSEDED — ADR-0025, 2026-08-25)

This online-gateway state machine described VISTAAR's own collection of
the ride fare from the customer. No such flow exists under the approved
P2P Payment Model — VISTAAR never collects the ride fare, so there is no
PENDING/PROCESSING/SUCCEEDED/FAILED/REFUNDED lifecycle for it. Kept for
historical record only.

States (as originally written)

PENDING
PROCESSING
SUCCEEDED
FAILED
REFUNDED

Online lifecycle:

PENDING
   ↓
PROCESSING
   ↓
SUCCEEDED

Failure:

PENDING → FAILED
PROCESSING → FAILED

Refund:

SUCCEEDED → REFUNDED

Only authorized refund workflows may create refunds.

30. Payment State Rules (SUPERSEDED — ADR-0025, 2026-08-25, same reason
as §29)

A payment cannot:

SUCCEEDED → PENDING
SUCCEEDED → FAILED
REFUNDED → SUCCEEDED

The client cannot directly set payment status.

Payment success is established by the payment gateway and server verification.

31. Offline Payment State Machine

CORRECTED (ADR-0025, 2026-08-25): if a driver fare-received confirmation
is ever built, it ends at CONFIRMED — there is no VISTAAR settlement
step, since the platform fee was already collected from the driver's
wallet at ride acceptance (technical-architecture.md §18):

EXPECTED
   ↓
DRIVER_CONFIRMING
   ↓
CONFIRMED

As originally written (superseded — the SETTLEMENT_PENDING/SETTLED
steps below modeled a VISTAAR settlement that no longer applies):

EXPECTED
   ↓
DRIVER_CONFIRMING
   ↓
CONFIRMED
   ↓
SETTLEMENT_PENDING
   ↓
SETTLED

If the driver receives less than the expected amount:

DRIVER_CONFIRMING
   ↓
REJECTED

The driver must ask the customer to pay the full amount.

32. Offline Payment Confirmation

CORRECTED (ADR-0025, 2026-08-25): the expected amount is the ride fare
only — VISTAAR's charge is never part of what the customer pays (it was
already collected from the driver's wallet at ride acceptance).

Expected:

Ride fare only

Example:

Ride fare = ₹100
Expected cash = ₹100

Driver enters:

₹100

Allowed:

confirmed_amount == expected_amount

If:

confirmed_amount != expected_amount

return:

FULL_PAYMENT_NOT_RECEIVED

As originally written (superseded — bundled a VISTAAR charge into the
expected amount that the customer never owes):

Expected:

Ride fare + VISTAAR charges

Example:

Ride fare = ₹100
VISTAAR charge = ₹30
Expected cash = ₹130

If confirmed_amount != expected_amount, return FULL_PAYMENT_NOT_RECEIVED
and do not settle the payment.

33. Wallet State Machine

The wallet has an available balance.

Financial operations:

CREDIT
DEBIT
OUTSTANDING
SETTLED

The wallet itself does not use a normal business-state lifecycle.

Every balance change must create a ledger transaction.

34. Wallet Debit

Before debit:

Lock wallet

Then:

Check balance
   ↓
Balance sufficient?
 ├── NO → reject
 └── YES
       ↓
Debit
       ↓
Create ledger
       ↓
Commit

Wallet balance must never become negative.

35. Insufficient Wallet (SUPERSEDED — ADR-0025, 2026-08-25)

This described a driver owing a "cash settlement" (VISTAAR's charge,
bundled into a customer cash payment) that the wallet couldn't cover.
That scenario no longer exists — the platform fee is checked and
debited from the driver's wallet at ride acceptance, before the ride
happens (§34 above); if the balance is insufficient, the driver simply
cannot accept the ride (`InsufficientWalletBalanceError`), not left with
a deferred "outstanding settlement" to recover later.

As originally written (superseded):

If a driver owes a cash settlement and wallet balance is insufficient:

Wallet balance = ₹0
Outstanding = ₹30

The system records:

outstanding_settlement = ₹30

No invalid negative wallet balance is created.

36. Recharge Settlement

CORRECTED (ADR-0025, 2026-08-25): recharge simply credits the wallet —
there is no "outstanding settlement" for it to apply against (§35).

When driver recharges:

Recharge payment succeeds
        ↓
Credit wallet

As originally written (superseded — the "Apply outstanding settlement"
step assumed §35's now-superseded outstanding-settlement concept):

Recharge payment succeeds
        ↓
Credit wallet
        ↓
Apply outstanding settlement
        ↓
Outstanding reduces

Example:

Recharge = ₹200
Outstanding = ₹30

Wallet credit available after settlement = ₹170

Both operations must be recorded in the wallet ledger.

37. Promotion State Machine

States

ACTIVE
RESERVED
CONSUMED
RESTORED
EXPIRED

Normal flow:

ACTIVE
 ↓
RESERVED
 ↓
CONSUMED

Qualifying cancellation:

RESERVED
 ↓
RESTORED

Expiry:

ACTIVE → EXPIRED
RESERVED → EXPIRED

37.1 Campaign State Machine (ADR-0041)

A campaign's own lifecycle — distinct from the entitlement states
above, which apply to what a redemption produces, not the campaign
definition itself.

States

DRAFT
ACTIVE
PAUSED
ENDED

Normal flow:

DRAFT
 ↓ (Activate)
ACTIVE
 ↕ (Pause / Activate)
PAUSED

Termination (from any non-terminal state):

DRAFT / ACTIVE / PAUSED
 ↓ (End)
ENDED

Editing (PATCH, discount terms/eligibility/limits) is permitted only in
DRAFT — once ACTIVE/PAUSED, only the status transitions above are
available, never the discount terms themselves, since a redemption may
already exist. Redemption (RedeemCampaignCode) itself is only accepted
while status = ACTIVE and the current time is within
[starts_at, ends_at).

38. Promotion Concurrency

Two simultaneous rides cannot consume the same single remaining use.

The server must:

Lock entitlement
 ↓
Check remaining uses
 ↓
Reserve
 ↓
Commit

Duplicate usage must return a conflict rather than consume twice.

39. Referral State Machine

States

ATTACHED
QUALIFIED
REWARDED
EXPIRED
REJECTED

Customer referral:

ATTACHED
 ↓
QUALIFIED
 ↓
REWARDED

Driver referral:

ATTACHED
 ↓
Driver approved
 ↓
QUALIFIED
 ↓
REWARDED

40. Penalty State Machine

States

OUTSTANDING
SETTLED
WAIVED

Lifecycle:

OUTSTANDING
 ├── SETTLED
 └── WAIVED

A settled penalty cannot return to outstanding.

Implementation status (Phase 13, ADR-0029, 2026-08-25): OUTSTANDING →
WAIVED is also how a disputed penalty (domain-design.md §17.3's
DisputePenalty, filed as a Support Case) is decided in the customer's
favor — no separate DISPUTED state exists or was added; a dispute
decided against the customer leaves the row exactly OUTSTANDING.

41. Penalty Expiry (corrected — customer penalties never expire)

BR-049 correction (owner decision, 2026-09-04, ADR-0069): customer
penalties in VISTAAR NEVER EXPIRE. An OUTSTANDING penalty remains
outstanding, collectible, and displayed indefinitely until it is
actually paid (→ SETTLED) or administratively waived (→ WAIVED). There
is no automatic expiry date, no time-based transition out of
OUTSTANDING, and no expiry enforcement job — deliberately not built,
by design, not merely "not yet built." EXPIRED is not a valid
`PenaltyStatus` value; the `penalty.penalties.expires_at` column that
previously backed a 30-day-from-issuance expiry has been dropped
(migration `b1d4e7f9a2c3`).

This supersedes the original §41 (30-day expiry, "exact behavior after
expiry must follow the final approved penalty policy" — that policy is
now decided: there is no expiry). This section covers only customer-side
penalties (`penalty.penalties`, BR-047/048/052/135). It is unrelated to
Sarthi cancellation-penalty debt (`wallet.wallets.outstanding_debt`,
ADR-0062), a separate mechanism recovered from the driver's next wallet
recharge, which never had an expiry concept either but follows an
entirely different code path — see ADR-0069 for the full distinction.

42. Driver Strike State

Driver strike count is cumulative operational data.

A strike record is created when a qualifying violation occurs.

Example:

Driver cancellation
 ↓
penalty.applied
 ↓
penalty.strike_recorded
 ↓
driver.strikes += 1

The changed-pickup PASS exception does not create a strike.

43. Verification State Machine

States

PENDING
PROCESSING
APPROVED
REJECTED
MANUAL_REVIEW
EXPIRED

Normal:

PENDING
 ↓
PROCESSING
 ↓
APPROVED

Failure:

PROCESSING → REJECTED

Low confidence:

PROCESSING → MANUAL_REVIEW

MANUAL_REVIEW → APPROVED | REJECTED is the CompleteManualReview command
(domain-design.md §18.3) — implemented (Phase 2 / Task 2.6B,
modules/verification/service.py::VerificationService.complete_manual_review()).
No HTTP endpoint triggers it — none is documented anywhere; it exists at
the service layer only, same "flag the missing contract instead of
inventing it" precedent as ADR-0009's Reject Driver/Vehicle before those
were explicitly authorized. Writing the outcome back onto the
corresponding driver.documents/vehicle.documents.verification_status
(§44) is also implemented (DriverDocumentService/VehicleDocumentService
.apply_verification_outcome(), Task 2.6B) — ADR-0008 item 5 is resolved
at the mechanism level, but nothing yet calls complete_manual_review()
followed by apply_verification_outcome() automatically; a caller (today,
only tests) must invoke both explicitly. business-rules.md BR-123's gate
on admin approval (§67/§68.1) is enforced in code as of Phase 2 / Task
2.6C — DriverService.approve_driver()/VehicleService.approve_vehicle()
now check the required-document set
(modules.driver/vehicle.domain.required_documents) before allowing
PENDING -> APPROVED. What remains unwired is only how a document itself
ever reaches APPROVED (the trigger question above), not whether
approval respects that state once reached.

44. Driver Document State

PENDING
APPROVED
REJECTED
EXPIRED

Expired documents cause the driver/vehicle to become ineligible for matching where required.

business-rules.md BR-123 (approved, enforced in code as of Phase 2 /
Task 2.6C) requires a driver's/vehicle's required documents (Government
ID + Driving Licence for drivers; RC + Insurance for vehicles — Vehicle
Photo deliberately excluded) to be APPROVED and not expired before admin
approval of the driver/vehicle itself is permitted (§67/§68.1). A
mechanism exists (Phase 2 / Task 2.6B) that can transition this status
away from PENDING: RunAIVerification's ManualReviewVerificationProvider
stub → CompleteManualReview admin decision → write-back onto this status
(DriverDocumentService/VehicleDocumentService.apply_verification_outcome()).
Only APPROVED/REJECTED are ever written by this path — EXPIRED remains
entirely untouched by verification (no automatic expiry job exists,
deliberately — expiry stays a separate, date-based concern). No HTTP
endpoint triggers any step of the Task 2.6B chain — none is documented
anywhere; it is exercised only by tests today. What Task 2.6C adds is
the other half: DriverService.approve_driver()/VehicleService.approve_vehicle()
now check this status before allowing PENDING -> APPROVED at the
driver/vehicle profile level, returning DRIVER_NOT_ELIGIBLE/
VEHICLE_NOT_ELIGIBLE when a required document isn't ready.

Event:

vehicle.document_expired

or:

driver.ineligible

45. Safety Incident State Machine

States

OPEN
ACKNOWLEDGED
IN_PROGRESS
RESOLVED
CLOSED

Lifecycle:

OPEN
 ↓
ACKNOWLEDGED
 ↓
IN_PROGRESS
 ↓
RESOLVED
 ↓
CLOSED

SOS creation is immediate.

Event:

safety.sos_triggered

46. Support Case State Machine

OPEN
ASSIGNED
IN_PROGRESS
WAITING_FOR_USER
RESOLVED
CLOSED

AI support can escalate:

AI
 ↓
support.escalated
 ↓
Human support

47. Advertisement Assignment State

ASSIGNED
PROOF_SUBMITTED
UNDER_REVIEW
APPROVED
REJECTED
PAYOUT_PENDING
PAID

48. Advertisement Payout

APPROVED
 ↓
PAYOUT_PENDING
 ↓
PAID

A payout cannot be issued twice.

Use:

idempotency_key

and a unique payout record.

49. State Transition Matrix — Ride

Current

Event

Next

Actor

SEARCHING

Driver accepts

ACCEPTED

Driver

SEARCHING

Customer cancels

CANCELLED

Customer

ACCEPTED

Driver arrives

ARRIVED

Driver

ACCEPTED

Cancellation

CANCELLED

Customer/Driver

ARRIVED

OTP valid

STARTED

Driver

ARRIVED

Cancellation

CANCELLED

Authorized actor

STARTED

GPS completion

COMPLETED

Driver

STARTED

Early drop

EARLY_DROP flow

Customer/Driver

COMPLETED

Payment/close flow

CLOSED

System

50. Invalid Ride Transitions

These must be rejected:

SEARCHING → STARTED
SEARCHING → COMPLETED
ACCEPTED → COMPLETED
ARRIVED → COMPLETED
COMPLETED → STARTED
COMPLETED → CANCELLED
CLOSED → ANY
CANCELLED → STARTED
CANCELLED → COMPLETED

51. State History

Every authoritative transition creates:

ride.state_history

with:

ride_id
from_status
to_status
reason
actor_type
actor_id
timestamp

This is immutable.

52. State and Events

State change and event creation must be in the same database transaction.

Example:

BEGIN

ride.status = COMPLETED

INSERT ride.state_history

INSERT shared.outbox_events
    event_type = ride.completed

COMMIT

Kafka publishing happens after commit.

53. Race Conditions

The backend must handle:

Two drivers accept same ride
Two cancellation requests
Payment webhook duplicated
Driver confirms cash twice
Customer submits destination change twice
Two promotion reservations
Two wallet debits

Recommended controls:

Row locks
Unique constraints
Optimistic versioning
Idempotency keys
Transactional state validation

54. Double Driver Acceptance

Scenario:

Driver A accepts
Driver B accepts

Only one may succeed.

Use an atomic transition:

UPDATE ride.rides
SET driver_id = $driver
WHERE id = $ride
AND status = 'SEARCHING';

If no row is updated:

RIDE_ALREADY_ASSIGNED

The second driver receives a conflict.

55. Double Cash Confirmation

Scenario:

Driver presses confirm twice

First:

CONFIRMED

Second:

idempotent success

or:

PAYMENT_ALREADY_CONFIRMED

depending on API semantics.

No second wallet debit is allowed.

56. Double Penalty

Penalty creation must use a business idempotency key such as:

penalty:{ride_id}:{penalty_type}

A duplicate attempt must not create another penalty.

57. State Machine Testing

Every state machine requires:

Positive tests

Valid transition succeeds

Negative tests

Invalid transition rejected

Concurrency tests

Only one competing transition succeeds

Replay tests

Duplicate request does not duplicate side effect

58. State Machine Implementation Rule

Controllers/routes should not contain scattered transition logic.

Use a domain/application layer such as:

RideStateMachine
PaymentStateMachine
OfferStateMachine
PromotionStateMachine
PenaltyStateMachine
VerificationStateMachine

Example:

ride_state_machine.transition(
    ride=ride,
    event="DRIVER_ARRIVED",
    actor=driver
)

The state machine validates the transition and required rules.

59. State Machine and API Separation

API:

POST /rides/{id}/start

does not directly mean:

ride.status = STARTED

Instead:

API command
 ↓
Application service
 ↓
State machine
 ↓
Business validation
 ↓
Database transaction

60. State Machine and Event Separation

Events are emitted after a successful state transition.

Never emit:

ride.completed

if the database transaction failed.

Correct:

Transition
+
State history
+
Outbox event
=
one transaction

61. Final Core State Diagram

                    ┌──────────────┐
                    │   SEARCHING  │
                    └──────┬───────┘
                           │
                     driver accepts
                           │
                           ▼
                    ┌──────────────┐
                    │   ACCEPTED   │
                    └──────┬───────┘
                           │
                        arrived
                           │
                           ▼
                    ┌──────────────┐
                    │   ARRIVED    │
                    └──────┬───────┘
                           │
                        OTP valid
                           │
                           ▼
                    ┌──────────────┐
                    │    STARTED   │
                    └──────┬───────┘
                           │
                   GPS completion
                           │
                           ▼
                    ┌──────────────┐
                    │  COMPLETED   │
                    └──────┬───────┘
                           │
                        close
                           │
                           ▼
                    ┌──────────────┐
                    │    CLOSED    │
                    └──────────────┘


SEARCHING ────────────────┐
ACCEPTED ─────────────────┤
ARRIVED ──────────────────┤
                          ▼
                    ┌──────────────┐
                    │  CANCELLED   │
                    └──────────────┘

62. Critical Business Flow Summary

Normal Ride

SEARCHING
→ ACCEPTED
→ ARRIVED
→ STARTED
→ COMPLETED
→ CLOSED

Driver Rejects Offer

PENDING
→ REJECTED
→ Next driver

Driver Lets Timer Expire

PENDING
→ EXPIRED
→ Next driver

Changed Pickup ≤100m (ADR-0056, 2026-08-31 — see §14)

Pickup change
→ Applied immediately

Changed Pickup >100m (ADR-0056, 2026-08-31 — supersedes the >250m
driver-decision flow this summary previously showed, see §14)

Pickup change
→ Rejected (PICKUP_CHANGE_TOO_FAR)
→ Ride unchanged
→ Customer must cancel + rebook to get a farther pickup

Destination Extension

Destination change
→ Calculate extension
→ ₹8/km
→ Customer confirmation
→ Continue

Early Drop

STARTED
→ Early-drop request
→ Customer + Driver confirmation
→ GPS verification
→ Early dropped
→ Fare remains payable

Ride-Fare Payment (corrected — ADR-0025, 2026-08-25: superseded the
former "Online Payment"/"Offline Payment" entries below, which had
VISTAAR collecting the fare)

Platform fee already debited from driver wallet at ACCEPTED (§5)
→ Customer pays driver directly (cash or UPI, BR-035) — no VISTAAR
  involvement, no settlement step

As originally written (superseded):

Online Payment

Fare + VISTAAR charges
→ Customer pays VISTAAR
→ Payment verified
→ Allocation
→ Driver settlement

Offline Payment

Customer pays full amount to driver
→ Driver confirms full amount
→ VISTAAR settlement
→ Driver wallet debit
→ If insufficient:
   outstanding settlement
→ Recover on future recharge

63. Open State-Machine Decisions

The following remain configurable/TBD:

Exact cancellation states after ride start.

Exact GPS radius for arrival.

Exact GPS radius for completion.

Exact early-drop GPS tolerance. RESOLVED AS N/A (ADR-0030, 2026-08-25) —
no tolerance/threshold check happens at all; GPS/location is recorded as
evidence only, per BR-088/api-contracts.md §27/technical-architecture.md
§43, which outrank this document's own §19-21 where the "tolerance"
question originated.

Exact behavior when destination change is rejected.

Exact behavior when early-drop GPS verification fails repeatedly.
RESOLVED AS N/A (ADR-0030, 2026-08-25) — same reasoning: no verification
step exists to fail.

Final suspension threshold for driver strikes.

Final penalty expiry behavior.

Final support escalation states.

Advertisement workflow details.

These should be finalized before production implementation.

64. Identity: OTP Challenge State Machine

Added during Phase 2 / Task 2.1 (Identity & Authentication Foundation).
This document had no authentication-specific state machine before; the
ride-start OTP pattern in business-rules.md BR-084 ("generating a new OTP
invalidates the previous one") and this document's own OTP-adjacent
principle "Only the latest valid OTP is accepted"
(technical-architecture.md §41) are reused here for login/registration OTP
rather than inventing a new pattern.

States

ACTIVE
VERIFIED
EXPIRED
INVALIDATED

ACTIVE
 ├── VERIFIED     (correct OTP submitted before expiry, attempts remaining)
 ├── EXPIRED       (expiry reached before a correct OTP is submitted)
 └── INVALIDATED   (a newer OTP was requested for the same phone number)

VERIFIED, EXPIRED, and INVALIDATED are terminal — none of them accept a
further verification attempt. A terminal challenge presented again returns
the same error as an unknown challenge_id (see security.md's general
enumeration-avoidance principle: distinguishing "wrong OTP" from "no such
challenge" would let an attacker probe for valid challenge_ids).

An ACTIVE challenge also tracks an attempts counter against a
per-challenge max_attempts; exceeding it does not itself change the
challenge's status column, but rejects all further verification the same
way OTP_MAX_ATTEMPTS does per api-contracts.md §49.

65. Identity: Session (Refresh Token) State Machine

Added during Phase 2 / Task 2.1.

A session is created on successful OTP verification and on every
subsequent refresh (rotation creates a new session and revokes the old
one — security.md §6: "Refresh tokens must be ... Rotated where
supported").

States (derived, not a stored column — see database-design.md §5.3):

ACTIVE     revoked_at IS NULL AND now() < expires_at
EXPIRED    revoked_at IS NULL AND now() >= expires_at
REVOKED    revoked_at IS NOT NULL

ACTIVE
 ├── REVOKED   (logout, or superseded by a refresh-triggered rotation)
 └── EXPIRED   (expires_at reached without being revoked first)

REVOKED and EXPIRED are terminal. A refresh or logout attempt against a
non-ACTIVE session returns AUTH_INVALID (api-contracts.md §49) — the
client cannot distinguish "revoked" from "expired" from the error alone,
by the same enumeration-avoidance principle applied to OTP challenges
above.

66. Open Identity State-Machine Decisions

The following remain configurable, per security.md §89's classification
of these as engineering/security configuration rather than unresolved
business rules (see modules/identity/config.py for the current
development defaults):

OTP expiry duration.

OTP max verification attempts.

OTP resend cooldown / request rate limit.

Access-token lifetime.

Refresh-token lifetime.

67. Driver: Profile State Space (partially a transitioning state machine)

Added during Phase 2 / Task 2.3 (Driver Profile Foundation). driver.drivers
(database-design.md §7.1) carries two independent status dimensions, per
domain-design.md §7.3's documented "Driver State" list and the
PENDING/APPROVED/REJECTED pattern already established for
driver.documents/vehicle.vehicles verification_status columns:

verification_status: PENDING (default) | APPROVED | REJECTED
operational_status:  OFFLINE (default) | ONLINE | ON_RIDE | SUSPENDED | INELIGIBLE

Task 2.3 created this schema with both fields read-only through
GET/PATCH /api/v1/drivers/me. verification_status now transitions:

ApproveDriver / RejectDriver  → verification_status: PENDING -> APPROVED | REJECTED
                                 (Phase 2 / Task 2.7A, modules/admin/router.py +
                                 modules/driver/service.py; requires an active admin —
                                 see docs/14-decisions/ADR-0009). Only valid from PENDING;
                                 already-decided drivers return INVALID_STATE_TRANSITION.
                                 business-rules.md BR-123 additionally requires the
                                 driver's required documents/verification cases to be
                                 approved/valid first — NOT YET ENFORCED in code (see
                                 §44 below and the Task 2.6B plan).

operational_status: real transitions now exist for the OFFLINE/ONLINE
pair (Phase 2 / Task 2.7B, unblocked once Task 2.6C enforced BR-123 —
see §44):

GoOnline   → operational_status: OFFLINE -> ONLINE (api-contracts.md §10,
                                 modules/driver/service.py::DriverService.go_online()).
                                 Requires, in order: driver currently OFFLINE
                                 (else INVALID_STATE_TRANSITION); driver
                                 APPROVED and its own required documents
                                 valid (else DRIVER_NOT_ELIGIBLE); an
                                 APPROVED + ACTIVE vehicle whose own
                                 required documents are valid (else
                                 DRIVER_NOT_ELIGIBLE). The vehicle-side
                                 checks are computed by
                                 modules/driver/router.py (fetching the
                                 driver's ACTIVE vehicle and its documents
                                 via modules.vehicle's own services) and
                                 passed into go_online() as plain values —
                                 modules.driver never imports
                                 modules.vehicle (see
                                 modules/driver/__init__.py).
GoOffline  → operational_status: ONLINE -> OFFLINE (api-contracts.md §10,
                                 ::go_offline()). Requires the driver
                                 currently ONLINE, else DRIVER_NOT_ONLINE
                                 — raised identically whether the driver is
                                 already OFFLINE or is ON_RIDE, since no
                                 ride/offer model exists yet to give
                                 ON_RIDE a distinct outcome (tracked as a
                                 Phase 3 dependency in
                                 modules/driver/domain/errors.py::DriverNotOnlineError,
                                 not an unresolved documentation conflict).

Both transitions lock the driver's row (SELECT ... FOR UPDATE) before
checking or writing operational_status, serializing concurrent Go
Online/Go Offline calls for the same driver — same mechanism as §68.3's
vehicle-activation row locking.

ON_RIDE remains untransitioned — no ride/matching domain exists yet to
move a driver into or out of it. INELIGIBLE likewise remains
untransitioned:

(document-expiry monitoring)    → operational_status: * -> INELIGIBLE (BR-104,
                                 no expiry-scheduling job exists yet — see
                                 modules/driver/__init__.py)

SUSPENDED now has real transitions (Phase 03, ADR-0021 — this is the task
that fills in the "which actor, which preconditions, which events" this
section previously deferred):

SuspendDriver    → operational_status: * -> SUSPENDED (any status except
                                 already-SUSPENDED — DriverAlreadySuspendedError
                                 otherwise). modules/driver/service.py::
                                 DriverService.suspend_driver(), row-locked
                                 (get_by_id_for_update()) same as GoOnline/
                                 GoOffline. Does NOT touch ride.rides even if
                                 the driver is ON_RIDE — no source document
                                 describes force-cancelling an active ride as
                                 part of suspension (ADR-0021 Decision 4).
                                 No HTTP endpoint exists — api-contracts.md
                                 documents none (ADR-0021 Decision 2); the
                                 actor is intended to be Admin, matching
                                 domain-design.md §7.4's command ownership,
                                 but nothing composes it yet.
ReactivateDriver → operational_status: SUSPENDED -> OFFLINE, never directly
                                 ONLINE — mirrors ADR-0009's "approval does
                                 not change eligibility" precedent; the
                                 driver must Go Online themselves afterward.
                                 DriverNotSuspendedError otherwise. Same
                                 actor/HTTP-endpoint status as SuspendDriver
                                 above.

Automatic, threshold-based suspension (BR-069/117/119's progressive
cancellation-abuse enforcement) is a distinct, still-unbuilt path — exact
strike thresholds and suspension duration remain TBD (business-rules.md
§43) — ADR-0021 does not resolve this, only the manual/admin-triggered
command above.

68. Vehicle: State Machines

Added during Phase 2 / Task 2.4 (Vehicle Management). vehicle.vehicles
(database-design.md §8.1) carries the same two-dimension shape as
driver.drivers (§67): a verification lifecycle and an operational
lifecycle.

68.1 Vehicle Verification State (partially a transitioning state machine)

verification_status: PENDING (default) | APPROVED | REJECTED

Same shape as driver.drivers.verification_status (§67). ApproveVehicle/
RejectVehicle (domain-design.md §8.3) now transition it: PENDING ->
APPROVED | REJECTED (Phase 2 / Task 2.7A, modules/admin/router.py +
modules/vehicle/service.py; requires an active admin). Only valid from
PENDING; already-decided vehicles return INVALID_STATE_TRANSITION.
operational_status is never touched by approval/rejection (stays
INACTIVE) — see §68.2. business-rules.md BR-123 additionally requires
the vehicle's required documents/verification cases to be approved/valid
first — NOT YET ENFORCED in code (see §44 and the Task 2.6B plan).

68.2 Vehicle Operational State (real state machine — implemented)

operational_status: INACTIVE (default) | ACTIVE

INACTIVE
 └── ACTIVE    via Activate Vehicle (api-contracts.md §11), requires:
                 verification_status = APPROVED
                 AND
                 the owning driver's driver.drivers.operational_status
                 NOT IN (ONLINE, ON_RIDE)
                 side effect: any other vehicle belonging to the same
                 driver that is currently ACTIVE is deactivated as part
                 of the same atomic operation (BR-122, approved — see
                 §68.3)

ACTIVE
 └── INACTIVE  via Deactivate Vehicle (api-contracts.md §11), requires:
                 the owning driver's driver.drivers.operational_status
                 NOT IN (ONLINE, ON_RIDE)

Unlike §67's driver operational state, this one is genuinely exercised:
Activate/Deactivate are real, tested transitions. The driver-offline
precondition reads the already-existing
driver.drivers.operational_status column (Task 2.3) — it is not a second,
duplicate availability mechanism.

One point remains open rather than assumed, because no source document
resolves it: whether Deactivate additionally requires verification_status
= APPROVED (BR-101 says "deactivate an approved vehicle"). In practice a
vehicle can only reach ACTIVE by having first been APPROVED (per
Activate's own precondition above), so this is moot for any vehicle
reachable through this API — flagged here only for completeness.

68.3 Single-Active-Vehicle Invariant (BR-122, approved)

Previously an open question in this section (see git history / earlier
drafts of this document); now resolved by an explicit approved business
decision:

One driver
    ↓
Multiple registered vehicles allowed
    ↓
Maximum ONE ACTIVE vehicle per driver
    ↓
Vehicle switching is allowed only while the driver is OFFLINE

Enforcement (database-design.md §8.1.1, "Vehicle Activation
Transaction"):

1. Application level: activating a vehicle locks every one of the
   driver's vehicle rows (SELECT ... FOR UPDATE) before checking or
   writing anything, serializing concurrent activation requests for the
   same driver_id. Within that lock, any other ACTIVE vehicle for the
   same driver is deactivated before the target vehicle is activated.
2. Database level: uq_vehicles_one_active_per_driver, a partial unique
   index on vehicle.vehicles(driver_id) WHERE operational_status =
   'ACTIVE', makes it structurally impossible for two rows with the same
   driver_id to both be ACTIVE — an unconditional backstop independent of
   the application logic in (1).

Verified with a real-PostgreSQL concurrency test (two simultaneous HTTP
activation requests for two different vehicles of the same driver) in
addition to sequential-request tests.

69. GPS Dispute State Machine

Implements BR-124/BR-125 (business-rules.md §39, approved 2026-08-25) and
ADR-0032. Opens automatically the moment §16/§17-equivalent GPS
verification (Driver Arrival, §6; Destination Completion, §8) reaches its
terminal `GPS_VERIFICATION_FAILED` outcome (ADR-0028's
RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW-th failure) — not a separate command
a customer/driver initiates.

States

OPEN
RESOLVED
EXPIRED

Lifecycle:

GPS_VERIFICATION_FAILED (terminal)
   ↓
OPEN
   ├── Evidence submitted, admin APPROVEs  → RESOLVED (decision: APPROVE)
   ├── Evidence submitted, admin REJECTs   → RESOLVED (decision: REJECT)
   ├── Admin decides with no evidence      → RESOLVED (decision: APPROVE or REJECT — an
   │                                          admin may still decide without evidence ever
   │                                          having been submitted; BR-124 does not require it)
   └── 24h evidence window elapses, never resolved → EXPIRED (lazily
       transitioned on the next read/write that observes the deadline has
       passed — no background worker, same "lazy evaluation" pattern this
       codebase already uses for matching offer expiry, ADR-0011 Decision 2)

RESOLVED(APPROVE) → the blocked ride transition proceeds: ACCEPTED →
ARRIVED (for an arrival dispute) or STARTED → COMPLETED → CLOSED (for a
completion dispute) — the exact transition mark_arrived()/complete_ride()
would have performed on a real PASS (ADR-0028), performed now instead by
resolve_gps_dispute().

RESOLVED(REJECT) and EXPIRED both leave the ride exactly where it was —
neither transitions it. No further automatic action follows (BR-124): the
ride may separately be cancelled through the already-existing
cancellation rules if it never resolves, but this state machine does not
invent that path.

A dispute already RESOLVED or EXPIRED never returns to OPEN.

69.1 Fare Rule State Machine (ADR-0042)

A fare rule's own authoring lifecycle — distinct from `fare_quotes`
(§15.2), which freezes its values at creation and never transitions at
all.

States

DRAFT
IN_REVIEW
PUBLISHED

Normal flow:

DRAFT
 ↓ (Submit for Review)
IN_REVIEW
 ↓ (Publish)
PUBLISHED

Shortcut (Submit for Review is not mandatory):

DRAFT
 ↓ (Publish)
PUBLISHED

PUBLISHED is terminal — no Unpublish/Reject/return-to-DRAFT transition
exists (only what Admin Web §4.8 names). Publishing a rule for a
vehicle_category that already has a PUBLISHED-and-live rule
additionally closes that prior rule out (sets its `effective_until` to
the new rule's `effective_from`) — at most one rule is ever live per
category, enforced by this side effect, not a separate uniqueness
constraint.

70. Document Status

Version: 1.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, Domain Design v1.0, Database Design v1.0, API Contracts v1.0, Event Contracts v1.0