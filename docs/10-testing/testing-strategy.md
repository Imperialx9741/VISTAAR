VISTAAR — Testing Strategy

Document Version: 1.0
Status: Draft
API Version: v1
Primary Database: PostgreSQL + PostGIS
Event Transport: Kafka

1. Purpose

This document defines the testing strategy for VISTAAR.

The objective is to ensure that:

Business rules are enforced by the server.

Invalid state transitions are rejected.

Financial operations cannot be duplicated.

Customer and driver flows behave consistently.

GPS verification correctly enforces whatever radius is server-configured.
NOTE: the exact GPS arrival/completion radius is TBD — PRD.md §62 and
business-rules.md §43 explicitly leave it unresolved. This document uses 50m
throughout as an illustrative placeholder value for worked test scenarios; it
is not an approved figure. The test behavior described below (boundary
checks, server authority, retry/dispute handling) remains valid regardless of
which radius is ultimately approved — only the placeholder number changes.
The same caveat applies to the pickup-change rate (placeholder: ₹20/km,
discussed range ₹10–₹20/km, not approved), the GPS retry count (placeholder:
3), and the evidence window (placeholder: 72 hours), none of which are
established in PRD.md or business-rules.md.

Dispute workflows are auditable. NOTE: whether "Dispute" is a formally
approved business domain is itself unresolved — see
docs/14-decisions/ADR-0002-dispute-domain-status.md.

Payment and wallet operations remain financially correct.

Event-driven services remain reliable.

Security controls prevent unauthorized actions.

Production deployments do not introduce regressions.

2. Testing Principles

VISTAAR follows:

Test business rules first
Test server authority
Test negative paths
Test concurrency
Test idempotency
Test financial invariants
Test security boundaries
Test failure recovery
Test real-world user journeys

The most important tests are not only:

"Does the happy path work?"

but also:

"Can the system be tricked into doing something it should never do?"

3. Testing Pyramid

Recommended distribution:

                 E2E
                /   \
              /       \
         Integration  Contract
          /              \
        /                  \
     Unit -------------------

Most logic should be tested at unit level.

Critical service interactions require integration tests.

Critical user journeys require E2E tests.

4. Test Layers

4.1 Unit Tests

Test:

Fare calculation
Penalty calculation
State transitions
GPS distance calculation
Promotion rules
Referral qualification
Wallet calculations
Payment amount validation
Authorization rules

4.2 Integration Tests

Test:

API + database
Service + Redis
Service + Kafka
Payment gateway integration
Object storage
Authentication

4.3 Contract Tests

Test:

REST API contracts
Kafka event schemas
Version compatibility
Consumer/producer expectations

4.4 End-to-End Tests

Test complete journeys:

Customer books
Driver accepts
Ride starts
Ride completes
Payment settles

4.5 Security Tests

Test:

Authentication
Authorization
IDOR/BOLA
Rate limits
Token security
Injection
File uploads
Privilege escalation

4.6 Performance Tests

Test:

Ride request throughput
Driver matching throughput
Concurrent payment operations
Wallet concurrency
Kafka consumer lag
API latency

5. Test Environments

Use separate environments:

LOCAL
TEST
STAGING
PRODUCTION

Production data must not be used directly in automated tests.

Test credentials and payment gateway credentials must be separate from production.

6. Test Data Strategy

Use deterministic test fixtures.

Core fixtures:

Customer
Driver
Vehicle
Ride
Fare Quote
Payment
Wallet
Promotion
Referral
Penalty
Verification Case
Support Case
Advertisement Assignment

Use factory helpers rather than manually duplicating large JSON objects.

7. Test Identifiers

Tests should use generated IDs.

Example:

customer_id = test UUID
ride_id = test UUID
driver_id = test UUID
payment_id = test UUID

Never depend on production IDs.

8. Ride State Machine Tests

Valid transitions must succeed.

SEARCHING → ACCEPTED
ACCEPTED → ARRIVED
ARRIVED → STARTED
STARTED → COMPLETED
COMPLETED → CLOSED

Cancellation tests:

SEARCHING → CANCELLED
ACCEPTED → CANCELLED
ARRIVED → CANCELLED

Invalid transitions must fail.

9. Invalid Ride Transition Tests

Verify rejection of:

SEARCHING → STARTED
SEARCHING → COMPLETED
ACCEPTED → COMPLETED
ARRIVED → COMPLETED
COMPLETED → STARTED
COMPLETED → CANCELLED
CLOSED → ANY
CANCELLED → STARTED
CANCELLED → COMPLETED

Expected:

409 INVALID_STATE_TRANSITION

10. Ride Acceptance Concurrency Test

Scenario:

Ride = SEARCHING

Driver A accepts
Driver B accepts

Expected:

Exactly one succeeds.
Exactly one driver is assigned.

The losing request receives:

RIDE_ALREADY_ASSIGNED

No duplicate ride assignment is permitted.

11. Offer Timer Tests

Offer lifetime:

20 seconds

Test:

Driver accepts at 19.9s
→ success

Driver accepts after expiry
→ reject

Driver does nothing for 20s
→ EXPIRED
→ next driver

Client clock manipulation must not bypass server expiry.

12. Offer Rejection Tests

Test:

Driver rejects
→ offer REJECTED
→ next eligible driver receives offer
→ original driver remains ONLINE

No cancellation penalty is applied.

13. Offer Expiry Tests

Test:

Offer expires
→ offer EXPIRED
→ next driver selected
→ original driver remains ONLINE

Expiry must not create a driver cancellation penalty.

14. Driver Availability Tests

Test:

OFFLINE → ONLINE
ONLINE → OFFLINE
ONLINE → OFFER_PENDING
ONLINE → ON_RIDE

Reject:

SUSPENDED → ONLINE
INELIGIBLE → ONLINE

unless the relevant eligibility condition has been restored.

15. GPS Verification Tests

Configured radius:

50 meters

Test coordinates:

49m → PASS
50m → PASS
50.01m → FAIL
100m → FAIL

Use geospatial distance calculations rather than simple latitude/longitude subtraction.

16. GPS Arrival Tests

Driver reaches within 50m
→ ARRIVED

Outside 50m:

→ ARRIVAL_VERIFICATION_FAILED

The client cannot submit:

gps_verified = true

to bypass server calculation.

17. GPS Completion Tests

Within 50m of destination
→ completion succeeds

Outside 50m:

→ verification fails
→ retry flow

Test boundary conditions around 50m.

18. GPS Early-Drop Tests

Early-drop flow:

Customer requests
→ Driver accepts
→ GPS verification

Within 50m:

→ early drop succeeds
→ ride ends immediately

Outside 50m:

→ retry

19. GPS Retry Tests

Initial attempt plus:

Retry 1
Retry 2
Retry 3

After all fail:

→ manual dispute

Test that the client cannot reset the retry counter by:

Restarting app
Changing device clock
Refreshing API
Submitting a new request

20. GPS Dispute Tests

After all GPS attempts fail:

Manual dispute opens

Verify preservation of:

Driver GPS history
Customer/ride GPS data
Timestamps
Ride details

21. Evidence Upload Tests

Both parties can submit:

Photos
Videos
Documents
Text explanation

Test:

Valid file → accepted
Oversized file → rejected
Invalid file type → rejected
Executable file → rejected
Malformed file → rejected
Unauthorized user → rejected

22. Evidence Window Tests

Evidence window:

72 hours

Test:

71h 59m → accepted
72h boundary → policy-consistent handling
After 72h → rejected

If no evidence is submitted:

Dispute closes
Original GPS result stands

23. Admin GPS Override Tests

Admin can:

APPROVE
REJECT

Test:

Authorized Admin → allowed
Customer → denied
Driver → denied
Unauthorized Admin role → denied

Audit record must contain:

Admin
Decision
Reason
Ride
Timestamp
Original GPS result

24. Early-Drop Tests

Customer can initiate:

Early drop

Driver can:

Accept
Reject

If rejected:

Ride continues normally

No automatic cancellation is created by the early-drop rejection.

Customer can request early drop again later.

There is no early-drop response timer.

25. Early-Drop Fare Tests

Example:

Original fare = ₹250
Early drop approved

Expected:

Fare remains ₹250
Ride ends immediately

The system must not reduce fare merely because the passenger got off early.

26. Destination Change Tests

Intermediate destination:

Original fare = ₹250
New destination lies between original start/end

Expected:

Fare = ₹250

No automatic reduction.

27. Destination Extension Tests

If destination extends beyond original destination:

Additional charge = ₹8/km

Test:

0 km extension → ₹0 additional
1 km → ₹8
2.5 km → ₹20

Use the server's precise monetary calculation and rounding policy.

28. Destination Confirmation Tests

If additional charge exists:

Calculate
→ Show customer
→ Customer confirms
→ Apply

If customer rejects:

Original destination remains

No hidden charge.

29. Multiple Destination Changes

Customer may change destination multiple times.

Each change must:

Use current authoritative ride state
Recalculate applicable charge
Require confirmation where charge changes
Prevent duplicate application

Historical fare revisions must remain traceable.

30. Pickup Change Tests

Threshold:

250m

Test:

249m → no additional charge
250m → no additional charge
>250m → changed-pickup flow

31. Pickup Change PASS Tests

For >250m:

Driver PASS
→ No ₹30 penalty
→ No strike
→ Rematch
→ New pickup used for matching

Test repeated pickup changes.

PASS remains available for each qualifying pickup change.

32. Pickup Change PROCEED Tests

For >250m:

Driver PROCEED
→ Calculate ₹20/km
→ Customer sees charge
→ Customer confirms
→ Pickup change applied

If customer rejects:

Original pickup remains

No hidden charge.

33. Pricing Configuration Tests

The pickup-change rate:

₹20/km

must be server-side configurable.

Destination extension:

₹8/km

must be server-side configurable.

Historical rides must retain the pricing rule version used.

34. Customer Cancellation Tests

Rules:

Within 2-minute grace → ₹0
First qualifying cancellation → ₹0
Subsequent qualifying cancellation → ₹15

Test:

Exactly 2 minutes
Before 2 minutes
After 2 minutes
First cancellation
Second cancellation
Repeated cancellation

The first ₹0 cancellation still counts in cancellation history.

35. Driver Cancellation Tests

Normal driver cancellation:

₹30 penalty
+
strike

Test:

Penalty created once
Strike created once
Wallet debit created once

Changed-pickup PASS:

No ₹30 penalty
No strike

36. Penalty Expiry Tests

Penalty expiry:

30 days

Test:

Before expiry
At expiry
After expiry

No duplicate expiration events.

37. Payment State Tests

Valid:

PENDING → PROCESSING
PROCESSING → SUCCEEDED
PENDING → FAILED
PROCESSING → FAILED
SUCCEEDED → REFUNDED

Invalid:

SUCCEEDED → FAILED
SUCCEEDED → PENDING
REFUNDED → SUCCEEDED

38. Payment Gateway Tests

Test gateway responses:

Success
Failure
Timeout
Duplicate webhook
Invalid signature
Wrong amount
Wrong currency
Unknown payment reference

Only verified gateway success changes payment to:

SUCCEEDED

39. Payment Webhook Idempotency

Send the same webhook:

1 time
2 times
10 times

Expected:

Exactly one payment effect
Exactly one settlement effect
Exactly one relevant wallet effect

40. Online Payment Tests

Example:

Fare = ₹250
Penalty = ₹30
Total = ₹280

Customer pays:

₹280 to VISTAAR

Server verifies payment.

The system must distinguish:

Original fare = ₹250
VISTAAR charge = ₹30
Total = ₹280

Do not silently overwrite the original fare.

41. Offline Payment Tests

Example:

Fare = ₹100
VISTAAR charge = ₹30
Expected cash = ₹130

Test:

₹130 → confirm allowed
₹100 → confirmation rejected
₹120 → confirmation rejected
₹0 → confirmation rejected

42. Driver Cash Confirmation Tests

Driver presses confirmation:

First time → process
Second time → idempotent / already confirmed

No duplicate settlement.

The server determines expected amount.

43. Cash Payment Dispute Tests

After driver confirms full payment:

Normal driver-side dispute is not reopened automatically.

If an authorized dispute is raised:

Admin can review

Admin actions must be audited.

44. Wallet Tests

Test:

Credit
Debit
Recharge
Outstanding settlement

Verify:

Balance = Credits - Debits

under every transaction sequence.

45. Wallet Concurrency Tests

Scenario:

Wallet = ₹100

Request A debit ₹70
Request B debit ₹70

Expected:

Only one ₹70 debit succeeds
Second request fails or becomes invalid
Wallet never becomes negative

46. Outstanding Wallet Tests

Example:

Wallet = ₹10
Charge = ₹30

Expected:

Wallet debit = ₹10
Outstanding = ₹20

Then:

Recharge = ₹200

Expected:

Outstanding recovered = ₹20
Available balance = ₹180

All movements must have ledger entries.

47. Promotion Tests

Promotion:

Granted
→ Active
→ Reserved
→ Consumed

Qualifying cancellation:

Reserved
→ Restored

Expiry:

Active → Expired

Test duplicate consumption and concurrent reservations.

48. Promotion Expiry Tests

Validity:

30 days from grant

Test:

29 days → valid
30-day boundary → policy-consistent
after expiry → invalid

Client cannot modify expiration.

49. Referral Tests

Customer referral:

Attached
→ Qualified
→ Rewarded

Driver referral:

Attached
→ Driver approved
→ Qualified
→ Rewarded

Test:

Self-referral
Duplicate referral
Duplicate reward
Invalid qualification
Expired referral

50. Verification Tests

Test:

PENDING → PROCESSING
PROCESSING → APPROVED
PROCESSING → REJECTED
PROCESSING → MANUAL_REVIEW

Low-confidence AI result must route correctly to manual review.

51. Driver Eligibility Tests

Driver cannot go online if:

Suspended
Required document expired
Vehicle not approved
Vehicle inactive

After approval/restoration:

Driver can become ONLINE

52. Safety/SOS Tests

SOS must:

Create incident
Record ride
Record reporter
Record location
Record timestamp
Notify appropriate systems

SOS must remain available even when ordinary API traffic is rate-limited.

53. Support Tests

Test:

OPEN
→ ASSIGNED
→ IN_PROGRESS
→ WAITING_FOR_USER
→ RESOLVED
→ CLOSED

AI escalation must preserve the original case context.

54. Advertisement Tests

Test:

ASSIGNED
→ PROOF_SUBMITTED
→ UNDER_REVIEW
→ APPROVED/REJECTED
→ PAYOUT_PENDING
→ PAID

Duplicate payout requests must not produce duplicate payouts.

55. API Contract Testing

For every API:

Authentication
Authorization
Request schema
Response schema
HTTP status
Error format
Idempotency
Validation

must be tested.

56. API Error Tests

Important errors:

400 VALIDATION_ERROR
401 UNAUTHORIZED
403 FORBIDDEN
404 NOT_FOUND
409 CONFLICT / INVALID_STATE_TRANSITION
429 RATE_LIMITED
500 INTERNAL_ERROR

Financial APIs must use predictable error semantics.

57. Object Authorization Tests

Attempt:

Customer A reads Customer B's ride
Driver A reads Driver B's wallet
Customer reads driver-only resource
Driver reads unrelated customer evidence
Normal user calls Admin API

Expected:

403 or 404 according to resource disclosure policy

58. Mass Assignment Tests

Submit unauthorized fields:

{
  "role": "ADMIN",
  "wallet_balance": 999999,
  "status": "COMPLETED"
}

Expected:

Fields ignored/rejected
No privileged state changed

59. Rate-Limit Tests

Test repeated requests for:

OTP
OTP verification
Ride creation
Cancellation
Payment
Cash confirmation
Promotion
Referral
Evidence upload
Admin endpoints

Expected:

429 after configured threshold

60. Authentication Tests

Test:

Valid OTP
Invalid OTP
Expired OTP
Reused OTP
Too many attempts
Too many OTP requests
Revoked session
Expired token
Invalid token

No token leakage.

61. File Security Tests

Test:

Valid JPG
Valid PNG
Valid MP4
Valid PDF
Oversized file
Wrong extension
Executable renamed as JPG
Malformed document
Malicious metadata
Unauthorized download

Private evidence must never become publicly accessible.

62. SQL Injection Tests

Test injection payloads against:

Search
Ride IDs
Support fields
Admin filters
Sorting
Pagination
User-controlled query parameters

Expected:

No SQL execution through untrusted input

63. XSS Tests

Where text is displayed:

Support messages
Dispute explanations
Driver/customer names
Admin notes
Advertisement content

test stored and reflected XSS.

64. CSRF Tests

For cookie-authenticated browser endpoints:

Missing CSRF token
Invalid CSRF token
Cross-origin request

must fail.

65. Session Tests

Test:

Session expiry
Refresh-token rotation
Logout
Token revocation
Multiple sessions
Compromised session revocation

66. Audit Log Tests

Sensitive operations must create audit logs.

Test:

GPS override
Penalty waiver
Refund
Wallet adjustment
Driver suspension
Pricing change
Promotion change
Admin role change

Audit records must not be silently deleted or altered through normal application APIs.

67. Event Contract Tests

For every event:

Schema valid
Required fields present
Version correct
Producer authorized
Consumer compatible

Test unknown optional fields.

Older consumers must continue working with compatible schema changes.

68. Event Idempotency Tests

Publish duplicate events:

ride.completed
payment.succeeded
wallet.debited
promotion.consumed
referral.reward_issued

Expected:

Business effect happens once.

69. Outbox Tests

Test:

DB transaction succeeds + outbox succeeds
DB transaction fails + outbox not created
Kafka unavailable + outbox retained
Kafka returns success + event marked published
Publisher restarts + no lost events

70. Dead-Letter Queue Tests

Force permanent consumer failure.

Expected:

Retry sequence
→ DLQ
→ Original event preserved
→ Error recorded
→ Alert generated

Replay must be possible after correction.

71. Kafka Ordering Tests

For one ride:

ride.requested
ride.accepted
ride.arrived
ride.started
ride.completed

must preserve ordering within the configured partition key.

Different rides do not require global ordering.

72. Redis Failure Tests

Simulate Redis failure.

Verify:

Wallet remains correct
Payment remains correct
Ride database state remains authoritative
System fails safely

73. Database Failure Tests

Simulate database outage during:

Ride acceptance
Payment
Wallet debit
Cash confirmation
Promotion consumption

Expected:

No false success
No partial financial transaction
No duplicate recovery transaction

74. Payment Provider Failure Tests

Simulate:

Timeout
5xx
Connection failure
Delayed webhook
Duplicate webhook

Expected:

Payment not marked successful without verification
Reconciliation can recover eventual success

75. Performance Testing

Measure:

API p50
API p95
API p99
Matching latency
Payment latency
Wallet transaction latency
Kafka consumer lag
Database query latency

Thresholds should be defined from production capacity planning.

76. Load Test Scenarios

Simulate:

Normal traffic
Peak booking traffic
Mass driver online/offline
High cancellation spike
Payment spike
Promotion launch
Large notification burst

77. Stress Tests

Increase load beyond expected peak until:

Capacity limit is identified

Verify graceful degradation.

Core financial integrity must remain intact.

78. Soak Tests

Run representative traffic continuously for extended periods.

Look for:

Memory leaks
Connection leaks
Kafka lag growth
Database connection exhaustion
Queue buildup
File-storage growth

79. Mobile Offline Tests

Test:

No internet during ride
Network reconnect
App restart
GPS temporarily unavailable
Duplicate submission after reconnect

The server remains authoritative.

Client retry must use idempotency keys where required.

80. Mobile Clock Manipulation Tests

Change device clock and verify it cannot bypass:

Offer expiry
OTP expiry
Promotion expiry
Evidence deadline
Payment timeout

Server time is authoritative.

81. Network Retry Tests

Simulate:

Request succeeds server-side
Response lost
Client retries

Expected:

No duplicate business effect

Especially for:

Payment
Cash confirmation
Wallet recharge
Ride acceptance
Promotion consumption
Cancellation

82. End-to-End Happy Path

Complete test:

Customer logs in
 ↓
Requests ride
 ↓
Driver receives offer
 ↓
Driver accepts
 ↓
Driver arrives within 50m
 ↓
Customer gives OTP
 ↓
Ride starts
 ↓
Ride completes within 50m
 ↓
Payment succeeds
 ↓
Ride closes

Expected:

All state transitions valid
Payment correct
Events emitted
Notifications generated
Audit data available

83. End-to-End Offline Payment Path

Customer books
 ↓
Driver accepts
 ↓
Ride starts
 ↓
Ride completes
 ↓
Customer owes ₹130
 ↓
Customer pays driver ₹130
 ↓
Driver confirms
 ↓
VISTAAR charge settled from wallet
 ↓
Ledger updated

Verify:

No duplicate debit
No duplicate settlement

84. End-to-End Insufficient Wallet Path

VISTAAR charge = ₹30
Driver wallet = ₹10

Expected:

₹10 debit
₹20 outstanding

Later:

Recharge = ₹200
 ↓
₹20 outstanding recovered
 ↓
₹180 remaining balance

85. End-to-End Pickup Change PASS

Customer changes pickup >250m
 ↓
Driver PASS
 ↓
No penalty
No strike
 ↓
New driver matched
 ↓
New driver receives new pickup

86. End-to-End Pickup Change PROCEED

Customer changes pickup >250m
 ↓
Driver PROCEED
 ↓
₹20/km calculated
 ↓
Customer confirms
 ↓
Pickup updated
 ↓
Ride continues

87. End-to-End Destination Extension

Original destination
 ↓
Customer extends destination
 ↓
Additional distance calculated
 ↓
₹8/km
 ↓
Customer confirms
 ↓
Destination updated
 ↓
Ride continues

88. End-to-End Early Drop

Customer requests early drop
 ↓
Driver accepts
 ↓
GPS within 50m
 ↓
Ride ends immediately
 ↓
Original fare remains payable
 ↓
Normal payment

89. End-to-End Early-Drop GPS Failure

Early drop requested
 ↓
GPS fail
 ↓
Retry 1
 ↓
Retry 2
 ↓
Retry 3
 ↓
Manual dispute
 ↓
Evidence window = 72h
 ↓
Admin APPROVE
 ↓
Treat as normally verified

90. End-to-End GPS Dispute Reject

GPS verification fails
 ↓
Retries exhausted
 ↓
Dispute
 ↓
No evidence within 72h
 ↓
Original GPS result stands

Or:

Evidence submitted
 ↓
Admin REJECT
 ↓
Ride remains completed
 ↓
Marked disputed/rejected
 ↓
Normal payment continues

91. Security Regression Suite

Every release must rerun:

Authentication
Authorization
IDOR
Wallet
Payment
Admin permissions
File uploads
Rate limits
State transitions
Idempotency

92. Financial Regression Suite

Every release affecting financial code must rerun:

Fare calculation
Penalty calculation
Online payment
Offline payment
Wallet debit
Wallet credit
Recharge
Outstanding debt
Refund
Promotion discount
Settlement

93. Critical Invariants

Automated tests must enforce:

Wallet never becomes invalid
Payment cannot be duplicated
Ride cannot be assigned twice
Promotion cannot be consumed twice
Referral reward cannot be issued twice
Penalty cannot be duplicated
Cash payment cannot be confirmed for a partial amount
Invalid state transitions cannot succeed
Client cannot override server-calculated fare
Client cannot override GPS verification
Admin overrides are auditable

94. Database Constraints to Test

Verify constraints for:

Unique event IDs
Unique idempotency keys
Unique wallet transaction references
Unique payment references
Unique promotion reservation/consumption
Unique referral reward
Unique driver assignment

Database constraints are a second line of defense after application validation.

95. Test Naming

Use descriptive names.

Example:

test_driver_cannot_accept_expired_offer()
test_wallet_debit_never_creates_negative_balance()
test_duplicate_payment_webhook_is_idempotent()
test_pickup_pass_has_no_driver_penalty()
test_destination_extension_requires_customer_confirmation()
test_early_drop_requires_driver_acceptance()
test_gps_failure_opens_dispute_after_three_retries()

96. Test Organization

Recommended:

tests/
├── unit/
│   ├── rides/
│   ├── pricing/
│   ├── payments/
│   ├── wallets/
│   ├── promotions/
│   ├── penalties/
│   └── verification/
├── integration/
│   ├── database/
│   ├── kafka/
│   ├── redis/
│   └── payments/
├── contract/
│   ├── api/
│   └── events/
├── e2e/
│   ├── customer/
│   ├── driver/
│   └── admin/
├── security/
└── performance/

97. CI Pipeline

Recommended pipeline:

Commit
 ↓
Lint
 ↓
Type checks
 ↓
Unit tests
 ↓
Security scans
 ↓
API contract tests
 ↓
Integration tests
 ↓
Build
 ↓
E2E tests
 ↓
Deploy to staging
 ↓
Smoke tests
 ↓
Production approval

98. Pull Request Rules

A pull request should not merge when:

Required tests fail
Security scan has blocking finding
Contract test fails
Migration test fails
Critical coverage regression occurs

99. Database Migration Testing

Every migration must test:

Fresh database
Existing database
Upgrade
Rollback where supported
Data preservation
Indexes
Constraints

Never test migrations only against an empty database.

100. Smoke Tests

After deployment, verify:

Health endpoint
Authentication
Customer ride request
Driver offer
Ride acceptance
Payment gateway connectivity
Wallet read
Kafka connectivity
Notification service
Admin login

101. Production Monitoring as Testing

Production verification must monitor:

Error rate
Latency
Payment failures
Wallet failures
Kafka lag
DLQ
Database errors
Authorization failures
GPS verification failures
Dispute volume

An unexpected spike can indicate a regression even when automated tests passed.

102. Release Strategy

For high-risk releases:

Deploy
 ↓
Smoke test
 ↓
Small traffic/canary
 ↓
Monitor
 ↓
Expand

Rollback must be available for application deployments.

Financial/database migrations require special rollback planning.

103. Test Coverage Priority

Highest priority:

1. Wallet
2. Payment
3. Ride state machine
4. Matching/offer acceptance
5. Fare calculation
6. GPS verification
7. Penalties
8. Promotions
9. Authorization
10. Admin actions

104. Definition of Done

A feature is considered test-complete only when:

Unit tests pass
Integration tests pass
API contract tests pass
Relevant E2E tests pass
Negative cases tested
Authorization tested
Idempotency tested where applicable
Audit behavior tested
Database constraints tested

105. Pre-Production Checklist

[ ] Unit tests passing
[ ] Integration tests passing
[ ] Contract tests passing
[ ] E2E tests passing
[ ] Security tests passing
[ ] Payment sandbox tests passing
[ ] Wallet concurrency tests passing
[ ] Kafka/outbox tests passing
[ ] Database migrations tested
[ ] Backup/restore verified
[ ] Monitoring configured
[ ] Alerts configured
[ ] Rollback plan ready

106. Critical Business Acceptance Checklist

Before production, verify:

IMPORTANT — items marked (TBD VALUE) below name a specific number only as a
placeholder for the worked test scenarios earlier in this document. The
number itself is NOT approved (see PRD.md §62, business-rules.md §43). Before
this checklist can be used as an actual production go-live gate, each (TBD
VALUE) item's real figure must be resolved by an explicit business decision
and this checklist updated to match. Items without that marker use values
that ARE approved in business-rules.md.

[ ] Arrival GPS verification enforced (TBD VALUE — placeholder used: 50m)
[ ] Completion GPS verification enforced (TBD VALUE — placeholder used: 50m)
[ ] Early-drop GPS verification enforced (TBD VALUE — placeholder used: 50m)
[ ] Configured number of additional GPS retries enforced (TBD VALUE — placeholder used: 3)
[ ] Manual dispute after failed retries
[ ] Evidence window enforced (TBD VALUE — placeholder used: 72 hours)
[ ] Customer + driver evidence
[ ] Admin APPROVE/REJECT
[ ] Admin GPS override
[ ] Rejected dispute remains completed
[ ] Early drop ends ride immediately
[ ] Full original fare on early drop
[ ] Customer-only early-drop initiation
[ ] Driver may reject early drop
[ ] Multiple early-drop requests allowed
[ ] Intermediate destination keeps original fare
[ ] Destination extension = ₹8/km
[ ] Pickup threshold = 250m
[ ] Pickup PROCEED additional charge enforced (TBD VALUE — placeholder used: ₹20/km; discussed range ₹10–₹20/km, not approved)
[ ] Pickup PASS has no penalty/strike
[ ] Customer confirms additional charges
[ ] Offer timer = 20 seconds
[ ] Driver remains online after reject/expiry
[ ] Driver cancellation = ₹30 + strike
[ ] Customer cancellation rules enforced
[ ] Penalty expiry = 30 days
[ ] Promotion expiry = 30 days
[ ] Offline payment requires full payment confirmation
[ ] Wallet recovers outstanding amount on recharge
[ ] Whether "Dispute" is a formally approved domain has been decided (see docs/14-decisions/ADR-0002-dispute-domain-status.md) before Phase 7 dispute items above are treated as scoped

107. Final Testing Invariants

The following must never fail in production:

No double payment
No double wallet debit
No double wallet credit
No double promotion use
No double referral reward
No double penalty
No double ride assignment
No unauthorized admin action
No unauthorized resource access
No client-controlled fare
No client-controlled payment success
No client-controlled GPS verification
No negative wallet balance
No lost financial ledger transaction
No lost outbox event

108. Document Status

Version: 1.0
Status: Draft

Derived from:

PRD

Business Rules

Technical Architecture

Domain Design

Database Design

API Contracts

Event Contracts

State Machines

Security Design

Finalized VISTAAR business decisions