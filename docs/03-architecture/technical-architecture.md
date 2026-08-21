VISTAAR — Technical Architecture & Developer Handbook

Document Version: 2.0
Status: Draft — Reconciled with PRD v2.0 and Approved Business Rules
Audience: Backend, Mobile, Frontend, DevOps, AI, QA, Security
Market: India
Currency: INR (₹)

1. Purpose

This document defines the technical architecture required to implement VISTAAR according to:

PRD v2.0

docs/02-business/business-rules.md

The architecture is subordinate to approved product/business decisions.

Where the previous Technical Architecture v1.0 conflicts with the PRD or business rules, this document takes precedence.

The architecture is designed around:

Domain ownership

Strong financial consistency

Explicit ride state transitions

Event-driven asynchronous processing where appropriate

Synchronous transactions where correctness requires them

Idempotency

Auditability

Security

Future extensibility

2. Architectural Principles

2.1 Business-first architecture

PRD
 ↓
Business Rules
 ↓
Domain Model
 ↓
Architecture
 ↓
API Contracts
 ↓
Database
 ↓
Events
 ↓
Implementation

Technology must not redefine approved business behavior.

2.2 Domain ownership

Each business domain owns its own rules and data.

Other domains interact through:

APIs

Commands

Events

Direct cross-domain database writes are prohibited.

2.3 Financial correctness

Wallet, payment, penalty, promotion, referral, and settlement operations require:

Atomicity

Idempotency

Immutable ledgers

Audit trails

Explicit transaction states

2.4 State-machine correctness

Important entities must use explicit state machines rather than unrestricted status updates.

2.5 Eventual consistency where safe

Real-time notifications, analytics, support indexing, and non-critical projections may be asynchronous.

Financial balances, ride acceptance, and other correctness-critical transitions must use synchronous transactional boundaries.

3. High-Level Architecture

NOTE: the labels "Next.js/PWA" (Customers) and "Node.js/Fastify" (API/BFF)
below are superseded by docs/14-decisions/ADR-0001-backend-and-client-technology-stack.md
— the actual repository implements the Customer app in Flutter and the
backend as a single Python/FastAPI application (no separate BFF service).
The diagram shape (domain APIs behind an API layer, backed by
PostgreSQL/PostGIS, Redis, and Kafka) is retained as-is since it was not
part of the reconciled discrepancy.

                         ┌─────────────────────┐
                         │     Customers       │
                         │   Next.js / PWA     │
                         └──────────┬──────────┘
                                    │ HTTPS/WSS
                                    │
                         ┌──────────▼──────────┐
                         │      API / BFF      │
                         │   Node.js/Fastify   │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼────────────────┐
                    │               │                │
             ┌──────▼──────┐ ┌─────▼─────┐ ┌────────▼────────┐
             │ Ride / Core │ │ Payments  │ │ Support / AI    │
             │ Domain APIs │ │ / Wallet  │ │ / Verification  │
             └──────┬──────┘ └─────┬─────┘ └────────┬────────┘
                    │              │                │
                    └──────────────┼────────────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ PostgreSQL/PostGIS│
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Redis             │
                         │ GEO / Cache / RT  │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Kafka / Event Bus │
                         └───────────────────┘


                         ┌─────────────────────┐
                         │   Driver Flutter    │
                         └──────────┬──────────┘
                                    │ HTTPS/WSS
                                    └──────────► API / BFF

4. Logical Domains

VISTAAR is divided into the following domains:

Identity
Customer
Driver
Vehicle
Ride
Matching
Pricing
Wallet
Payment
Promotion
Referral
Cancellation & Penalty
Verification
Safety
Notification
Support / AI
Advertisement
Admin

5. Domain Responsibilities

5.1 Identity Domain

Owns:

Authentication

OTP

Sessions

Account identity

Account status

Does not own:

Ride state

Wallet balance

Promotions

5.2 Customer Domain

Owns:

Customer profile

Customer preferences

Customer status

Customer ride history projection

Customer eligibility

5.3 Driver Domain

Owns:

Driver profile

Driver onboarding

Driver approval

Driver availability

Driver behavioral state

Driver strikes

Driver eligibility

5.4 Vehicle Domain

Owns:

Vehicle records

Vehicle documents

Vehicle verification

Vehicle activation/deactivation

Vehicle category

Vehicle expiry

A driver may have multiple vehicles.

5.5 Ride Domain

Owns:

Ride lifecycle

Pickup

Destination

Driver assignment

Ride state

Ride timestamps

Ride completion

Early drop

Ride cancellation request

Ride does not directly own wallet balances.

5.6 Matching Domain

Owns:

Driver discovery

Geo-index

Eligibility filtering

Driver request dispatch

20-second request timer

Rematching

Matching does not own final wallet balances.

5.7 Pricing Domain

Owns:

Fare calculation

Fare breakdown

Additional distance

Waiting

Parking

Pickup-change charges

Destination-change calculations

Fare revisions

Pricing produces a versioned fare quote.

5.8 Wallet Domain

Owns:

Driver wallet

Wallet balance

Immutable wallet ledger

Wallet recharge credits

Platform fee deductions

Driver penalties

Referral/joining credits

VISTAAR cash settlement deductions

Wallet is the financial source of truth for driver-side wallet accounting.

5.9 Payment Domain

Owns:

Customer online payments

Payment intents

Payment gateway integration

Payment status

Payment settlement

Payment reconciliation

Refunds

The Payment domain does not directly modify the Wallet database.

5.10 Promotion Domain

Owns:

Welcome promotions

Ride discounts

Promotion entitlement

Promotion usage

Promotion restoration

Promotion expiry

5.11 Referral Domain

Owns:

Referral codes

Referral attribution

Referral qualification

Referral rewards

Abuse prevention

5.12 Cancellation & Penalty Domain

Owns:

Cancellation classification

Customer cancellation charges

Driver cancellation penalties

No-show charges

Strike creation

Penalty expiry

5.13 Verification Domain

Owns:

Driver verification

Vehicle verification

Parking proof verification

AI verification results

Verification audit records

5.14 Safety Domain

Owns:

SOS

Safety incidents

Emergency escalation

Safety case records

Safety audit information

5.15 Notification Domain

Owns:

Push notifications

SMS/WhatsApp notifications

Ride notifications

Wallet notifications

Promotion notifications

Document-expiry notifications

5.16 Support / AI Domain

Owns:

Support conversations

Knowledge retrieval

AI responses

Escalation

Support cases

AI does not directly perform unrestricted financial or safety actions.

5.17 Advertisement Domain

Owns:

Campaigns

Driver campaign assignments

Advertisement verification

Advertisement payouts

Partner integration

5.18 Admin Domain

Owns:

Administrative workflows

Review queues

Manual decisions

Account restrictions

Verification review

Financial review

Safety review

Fraud investigation

6. Technology Stack

The existing stack remains the baseline unless later changed by an ADR.

UPDATED per docs/14-decisions/ADR-0001-backend-and-client-technology-stack.md:
the rows below for Core backend, BFF/API, Customer app, and Admin web reflect
the stack the repository actually implements and CI-tests against, which
superseded the original Go/Node/Next.js-PWA baseline before this document was
reconciled. See the ADR for the evidence and reasoning.

Layer

Technology

Core backend

Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic (ADR-0001; was: Go 1.21+)

BFF/API

Not a separate service in the current implementation — apps/backend is a
single FastAPI application (ADR-0001; was: Node.js + Fastify). Whether a
distinct BFF is introduced later remains an implementation choice, not a
business-policy question.

Relational DB

PostgreSQL 15+

Spatial DB

PostGIS 3.4+

Cache/Geo

Redis 7.2+

Event bus

Apache Kafka 3.6+

Driver app

Flutter

Customer app

Flutter (ADR-0001; was: Next.js PWA)

Admin web

Next.js (ADR-0001; not previously listed in this table)

AI

Groq/OpenAI-compatible LLM

RAG

LangChain.js

Vector store

pgvector

Maps

Mapbox + OSM

Cloud

DigitalOcean Kubernetes

Payment gateway

TBD

Notifications

TBD

The exact service-to-language mapping may be refined during implementation.

7. Service Boundary

The BFF is an API aggregation and security boundary.

It must not become a business-logic dumping ground.

Client
 ↓
BFF
 ↓
Domain service
 ↓
Domain database / transaction

BFF responsibilities:

Authentication/session validation

Request validation

Rate limiting

API composition

Client-specific response formatting

Integration proxying

BFF must not directly modify domain-owned financial records.

8. Database Strategy

PostgreSQL is the primary durable database.

PostGIS handles:

Pickup coordinates

Destination coordinates

Vehicle location history where appropriate

Geo-fencing

Spatial verification

Redis handles:

Driver online state

Driver GEO indexes

Short-lived ride request state

Real-time telemetry

Cache

WebSocket coordination

Kafka handles:

Domain events

Async processing

Notifications

Projections

Reconciliation workflows

9. Core Identity Tables

customers

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) UNIQUE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

drivers

CREATE TABLE drivers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) UNIQUE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'OFFLINE',
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Driver location is not stored as the primary high-frequency operational state in PostgreSQL.

10. Vehicle Schema

The old single vehicle_type field is replaced by a separate vehicle model because one driver can own/use multiple vehicles.

CREATE TABLE vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    category VARCHAR(20) NOT NULL,
    registration_number VARCHAR(30) UNIQUE NOT NULL,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    operational_status VARCHAR(20) NOT NULL DEFAULT 'INACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Vehicle documents belong to the vehicle.

CREATE TABLE vehicle_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id UUID NOT NULL REFERENCES vehicles(id),
    document_type VARCHAR(40) NOT NULL,
    document_number VARCHAR(100),
    expires_at TIMESTAMPTZ,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    evidence_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Driver identity documents use a separate driver-document model.

11. Ride Schema

CREATE TABLE rides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    driver_id UUID REFERENCES drivers(id),
    vehicle_id UUID REFERENCES vehicles(id),

    status VARCHAR(30) NOT NULL,

    original_pickup_geo GEOMETRY(Point, 4326) NOT NULL,
    current_pickup_geo GEOMETRY(Point, 4326) NOT NULL,

    original_drop_geo GEOMETRY(Point, 4326) NOT NULL,
    current_drop_geo GEOMETRY(Point, 4326) NOT NULL,

    fare_quote_id UUID,
    final_fare NUMERIC(12,2),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

12. Ride State Machine

SEARCHING
   │
   ├── driver accepted ──► ACCEPTED
   │
   └── no driver ────────► NO_DRIVER
                              │
                              ├── RETRY → SEARCHING
                              └── FARE_INCREASE → SEARCHING

ACCEPTED
   │
   ├── driver arrives ──► ARRIVED
   └── cancellation ────► CANCELLED

ARRIVED
   │
   ├── OTP valid ───────► STARTED
   └── cancellation ────► CANCELLED

STARTED
   │
   ├── normal end ──────► COMPLETED
   └── early drop ──────► COMPLETED

COMPLETED
   │
   └── payment confirmed ► CLOSED

Additional internal states may be used for payment and settlement without changing the customer-facing ride lifecycle.

13. Ride Request State

A ride request is separate from the ride.

CREATE TABLE ride_offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES rides(id),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    status VARCHAR(30) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Offer states:

PENDING
ACCEPTED
REJECTED
EXPIRED
CANCELLED

Offer timeout:

20 seconds

14. Matching Architecture

Redis GEO indexes:

geo:drivers:BIKE
geo:drivers:AUTO
geo:drivers:CAB

Driver online state:

driver:online:{driver_id}

Driver state contains:

Latitude

Longitude

Vehicle ID

Vehicle category

Availability

Current ride state

Last heartbeat

Matching algorithm:

Ride requested
 ↓
Determine vehicle category
 ↓
Find nearby drivers
 ↓
Filter eligibility
 ↓
Rank by distance/dispatch rules
 ↓
Create offer
 ↓
20-second timer
 ↓
Accepted?
 ├── YES → atomic assignment
 └── NO → next eligible driver

The production search radius and ranking weights remain configurable.

15. Driver Eligibility

Driver must satisfy:

Driver approved
AND
Vehicle approved
AND
Vehicle active
AND
Driver ONLINE
AND
Driver not ON_RIDE
AND
Required wallet balance available
AND
Required documents valid

Document expiry removes eligibility for new rides.

16. Wallet Architecture

The wallet requires:

Current balance

Immutable transaction ledger

Idempotency

Row-level locking

Audit metadata

CREATE TABLE wallets (
    driver_id UUID PRIMARY KEY REFERENCES drivers(id),
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Ledger:

CREATE TABLE wallet_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    ride_id UUID,
    type VARCHAR(50) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    balance_after NUMERIC(12,2) NOT NULL,
    idempotency_key VARCHAR(150) UNIQUE NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

17. Platform Fee Configuration

Do not hard-code platform fees in application logic.

Use configuration:

BIKE → ₹10
AUTO → ₹20
CAB  → ₹20

Example:

CREATE TABLE platform_fee_rules (
    vehicle_category VARCHAR(20) PRIMARY KEY,
    fee_amount NUMERIC(12,2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

This allows future pricing changes without rewriting the wallet engine.

18. Accept-Ride Transaction

Ride acceptance is synchronous and atomic.

Transaction:

BEGIN
 ↓
Lock wallet row
 ↓
Validate ride still SEARCHING
 ↓
Validate offer still PENDING
 ↓
Validate driver eligibility
 ↓
Read vehicle category
 ↓
Read applicable platform fee
 ↓
Validate balance
 ↓
Debit wallet
 ↓
Create immutable ledger entry
 ↓
Assign driver
 ↓
Update offer = ACCEPTED
 ↓
Ride = ACCEPTED
 ↓
COMMIT

If any step fails:

ROLLBACK

No partial acceptance is allowed.

19. Platform Fee Reversal

Cancellation does not mean every fee reversal must be asynchronous.

The cancellation service must first determine whether the driver's platform fee should be reversed.

If reversal is required, it must be idempotent.

For non-critical post-cancellation processing:

RideCancelled
 ↓
Kafka
 ↓
Wallet reversal consumer

The reversal transaction must verify:

Original debit exists.

Reversal does not already exist.

Cancellation reason qualifies.

20. Customer Payment Architecture

The old P2P-only payment architecture is replaced.

VISTAAR supports:

ONLINE
OFFLINE

Online

Customer
 ↓
Payment Intent
 ↓
Payment Gateway
 ↓
Verified Payment
 ↓
Payment Ledger
 ↓
Settlement
 ├── Driver ride amount
 └── VISTAAR-owned charges

Offline

Customer
 ↓
Driver
 ↓
Driver confirms full cash amount
 ↓
Cash settlement record
 ↓
VISTAAR wallet debit

21. Payment Tables

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID REFERENCES rides(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    method VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL,
    gross_amount NUMERIC(12,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    gateway_reference VARCHAR(150),
    idempotency_key VARCHAR(150) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Payment allocations:

CREATE TABLE payment_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID NOT NULL REFERENCES payments(id),
    allocation_type VARCHAR(40) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    beneficiary_reference UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

22. Offline Cash Confirmation

The driver app sends:

{
  "ride_id": "...",
  "expected_amount": 230.00,
  "confirmed_amount": 230.00
}

The server must verify:

confirmed_amount == expected_amount

If false:

Reject confirmation

If true:

Payment → CONFIRMED
Create cash settlement
Create VISTAAR settlement liability

23. Cash Settlement

For:

Ride fare = ₹200
VISTAAR charge = ₹30
Customer pays = ₹230

Ledger concept:

Driver ride earning = ₹200
VISTAAR settlement = ₹30

The driver wallet records:

DEBIT_CASH_SETTLEMENT = ₹30

If insufficient:

OUTSTANDING_SETTLEMENT

The amount is recovered from future recharge according to the wallet settlement rules.

24. Fare Domain

Fare calculations are versioned.

CREATE TABLE fare_quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES rides(id),
    version INT NOT NULL,
    base_fare NUMERIC(12,2),
    distance_charge NUMERIC(12,2),
    time_charge NUMERIC(12,2),
    waiting_charge NUMERIC(12,2),
    parking_charge NUMERIC(12,2),
    toll_charge NUMERIC(12,2),
    promotion_discount NUMERIC(12,2),
    additional_charge NUMERIC(12,2),
    total NUMERIC(12,2) NOT NULL,
    reason VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Every material fare revision creates a new version.

25. Fare Change Approval

For pickup/destination changes:

Calculate
 ↓
Create new quote
 ↓
Show customer
 ↓
Customer confirms
 ↓
Activate quote

No new quote becomes payable without the required confirmation.

26. Pickup Change Architecture

When pickup changes:

Calculate distance from driver's relevant location
to new pickup

If:

distance <= 250m

No special pickup-change charge.

If:

distance > 250m

Driver chooses:

PROCEED
OR
PASS

PROCEED

Calculate additional charge
 ↓
New fare quote
 ↓
Customer confirmation
 ↓
Driver receives confirmation
 ↓
Proceed

PASS

Special cancellation reason
 ↓
No ₹30 penalty
 ↓
No strike
 ↓
Matching resumes near new pickup

27. Destination Change Architecture

Case A — Within original route

Original fare remains.

Case B — Beyond original destination

additional_distance × ₹8/km

Case C — Different route

Recalculate from current location to new destination.

All fare increases require customer confirmation.

28. Promotion Architecture

Promotions are entitlements, not hard-coded counters.

CREATE TABLE promotion_entitlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    promotion_type VARCHAR(50) NOT NULL,
    total_uses INT NOT NULL,
    remaining_uses INT NOT NULL,
    discount_percent NUMERIC(5,2),
    max_discount_amount NUMERIC(12,2),
    activated_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

Promotion use must be idempotent.

29. Welcome Promotion

New customer:

3 rides × 50% discount

The entitlement expires after 30 days.

30. Referral Promotion

Referred customer:

3 additional rides × 50%

Referring customer:

2 rides × 50%

Activation requires successful registration/login through referral.

31. Promotion Reservation

Promotion usage should be reserved when the ride reaches the appropriate financial commitment point.

If an eligible early cancellation occurs:

RESERVED → RESTORED

If a late cancellation occurs:

RESERVED → CONSUMED

The exact early/late boundary is configurable.

32. Referral Architecture

Referral entities:

CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_customer_id UUID,
    referred_customer_id UUID,
    referral_code VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ
);

Rewards are generated only once.

Use a unique qualification key such as:

referral:{referral_id}:activation

33. Penalty Architecture

Penalty records are separate from wallet transactions.

CREATE TABLE penalties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    ride_id UUID,
    type VARCHAR(50) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

This allows:

Expiry

Payment status

Audit

Dispute/review

Wallet settlement

34. Customer Cancellation

Rules:

Driver accepted
 ↓
2-minute grace
 ├── cancel → no penalty
 └── continue
       ↓
qualifying cancellation
       ↓
first → ₹0
second+ → ₹15

Every charge has a 30-day expiry.

35. No-Show

Waiting:

0–3 min   → free
3–13 min  → driver waits
after 13m → no-show

No-show charge:

₹30 total

Expiry:

30 days

36. Driver Cancellation

Normal qualifying driver cancellation:

₹30 penalty
+
1 strike

The penalty is processed through the Wallet domain.

The changed-pickup pass reason is excluded from the normal penalty.

37. Strike System

Strike data is separate:

CREATE TABLE behavioral_strikes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    ride_id UUID,
    reason VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Suspension thresholds are configuration/TBD.

38. Parking Verification

Driver workflow:

Parking incurred
 ↓
Take photo
 ↓
Upload proof
 ↓
Verification service
 ↓
AI confidence/result
 ↓
Approved?
 ├── YES → parking charge eligible
 └── NO → manual review

Target verification latency:

≤ 5 seconds under normal conditions

The final charge is created only after approval.

39. Verification Architecture

Verification service supports:

DRIVER_DOCUMENT
VEHICLE_DOCUMENT
PARKING_PROOF

Each verification has:

Subject

Evidence

Verification result

Confidence

Reviewer

Timestamp

Audit record

40. AI Verification Safety

AI may recommend:

APPROVE
REJECT
REVIEW

AI must not bypass required human review for ambiguous or high-risk evidence.

AI verification must be auditable.

41. OTP Architecture

OTP records must contain:

Ride ID

Customer ID

OTP hash

Expiry

Attempt count

Status

Only the latest valid OTP is accepted.

Generating a new OTP invalidates the previous one.

42. GPS Verification

Arrival verification:

Driver location
within configured pickup radius

Completion verification:

Driver/current ride location
within configured destination radius

The exact radii remain configuration/TBD.

GPS verification events should be stored for audit.

43. Early Drop

Flow:

Customer requests early drop
 ↓
Driver records request
 ↓
Customer confirms
 ↓
Capture GPS + timestamp
 ↓
Complete ride

The original fare remains payable under the approved rule.

44. Safety / SOS

SOS service creates an incident:

CREATE TABLE safety_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID,
    reporter_id UUID NOT NULL,
    type VARCHAR(50) NOT NULL,
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SOS should trigger:

Safety notification

Current ride context

Current location

Admin/Safety case

Emergency-service integration is TBD.

45. Lost and Found

CREATE TABLE lost_item_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL,
    reporter_id UUID NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Driver response:

FOUND
NOT_FOUND
UNRESOLVED

Admin may intervene.

Arbitrary driver return fees are prohibited.

46. Notification Architecture

Domain services emit events.

Notification service consumes:

RideAccepted
DriverArriving
DriverArrived
RideStarted
FareChanged
DestinationChanged
RideCompleted
PaymentRequired
PaymentConfirmed
WalletLow
PenaltyApplied
PromotionActivated
PromotionExpiring
DocumentExpiring
SafetyIncidentCreated
SupportEscalated

Notification delivery must be idempotent.

47. Event Bus

Kafka topics should be domain-oriented.

Example:

ride.events
wallet.events
payment.events
promotion.events
referral.events
safety.events
verification.events
notification.events
support.events

Events should contain:

{
  "event_id": "uuid",
  "event_type": "RideAccepted",
  "aggregate_id": "uuid",
  "occurred_at": "timestamp",
  "version": 1,
  "producer": "ride-service",
  "payload": {}
}

Consumers must support idempotent processing.

48. Outbox Pattern

Any transaction that changes durable business state and publishes an event must use an outbox pattern where required.

Example:

BEGIN
 ↓
Update domain state
 ↓
Insert outbox event
 ↓
COMMIT
 ↓
Outbox publisher
 ↓
Kafka

This prevents:

DB updated
but event lost

49. API Standards

All APIs should use:

/api/v1/...

Responses should use a consistent envelope:

{
  "data": {},
  "error": null,
  "request_id": "..."
}

Errors:

{
  "data": null,
  "error": {
    "code": "INSUFFICIENT_WALLET_BALANCE",
    "message": "Insufficient wallet balance"
  },
  "request_id": "..."
}

50. Core API Examples

Customer

POST /api/v1/rides
GET  /api/v1/rides/{ride_id}
POST /api/v1/rides/{ride_id}/cancel
POST /api/v1/rides/{ride_id}/pickup-change
POST /api/v1/rides/{ride_id}/destination-change
POST /api/v1/rides/{ride_id}/payment
POST /api/v1/rides/{ride_id}/rating

Driver

POST /api/v1/drivers/online
POST /api/v1/drivers/offline
POST /api/v1/ride-offers/{offer_id}/accept
POST /api/v1/ride-offers/{offer_id}/reject
POST /api/v1/rides/{ride_id}/arrived
POST /api/v1/rides/{ride_id}/start
POST /api/v1/rides/{ride_id}/complete
POST /api/v1/rides/{ride_id}/cash-payment/confirm

Wallet

GET  /api/v1/wallet
POST /api/v1/wallet/recharge
GET  /api/v1/wallet/transactions

Verification

POST /api/v1/verification/parking
POST /api/v1/verification/vehicle-document
POST /api/v1/verification/driver-document

51. Idempotency

The following operations require idempotency:

Ride creation

Ride acceptance

Wallet recharge

Platform fee deduction

Fee reversal

Online payment

Cash confirmation

Promotion usage

Promotion restoration

Referral reward

Penalty application

Penalty settlement

Use:

Idempotency-Key

and persist the key with the operation result.

52. Security

Authentication

OTP/session-based authentication

Secure token rotation

Device/session tracking

Authorization

Use role-based authorization:

CUSTOMER
DRIVER
ADMIN
SAFETY_ADMIN
FINANCE_ADMIN
SUPER_ADMIN

Financial APIs

Require:

Authentication

Authorization

Idempotency

Audit logging

Server-side validation

Admin

Admin actions must be audited.

53. Location Privacy

Location data is sensitive.

Requirements:

Only authorized users can access ride location.

Shared ride links must expire.

Historical location retention must be configurable.

Admin access must be audited.

Location should not be exposed unnecessarily after ride completion.

54. AI Support Architecture

Customer
 ↓
Support API
 ↓
AI Orchestrator
 ↓
Retriever
 ↓
Policy Knowledge Base
 ↓
LLM
 ↓
Response

AI tools should be allow-listed.

Examples:

Allowed:

getRideStatus
getFareBreakdown
getCancellationPolicy
createSupportCase

Restricted:

applyPenalty
refundPayment
suspendDriver
modifyWallet

Restricted actions require explicit policy/authorization and, where applicable, human review.

55. Advertisement Architecture

Partner:

Admoto

Flow:

Campaign assigned
 ↓
Driver accepts/receives campaign
 ↓
Advertisement installed
 ↓
Driver uploads live proof
 ↓
Verification
 ↓
Admoto verification
 ↓
Monthly settlement

Payout:

80% Driver
20% VISTAAR

Advertisement payout enters the Driver Wallet as:

CREDIT_AD_PAYOUT

56. Frontend Architecture — Driver

Flutter.

Required screens:

Login/OTP

Driver onboarding

Verification

Vehicle management

Online/offline

Ride request

Navigation

Arrival

OTP

Active ride

Fare change approval

Parking proof

Cash payment confirmation

Ride completion

Wallet

Recharge

Bonuses/referrals

Earnings

Safety/SOS

Lost & Found

Ride request timer:

20 seconds

57. Frontend Architecture — Customer

Flutter (ADR-0001; was: Next.js PWA — see
docs/14-decisions/ADR-0001-backend-and-client-technology-stack.md).

Required screens:

Registration/login

Home/map

Pickup

Destination

Vehicle selection

Fare estimate

Booking/searching

Driver tracking

Cancellation

Fare increase

Pickup change

Destination change

OTP

Active ride

Payment

Promotions

Outstanding charges

Rating

SOS

Ride sharing

Lost & Found

Support

58. Fare Change UI Contract

Whenever a charge changes:

Original fare
₹250

Additional charge
₹40

New total
₹290

[ Confirm ]
[ Cancel ]

Customer confirmation is required where specified by business rules.

59. Driver Cash Confirmation UI

Ride Fare                  ₹200
VISTAAR Charge              ₹30
--------------------------------
Total Cash Required        ₹230

[ CONFIRM ₹230 RECEIVED ]

The server independently validates the expected amount.

60. Observability

Every service must emit:

Structured logs

Metrics

Traces

Request IDs

Event IDs

Critical metrics:

ride_accept_latency
matching_latency
wallet_debit_failures
wallet_balance_mismatch
payment_success_rate
cash_confirmation_failures
promotion_duplicate_attempts
referral_abuse_attempts
parking_verification_latency
sos_incident_count

61. Reliability

Critical operations require:

Database transactions

Idempotency

Retry policies

Dead-letter queues where appropriate

Reconciliation jobs

Audit logs

No financial event should rely exclusively on in-memory state.

62. Reconciliation Jobs

Periodic jobs must compare:

Payment records
vs
Settlement records

Wallet balance
vs
Wallet ledger

Promotion entitlement
vs
Promotion usage

Referral qualification
vs
Referral reward

Ride state
vs
Payment state

Mismatches generate review alerts.

63. Failure Handling

Driver accepts but network disconnects

Server transaction decides whether acceptance succeeded.

Client reconnects and fetches authoritative ride state.

Payment webhook duplicated

Webhook idempotency prevents duplicate credit.

Kafka event duplicated

Consumer idempotency prevents duplicate processing.

App crashes during ride

Ride state remains server-side.

Wallet recharge callback delayed

Payment remains pending until verified.

64. Deployment

Baseline infrastructure:

DigitalOcean Kubernetes
├── API/BFF
├── Core services
├── Workers
├── Notification service
└── Support/AI service

Managed PostgreSQL
Managed Redis
Kafka

The initial cluster size remains subject to load testing and cost validation.

65. Cost Controls

Mapbox usage should be monitored.

LLM usage should have:

Token limits

Rate limits

Model fallback

Caching where appropriate

Messaging costs should be monitored.

No architectural decision should compromise financial correctness solely to reduce infrastructure cost.

66. Testing Strategy

Every approved business rule must have automated tests.

Unit

Fare calculations

Cancellation

Penalties

Promotions

Referral qualification

Wallet calculations

Eligibility

Integration

Ride acceptance

Wallet deduction

Payment

Cash settlement

Parking verification

GPS verification

Concurrency

Two drivers accepting same ride

Two wallet deductions

Duplicate payment callback

Duplicate referral reward

Duplicate promotion use

End-to-end

Customer books
→ Matching
→ Driver accepts
→ Driver arrives
→ OTP
→ Ride
→ Completion
→ Payment
→ Settlement
→ Rating

67. Architecture Decision Records Required

Before implementation, create ADRs for:

Final service boundaries.

Go vs Node ownership.

Payment gateway selection.

Payment settlement model.

Exact fare engine.

Matching ranking.

Event delivery guarantees.

Data retention.

Emergency integration.

AI tool permissions.

68. Migration From Technical Architecture v1.0

The following v1.0 assumptions are explicitly superseded.

v1.0

v2.0

P2P-only ride payment

Online + offline

VISTAAR does not process ride payment

VISTAAR processes online payment

Universal ₹10 fee

Bike ₹10 / Auto ₹20 / Cab ₹20

10-second driver timer

20-second timer

Single vehicle type on driver

Separate vehicle entity

Old cancellation rules

Approved cancellation matrix

Customer penalty paid directly to driver

VISTAAR-owned charge with online/offline settlement

P2P-only payment UI

Payment method selection + settlement

OCR explicitly V2

Parking proof verification is MVP

Static platform fee in code

Configurable fee rules

Direct unrestricted AI strike tool

Restricted, audited AI tools

Basic ride schema

Versioned fare/payment/settlement model

69. Implementation Order

Do not implement all domains simultaneously.

Recommended order:

Phase 1
Identity
Customer
Driver
Vehicle
        ↓
Phase 2
Wallet
        ↓
Phase 3
Ride
Matching
        ↓
Phase 4
Pricing
        ↓
Phase 5
Payment
        ↓
Phase 6
Cancellation / Penalty
        ↓
Phase 7
Promotion / Referral
        ↓
Phase 8
Verification
        ↓
Phase 9
Safety / Notifications
        ↓
Phase 10
Support / AI
        ↓
Phase 11
Advertisement
        ↓
Phase 12
Admin

70. Source-of-Truth Hierarchy

PRD
 ↓
Business Rules
 ↓
Architecture
 ↓
API Contracts
 ↓
Database Schema
 ↓
Events
 ↓
State Machines
 ↓
Code
 ↓
Tests

If code conflicts with the business rules, code is wrong.

If architecture conflicts with the business rules, architecture must be updated.

If a business rule changes, affected downstream artifacts must be reviewed.

71. Final Status

Version: 2.0
Status: Draft — Architecture Reconciled
Product: VISTAAR
Market: India
Currency: INR

This architecture is ready for the next design stage, but implementation must not begin until the remaining TBD decisions that materially affect the affected domain have been finalized.
