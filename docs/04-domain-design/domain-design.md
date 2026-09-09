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

At most one of a driver's vehicles may be ACTIVE at a time
(business-rules.md BR-122, approved). Activating a different vehicle
deactivates the previously ACTIVE one as part of the same atomic
operation.

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
GPS dispute records (BR-124/BR-125, ADR-0032)

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
ScheduleRide (IMPLEMENTED, ADR-0057, 2026-08-31 — composed into an
extended CreateRide when the request names a future scheduled_for)
PromoteScheduledRideToSearching (IMPLEMENTED, ADR-0057 — not customer-
or driver-triggered; composed by a Celery Beat task polling every 5
minutes, mirroring ADR-0055's own scheduled-broadcast dispatch task)

Implementation status: CreateRide/AssignDriver/MarkArrived/StartRide/
CompleteRide/CancelRide implemented (Phases 3-7). RequestEarlyDrop/
ConfirmEarlyDrop implemented (Phase 08, ADR-0030, 2026-08-25) — see the
ADR for why no GPS-verification gate exists between them, unlike
MarkArrived/CompleteRide. RequestPickupChange was implemented (Phase
09, ADR-0033, 2026-08-25) with a driver PROCEED/PASS decision step and
a ConfirmPickupChange command; simplified by ADR-0056 (owner decision,
2026-08-31) to a flat 100m hard threshold with no driver decision at
all — RequestPickupChange now either applies the change immediately or
rejects it outright, both in one step, and ConfirmPickupChange no
longer exists (nothing is ever left pending for it to confirm).
RequestDestinationChange/ConfirmDestinationChange
implemented (ADR-0033 Decision 9, 2026-08-25) — BR-080's rate was never
actually TBD (₹8/km, already ratified); the case-classification
algorithm (BR-079/080/081) is an engineering judgment call, not a new
business rule (see the ADR). SubmitGpsDisputeEvidence/ResolveGpsDispute
implemented (BR-124/BR-125,
ADR-0032, 2026-08-25) — not listed above since they didn't exist in this
list before; a GPS dispute itself is auto-opened by MarkArrived/
CompleteRide's own terminal-failure path, not a separate client-initiated
command.

9.5 Events

RideRequested
RideAccepted
RideArrived
RideStarted
RidePickupChanged (REMOVED, ADR-0056, 2026-08-31 — no driver-decision/
confirmation step exists for pickup change anymore to publish this
event from)
RideDestinationChanged
RideEarlyDropRequested
RideEarlyDropConfirmed
RideCompleted
RideCancelled
NoDriverFound
GpsDisputeOpened (BR-124/BR-125, ADR-0032 — event-contracts.md §10.9/10.10)
GpsDisputeResolved
RideSchedulePromoted (IMPLEMENTED, ADR-0057 — fired at SCHEDULED →
SEARCHING, `{"ride_id", "promoted_at"}`; event-contracts.md §10.12)

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
CalculatePickupChangeCharge (REMOVED, ADR-0056, 2026-08-31 — pickup
change has no chargeable path anymore)
CalculateDestinationChangeFare
ApplyPromotionDiscount
CreateFareRule / SubmitFareRuleForReview / PublishFareRule (ADR-0042)
CreatePlatformFeeRule / SubmitPlatformFeeRuleForReview /
  PublishPlatformFeeRule (ADR-0045, 2026-08-26, implemented; the
  identical workflow as the FareRule trio above, applied to
  `pricing.platform_fee_rules`, a separate table since a platform fee
  and a customer fare are different concepts — see the ADR)

Implementation status: CalculateFare (+ApplyPromotionDiscount, folded in
per ADR-0020 Decision 6) implemented since Phase 04. CalculatePickup
ChangeCharge was implemented (ADR-0033, 2026-08-25) — billed the
distance beyond the 250m threshold, at the ride's own per_km rate — and
then removed (ADR-0056, owner decision, 2026-08-31): pickup change no
longer has any chargeable path, so there is nothing left for this
command to compute. CalculateDestinationChangeFare implemented
(ADR-0033 Decision 9,
2026-08-25) — classifies WITHIN_ROUTE/BEYOND_ORIGINAL/DIFFERENT_ROUTE
(BR-079/080/081) and bills accordingly; the route-deviation tolerance
used to classify is an engineering judgment (see the ADR), not itself a
new business value. CreateFareRevision remains unbuilt.
CreateFareRule/SubmitFareRuleForReview/PublishFareRule implemented
(ADR-0042, 2026-08-26) — the Fare Management admin authoring workflow
(Admin Web §4.8): DRAFT -> IN_REVIEW -> PUBLISHED, replacing the old
`active` boolean with a derived liveness check
(`status='PUBLISHED' AND` the effective window), and Publish closing
out the previously-live rule for the same vehicle_category so at most
one is ever live per category. No Edit/Reject transitions exist — only
what the Admin Web plan's own §4.8 table names.
CreatePlatformFeeRule/SubmitPlatformFeeRuleForReview/
PublishPlatformFeeRule implemented (ADR-0045, 2026-08-26) — the
identical workflow, applied to `pricing.platform_fee_rules` (BR-011's
driver platform fee) instead of the customer-facing fare.

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

RECONCILED (ADR-0025, 2026-08-25 — approved P2P Payment Model; extended
ADR-0026, 2026-08-26): §13.1-13.6 below describe a domain that collects
and settles the customer's ride-fare payment. VISTAAR never collects
the ride fare — the customer pays the driver directly, and the platform
fee is a Wallet Domain (§12) concern already resolved (charged to the
driver's wallet at ride acceptance — see technical-architecture.md §18,
ADR-0014). If a Payment domain is built at all, its scope is now two
narrow flows, neither the ride fare: (1) driver wallet-recharge gateway
integration (ADR-0025 rule 7), and (2) customer outstanding-penalty
collection (ADR-0026, Option A — "Customer → VISTAAR," never routed
through the Wallet Domain or the driver). Everything below describes
the now-superseded ride-fare scope.

13.1 Responsibility (superseded)

Owns customer payment lifecycle and gateway interaction.

13.2 Owns (superseded)

payments
payment intents
payment callbacks
payment allocations
settlement state
refund records
reconciliation state

13.3 Payment Methods (superseded — no VISTAAR-collected payment method
exists for the ride fare; BR-035's UPI/Cash describe the customer→driver
payment, not a VISTAAR method)

ONLINE
OFFLINE

13.4 Commands (superseded)

CreatePaymentIntent
ConfirmOnlinePayment
ProcessGatewayWebhook
RecordOfflinePayment
ConfirmCashPayment
CreateSettlement
RequestRefund
ReconcilePayment

13.5 Events (superseded)

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

This constraint is unaffected by ADR-0025 and stays correct regardless
of the Payment domain's narrowed scope.

14. Cash Settlement Boundary

SUPERSEDED IN FULL (ADR-0025, 2026-08-25): this entire flow described
the Payment Domain creating a VISTAAR settlement obligation from a
customer's cash payment, which the Wallet Domain then debits. That
sequence does not exist under the approved model. The correct sequence
is the reverse order and does not involve the Payment Domain at all:

Wallet Domain (§12) debits the platform fee from the driver's wallet,
during ride acceptance (technical-architecture.md §18) — before the
ride happens.
        ↓
Ride happens.
        ↓
Customer pays driver directly (cash or UPI, BR-035) — no domain
involvement beyond the Ride/Customer domains recording that the ride is
complete.

As originally written (superseded):

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
promotion_campaigns (ADR-0041)
promotion_campaign_eligible_customers (ADR-0041)

15.3 Commands

GrantWelcomePromotion
GrantReferralPromotion
ReservePromotion
ConsumePromotion
RestorePromotion
ExpirePromotion
CreateCampaign (ADR-0041)
UpdateCampaign (ADR-0041, DRAFT only)
ActivateCampaign / PauseCampaign / EndCampaign (ADR-0041)
RedeemCampaignCode (ADR-0041)

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

15.6 Campaign (ADR-0041)

An authored, many-times-redeemable coupon definition — distinct from
an Entitlement (one customer's own grant, possibly created BY redeeming
a campaign's code). Lifecycle: DRAFT -> ACTIVE <-> PAUSED, and
DRAFT/ACTIVE/PAUSED -> ENDED (terminal). Editable only in DRAFT — once
ACTIVE/PAUSED it may already have real redemptions, so only its status
can change from then on, never discount terms (same never-rewrite-
history principle Fare Management applies to published fares).
RedeemCampaignCode validates status/window/vehicle-category/eligible-
scope/minimum-fare/usage-limits, then creates an Entitlement with the
discount fields copied from the campaign at that moment (not read live)
— a FLAT campaign's discount_value is represented on that entitlement
as discount_percent=100 + max_discount_amount=<value> (§6.1 of the
ADR), reusing Entitlement's existing two discount fields rather than
adding a new one. The redeemed entitlement's total_uses is the
campaign's ride_count_limit (falling back to 1, single-use per
redemption, when unset), and its expiry is capped at the campaign's own
ends_at in addition to the usual 30-day window.

16. Referral Domain

16.1 Responsibility

Owns referral attribution and qualification.

16.2 Owns

referral codes
referral relationships
referral qualification
referral reward records
referral reward configuration (ADR-0043, 2026-08-26, implemented)

16.3 Commands

CreateReferralCode
AttachReferral
QualifyCustomerReferral
QualifyDriverReferral
IssueReferralReward
RejectReferral
ConfigureDriverBonusRule / ConfigureCustomerRewardRule (ADR-0043,
  implemented) — Create Draft -> Submit for Review -> Publish, the
  identical workflow ADR-0042 established for Fare Management.
  QualifyCustomerReferral/QualifyDriverReferral read the currently-
  PUBLISHED config row at qualification time and copy its values onto
  the issued reward — never read live again afterward, same
  "copy at the moment of the event" principle ADR-0041 §6.1 already
  established for campaign redemption.

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
SearchDriverStrikeHistory (admin read, 2026-08-26, design only — owner
  decision; a read surface over `penalty.strikes`, already fully
  populated by RecordStrike since BR-068 — no new column, no new
  command semantics, `driver.drivers.strikes` stays the at-a-glance
  summary counter it already is)

Implementation status (Phase 13, ADR-0029, 2026-08-25): DisputePenalty is
implemented WITHOUT a dedicated command/endpoint of its own — it is
realized as a Support Case (domain-design.md §21.3's CreateSupportCase,
`category: "PENALTY_DISPUTE"`) that ResolvePenalty (already implemented,
below) then decides. See the ADR for why no new `PenaltyStatus` value or
endpoint was invented for it.

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
SearchSafetyIncidents (admin read, Admin Web §4.13, 2026-08-26 — the
  Acknowledge/Escalate/Resolve commands above were already implemented
  and tested; only the admin HTTP surface, including this search/queue
  read, was missing)

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

Implementation status: IMPLEMENTED for the foundation (ADR-0034,
2026-08-25) — `NotificationService.send()` (IN_APP/SMS real; PUSH/
WHATSAPP raise ChannelNotAvailableError, see the ADR) and
get_or_create_preferences()/update semantics. No HTTP endpoint exists
anywhere in api-contracts.md (the same §0.3 stop condition ADR-0018/
ADR-0021 already hit) — the service layer is composed directly at other
modules' routers instead of exposed. `ride.accepted`/`ride.arrived` are
composed synchronously at the router layer (modules/matching/router.py,
modules/ride/router.py), as a proof the mechanism is real.

Extended (ADR-0038, 2026-08-26): `modules/notification/consumer.py`'s
`NotificationConsumer` is the first real Kafka consumer in this
codebase, additively wiring four more of §20.3's events —
`ride.started`, `ride.completed`, `ride.cancelled`, `penalty.applied` —
each explicitly named as a Notification consumer in event-contracts.md's
own per-event "Consumers:" list (§10.4/§10.8/§10.9/§17.1), not just
domain-design.md's own looser example list here. The remaining §20.3
examples are deliberately deferred, not silently skipped — see ADR-0038
Decision 3 for exactly why each one (SOSTriggered's recipient ambiguity,
PromotionActivated's semantic mismatch with the real `promotion.
reserved` event, FareChanged's redundancy with the same request's own
HTTP response, PaymentRequired/PaymentConfirmed's N/A status under
ADR-0025, WalletLow/PromotionExpiring/DocumentExpiring's missing
scheduled-job trigger, and SupportEscalated's missing real event).

Extended again (ADR-0039, 2026-08-26): the owner approved Celery,
closing the Background Worker Foundation gap ADR-0038 named as the
reason `PromotionExpiring`/`DocumentExpiring` couldn't be built.
`modules/notification/tasks.py` adds both as real Celery Beat periodic
tasks (not this domain's Kafka consumer, since neither event was ever
produced anywhere to consume) — a daily scan warns a customer/driver 3
days (configurable) before a promotion entitlement or an approved
driver/vehicle document expires, using the same `NotificationService.
send()` dispatch and idempotency mechanism the Kafka consumer already
established, keyed by a value derived from the entity's id and its
current `expires_at` (not the id alone, so a renewed entity that later
approaches expiry again still gets warned). `WalletLow` remains
deferred — better wired reactively at a debit than on a schedule.

Extended again (ADR-0044, 2026-08-26, implemented): `templates`
(§20.2's own already-named ownership) becomes a real, admin-editable,
versioned store (`notification.templates`). `send()`'s template
lookup checks the currently-PUBLISHED row for `(template_key,
channel)` first; the exact version rendered is stamped onto the
`Delivery` row it produces (`template_version_id`) so a later template
edit can never appear to change what a past delivery actually said.
The static `SMS_TEMPLATES` Python dict was NOT deleted as originally
planned — resolved during implementation (2026-08-26), the same "no
fallback is too fragile" lesson ADR-0043 already learned: it remains a
last-resort fallback, used only when no PUBLISHED row exists yet for a
given (template_key, channel). See ADR-0044 for the full design.

Extended again (ADR-0050, 2026-08-28, implemented): `safety.
sos_triggered` — the one §20.3 example ADR-0038 deferred specifically
for "recipient ambiguity" — is now wired into `NotificationConsumer`.
The owner resolved the ambiguity: the recipient is VISTAAR's own
internal safety/call-center team (every Super Admin plus every employee
admin holding SAFETY MANAGE access, ADR-0040's permission model), not a
real emergency-service API (BR-112). Sent over both IN_APP and SMS,
unlike every other wired event here (IN_APP-only) — an SOS is
time-sensitive enough that an in-app badge alone isn't treated as
sufficient.

Extended again (ADR-0052, 2026-08-28, implemented): `Channel.PUSH` is
real now too, closing the last gap ADR-0034 originally left ("PUSH/
WHATSAPP have no real provider yet"). `notification.device_tokens`
(new table) holds one row per registered FCM token, written via this
domain's first-ever customer/driver-facing HTTP endpoints
(`POST`/`DELETE /api/v1/notifications/me/devices`, api-contracts.md
§45.1) — reachable by any authenticated account, not tied to one
account type. `NotificationService.send()`'s PUSH branch now looks up
the user's registered devices and dispatches via a `PushProvider`
(mirrors `SmsProvider`'s own dev/real split — `DevConsolePushProvider`
by default, `FcmPushProvider` once `PUSH_PROVIDER=fcm` and a real
Firebase service-account credential are supplied). `Channel.WHATSAPP`
is unaffected — still blocked on BSP selection.

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

Implementation status (Phase 13/14, ADR-0022 + ADR-0029): CreateSupportCase/
ResolveSupportCase implemented (ADR-0022); EscalateToHuman implemented as
AssignSupportCase (ADR-0022 Decision 2 — an admin claiming the case IS the
human escalation, no separate AI actor exists to escalate from);
AskSupportAI BLOCKED (no LLM provider — ADR-0022 Decision 4). Both
dispute concepts this documentation set names (BR-121's ride-fare
disputes, §17.3's DisputePenalty) are filed as ordinary
CreateSupportCase calls (`category: "RIDE_FARE_DISPUTE"` /
`"PENALTY_DISPUTE"`) — see ADR-0029; no dedicated dispute command exists
in this domain either. SearchSupportCases (admin read, Admin Web §4.14,
2026-08-26) added — an admin HTTP surface over
CreateSupportCase/ResolveSupportCase/search now exists (AssignSupportCase
still has no HTTP route: no source document names it as an Admin Web
screen).

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
PauseCampaign / ResumeCampaign / EndCampaign (ADR-0046, 2026-08-26,
  implemented)

22.4 Current Payout

80% → Driver
20% → VISTAAR

Driver payout enters Wallet as a credit.

Implementation status: the domain/service/repository layer
(CreateCampaign through SettlePayout, plus the Pause/Resume/End trio)
is IMPLEMENTED and tested (ADR-0018, 2026-08-24; Pause/Resume/End
added by ADR-0046, 2026-08-26). ADR-0018 originally built no HTTP
router because no endpoint shape was documented anywhere (Item 2, a
§0.3 stop condition); ADR-0046 resolves that with a full admin HTTP
surface, now IMPLEMENTED — campaign management including the new
PAUSED/ENDED lifecycle, driver assignment, installation-proof review,
approve/reject (the existing manual `VerifyAdvertisement`, not a live
Admoto integration — ADR-0018 Item 3 stays deferred), and
payout/settlement monitoring. The 80/20 split above is unchanged.

23. Admin Domain

Implementation status (ADR-0040, BR-126/BR-127, 2026-08-26): Admin
Management and the permission model are IMPLEMENTED — one Super Admin
level plus granular per-module permissions on employee ADMIN accounts,
resolving business-rules.md §43's "Admin roles"/"Permission hierarchy"
TBD markers. See §23.4 below. Of the capabilities §23.2 lists,
Customer review, Driver/Vehicle review (including search/list, not just
detail-by-id, and Suspend/Reactivate Driver), Ride monitoring, Wallet
review (including transaction history), Penalty review, Promotion
review (the Offers/Coupons Campaign CRUD, ADR-0041), Fare Management
(ADR-0042), Safety review, and Support review are implemented (Phase
2/16, ADR-0009/ADR-0022/ADR-0023/ADR-0040/ADR-0041/ADR-0042,
2026-08-26); Fraud investigation and Payment review remain
undocumented API contracts — see docs/15-admin-web/
admin-web-implementation-plan.md for the full per-module gap list.

Approved, design-only as of 2026-08-26 (owner decision batch,
implementation deliberately deferred to a later task, then most of it
resumed the same day, and the remainder resumed on 2026-08-28, under a
broader authorization): Driver Strike History (a read surface over
`penalty.strikes`, §26.2 — no new domain command), and Coupon/Campaign
CSV bulk customer targeting (ADR-0041 §9). Referral Reward
Configuration (ADR-0043, now IMPLEMENTED — see §16.2/§16.3),
Notification Template Management (ADR-0044, now IMPLEMENTED — see §20
above), Platform Fee Management (ADR-0045, now IMPLEMENTED — see §11.4
above), the Advertisement admin surface (ADR-0046, now IMPLEMENTED —
see §22.4 above), Reports/Analytics MVP (ADR-0047, now IMPLEMENTED —
new capability for this domain, §23.2 never listed it before now), and
Settings MVP (ADR-0048, now IMPLEMENTED — see §23.2 below) are
recorded under their own domains (§16, §20, §11, §22, §23.2).

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

Reports / Analytics (ADR-0047, 2026-08-26, implemented — added to
this list by the owner's decision batch; not present before)

Settings (ADR-0048, 2026-08-28, implemented — same)

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

23.4 Admin Permission Model (ADR-0040, BR-126/BR-127)

One Super Admin level, controlled by the core team, provisioned only
out-of-band (`scripts/provision_admin.py`, never a public endpoint —
BR-127). A Super Admin creates employee ADMIN accounts and grants each
one VIEW or MANAGE access per module (database-design.md §33.3); no
fixed role set (no separate SAFETY_ADMIN/FINANCE_ADMIN-as-account-types
— security.md §7's earlier example list is superseded). Permission
changes are enforced server-side on every request, not only reflected
in the Admin Web's own navigation. Admin Management and Settings module
access is never grantable to an employee admin, only ever implicit for
a Super Admin.

Commands (implemented, `modules.admin.service.AdminService`):

CreateEmployeeAdmin
ListAdmins
GetAdmin
UpdateAdminPermissions
DisableAdmin
EnableAdmin
SearchAuditLogs (2026-08-26 — read-only; §23.3's audit fields were
  written from the start, but nothing read them back until now)

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
Ride Domain (updated fare payable to the driver — corrected, ADR-0025,
2026-08-25: not the Payment Domain, since the parking charge is owed to
the driver directly, the same as the rest of the fare, not collected by
VISTAAR)

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
Customer charge becomes outstanding (detailed by ADR-0026, 2026-08-26,
settlement mechanism updated by ADR-0066, 2026-09-03 — surfaced AND
attached, not just displayed, at the customer's next ride booking;
settled by the customer paying the Sarthi directly, combined with the
ride fare, with VISTAAR recovering its own share through the Wallet
Domain at that ride's completion — the opposite of this bullet's
original "never through the Wallet Domain or the driver")
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

32. Customer Online Payment Flow (SUPERSEDED — ADR-0025, 2026-08-25)

No VISTAAR-collected online payment exists for the ride fare. Ride
CLOSED (state-machines.md §10) does not depend on any VISTAAR payment
confirmation — it was never actually gated on this flow in
state-machines.md's own authoritative CLOSED entry conditions, but this
flow's last step below wrongly implied it was.

As originally written (superseded):

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

33. Offline Payment Flow (SUPERSEDED — ADR-0025, 2026-08-25)

The correct flow has no VISTAAR settlement step — the platform fee was
already debited from the driver's wallet at ride acceptance (§12,
technical-architecture.md §18):

Ride complete
 ↓
Customer pays driver directly (cash or UPI, BR-035) — no domain
involvement

As originally written (superseded):

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
RidePickupChanged (REMOVED, ADR-0056, 2026-08-31 — no driver-decision/
confirmation step exists for pickup change anymore to publish this
event from)
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

Exact payment gateway (narrowed — ADR-0025, 2026-08-25: only for driver
wallet recharge; no customer-facing ride-fare gateway is needed).

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