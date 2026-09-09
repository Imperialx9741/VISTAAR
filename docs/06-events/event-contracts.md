VISTAAR — Event Contracts

Document Version: 1.0
Status: Draft — Derived from PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, Domain Design v1.0, Database Design v1.0, and API Contracts v1.0
Event Transport: Apache Kafka
Currency: INR (₹)

1. Purpose

This document defines the event-driven communication contract for VISTAAR.

It specifies:

Event naming

Event envelopes

Event producers

Event consumers

Payload schemas

Versioning

Ordering

Idempotency

Retry behavior

Dead-letter handling

Transactional outbox

Event security

Event observability

Events communicate facts that have already occurred.

A consumer must not assume an event is a command unless the event is explicitly defined as a command message.

2. Event Architecture

Domain Service
     ↓
PostgreSQL Transaction
     ↓
Outbox Event
     ↓
Outbox Publisher
     ↓
Kafka
     ↓
Consumer
     ↓
Consumer DB Transaction
     ↓
Consumer Side Effects

The database transaction and outbox insert must succeed together.

The Kafka publish occurs after the transaction.

3. Event Envelope

All domain events use a common envelope.

Example:

{
  "event_id": "01JEXAMPLE",
  "event_type": "ride.accepted",
  "event_version": 1,
  "occurred_at": "2026-08-18T10:00:00Z",
  "producer": "ride-service",
  "aggregate_type": "ride",
  "aggregate_id": "ride-uuid",
  "correlation_id": "request-uuid",
  "causation_id": "event-uuid",
  "tenant_id": "vistaar",
  "data": {}
}

Required fields:

event_id
event_type
event_version
occurred_at
producer
aggregate_type
aggregate_id
correlation_id
data

4. Event ID

event_id must be globally unique.

Recommended:

UUIDv7

or an equivalent time-sortable unique identifier.

Consumers must store processed event IDs when exactly-once business effects are required.

5. Event Naming

Use:

<domain>.<past-tense-fact>

Examples:

ride.requested
ride.accepted
ride.started
ride.completed

wallet.debited
wallet.credited

payment.succeeded
payment.failed

penalty.applied
promotion.consumed

Avoid vague names:

ride.update
wallet.change
payment.process

6. Kafka Topic Strategy

Recommended topic families:

vistaar.ride
vistaar.matching
vistaar.pricing
vistaar.wallet
vistaar.payment
vistaar.promotion
vistaar.referral
vistaar.penalty
vistaar.verification
vistaar.safety
vistaar.driver
vistaar.vehicle
vistaar.notification
vistaar.support
vistaar.advertisement
vistaar.identity

For high-throughput systems, topics may later be split by event class.

7. Partition Key

For ride events:

aggregate_id = ride_id

For wallet events:

aggregate_id = driver_id

For payment events:

aggregate_id = payment_id

For promotion events:

aggregate_id = entitlement_id

This preserves ordering for events belonging to the same aggregate.

8. Ordering Rule

Kafka ordering is guaranteed only within a partition.

Therefore:

same aggregate
→ same partition key
→ ordered events

Example:

ride.requested
ride.accepted
ride.arrived
ride.started
ride.completed

must use the same ride ID as the partition key.

9. Event Delivery Semantics

The system uses:

At-least-once delivery

Therefore consumers must be idempotent.

Do not rely on Kafka delivery alone to guarantee business-level exactly-once behavior.

Business effects must be protected by:

Unique constraints

Event IDs

Idempotency keys

Transactions

10. Ride Events

10.1 ride.requested

Producer:

Ride Service

Consumers:

Matching
Notification
Analytics

Payload:

{
  "ride_id": "uuid",
  "customer_id": "uuid",
  "vehicle_category": "CAB",
  "pickup": {
    "latitude": 25.5941,
    "longitude": 85.1376
  },
  "destination": {
    "latitude": 25.6120,
    "longitude": 85.1580
  },
  "fare_quote_id": "uuid"
}

10.2 ride.accepted

Producer:

Ride Service

Consumers:

Customer Notification
Payment
Analytics

Payload:

{
  "ride_id": "uuid",
  "driver_id": "uuid",
  "vehicle_id": "uuid",
  "fare_quote_id": "uuid",
  "accepted_at": "timestamp"
}

10.3 ride.arrived

Producer:

Ride Service

Consumers:

Notification
Penalty
Analytics

Payload:

{
  "ride_id": "uuid",
  "driver_id": "uuid",
  "arrived_at": "timestamp",
  "gps_verified": true
}

10.4 ride.started

Producer:

Ride Service

Consumers:

Notification
Analytics

Payload:

{
  "ride_id": "uuid",
  "driver_id": "uuid",
  "started_at": "timestamp"
}

Notification consumer: IMPLEMENTED (ADR-0038, 2026-08-26) — notifies
the ride's customer (looked up by `ride_id`, since this payload does
not carry `customer_id`). Analytics consumer: not implemented.

10.5 ride.pickup_changed — REMOVED (ADR-0056, 2026-08-31)

SUPERSEDED — owner decision, 2026-08-31 (see ADR-0056-pickup-change-
simplification-hard-threshold.md). Pickup change no longer has a
driver-decision/customer-confirmation step to fire this event from —
a ≤threshold change now applies with no request/confirmation ceremony
at all (same as it always did, ADR-0033 Decision 5), and a >threshold
change is rejected outright, nothing to confirm. `POST .../pickup-
change/confirm`, this event's only publisher, was removed. This event
is never published by any live code path anymore. Kept below as the
historical record of the original design (ADR-0033, 2026-08-25).

Payload (as originally implemented, before ADR-0056):

{
  "ride_id": "uuid",
  "old_pickup": {},
  "new_pickup": {},
  "distance_change_meters": 310,
  "additional_charge": "<computed by Pricing at the approved pickup-change rate>",
  "customer_confirmed": true,
  "driver_decision": "PROCEED"
}

NOTE: distance_change_meters and additional_charge above are illustrative
placeholders showing payload shape only, not a worked example. RESOLVED
(ADR-0033, 2026-08-25) — the pickup-change rate is the ride's own base
per-km fare, not a new flat number (business-rules.md BR-076);
additional_charge is always the server-calculated value at that rate.

Consumers (as originally implemented):

Pricing
Notification
Analytics

10.6 ride.destination_changed

IMPLEMENTED (ADR-0033 Decision 9, 2026-08-25) — published by
POST /api/v1/rides/{ride_id}/destination-change/confirm, only for the
BEYOND_ORIGINAL/DIFFERENT_ROUTE cases (BR-080/081); the WITHIN_ROUTE
case (BR-079) never fires this event, same "nothing changed, no
ceremony" reasoning a ≤threshold pickup change gets. Unaffected by
ADR-0056 (which removed §10.5's ride.pickup_changed entirely, not this
event).

Payload:

{
  "ride_id": "uuid",
  "old_destination": {},
  "new_destination": {},
  "fare_revision_id": "uuid",
  "additional_charge": 40,
  "customer_confirmed": true
}

Consumers:

Pricing
Payment
Notification
Analytics

10.7 ride.early_drop_confirmed

Payload:

{
  "ride_id": "uuid",
  "customer_id": "uuid",
  "driver_id": "uuid",
  "gps_location": {},
  "customer_confirmed": true,
  "driver_confirmed": true,
  "timestamp": "timestamp"
}

Consumers:

Payment
Verification
Notification
Analytics

Implementation status (Phase 08, ADR-0030, 2026-08-25): COMPLETE —
published with this exact payload once both parties confirm
(`gps_location` = `{"latitude": ..., "longitude": ...}`, the driver's own
submitted coordinates — ADR-0030 Decision 3). No consumer exists in this
codebase for any of the four listed (no Payment/Verification domain, no
notification provider — this producer writes the outbox row regardless,
same "no real caller, no invented composition" restraint used
throughout).

10.8 ride.completed

Payload:

{
  "ride_id": "uuid",
  "customer_id": "uuid",
  "driver_id": "uuid",
  "vehicle_id": "uuid",
  "final_fare_quote_id": "uuid",
  "completion_location": {},
  "gps_verified": true,
  "completed_at": "timestamp"
}

Consumers:

Payment
Promotion
Notification
Rating
Analytics

Notification consumer: IMPLEMENTED (ADR-0038, 2026-08-26) — notifies
the ride's customer (`customer_id`, already in the payload). Payment/
Promotion/Rating/Analytics consumers: not implemented.

10.9 ride.cancelled

Payload:

{
  "ride_id": "uuid",
  "cancelled_by": "CUSTOMER",
  "reason": "CUSTOMER_CHANGED_PLANS",
  "cancelled_at": "timestamp"
}

Consumers:

Penalty
Promotion
Matching
Notification
Analytics

Notification consumer: IMPLEMENTED (ADR-0038, 2026-08-26) — notifies
whichever party did NOT cancel (looked up by `ride_id`, since this
payload carries `cancelled_by` as a role, not either party's ID
directly); skipped when the ride never had a driver assigned yet.
Penalty/Promotion/Matching/Analytics consumers: not implemented here
(Penalty's own cancellation-charge composition is a separate, already-
implemented synchronous path — see modules/ride/router.py's
`cancel_ride`/`driver_cancel_ride` — not this consumer).

10.10 ride.gps_dispute_opened

Producer:

Ride Service

Consumers:

Notification
Analytics

Payload:

{
  "dispute_id": "uuid",
  "ride_id": "uuid",
  "gps_verification_id": "uuid",
  "verification_type": "ARRIVAL",
  "evidence_deadline": "timestamp"
}

10.11 ride.gps_dispute_resolved

Producer:

Ride Service

Consumers:

Notification
Analytics

Payload:

{
  "dispute_id": "uuid",
  "ride_id": "uuid",
  "decision": "APPROVE",
  "decided_by": "uuid",
  "decided_at": "timestamp"
}

Implementation status (§10.10/§10.11, BR-124/BR-125, ADR-0032,
2026-08-25): COMPLETE. Neither event has a real consumer in this
codebase (no notification provider is wired to react to these
specifically, no Analytics domain exists) — both outbox rows are still
written regardless, same "producer writes independent of whether a
consumer exists" principle used throughout.

10.12 ride.schedule_promoted (IMPLEMENTED — ADR-0057, 2026-08-31)

Producer:

Ride Service (fired by the scheduled-ride Beat task, not a customer-
or driver-triggered command)

Consumers:

Notification (a plausible "your ride is now being matched" push once
push notifications themselves are wired, api-contracts.md §46.3 —
not built yet either; this event exists so that consumer has something
real to subscribe to once it does)

Payload:

{
  "ride_id": "uuid",
  "promoted_at": "timestamp"
}

Implementation status: COMPLETE. Fired at SCHEDULED → SEARCHING
(state-machines.md §3.9) — the moment a scheduled ride's driver
lock-in window is reached and it re-enters the ordinary matching flow.
`ride.requested` is still fired at the ride's original SCHEDULED entry
(same payload shape an immediate ride's own SEARCHING entry already
uses) — this event is additive, not a replacement. No real consumer
exists yet (Notification's own push channel is itself not wired,
api-contracts.md §46.3) — the outbox row is still written regardless,
same "producer writes independent of whether a consumer exists"
principle §10.10/§10.11 above already established.

11. Matching Events

11.1 matching.offer_created

Payload:

{
  "offer_id": "uuid",
  "ride_id": "uuid",
  "driver_id": "uuid",
  "vehicle_id": "uuid",
  "expires_at": "timestamp"
}

Consumers:

Notification
Analytics

11.2 matching.offer_rejected

Payload:

{
  "offer_id": "uuid",
  "ride_id": "uuid",
  "driver_id": "uuid",
  "reason": "DRIVER_REJECTED"
}

Consumers:

Matching
Analytics

11.3 matching.offer_expired

Payload:

{
  "offer_id": "uuid",
  "ride_id": "uuid",
  "driver_id": "uuid",
  "expired_at": "timestamp"
}

Consumers:

Matching
Notification
Analytics

11.4 matching.ride_rematched

Payload:

{
  "ride_id": "uuid",
  "previous_driver_id": "uuid",
  "reason": "PICKUP_CHANGE_PASS"
}

Consumers:

Notification
Analytics

12. Pricing Events

12.1 pricing.fare_calculated

Payload:

{
  "fare_quote_id": "uuid",
  "ride_id": "uuid",
  "version": 1,
  "total": 250,
  "currency": "INR",
  "reason": "INITIAL_QUOTE"
}

12.2 pricing.fare_revision_created

Payload:

{
  "fare_quote_id": "uuid",
  "ride_id": "uuid",
  "version": 2,
  "previous_total": 250,
  "new_total": 290,
  "additional_charge": 40,
  "reason": "DESTINATION_CHANGE"
}

Consumers:

Ride
Payment
Notification

12.3 pricing.fare_change_confirmed

Payload:

{
  "ride_id": "uuid",
  "fare_quote_id": "uuid",
  "version": 2,
  "confirmed_by": "CUSTOMER",
  "confirmed_at": "timestamp"
}

13. Wallet Events

13.1 wallet.debited

Payload:

{
  "wallet_transaction_id": "uuid",
  "driver_id": "uuid",
  "amount": 20,
  "transaction_type": "PLATFORM_FEE",
  "balance_after": 180,
  "ride_id": "uuid",
  "idempotency_key": "ride:uuid:platform-fee"
}

Consumers:

Ride
Payment
Notification
Analytics

13.2 wallet.credited

Payload:

{
  "wallet_transaction_id": "uuid",
  "driver_id": "uuid",
  "amount": 100,
  "transaction_type": "JOINING_BONUS",
  "balance_after": 200
}

13.3 wallet.recharged

Payload:

{
  "recharge_id": "uuid",
  "driver_id": "uuid",
  "amount": 200,
  "payment_id": "uuid"
}

Consumers:

Wallet
Notification
Analytics

13.4 wallet.cash_settlement_recorded

Payload:

{
  "driver_id": "uuid",
  "ride_id": "uuid",
  "amount": 30,
  "settlement_id": "uuid"
}

14. Payment Events

SUPERSEDED IN FULL for the ride fare (ADR-0025, 2026-08-25 — annotated
2026-09-02, closing the follow-up ADR-0025 §5 itself explicitly flagged
as still outstanding for this section, same as security.md §27-32).
VISTAAR never collects the ride fare — none of the six events below are
ever published for it; `"amount": 130`/`"method": "ONLINE"` in §14.1's
own payload example describes the rejected combined-collection model.
These event shapes may still be a reasonable starting point for a
future driver-wallet-recharge or customer-penalty-collection payment
flow (both still genuinely TBD, ADR-0013 Item 3 / ADR-0026 §5) — kept
below for that reason, not deleted, but not currently published by any
real code path.

14.1 payment.initiated

Payload:

{
  "payment_id": "uuid",
  "ride_id": "uuid",
  "customer_id": "uuid",
  "amount": 130,
  "method": "ONLINE"
}

14.2 payment.succeeded

Payload:

{
  "payment_id": "uuid",
  "ride_id": "uuid",
  "amount": 130,
  "gateway_reference": "gateway-reference",
  "succeeded_at": "timestamp"
}

Consumers:

Ride
Wallet
Notification
Promotion
Analytics

14.3 payment.failed

Payload:

{
  "payment_id": "uuid",
  "ride_id": "uuid",
  "reason": "GATEWAY_DECLINED",
  "failed_at": "timestamp"
}

14.4 payment.cash_confirmed

Payload:

{
  "payment_id": "uuid",
  "ride_id": "uuid",
  "driver_id": "uuid",
  "expected_amount": 130,
  "confirmed_amount": 130,
  "confirmed_at": "timestamp"
}

The event is emitted only after the server validates:

confirmed_amount == expected_amount

14.5 payment.settlement_created

Payload:

{
  "settlement_id": "uuid",
  "payment_id": "uuid",
  "driver_id": "uuid",
  "amount": 30,
  "settlement_type": "VISTAAR_CASH_SETTLEMENT"
}

14.6 payment.refund_completed

Payload:

{
  "payment_id": "uuid",
  "refund_id": "uuid",
  "amount": 30,
  "reason": "ADMIN_APPROVED"
}

15. Promotion Events

15.1 promotion.granted

Payload:

{
  "entitlement_id": "uuid",
  "customer_id": "uuid",
  "promotion_type": "WELCOME",
  "discount_percent": 50,
  "total_uses": 3,
  "expires_at": "timestamp"
}

15.2 promotion.reserved

Payload:

{
  "entitlement_id": "uuid",
  "ride_id": "uuid",
  "reservation_id": "uuid"
}

15.3 promotion.consumed

Payload:

{
  "entitlement_id": "uuid",
  "ride_id": "uuid",
  "discount_amount": 50,
  "remaining_uses": 1
}

15.4 promotion.restored

Payload:

{
  "entitlement_id": "uuid",
  "ride_id": "uuid",
  "reason": "QUALIFYING_CANCELLATION",
  "restored_uses": 1
}

15.5 promotion.expired

Payload:

{
  "entitlement_id": "uuid",
  "customer_id": "uuid",
  "expired_at": "timestamp"
}

16. Referral Events

16.1 referral.attached

Payload:

{
  "referral_id": "uuid",
  "referrer_id": "uuid",
  "referred_id": "uuid",
  "referred_type": "CUSTOMER"
}

16.2 referral.qualified

Customer:

{
  "referral_id": "uuid",
  "referred_type": "CUSTOMER",
  "qualification": "REGISTERED"
}

Driver:

{
  "referral_id": "uuid",
  "referred_type": "DRIVER",
  "qualification": "VERIFIED_AND_APPROVED"
}

16.3 referral.reward_issued

Payload:

{
  "reward_id": "uuid",
  "referral_id": "uuid",
  "recipient_id": "uuid",
  "reward_type": "DRIVER_BONUS",
  "amount": 100,
  "expires_at": "timestamp"
}

17. Penalty Events

17.1 penalty.applied

Payload:

{
  "penalty_id": "uuid",
  "user_id": "uuid",
  "ride_id": "uuid",
  "penalty_type": "NO_SHOW",
  "amount": 30,
  "expires_at": "timestamp"
}

Consumers:

Payment
Notification
Support
Analytics

Notification consumer: IMPLEMENTED (ADR-0038, 2026-08-26) — notifies
the penalized user (`user_id`, already in the payload). Payment/
Support/Analytics consumers: not implemented.

17.2 penalty.strike_recorded

Payload:

{
  "strike_id": "uuid",
  "driver_id": "uuid",
  "ride_id": "uuid",
  "reason": "DRIVER_CANCELLATION"
}

17.3 penalty.expired

Payload:

{
  "penalty_id": "uuid",
  "user_id": "uuid",
  "expired_at": "timestamp"
}

18. Verification Events

18.1 verification.submitted

Payload:

{
  "case_id": "uuid",
  "subject_type": "PARKING_PROOF",
  "subject_id": "uuid",
  "evidence_id": "uuid"
}

18.2 verification.approved

Payload:

{
  "case_id": "uuid",
  "subject_type": "PARKING_PROOF",
  "subject_id": "uuid",
  "confidence": 0.96,
  "model_name": "parking-model-v1"
}

18.3 verification.rejected

Payload:

{
  "case_id": "uuid",
  "subject_type": "VEHICLE_DOCUMENT",
  "subject_id": "uuid",
  "reason": "DOCUMENT_INVALID"
}

18.4 verification.manual_review_requested

Payload:

{
  "case_id": "uuid",
  "reason": "LOW_CONFIDENCE",
  "confidence": 0.48
}

19. Driver Events

19.1 driver.approved

Payload:

{
  "driver_id": "uuid",
  "approved_at": "timestamp"
}

Consumers:

Matching
Wallet
Referral
Notification

19.2 driver.online

Payload:

{
  "driver_id": "uuid",
  "vehicle_id": "uuid",
  "vehicle_category": "CAB",
  "location": {}
}

19.3 driver.offline

Payload:

{
  "driver_id": "uuid",
  "reason": "DRIVER_REQUESTED"
}

19.4 driver.suspended

Payload:

{
  "driver_id": "uuid",
  "reason": "STRIKE_THRESHOLD"
}

19.5 driver.ineligible

Payload:

{
  "driver_id": "uuid",
  "reason": "DOCUMENT_EXPIRED"
}

20. Vehicle Events

vehicle.approved

{
  "vehicle_id": "uuid",
  "driver_id": "uuid",
  "category": "CAB"
}

vehicle.activated

{
  "vehicle_id": "uuid",
  "driver_id": "uuid"
}

vehicle.deactivated

{
  "vehicle_id": "uuid",
  "driver_id": "uuid",
  "reason": "DOCUMENT_EXPIRED"
}

vehicle.document_expired

{
  "vehicle_id": "uuid",
  "document_id": "uuid",
  "document_type": "INSURANCE"
}

21. Safety Events

21.1 safety.sos_triggered

Payload:

{
  "incident_id": "uuid",
  "ride_id": "uuid",
  "reporter_id": "uuid",
  "location": {
    "latitude": 25.5941,
    "longitude": 85.1376
  },
  "triggered_at": "timestamp"
}

Consumers:

Safety
Notification
Admin
Analytics

21.2 safety.incident_resolved

Payload:

{
  "incident_id": "uuid",
  "resolved_by": "uuid",
  "resolved_at": "timestamp"
}

22. Notification Events

Notification service generally consumes domain events rather than producing business events.

Examples:

ride.accepted
ride.arrived
ride.started
ride.completed
payment.succeeded
payment.failed
penalty.applied
promotion.expiring
vehicle.document_expired
safety.sos_triggered

Notification delivery failure must not normally roll back the source business transaction.

23. Support Events

support.case_created

Payload:

{
  "case_id": "uuid",
  "user_id": "uuid",
  "category": "PAYMENT",
  "priority": "NORMAL"
}

support.escalated

Payload:

{
  "case_id": "uuid",
  "reason": "AI_LOW_CONFIDENCE"
}

24. Advertisement Events

advertisement.campaign_assigned

{
  "campaign_id": "uuid",
  "driver_id": "uuid",
  "assignment_id": "uuid"
}

advertisement.verified

{
  "campaign_id": "uuid",
  "driver_id": "uuid",
  "assignment_id": "uuid",
  "verified": true
}

advertisement.payout_issued

{
  "payout_id": "uuid",
  "driver_id": "uuid",
  "gross_amount": 1000,
  "driver_amount": 800,
  "vistaar_amount": 200
}

25. Event Consumers

Example dependency map:

ride.requested
    → Matching
    → Notification
    → Analytics

ride.accepted
    → Notification
    → Analytics

ride.completed
    → Payment
    → Promotion
    → Notification
    → Analytics

ride.cancelled
    → Penalty
    → Promotion
    → Matching
    → Notification

wallet.debited
    → Notification
    → Analytics

payment.succeeded
    → Ride
    → Wallet
    → Notification
    → Promotion

payment.cash_confirmed
    → Wallet
    → Notification
    → Analytics

penalty.applied
    → Payment
    → Notification
    → Support

verification.approved
    → Driver/Vehicle
    → Pricing
    → Notification

26. Critical Event Rule

Events must not be used where the user needs an immediate authoritative answer.

Example:

Bad:

Driver accepts
→ Kafka
→ Wallet consumer eventually debits

This could allow the ride to be accepted before the platform fee is secured.

Correct:

Driver accepts
→ transactional acceptance boundary
→ wallet debit
→ ride assignment
→ commit
→ publish event

Kafka is then used to notify downstream systems.

27. Transactional Outbox

When a domain changes state:

BEGIN TRANSACTION

UPDATE business table

INSERT INTO shared.outbox_events

COMMIT

Then:

Outbox Publisher
→ Kafka

This prevents:

DB committed
BUT
Kafka event lost

28. Outbox Publisher (IMPLEMENTED — ADR-0071, 2026-09-04, for the retry/
    DLQ half; the base publish/acknowledge/mark-published flow was
    already IMPLEMENTED, ADR-0017)

Publisher behavior:

Read unpublished events
 ↓
Publish to Kafka
 ↓
Receive broker acknowledgement
 ↓
Mark published_at

If publishing fails:

Keep event unpublished
Retry

29. Consumer Idempotency (IMPLEMENTED — ADR-0071, 2026-09-04)

`shared.processed_events` (exactly the recommended table below) is
checked/recorded around every `modules/notification/consumer.py`
handler dispatch — the BEGIN/check/apply/record/COMMIT sequence exactly
as documented. Previously deferred (ADR-0017 §4) for lack of a real
consumer to need it; `NotificationConsumer` (ADR-0038) is now that
consumer.

Consumer transaction:

BEGIN
 ↓
Check event_id
 ↓
Already processed?
 ├── YES → COMMIT/ACK
 └── NO
      ↓
Apply business effect
      ↓
Record event_id
      ↓
COMMIT
 ↓
ACK Kafka

Recommended table:

CREATE TABLE shared.processed_events (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

30. Retry Policy (IMPLEMENTED — ADR-0071, 2026-09-04, for
    shared.outbox_events / the Outbox Publisher)

Recommended retry sequence:

1st failure → 5 seconds
2nd         → 30 seconds
3rd         → 2 minutes
4th         → 10 minutes
5th         → 30 minutes

Exact timings are configurable.

Implemented as a genuine exponential formula (base * multiplier^(attempt-1),
capped at max — `shared/outbox_publisher.py::next_attempt_delay_seconds()`,
`core/config.py`'s `EVENT_RETRY_*` settings), not this exact irregular
sequence reproduced number-for-number — "exact timings are configurable"
above explicitly allows that. The default configuration (base=5s,
multiplier=5, cap=30min, max attempts=5) produces 5s/25s/~2m/~10m/30m
(capped), closely tracking this same recommended progression. Does not
(yet) apply to `modules/notification/consumer.py`'s own message-handling
failures — see that module's `consume_forever()` docstring and ADR-0071
§5 for why that was scoped out deliberately.

After maximum retries:

Dead Letter Topic

31. Dead Letter Topics (IMPLEMENTED — ADR-0071, 2026-09-04, for the
    Outbox Publisher)

Naming:

vistaar.dlq.<domain>

Examples:

vistaar.dlq.payment
vistaar.dlq.wallet
vistaar.dlq.notification
vistaar.dlq.promotion

A DLQ record must retain:

original event
error
consumer
attempt count
first failure
last failure

All six preserved exactly as documented — the DLQ message carries the
original envelope untouched plus a `dlq_metadata` block (`original_topic`,
`attempt_count`, `first_failure_at`, `last_failure_at`, `last_error`
implicitly via the row's own `last_error` column, `failed_by`) — see
ADR-0071 §4 for the exact shape and
tests/test_outbox_publisher.py::test_event_is_dead_lettered_after_max_attempts_and_preserves_metadata
for the proof.

32. Poison Message Handling (PARTIAL — applies to the Outbox Publisher,
    ADR-0071, 2026-09-04; NOT applied to modules/notification/consumer.py)

A malformed or permanently invalid event must not block the Kafka partition indefinitely.

The Outbox Publisher (§28/§30/§31) follows exactly this flow for a
publish that keeps failing. `NotificationConsumer` does not: a message
whose handler keeps raising has no retry-policy/DLQ/alert path of its
own today — it is simply left with its Kafka offset uncommitted (ADR-
0038 Decision 2) and redelivered whenever this consumer group next
starts consuming that partition (a restart or rebalance), with no
attempt cap and no DLQ. Flagged here deliberately (ADR-0071 §5), not
silently left unmentioned — building this for the consumer side would
need its own persistent per-message retry-state store (Kafka itself has
no notion of "retry this one message later with backoff"), a
meaningfully larger addition than reusing the Outbox Publisher's
existing row-based mechanism, and was judged out of scope for the
specific "2 remaining" items (Event retry, Dead-letter handling) this
task closed.

Flow:

Consume
 ↓
Validation fails
 ↓
Retry policy
 ↓
DLQ
 ↓
Alert
 ↓
Manual/replay process

33. Event Schema Versioning

Every event contains:

event_version

Backward-compatible changes may be introduced within the same version.

Examples:

Allowed:

Add optional field

Not allowed:

Rename required field
Change field meaning
Change type
Remove required field

Breaking changes require:

event_version = 2

34. Event Compatibility

Consumers must tolerate unknown optional fields.

Example:

{
  "ride_id": "uuid",
  "driver_id": "uuid",
  "new_optional_field": "value"
}

Older consumers should continue processing the event.

35. Correlation IDs

A single user operation may generate multiple events.

Example:

HTTP request
 ↓
correlation_id = request-123
 ↓
ride.requested
 ↓
matching.offer_created
 ↓
matching.offer_accepted
 ↓
ride.accepted
 ↓
wallet.debited

All related events should retain the same correlation ID when causally connected.

36. Causation IDs

causation_id points to the event or command that directly caused the current event.

Example:

ride.accepted
caused by:
matching.offer_accepted

This helps trace distributed workflows.

37. Event Security

Kafka must use:

TLS

Authentication

ACLs

Least-privilege producers/consumers

A service should publish only to authorized topics.

Example:

Wallet Service
→ can publish wallet.*
→ cannot publish payment.*

38. Sensitive Data

Do not put sensitive secrets into events.

Never publish:

OTP values

Access tokens

Payment credentials

Private API keys

Full document contents

Use references:

document_id
payment_id
evidence_uri

rather than sensitive raw data.

39. Event Retention

Retention depends on event type.

Operational events may have shorter retention.

Financial/audit-related event streams may require longer retention.

Exact retention is TBD based on:

Compliance

Analytics

Recovery

Storage cost

40. Event Replay

Consumers must support replay where practical.

Replay requirements:

Idempotent consumers
Version-aware schemas
No duplicate financial effects

A replay must not:

Credit wallet twice
Apply penalty twice
Consume promotion twice
Issue referral reward twice

41. Financial Event Invariants

For:

wallet.debited
wallet.credited
payment.succeeded
payment.cash_confirmed
payment.settlement_created

the payload must contain enough information to trace the financial operation.

At minimum:

event_id
aggregate_id
transaction/payment ID
amount
currency
transaction type
idempotency key where applicable
occurred_at

42. Ride Event Invariants

Ride events must preserve:

ride_id
current authoritative state
actor where relevant
timestamp
correlation_id

A consumer must not infer a ride state from an old event if it can query the authoritative Ride API.

43. Event Ordering Example

For one ride:

ride.requested
        ↓
matching.offer_created
        ↓
matching.offer_accepted
        ↓
wallet.debited
        ↓
ride.accepted
        ↓
ride.arrived
        ↓
ride.started
        ↓
ride.completed
        ↓
payment.succeeded

Different domains may emit events independently.

Consumers must not assume that unrelated topics are globally ordered.

44. Pickup Change Event Flow — SUPERSEDED (ADR-0056, 2026-08-31)

Current flow (ADR-0056): no event is published for pickup change at
all, either branch.

Customer requests pickup change
        ↓
≤100m: applied immediately (no event)
or
>100m: rejected outright (PICKUP_CHANGE_TOO_FAR, no event)

As originally implemented (ADR-0033, 2026-08-25 — superseded):

Customer requests pickup change
        ↓
Ride validates
        ↓
Pricing calculates
        ↓
Customer confirms
        ↓
ride.pickup_changed
        ↓
Notification
        ↓
Analytics

If >250m:

Driver PASS
→ matching.ride_rematched

Driver PROCEED
→ pricing.fare_revision_created
→ customer confirmation
→ ride.pickup_changed

45. Destination Change Event Flow

Request
 ↓
Pricing
 ↓
fare_revision_created
 ↓
Customer confirmation
 ↓
fare_change_confirmed
 ↓
ride.destination_changed

No fare increase may be applied without the required confirmation.

46. Cash Settlement Event Flow

Customer pays driver
 ↓
Driver confirms
 ↓
payment.cash_confirmed
 ↓
payment.settlement_created
 ↓
wallet.debited

If wallet is insufficient:

wallet.outstanding_settlement_created

The outstanding balance is later settled through recharge.

47. Penalty Event Flow

Example no-show:

ride.no_show
 ↓
penalty.applied
 ↓
notification
 ↓
payment/outstanding charge

Driver cancellation:

ride.cancelled
 ↓
penalty.applied
 ↓
penalty.strike_recorded
 ↓
wallet.debited

Changed-pickup pass:

ride.cancelled/rematched
 ↓
NO penalty
NO strike

48. Promotion Event Flow

Qualifying cancellation:

ride.cancelled
 ↓
Promotion evaluates
 ↓
promotion.restored

Completed ride:

ride.completed
 ↓
promotion.consumed

A promotion consumer must use a unique constraint to prevent duplicate usage.

49. Referral Event Flow

Customer referral:

referral.attached
 ↓
referral.qualified
 ↓
promotion.granted

Driver referral:

driver.approved
 ↓
referral.qualified
 ↓
wallet.credited

50. Verification Event Flow

verification.submitted
 ↓
AI/manual verification
 ↓
verification.approved

or:

verification.submitted
 ↓
verification.manual_review_requested
 ↓
verification.approved/rejected

51. Notification Consumption

Notification service consumes events and converts them into:

Push
SMS
WhatsApp
In-app

The original event remains the business source.

Notification service must not modify ride/payment state.

52. Analytics Consumption

Analytics may consume nearly all domain events.

Analytics failures must not block core transactions.

Recommended architecture:

Kafka
 ↓
Analytics Consumer
 ↓
Data Warehouse / Lake

53. Monitoring

Monitor:

Kafka consumer lag
Event publish failures
DLQ count
Retry count
Processing latency
Event age
Outbox backlog

Critical alerts:

Payment DLQ > threshold
Wallet consumer lag > threshold
Ride event lag > threshold
Outbox backlog growing

54. Event Traceability

Every event should be traceable to:

User request
 ↓
Request ID
 ↓
Domain transaction
 ↓
Event
 ↓
Consumer
 ↓
Side effect

This is especially important for:

Payments

Wallet

Penalties

Promotions

Referrals

Safety

55. Event Contract Testing

Each event requires:

Producer schema test

Consumer compatibility test

Required-field test

Version compatibility test

Idempotency test

Retry test

DLQ test

Critical events require end-to-end tests.

56. Initial Event Registry

Event

Producer

Main Consumers

ride.requested

Ride

Matching, Notification

ride.accepted

Ride

Notification, Analytics

ride.arrived

Ride

Notification, Penalty

ride.started

Ride

Notification

ride.pickup_changed — REMOVED (ADR-0056, 2026-08-31), never published

Ride

Pricing, Notification

ride.destination_changed

Ride

Payment, Notification

ride.completed

Ride

Payment, Promotion

ride.cancelled

Ride

Penalty, Promotion, Matching

matching.offer_created

Matching

Notification

matching.offer_expired

Matching

Matching, Analytics

matching.ride_rematched

Matching

Notification

pricing.fare_calculated

Pricing

Ride

pricing.fare_revision_created

Pricing

Ride, Payment

wallet.debited

Wallet

Analytics, Notification

wallet.credited

Wallet

Notification, Analytics

payment.succeeded

Payment

Ride, Wallet

payment.cash_confirmed

Payment

Wallet, Analytics

payment.settlement_created

Payment

Wallet

promotion.granted

Promotion

Customer/Notification

promotion.consumed

Promotion

Analytics

promotion.restored

Promotion

Notification

referral.qualified

Referral

Promotion/Wallet

referral.reward_issued

Referral

Wallet/Promotion

penalty.applied

Penalty

Payment, Notification

penalty.strike_recorded

Penalty

Driver, Admin

verification.approved

Verification

Driver/Vehicle/Pricing

safety.sos_triggered

Safety

Notification/Admin

driver.approved

Driver

Matching, Referral

driver.ineligible

Driver

Matching, Notification

vehicle.approved

Vehicle

Driver, Matching

vehicle.document_expired

Vehicle

Driver, Matching

support.case_created

Support

Notification

advertisement.payout_issued

Advertisement

Wallet

57. Event Contract Invariants

Events are immutable facts.

Events are versioned.

Events are idempotently consumed.

Same aggregate uses the same partition key.

Financial effects are protected by database constraints and transactions.

The outbox pattern is used for reliable publication.

Consumers use retries and DLQs.

Events never contain secrets.

Correlation and causation IDs are propagated.

Event replay must not duplicate business effects.

58. Next Document

Document chain (corrected to match actual repository folder names — see docs/14-decisions/ for the numbering-reconciliation record):

06-events/event-contracts.md   ← THIS
        ↓
07-state-machines/state-machines.md
        ↓
08-security/security.md
        ↓
10-testing/testing-strategy.md
        ↓
Implementation

docs/09-errors/ is a reserved, currently-empty folder for a future error-catalog document; it is not yet part of this chain.

59. Document Status

Version: 1.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, Domain Design v1.0, Database Design v1.0, API Contracts v1.0