VISTAAR — Domain Design & Service Boundaries

Document Version: 1.0
Status: Draft — Derived from PRD v2.0, Business Rules v1.0, and Technical Architecture v2.0
Market: India
Currency: INR (₹)

1. Purpose

This document defines the business-domain boundaries of VISTAAR.

It answers:

What each domain owns.

What data each domain owns.

What each domain may change.

What APIs/commands each domain exposes.

What events each domain publishes.

What events each domain consumes.

What each domain must not directly access.

Which operations must remain synchronous.

Which operations can be asynchronous.

This document is the bridge between:

PRD
  ↓
Business Rules
  ↓
Technical Architecture
  ↓
DOMAIN DESIGN
  ↓
Database Design
  ↓
API Contracts
  ↓
Implementation

2. Core Domain Principles

DD-001 — One Owner Per Business Fact

Every important business fact has exactly one authoritative domain.

Examples:

Driver profile        → Driver Domain
Vehicle verification  → Vehicle Domain
Ride state            → Ride Domain
Driver matching       → Matching Domain
Fare calculation      → Pricing Domain
Wallet balance        → Wallet Domain
Payment status        → Payment Domain
Promotion entitlement → Promotion Domain
Referral qualification→ Referral Domain
Penalty               → Penalty Domain
Parking verification  → Verification Domain
SOS incident          → Safety Domain

Other domains may maintain read projections, but they must not become competing sources of truth.

3. Domain Map

                         ┌───────────────┐
                         │   Identity    │
                         └───────┬───────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
      ┌─────▼─────┐       ┌──────▼─────┐      ┌──────▼─────┐
      │ Customer  │       │   Driver   │      │   Vehicle  │
      └─────┬─────┘       └──────┬─────┘      └──────┬─────┘
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 │
                          ┌──────▼──────┐
                          │    Ride     │
                          └──────┬──────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
         ┌──────▼─────┐   ┌──────▼─────┐   ┌──────▼─────┐
         │  Matching  │   │  Pricing   │   │ Verification│
         └────────────┘   └────────────┘   └────────────┘
                │                │                │
                └────────────────┼────────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │      Financial Domains      │
                  │ Payment / Wallet / Penalty │
                  └──────────────┬──────────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
         ┌──────▼─────┐   ┌──────▼─────┐   ┌──────▼─────┐
         │ Promotion  │   │  Referral  │   │   Safety   │
         └────────────┘   └────────────┘   └────────────┘
                                 │
                         ┌───────▼────────┐
                         │ Support / AI   │
                         └───────┬────────┘
                                 │
                         ┌───────▼────────┐
                         │     Admin      │
                         └────────────────┘

4. Domain Classification

Core Transaction Domains

Ride

Matching

Pricing

Payment

Wallet

User/Resource Domains

Identity

Customer

Driver

Vehicle

Policy/Entitlement Domains

Promotion

Referral

Penalty

Operational Domains

Verification

Safety

Notification

Support/AI

Advertisement

Admin

5. Identity Domain

5.1 Responsibility

Identity owns authentication and account identity.

5.2 Owns

accounts
sessions
OTP challenges
authentication credentials
account status
device/session metadata

5.3 Commands

RegisterAccount
RequestOTP
VerifyOTP
RefreshSession
Logout
SuspendAccount
ReactivateAccount

5.4 Events

Publishes:

AccountRegistered
AccountVerified
AccountSuspended
AccountReactivated

5.5 Consumes

May consume:

AdminAccountRestrictionRequested

5.6 Must Not Own

Identity must not own:

Ride state

Driver wallet

Fare

Promotions

Driver verification result

6. Customer Domain

6.1 Responsibility

Owns the customer's business profile and customer-specific eligibility data.

6.2 Owns

customers
customer preferences
customer profile
customer status
customer settings

6.3 Commands

CreateCustomerProfile
UpdateCustomerProfile
DeactivateCustomer
ReactivateCustomer

6.4 Events

CustomerCreated
CustomerProfileUpdated
CustomerDeactivated

6.5 Reads From

Customer may read:

Ride projections

Promotion projections

Wallet/charge projections

Support case projections

It does not directly own those records.

7. Driver Domain

7.1 Responsibility

Owns driver identity at the business level, onboarding, eligibility, availability state, and driver behavioral records.

7.2 Owns

drivers
driver documents
driver verification status
driver availability
driver strikes
driver eligibility
driver onboarding state

7.3 Driver State

OFFLINE
ONLINE
ON_RIDE
SUSPENDED
INELIGIBLE

7.4 Commands

CreateDriverProfile
SubmitDriverDocuments
ApproveDriver
RejectDriver
GoOnline
GoOffline
RecordDriverStrike
SuspendDriver
ReactivateDriver

7.5 Events

DriverCreated
DriverApproved
DriverRejected
DriverOnline
DriverOffline
DriverBecameIneligible
DriverStrikeRecorded
DriverSuspended
DriverReactivated

7.6 Must Not Own

Driver does not directly modify:

Ride assignment

Wallet balance

Payment status

Fare calculation

Promotion entitlement

8. Vehicle Domain

8.1 Responsibility

Owns all vehicle resources associated with drivers.

8.2 Owns

vehicles
vehicle documents
vehicle verification
vehicle category
vehicle activation state
vehicle expiry state

8.3 Commands

AddVehicle
UpdateVehicle
SubmitVehicleDocument
ApproveVehicle
RejectVehicle
ActivateVehicle
DeactivateVehicle

8.4 Rules

A driver may have multiple vehicles.

Only an approved and active vehicle may be used for matching.

A vehicle cannot be switched while the driver is ONLINE or ON_RIDE.

8.5 Events

VehicleAdded
VehicleUpdated
VehicleApproved
VehicleRejected
VehicleActivated
VehicleDeactivated
VehicleDocumentExpiring
VehicleDocumentExpired

8.6 Must Not Own

Vehicle domain does not assign rides or calculate fares.

9. Ride Domain

9.1 Responsibility

Ride is the authoritative owner of the ride lifecycle.

9.2 Owns

rides
ride state
pickup
destination
driver assignment reference
ride timestamps
OTP lifecycle reference
ride completion
early-drop records
ride cancellation request

9.3 Ride States

SEARCHING
ACCEPTED
ARRIVED
STARTED
COMPLETED
CLOSED
CANCELLED
NO_DRIVER

9.4 Commands

CreateRide
AssignDriver
MarkArrived
StartRide
RequestPickupChange
ConfirmPickupChange
RequestDestinationChange
ConfirmDestinationChange
RequestEarlyDrop
ConfirmEarlyDrop
CompleteRide
CancelRide

9.5 Events

RideRequested
RideAccepted
RideArrived
RideStarted
RidePickupChanged
RideDestinationChanged
RideEarlyDropRequested
RideEarlyDropConfirmed
RideCompleted
RideCancelled
NoDriverFound

9.6 Critical Rule

Only the Ride Domain may transition the authoritative ride state.

Other domains may request a transition, but cannot directly update ride status.

10. Matching Domain

10.1 Responsibility

Finds and dispatches rides to eligible nearby drivers.

10.2 Owns

driver geo index
ride-offer records
offer timers
dispatch state
matching configuration

10.3 Commands

FindDrivers
CreateDriverOffer
AcceptOffer
RejectOffer
ExpireOffer
RematchRide

10.4 Events

DriverOfferCreated
DriverOfferAccepted
DriverOfferRejected
DriverOfferExpired
RideRematched

10.5 Rules

Driver request timer:

20 seconds

Matching must filter:

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
Required wallet balance
AND
Required documents valid

10.6 Critical Acceptance Boundary

Ride acceptance requires coordination with Wallet.

The authoritative transaction is:

Validate offer
→ Validate ride
→ Validate driver
→ Validate wallet
→ Deduct platform fee
→ Assign driver

This operation must be atomic.

11. Pricing Domain

11.1 Responsibility

Calculates and versions fare quotes.

11.2 Owns

fare_quotes
fare_rules
vehicle pricing rules
fare revisions
additional-charge calculations

11.3 Base Calculation

Base Fare
+ Distance
+ Time
+ Waiting
+ Parking
+ Toll
+ Taxes
- Promotion
+ Approved additional charges
= Final Fare

11.4 Commands

CalculateFare
CreateFareRevision
CalculatePickupChangeCharge
CalculateDestinationChangeFare
ApplyPromotionDiscount

11.5 Events

FareCalculated
FareRevisionCreated
FareChangeRequiresCustomerConfirmation
FareChangeConfirmed

11.6 Rules

Destination change:

Along original route
→ original fare

Beyond original destination
→ ₹8/km additional

Different route
→ recalculate from current location

Pickup change:

≤250m
→ normal flow

>250m
→ additional charge calculation
→ customer confirmation

12. Wallet Domain

12.1 Responsibility

Authoritative owner of driver wallet balances and wallet ledger.

12.2 Owns

wallets
wallet_transactions
wallet configuration
wallet holds/reservations where required

12.3 Commands

CreateWallet
CreditWallet
DebitWallet
ReserveWalletAmount
ReleaseWalletAmount
RechargeWallet
SettleCashCollected
ReverseWalletTransaction

12.4 Events

WalletCreated
WalletCredited
WalletDebited
WalletRecharged
WalletSettlementRecorded
WalletTransactionReversed

12.5 Platform Fees

BIKE → ₹10
AUTO → ₹20
CAB  → ₹20

12.6 Joining Bonus

₹100
expires after 30 days

12.7 Driver Referral Reward

₹100
expires after 30 days

12.8 Critical Rules

Wallet operations require:

Transaction

Idempotency

Immutable ledger

Concurrency control

Audit metadata

Wallet balance must never be modified by another domain through direct database access.

13. Payment Domain

13.1 Responsibility

Owns customer payment lifecycle and gateway interaction.

13.2 Owns

payments
payment intents
payment callbacks
payment allocations
settlement state
refund records
reconciliation state

13.3 Payment Methods

ONLINE
OFFLINE

13.4 Commands

CreatePaymentIntent
ConfirmOnlinePayment
ProcessGatewayWebhook
RecordOfflinePayment
ConfirmCashPayment
CreateSettlement
RequestRefund
ReconcilePayment

13.5 Events

PaymentInitiated
PaymentSucceeded
PaymentFailed
PaymentConfirmed
CashPaymentConfirmed
SettlementCreated
RefundRequested
RefundCompleted

13.6 Must Not Own

Payment must not directly modify:

Wallet balance

Ride state

Promotion entitlement

It requests those domain operations.

14. Cash Settlement Boundary

For an offline ride:

Customer pays driver
        ↓
Driver confirms full amount
        ↓
Payment Domain records payment
        ↓
Payment Domain creates VISTAAR settlement obligation
        ↓
Wallet Domain debits VISTAAR amount

Example:

Ride fare       ₹100
VISTAAR charge   ₹30
Cash received   ₹130

Driver earning  ₹100
VISTAAR          ₹30

If wallet is insufficient:

Outstanding settlement
→ Wallet Domain records liability
→ Future recharge settles it

15. Promotion Domain

15.1 Responsibility

Owns customer promotional entitlements.

15.2 Owns

promotion_entitlements
promotion_usage
promotion_reservations
promotion_rules

15.3 Commands

GrantWelcomePromotion
GrantReferralPromotion
ReservePromotion
ConsumePromotion
RestorePromotion
ExpirePromotion

15.4 Events

PromotionGranted
PromotionReserved
PromotionConsumed
PromotionRestored
PromotionExpired

15.5 Current Rules

Welcome:

3 rides × 50%

Referral customer:

3 additional rides × 50%

Referring customer:

2 rides × 50%

Expiry:

30 days

Discount cap:

TBD

16. Referral Domain

16.1 Responsibility

Owns referral attribution and qualification.

16.2 Owns

referral codes
referral relationships
referral qualification
referral reward records

16.3 Commands

CreateReferralCode
AttachReferral
QualifyCustomerReferral
QualifyDriverReferral
IssueReferralReward
RejectReferral

16.4 Events

CustomerReferralAttached
CustomerReferralActivated
DriverReferralActivated
ReferralRewardIssued
ReferralRejected

16.5 Customer Referral

Activated when the referred customer:

Downloads app
→ Registers/logs in
→ Referral attribution succeeds

A completed ride is not required.

16.6 Driver Referral

Activated after:

Registration
→ Onboarding
→ Verification
→ Approval

17. Penalty Domain

17.1 Responsibility

Owns penalties and behavioral strikes.

17.2 Owns

penalties
behavioral_strikes
penalty expiry
penalty status

17.3 Commands

ApplyCustomerCancellationPenalty
ApplyNoShowPenalty
ApplyDriverCancellationPenalty
RecordStrike
ExpirePenalty
DisputePenalty
ResolvePenalty

17.4 Current Rules

Customer:

First qualifying cancellation → ₹0
Second+ → ₹15

No-show:

₹30 total

Driver:

₹30 + strike

Changed-pickup pass:

₹0 + no strike

17.5 Expiry

Customer penalty validity:

30 days

18. Verification Domain

18.1 Responsibility

Owns evidence verification.

18.2 Verification Types

DRIVER_DOCUMENT
VEHICLE_DOCUMENT
PARKING_PROOF

18.3 Commands

SubmitEvidence
RunAIVerification
ApproveEvidence
RejectEvidence
RequestManualReview
CompleteManualReview

18.4 Events

EvidenceSubmitted
VerificationStarted
VerificationApproved
VerificationRejected
ManualReviewRequested
ManualReviewCompleted

18.5 Parking Proof

Driver uploads proof
→ AI verification
→ Approved
→ Pricing may include parking charge

Target:

≤5 seconds under normal conditions

Ambiguous evidence goes to manual review.

19. Safety Domain

19.1 Responsibility

Owns safety incidents and SOS.

19.2 Owns

safety_incidents
SOS events
safety escalation state

19.3 Commands

TriggerSOS
AcknowledgeSOS
EscalateSOS
ResolveSafetyIncident

19.4 Events

SOSTriggered
SafetyIncidentCreated
SafetyIncidentEscalated
SafetyIncidentResolved

19.5 Data Captured

Where available:

Ride ID

User ID

GPS

Vehicle

Timestamp

Ride state

20. Notification Domain

20.1 Responsibility

Delivers notifications generated by other domains.

20.2 Owns

notification_preferences
notification_delivery_records
templates
delivery status

20.3 Consumes

Examples:

RideAccepted
DriverArrived
RideStarted
FareChanged
RideCompleted
PaymentRequired
PaymentConfirmed
WalletLow
PenaltyApplied
PromotionActivated
PromotionExpiring
DocumentExpiring
SOSTriggered
SupportEscalated

20.4 Rule

Notification failure must not normally roll back a completed business transaction.

Example:

RideAccepted
→ business transaction succeeds
→ notification fails
→ retry notification

21. Support / AI Domain

21.1 Responsibility

Provides customer/driver support and AI-assisted assistance.

21.2 Owns

support_cases
support_messages
AI interaction metadata
escalation records
knowledge references

21.3 Commands

AskSupportAI
CreateSupportCase
EscalateToHuman
ResolveSupportCase

21.4 Allowed AI Tools

Examples:

GetRideStatus
GetFareBreakdown
GetPaymentStatus
GetPromotionStatus
GetCancellationPolicy
CreateSupportCase

21.5 Restricted Tools

Examples:

ModifyWallet
RefundPayment
ApplyPenalty
SuspendDriver
ChangeRideFare

Restricted operations require explicit authorization and applicable human review.

22. Advertisement Domain

22.1 Responsibility

Owns driver advertising programs.

22.2 Owns

campaigns
driver_campaign_assignments
ad verification
ad payout records
partner settlement

22.3 Commands

CreateCampaign
AssignDriver
SubmitInstallationProof
VerifyAdvertisement
CalculatePayout
SettlePayout

22.4 Current Payout

80% → Driver
20% → VISTAAR

Driver payout enters Wallet as a credit.

23. Admin Domain

23.1 Responsibility

Admin is the operational control plane.

It does not become the owner of every business object.

Instead, Admin creates authorized commands against the owning domain.

Example:

Admin
 ↓
"Approve vehicle"
 ↓
Vehicle Domain
 ↓
VehicleApproved

23.2 Admin Capabilities

Customer review

Driver review

Vehicle verification

Parking review

Ride monitoring

Payment review

Wallet review

Penalty review

Promotion review

Referral review

Safety review

Fraud investigation

Account restriction

Support escalation

23.3 Admin Audit

Every administrative action must record:

admin_id
action
target_type
target_id
reason
before_state
after_state
timestamp
request_id

24. Cross-Domain Access Rules

Rule 1

No domain may directly update another domain's tables.

Rule 2

Read access should use:

API

Read model

Event-driven projection

where practical.

Rule 3

Critical financial operations require explicit commands.

Rule 4

Events are notifications of completed facts, not instructions to mutate another domain's database blindly.

25. Domain Dependency Matrix

Domain

May Call

Should Not Own

Identity

Customer, Driver

Ride/Wallet

Customer

Ride, Promotion, Support

Fare calculation

Driver

Vehicle, Matching

Wallet balance

Vehicle

Driver, Verification

Ride

Ride

Matching, Pricing, Payment

Wallet ledger

Matching

Driver, Vehicle, Wallet eligibility

Fare

Pricing

Promotion, Verification evidence

Wallet

Wallet

Payment settlement requests

Ride state

Payment

Wallet, Ride, Promotion

Wallet data

Promotion

Ride, Customer

Payment

Referral

Customer, Driver, Promotion, Wallet

Ride

Penalty

Ride, Wallet

Ride state

Verification

Driver, Vehicle, Pricing

Wallet

Safety

Ride, Driver, Customer, Admin

Fare

Notification

All domains via events

Business state

Support/AI

Read APIs / approved tools

Direct DB mutation

Advertisement

Driver, Wallet

Ride state

Admin

All domains through authorized commands

Direct unrestricted DB writes

26. Synchronous vs Asynchronous Operations

Must be synchronous

Ride acceptance
Wallet platform-fee debit
Ride assignment
Customer fare confirmation
Payment confirmation
Cash payment confirmation
Promotion reservation where required
Penalty creation where user-facing immediately

Can be asynchronous

Notifications
Analytics
Search indexing
Support indexing
Non-critical projections
Fraud signals
Reconciliation
Advertisement settlement processing

27. Ride Acceptance Cross-Domain Transaction

The most sensitive cross-domain operation is driver acceptance.

Required behavior:

Offer PENDING
AND
Ride SEARCHING
AND
Driver eligible
AND
Vehicle eligible
AND
Wallet sufficient
        ↓
Atomic acceptance boundary
        ↓
Wallet debit
        ↓
Ride assignment
        ↓
Offer ACCEPTED

Implementation may use:

A transactional orchestration boundary

Reservation/authorization

Saga with compensating transaction

The exact implementation is an architecture decision, but the business invariant is fixed:

A ride must not become accepted without successfully handling its required platform fee.

28. Fare Change Cross-Domain Flow

Customer/Driver requests change
 ↓
Ride Domain validates request
 ↓
Pricing Domain calculates new quote
 ↓
Ride Domain marks quote PENDING_CONFIRMATION
 ↓
Customer confirms
 ↓
Ride Domain activates quote
 ↓
Notification Domain informs driver/customer

29. Parking Charge Cross-Domain Flow

Driver
 ↓
Verification Domain
 ↓
AI verification
 ↓
VerificationApproved
 ↓
Pricing Domain
 ↓
Parking charge added to fare
 ↓
Customer confirmation if required
 ↓
Payment Domain

Verification does not directly change the customer's payable amount.

30. Cancellation Cross-Domain Flow

Ride cancellation requested
 ↓
Ride Domain classifies event
 ↓
Penalty Domain determines charge/strike
 ↓
Wallet Domain settles driver penalty
 OR
Customer charge becomes outstanding
 ↓
Promotion Domain restores/consumes promotion where applicable
 ↓
Notification Domain informs user

The cancellation decision itself remains owned by Ride.

31. No-Show Cross-Domain Flow

Driver ARRIVED
 ↓
Waiting timer
 ↓
3 minutes
 ↓
Additional 10 minutes
 ↓
No customer
 ↓
Ride Domain → NoShow
 ↓
Penalty Domain → ₹30
 ↓
Customer outstanding charge
 ↓
Notification

32. Customer Online Payment Flow

Customer
 ↓
Payment Domain
 ↓
Payment Gateway
 ↓
PaymentSucceeded
 ↓
Payment allocation
 ├── Ride fare
 └── VISTAAR charges
 ↓
Settlement
 ↓
PaymentConfirmed
 ↓
Ride may move to CLOSED

33. Offline Payment Flow

Ride complete
 ↓
Customer pays driver
 ↓
Driver confirms full amount
 ↓
Payment Domain
 ↓
CashPaymentConfirmed
 ↓
VISTAAR settlement obligation
 ↓
Wallet Domain
 ↓
Debit VISTAAR amount
 ↓
Settlement completed

34. Referral Reward Flow

Customer

Referral attached
 ↓
New customer registers/logs in
 ↓
Referral qualified
 ↓
Referral Domain issues qualification
 ↓
Promotion Domain grants 3 × 50% to referred customer
 ↓
Promotion Domain grants 2 × 50% to referrer

Driver

Referral attached
 ↓
Driver onboarding complete
 ↓
Verification approved
 ↓
Referral qualified
 ↓
Wallet Domain
 ├── ₹100 referrer
 └── ₹100 new driver

All reward operations require idempotency.

35. Driver Joining Bonus Flow

Driver approved
 ↓
Referral/Reward qualification check
 ↓
Wallet Domain
 ↓
Credit ₹100
 ↓
Expiry = 30 days

The bonus credit must have a unique reward key.

36. Document Expiry Flow

Document approaching expiry
 ↓
Notification
 ↓
Document expires
 ↓
Verification Domain
 ↓
Driver becomes ineligible
 ↓
Driver Domain updates eligibility
 ↓
Matching stops new assignments

If driver is already on a ride:

Current ride normally completes
 ↓
Driver becomes ineligible

subject to legal/safety requirements.

37. Read Models

Domains may create projections for efficient UI queries.

Examples:

CustomerRideSummary
DriverEarningsSummary
DriverWalletSummary
CustomerPromotionSummary
AdminRideSearch
AdminDriverSummary

Read models are not sources of truth.

38. Anti-Corruption Boundaries

External providers must not leak their data model into core domains.

Examples:

Payment Gateway
    ↓
Payment Adapter
    ↓
VISTAAR Payment Model

Map Provider
    ↓
Maps Adapter
    ↓
VISTAAR Location Model

AI Provider
    ↓
AI Adapter
    ↓
VISTAAR Verification Result

This allows providers to change without rewriting business domains.

39. Domain Configuration

Business values that may change should be configuration-driven.

Examples:

Bike platform fee = ₹10
Auto platform fee = ₹20
Cab platform fee = ₹20

Driver request timeout = 20 sec
Pickup threshold = 250m
Destination extension = ₹8/km

Customer cancellation grace = 2 min
Customer cancellation penalty = ₹15
No-show = ₹30
Driver cancellation = ₹30

Driver joining bonus = ₹100
Driver referral = ₹100
Promotion expiry = 30 days

Configuration changes must be audited.

40. What Must Never Be Hard-Coded

Do not hard-code in controllers/UI:

Platform fees

Penalties

Promotion amounts

Expiry durations

GPS radii

Request timers

Fare rates

Pickup-change rates

Discount caps

These belong in domain configuration/rule tables.

41. Database Ownership Summary

Identity
├── accounts
├── sessions
└── otp_challenges

Customer
├── customers
└── customer_preferences

Driver
├── drivers
├── driver_documents
└── driver_status_history

Vehicle
├── vehicles
└── vehicle_documents

Ride
├── rides
├── ride_state_history
├── ride_offers*
└── ride_change_requests

Matching
├── dispatch configuration
└── offer/dispatch operational state*

Pricing
├── fare_rules
├── fare_quotes
└── fare_quote_items

Wallet
├── wallets
├── wallet_transactions
└── wallet_holds

Payment
├── payments
├── payment_allocations
├── payment_webhooks
└── settlements

Promotion
├── promotion_entitlements
├── promotion_usage
└── promotion_reservations

Referral
├── referral_codes
├── referrals
└── referral_rewards

Penalty
├── penalties
└── behavioral_strikes

Verification
├── verification_cases
├── evidence
└── verification_results

Safety
├── safety_incidents
└── safety_events

Notification
├── notification_preferences
└── notification_deliveries

Support
├── support_cases
├── support_messages
└── AI interaction records

Advertisement
├── campaigns
├── driver_campaigns
└── advertisement_payouts

Admin
├── admin_users
├── admin_roles
└── admin_audit_logs

* indicates operational data whose final persistence ownership should be finalized during database design.

42. Domain Design Invariants

The following invariants must always hold.

Ride

A ride has at most one active driver assignment.

Matching

A driver cannot accept two active rides through concurrent requests.

Wallet

Wallet balance = sum of valid immutable ledger effects.

Payment

A payment cannot be settled twice.

Promotion

A promotion use cannot be consumed twice.

Referral

A qualifying referral reward can be issued only once.

Penalty

One business event cannot create duplicate penalties.

Verification

One evidence submission has one authoritative verification outcome.

43. Domain Events — Initial Contract List

Identity

AccountRegistered
AccountVerified
AccountSuspended

Driver

DriverApproved
DriverOnline
DriverOffline
DriverSuspended
DriverBecameIneligible

Vehicle

VehicleAdded
VehicleApproved
VehicleActivated
VehicleDeactivated
VehicleDocumentExpired

Ride

RideRequested
RideAccepted
RideArrived
RideStarted
RidePickupChanged
RideDestinationChanged
RideCompleted
RideCancelled
NoDriverFound

Matching

DriverOfferCreated
DriverOfferAccepted
DriverOfferRejected
DriverOfferExpired
RideRematched

Pricing

FareCalculated
FareRevisionCreated
FareChangeConfirmed

Wallet

WalletCredited
WalletDebited
WalletRecharged
WalletSettlementRecorded

Payment

PaymentInitiated
PaymentSucceeded
PaymentFailed
PaymentConfirmed
CashPaymentConfirmed
SettlementCreated
RefundCompleted

Promotion

PromotionGranted
PromotionReserved
PromotionConsumed
PromotionRestored
PromotionExpired

Referral

ReferralQualified
ReferralRewardIssued

Penalty

PenaltyApplied
PenaltyExpired
StrikeRecorded

Verification

EvidenceSubmitted
VerificationApproved
VerificationRejected
ManualReviewRequested

Safety

SOSTriggered
SafetyIncidentCreated
SafetyIncidentResolved

44. Domain Design Rules for Developers

Rule A

Do not import another domain's ORM models to modify them.

Rule B

Do not call another service's database directly.

Rule C

Do not duplicate business rules in frontend code.

Rule D

Do not use Kafka to hide a transaction that requires immediate consistency.

Rule E

Do not use synchronous service calls for work that can safely be event-driven.

Rule F

Every financial operation must have an idempotency strategy.

Rule G

Every state transition must be validated against the current state.

Rule H

Every admin mutation must be audited.

Rule I

Every external integration must be behind an adapter.

Rule J

Every business rule change must update documentation and tests.

45. What Comes Next

This domain design is intentionally not the final database schema or API specification.

Next documents:

04-domain-design/domain-design.md       ← THIS
                ↓
05-database/database-design.md
                ↓
06-api/api-contracts.md
                ↓
07-events/event-contracts.md
                ↓
08-state-machines/state-machines.md
                ↓
09-security/security.md
                ↓
10-testing/testing-strategy.md
                ↓
Implementation

46. Open Decisions

The following remain intentionally TBD:

Final service deployment boundaries.

Whether Go and Node domains are split into separate deployables.

Exact payment gateway.

Exact payout/settlement provider.

Exact fare engine formula.

Exact matching ranking formula.

Exact GPS radii.

Promotion discount cap.

Pickup-change exact rate.

Cancellation strike thresholds.

Emergency-service integration.

Data retention periods.

These must be resolved before the affected implementation is finalized.

47. Document Status

Version: 1.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0
Next: Database Design

The domain boundaries defined here must be reviewed before creating the production database schema.