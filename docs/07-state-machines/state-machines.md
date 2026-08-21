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

SEARCHING
ACCEPTED
ARRIVED
STARTED
COMPLETED
CANCELLED
CLOSED

3.2 Main Lifecycle

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

SEARCHING ─────→ CANCELLED
ACCEPTED ───────→ CANCELLED
ARRIVED ────────→ CANCELLED
STARTED ────────→ CANCELLED only through approved exceptional flows

4. Ride: SEARCHING

Entered when

Customer successfully requests a ride.

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

14. Changed Pickup: Driver Pass

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

15. Changed Pickup: Driver Proceed

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

16. Changed Pickup: Customer Rejects Charge

If the additional charge is presented and the customer does not confirm:

Pickup change → NOT APPLIED

The existing ride remains valid unless the customer separately cancels.

No hidden charge is created.

17. Destination Change State Machine

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

29. Payment State Machine

States

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

30. Payment State Rules

A payment cannot:

SUCCEEDED → PENDING
SUCCEEDED → FAILED
REFUNDED → SUCCEEDED

The client cannot directly set payment status.

Payment success is established by the payment gateway and server verification.

31. Offline Payment State Machine

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

Expected:

Ride fare + VISTAAR charges

Example:

Ride fare = ₹100
VISTAAR charge = ₹30
Expected cash = ₹130

Driver enters:

₹130

Allowed:

confirmed_amount == expected_amount

If:

confirmed_amount != expected_amount

return:

FULL_PAYMENT_NOT_RECEIVED

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

35. Insufficient Wallet

If a driver owes a cash settlement and wallet balance is insufficient:

Wallet balance = ₹0
Outstanding = ₹30

The system records:

outstanding_settlement = ₹30

No invalid negative wallet balance is created.

36. Recharge Settlement

When driver recharges:

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
EXPIRED

Lifecycle:

OUTSTANDING
 ├── SETTLED
 ├── WAIVED
 └── EXPIRED

A settled penalty cannot return to outstanding.

41. Penalty Expiry

Penalty duration:

30 days

If not settled within the applicable period:

OUTSTANDING → EXPIRED

The exact behavior after expiry must follow the final approved penalty policy.

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

44. Driver Document State

PENDING
APPROVED
REJECTED
EXPIRED

Expired documents cause the driver/vehicle to become ineligible for matching where required.

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

Changed Pickup >250m

Pickup change
→ Driver PASS
→ Rematch

or:

Pickup change
→ Driver PROCEED
→ Additional charge
→ Customer confirmation
→ Continue

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

Exact early-drop GPS tolerance.

Exact behavior when destination change is rejected.

Exact behavior when early-drop GPS verification fails repeatedly.

Final suspension threshold for driver strikes.

Final penalty expiry behavior.

Final support escalation states.

Advertisement workflow details.

These should be finalized before production implementation.

64. Document Status

Version: 1.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, Domain Design v1.0, Database Design v1.0, API Contracts v1.0, Event Contracts v1.0