VISTAAR — Product Requirements Document

Document Version: 2.0
Status: Draft — Updated with Approved Business Rules
Product: VISTAAR
Market: India
Currency: Indian Rupee (INR / ₹)
Languages: English, Hindi
Initial Vehicle Categories: Auto, Bike, Cab

1. Product Overview

VISTAAR is an India-focused ride-matching platform designed to connect customers with nearby drivers and provide affordable, convenient, transparent, and reliable transportation services.

VISTAAR initially supports:

Auto

Bike

Cab

The product is designed around transparent pricing, customer and driver choice, reliable ride state management, driver wallet accounting, safety, and an extensible architecture.

2. Product Vision

Provide affordable, convenient and accessible transportation by efficiently connecting customers with eligible nearby drivers.

VISTAAR's long-term vision is to become a scalable transportation platform for the Indian market with support for additional vehicle categories and services.

3. Product Goals

3.1 Primary Goals

Provide affordable rides.

Make ride booking simple.

Connect customers with nearby eligible drivers efficiently.

Provide real-time ride and driver tracking.

Provide a reliable ride lifecycle.

Maintain accurate wallet and platform-fee accounting.

Provide customer and driver safety functionality.

Support English and Hindi.

Support UPI and cash payment flows.

Provide transparent fare and charge disclosure.

Support promotions and referrals without allowing promotional abuse.

Build an architecture capable of supporting additional vehicle categories and future features.

3.2 Affordability Goal

VISTAAR's primary product differentiation is affordability.

The exact target reduction compared with competing platforms remains TBD and must be established through unit-economics analysis before launch.

4. Non-Goals

The following remain outside the initial MVP unless separately approved:

AI Voice Agent

Fleet Owner Portal

Scheduled rides

Ride pooling

Subscription programs

Parking OCR clarification

Parking proof verification is an MVP business requirement. The driver must upload proof and VISTAAR may use AI verification. Full OCR automation is an implementation detail and may be introduced incrementally.

In-App Chat clarification

General customer-driver chat is not required for MVP. Safety/support communication is handled through defined support mechanisms.

5. Target Users

5.1 Customer

A person who uses VISTAAR to book transportation.

5.2 Driver

A verified driver who uses VISTAAR to receive and complete rides.

5.3 Admin

Authorized VISTAAR personnel responsible for operational monitoring, verification, support, safety, financial review, and platform management.

6. Geographic Scope

Initial market:

India

Currency:

INR / ₹

Languages:

English

Hindi

The application must use localization so additional Indian languages can be added without major redesign.

7. Vehicle Categories

MVP:

Auto

Bike

Cab

The architecture must support future vehicle categories without redesigning the ride-matching domain.

8. Customer Registration and Authentication

Customers must be able to:

Register

Log in

Verify their account

Maintain their profile

Access their ride history

Access promotions and outstanding charges

The exact authentication provider is TBD.

Recommended MVP:

Mobile number

OTP

9. Driver Registration and Verification

Driver onboarding must support:

Personal information

Full name

Mobile number

Date of birth

Address

Profile photo

Identity

Government identification

Driving licence

Vehicle

RC

Insurance

Registration number

Vehicle photo

Vehicle category

Payment

Required payout/payment details

Exact KYC requirements must be finalized according to applicable Indian requirements.

A driver must be approved before receiving rides.

10. Vehicle Management

A driver may have multiple vehicles.

Example:

Driver
├── Bike → Approved
├── Auto → Approved
└── Cab → Pending

Each vehicle is independently verified.

A driver may deactivate an approved vehicle temporarily.

A driver cannot switch vehicles while:

ONLINE

ON_RIDE

The driver must:

Go OFFLINE
→ Select approved vehicle
→ Activate vehicle
→ Go ONLINE

11. Driver Document Expiry

VISTAAR must notify drivers before required documents expire.

When a required document expires:

Driver
→ Temporarily ineligible for new rides
→ Renew document
→ Verification
→ Approval
→ Eligible again

If a required document expires during an active ride, the current ride should normally be allowed to complete, subject to safety/legal requirements. The driver becomes ineligible for new rides afterward.

12. Customer Ride Booking

The customer must be able to:

Select pickup.

Select destination.

Select vehicle category.

View estimated fare.

View applicable outstanding charges.

View applicable promotions.

Request a ride.

Receive driver assignment.

Track the driver.

Start the ride using OTP.

Change pickup where permitted.

Change destination where permitted.

View fare changes before accepting them.

View final fare.

Select online or offline payment.

Complete payment.

Rate the driver.

13. Ride Lifecycle

Core lifecycle:

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

Cancellation or special flows may branch from the normal lifecycle.

Important state transitions:

SEARCHING → ACCEPTED
Driver accepts and platform fee is atomically processed.

ACCEPTED → ARRIVED
Driver reaches verified pickup area.

ARRIVED → STARTED
Customer OTP is successfully verified.

STARTED → COMPLETED
Ride ends and completion is verified.

COMPLETED → CLOSED
Required payment confirmation is completed.

14. Driver Online / Offline

Driver states:

OFFLINE

ONLINE

ON_RIDE

An offline driver does not receive normal ride requests.

A driver on an active ride does not receive another normal ride request.

If a driver has a pending request, the driver cannot immediately go offline.

The driver must:

Reject
OR
Allow request timer to expire

Then the request proceeds to the next eligible driver and the driver may go offline.

15. Driver Location Tracking

Drivers periodically transmit location.

The real-time location system should maintain:

Current latitude

Current longitude

Availability

Vehicle category

Ride state

The technical architecture may use Redis GEO or an equivalent real-time geospatial system.

The target location update interval is approximately 5 seconds, subject to mobile/OS constraints.

16. Driver Matching

VISTAAR prioritizes the nearest eligible driver.

Eligibility includes:

Driver approved

Vehicle approved

Correct vehicle category

Driver ONLINE

Driver not already assigned to another active ride

Required wallet balance available

The exact dispatch-ranking algorithm can include distance and operational eligibility rules.

17. Ride Request Timer

Each driver receives:

20 seconds to respond to a ride request.

If the driver accepts:

Driver → Ride assigned

If the driver rejects:

Reject
→ Next eligible driver

If the timer expires:

Timer expires
→ Next eligible driver

18. No Driver Accepts

If no driver accepts the ride, the customer receives:

Retry

Increase Fare

Predefined fare increases:

+₹10

+₹20

+₹40

Custom

Fare increase is always voluntary.

It is never applied automatically.

The entire customer-approved fare increase belongs to the driver, while the normal VISTAAR platform fee still applies.

Example:

Original fare = ₹180
Customer increase = ₹40

Driver ride fare = ₹220
VISTAAR platform fee = normal vehicle fee

Custom increase limits are TBD.

19. Fare Model

The initial fare model is:

Base Fare
+ Distance Charge
+ Time Charge
+ Applicable Waiting Charge
+ Applicable Parking Charge
+ Applicable Toll
+ Applicable Taxes
= Ride Fare

Exact rates remain TBD:

Base fare

Per-km rate

Per-minute rate

Waiting rate

Toll treatment

Taxes

Minimum fare

Vehicle-specific base rates

20. Driver Platform Fee

VISTAAR uses a fixed platform fee rather than a percentage commission on the ride fare.

Vehicle

Platform Fee

Bike

₹10

Auto

₹20

Cab

₹20

The platform fee is deducted when the driver accepts the ride.

The fee and ride assignment must be processed atomically.

A driver cannot accept a ride when the wallet balance is insufficient for the applicable platform fee.

21. Driver Wallet

The driver wallet is used for VISTAAR platform transactions.

It may contain:

Driver balance

Platform-fee deductions

Driver penalties

Joining bonuses

Referral bonuses

Advertisement payouts

Cash settlement deductions

Reversals

Complete transaction ledger

Wallet transactions must be immutable ledger entries.

The system must prevent:

Double deductions

Duplicate credits

Incorrect balances

Concurrent balance corruption

Missing ledger entries

All financial operations must be idempotent.

22. Wallet Recharge

Minimum wallet recharge:

₹200

Supported methods:

UPI

Credit card

Debit card

The wallet is credited only after successful payment verification.

A driver may recharge during an active ride, but the recharge does not change the platform fee already applied to that accepted ride.

23. Wallet Withdrawal

Driver wallet withdrawal is not supported in MVP.

The wallet is a platform transaction balance and not a general-purpose bank account.

24. Driver Joining Bonus

A newly approved driver receives:

₹100 wallet credit

Activation:

Registration
→ Required verification
→ Approval
→ ₹100 credited

The joining bonus expires after:

30 days

25. Driver Referral Program

When an existing driver successfully refers a new driver:

Existing driver → ₹100
New driver      → ₹100

The referral becomes successful after the new driver:

Registers through the referral.

Completes required onboarding.

Passes verification.

Is approved.

Referral rewards expire after:

30 days

Self-referrals, duplicate accounts, fake accounts, and referral farming must not generate rewards.

26. Customer Payment Model

VISTAAR supports two customer payment methods:

Online through VISTAAR.

Offline through the driver.

The payment model must distinguish between:

Driver ride earnings

VISTAAR-owned charges

27. Online Customer Payment

When the customer selects online payment:

Customer
    ↓
VISTAAR Payment Gateway
    ↓
Payment received
    ↓
Financial split
    ├── Ride fare → Driver settlement
    └── VISTAAR charges → VISTAAR

Example:

Ride fare = ₹100
Penalty = ₹30

Customer pays = ₹130

₹100 → Driver
₹30  → VISTAAR

The customer must see the complete breakdown before payment.

Example:

Ride Fare                 ₹100
Outstanding Charge         ₹30
--------------------------------
Total                     ₹130

28. Offline Customer Payment

If the customer selects offline payment, the customer pays the complete displayed amount to the driver.

Example:

Ride fare = ₹100
VISTAAR charge = ₹30

Cash required = ₹130

The Driver App must show:

Ride fare                 ₹100
VISTAAR charge             ₹30
--------------------------------
Total cash required       ₹130

[ CONFIRM ₹130 RECEIVED ]

The driver must press the confirmation button only after receiving the full amount.

29. Partial Cash Payment

If the customer pays less than the displayed total:

Driver must NOT confirm payment.

The driver should request the remaining amount.

If the driver confirms full payment, the payment event is treated as confirmed for that transaction.

30. VISTAAR Cash Settlement

When the driver collects a VISTAAR-owned charge in cash:

Ride fare                 → Driver earnings
VISTAAR charge            → VISTAAR settlement liability

The VISTAAR portion is not driver income.

After the driver confirms receiving the complete amount, the applicable VISTAAR amount is deducted from the driver's wallet.

If the wallet does not contain enough balance:

Outstanding settlement
→ Remains attached to driver
→ Recovered from future recharge

Example:

Outstanding = ₹30
Driver recharges = ₹200

₹30 → settlement
₹170 → usable wallet balance

31. Customer Cancellation

Cancellation rules:

First qualifying cancellation

Penalty:

₹0

Second and subsequent qualifying cancellations

Penalty:

₹15

Cancellation grace period

2 minutes after driver acceptance

Cancellation within the 2-minute grace period does not incur the ₹15 charge.

The driver's platform fee is refunded when a qualifying customer cancellation causes the ride to terminate.

Each applicable customer cancellation charge expires after:

30 days

32. Customer No-Show

When the driver reaches the pickup area:

First 3 minutes = free waiting

Then:

Additional 10 minutes = driver waiting period

Total waiting period:

13 minutes

If the customer does not arrive:

No-show charge = ₹30 total

The charge is not ₹30 + ₹30.

The no-show charge expires after:

30 days

33. Driver Cancellation

Normal qualifying driver cancellation:

₹30 penalty

A behavioral strike is also recorded.

Repeated cancellations may result in:

Cancellation
→ Strike
→ Warning
→ Temporary suspension
→ Admin review

Exact suspension thresholds are TBD.

34. Special Driver Cancellation — Changed Pickup

If the customer changes the pickup location by more than 250 meters and the driver does not want to travel to the new location:

Driver may pass/cancel
→ No ₹30 penalty
→ No cancellation strike
→ Ride is rematched to a nearby eligible driver

This is a distinct cancellation reason and must not be treated as ordinary driver cancellation.

35. Pickup Location Changes

Customers may change pickup during the ride request/assignment flow.

Within 250 meters

If the changed pickup is within 250 meters of the driver's relevant current location:

Ride continues normally.

More than 250 meters

If the new pickup is more than 250 meters away:

The driver gets two choices:

Proceed to the new pickup.

Pass/cancel without penalty.

If the driver accepts the new pickup:

Calculate additional charge
→ Show charge to customer
→ Customer confirms
→ Driver proceeds

The driver must not proceed toward a chargeable changed pickup before customer confirmation.

The additional charge applies to the extra distance beyond the 250-meter threshold.

The exact rate is TBD; the current business direction is approximately ₹10–₹20/km.

36. Destination Changes

Destination changes follow these rules.

Case A — New destination remains within the original route/end area

If the customer changes the destination to a point between the original pickup and original destination:

Original fare remains ₹250

for the example where the original fare was ₹250.

Case B — New destination is beyond the original destination

Additional distance is charged at:

₹8/km

from the applicable original destination boundary/current route calculation to the new destination.

Example:

Original fare = ₹250
Additional distance = 5 km
Additional charge = ₹40
Final fare = ₹290

Case C — New destination creates a materially different route

VISTAAR should recalculate the applicable fare from the driver's current location to the new destination.

Whenever the destination change changes the payable amount:

New fare calculated
→ Customer sees revised fare
→ Customer confirms
→ Driver receives updated route/fare
→ Ride continues

No changed fare may be silently imposed.

37. Ride Start OTP

OTP verification is required before a ride transitions from ARRIVED to STARTED.

If OTP is incorrect:

Retry
OR
Generate/refresh OTP

When a new OTP is generated, the previous OTP becomes invalid.

Repeated failure should escalate to support/admin rather than allowing an unsafe bypass.

38. Driver Arrival

The Driver App may mark ARRIVED only when the driver is within the configured pickup GPS radius.

The exact production radius is TBD.

The waiting timer starts from a verified arrival event.

39. Early Drop

A customer may request to end the ride before the original destination.

The driver must record:

Customer requested early drop

The customer confirms the request.

VISTAAR records:

Ride ID

GPS location

Timestamp

Driver confirmation

Customer confirmation

Reason

Under the current approved business rule, the original fare remains payable even when the customer requests an early drop.

40. Normal Ride Completion

Normal completion requires GPS verification.

Flow:

Driver selects Complete
→ VISTAAR verifies destination GPS
→ Destination verified
→ Ride COMPLETED

The exact destination verification radius is TBD.

41. Fare Transparency

The customer must always be able to understand:

Original fare

Additional charges

Penalties

Discounts

Promotional discount

Final payable amount

Payment method

Any charge that changes the customer's payable amount must be shown before the customer is required to accept it.

42. Customer Promotions

42.1 Welcome Offer

A new customer receives:

50% off the first 3 rides

42.2 Customer Referral Offer

A referred new customer receives:

50% off 3 additional rides

42.3 Referring Customer Reward

The referring customer receives:

50% off 2 rides

The referring customer's reward activates after the new customer:

Downloads VISTAAR
→ Successfully registers/logs in through referral

A completed first ride is not required.

42.4 Combined Eligibility

A customer may enjoy both welcome and referral offers.

The discounts cannot stack on the same ride.

A referred new customer may therefore have up to:

3 welcome promotional rides
+
3 referral promotional rides
=
6 promotional rides

42.5 Expiry

Customer promotional benefits expire:

30 days after activation

42.6 Discount Cap

The maximum rupee value of the 50% discount is:

TBD — determined by unit economics.

43. Promotional Cancellation

If a promotional ride is cancelled early:

Promotion restored

If a promotional ride is cancelled late:

Promotion consumed

The exact boundary between early and late cancellation remains TBD.

44. Promotion and Referral Abuse

The platform must prevent:

Self-referral

Duplicate accounts

Repeated welcome bonuses

Fake referral accounts

Referral farming

Promotional farming

Duplicate reward credits

Rewards must be idempotent and linked to a unique qualifying event.

45. Parking Charges

Parking charges are added only when the driver actually incurs a paid parking expense.

Driver workflow:

Driver pays parking
→ Captures parking proof
→ Uploads proof
→ VISTAAR verifies
→ Charge approved
→ Customer sees charge

The driver must provide proof before the charge is accepted.

AI verification may check:

Readability

Receipt/ticket presence

Amount

Relevant information

Potential duplication/manipulation

Target verification time:

≤ 5 seconds under normal conditions

If verification fails or confidence is insufficient, the case goes to review.

46. Driver Ratings

After a completed ride:

Customer → Driver: 1–5 stars
Driver   → Customer: 1–5 stars

Written comments are optional.

Ratings should not be exposed in a way that creates retaliation risk before the relevant rating period is complete.

Submitted ratings cannot be edited by the submitting user.

Admin may review ratings for abuse.

47. Customer Safety / SOS

Both customer and driver must have access to SOS.

An SOS event should capture, where available:

Ride ID

User ID

Current GPS

Vehicle information

Ride state

Timestamp

Emergency-service integration is TBD.

48. Ride Sharing

Customers should be able to share ride status with another person.

The shared view may expose:

Driver

Vehicle

Ride status

Live location

Relevant safety information

Privacy controls and public-link expiry must be defined in the security/design requirements.

49. Lost and Found

Customers can report an item lost during a ride.

The case is linked to the ride.

The driver can report whether the item was found.

Unresolved cases can be escalated to Admin/Safety.

Drivers cannot demand arbitrary return fees.

50. Driver and Customer Abuse Controls

The platform should use progressive enforcement.

Example:

Violation
→ Warning
→ Strike
→ Temporary restriction/suspension
→ Admin review

Financial penalties and behavioral strikes must be stored separately.

Special business-rule exceptions, such as changed-pickup pass cancellation, must not generate ordinary cancellation penalties.

51. Advertisement System

VISTAAR may integrate with an advertising/inventory partner such as Admoto.

Current business model:

Advertising payout
├── 80% → Driver
└── 20% → VISTAAR

Example:

Gross payout = ₹1,200

Driver = ₹960
VISTAAR = ₹240

The driver must provide required installation proof and VISTAAR must perform applicable verification before payout.

52. AI Support

VISTAAR may provide AI-assisted customer support.

Potential support topics:

Ride status

Cancellation policy

Extra-charge complaints

Payment explanations

Promotion rules

General platform policies

Basic ride questions

AI must not independently make irreversible financial, safety, suspension, or account decisions unless an explicitly approved tool policy allows it.

Low-confidence or sensitive cases must escalate to human support.

The existing technical target of confidence below 0.7 may be used as an escalation trigger, subject to validation.

53. Human Support Escalation

Human support must be available when:

Customer explicitly requests an agent.

AI confidence is below the configured threshold.

Safety incident occurs.

Payment dispute requires human review.

Fraud is suspected.

A business-rule exception requires authorization.

The exact support provider/channel is TBD.

54. Admin System

Admin capabilities should include:

Customer management

Driver management

Driver verification

Vehicle verification

Ride monitoring

Ride search

Wallet/transaction monitoring

Promotion monitoring

Referral monitoring

Complaint management

Payment disputes

Safety incident management

Advertisement management

Fraud review

Account restrictions

Basic reports

Admin roles and permissions are TBD and must use least-privilege access.

55. Notifications

Important notifications include:

Ride request

Driver accepted

Driver arriving

Driver arrived

Ride started

Destination changed

Fare changed

Ride completed

Payment required

Payment confirmed

Ride cancelled

Wallet recharge

Low wallet balance

Penalty applied

Promotion activated

Promotion expiring

Safety event

Support update

Document expiry

Exact providers are TBD.

56. MVP Scope

Customer

Registration/login

Pickup/destination

Vehicle selection

Fare estimate

Ride booking

Driver matching

Driver tracking

Ride status

Pickup change

Destination change

OTP

SOS

Ride sharing

Promotions

Referrals

Outstanding charges

Online payment

Offline payment

Payment confirmation

Ratings

Support

Driver

Registration

Verification

Vehicle management

Online/offline

Location tracking

Ride requests

20-second request timer

Ride acceptance

Ride rejection

Navigation

Arrival

OTP

Start ride

Destination change handling

Early-drop handling

Complete ride

Fare summary

Parking proof

Wallet

Wallet recharge

Bonuses

Referrals

Advertisement verification

Core Platform

Ride lifecycle

Driver matching

Wallet

Platform fees

Cancellation engine

Penalty engine

Promotion engine

Referral engine

Payment orchestration

Cash settlement

Wallet reversal

GPS verification

Real-time ride updates

Dispute handling

Integrations

Payment gateway

UPI

Maps/location services

Advertising partner

AI support

Notification services

Admin

Customer management

Driver management

Vehicle verification

Ride monitoring

Financial monitoring

Promotions

Referrals

Complaints

Safety

Fraud review

57. V2 Scope

The following are not required for MVP unless separately approved:

AI Voice Agent

Fleet Owner Portal

General in-app customer-driver chat

Scheduled rides

Ride pooling

Subscription programs

Additional vehicle categories

58. Success Metrics

Customer

Average booking time

Ride completion rate

Customer cancellation rate

No-show rate

Repeat customer rate

Average ride cost

Promotional conversion

Customer satisfaction

Payment success rate

Driver

Acceptance rate

Driver cancellation rate

Average earnings

Utilization

Retention

Wallet recharge frequency

Average wallet balance

Referral conversion

Platform

Rides/day

Successful completion rate

Matching latency

API latency

Payment success rate

Wallet transaction accuracy

Support resolution time

Revenue per completed ride

Fraud rate

Primary Product Metric

Average comparable ride cost against competing platforms.

Exact affordability target:

TBD

59. Non-Functional Requirements

Reliability

Ride state and wallet state must remain consistent during:

Retries

Network failures

Duplicate requests

Concurrent requests

Partial service failures

Performance

Ride matching, ride acceptance, payment state changes, and real-time ride updates must operate with low enough latency for a real-time ride-hailing experience.

Concurrency

Wallet acceptance must use an atomic transaction.

The implementation must prevent concurrent requests from:

Spending the same wallet balance twice

Assigning the same ride to multiple drivers

Creating duplicate ledger entries

Security

Protect:

Customer data

Driver data

Authentication

Payment information

Wallet information

Location information

Administrative operations

Auditability

Important financial and operational actions must be auditable, including:

Wallet transactions

Penalties

Promotions

Referral rewards

Payment confirmation

Fare changes

Destination changes

Pickup changes

Admin actions

Safety actions

60. Product Constraints

Confirmed:

India launch

INR

English and Hindi

Auto, Bike, Cab

Affordable positioning

Online and offline payment

Driver wallet

Fixed driver platform fee

Customer promotions

Referral system

GPS verification

SOS

Still TBD:

Launch city

Launch date

Initial user count

Initial driver count

Expected rides/day

Exact fare model

Promotional discount cap

Pickup-change rate

Cancellation abuse thresholds

GPS radii

Final KYC requirements

Payment providers

Emergency-service integration

Notification providers

Data retention policy

61. Business Rule Summary

The following rules are considered approved for the current product baseline.

Area

Approved Rule

Vehicle categories

Auto, Bike, Cab

Driver platform fee

Bike ₹10 / Auto ₹20 / Cab ₹20

Minimum wallet recharge

₹200

Joining bonus

₹100

Joining bonus expiry

30 days

Driver referral

₹100 + ₹100

Driver referral expiry

30 days

Driver request timer

20 seconds

No-driver options

Retry / Increase Fare

Fare increase

₹10 / ₹20 / ₹40 / Custom

Customer cancellation grace

2 minutes

First qualifying cancellation

Free

Later qualifying cancellation

₹15

Cancellation charge expiry

30 days

No-show

₹30 total

No-show waiting

3 min + 10 min

No-show expiry

30 days

Driver cancellation

₹30 + strike

Changed pickup threshold

250m

Changed pickup driver pass

No penalty

Destination extension

₹8/km

Welcome promotion

50% off 3 rides

Referral customer promotion

50% off 3 additional rides

Referring customer reward

50% off 2 rides

Promotion expiry

30 days

Early promotional cancellation

Restore promotion

Late promotional cancellation

Consume promotion

Parking

Proof required

Early drop

Customer-requested + verified

Normal completion

GPS verification

Ride start

OTP

Ratings

Two-way 1–5

Payment

Online or offline

Online payment

VISTAAR receives and splits

Offline payment

Driver receives complete amount

Offline VISTAAR charge

Deduct from driver wallet

Empty wallet settlement

Recover on next recharge

62. Explicitly Unresolved Business Decisions

The following must not be invented by engineering:

Exact base fares.

Exact per-km rates.

Exact per-minute rates.

Waiting charge.

Toll treatment.

Tax treatment.

Minimum fare.

Promotional rupee discount cap.

Custom fare-increase maximum.

Exact pickup-change additional rate.

Exact GPS arrival radius.

Exact GPS completion radius.

Exact early/late promotional cancellation boundary.

Driver strike thresholds.

Driver suspension duration.

Customer abuse thresholds.

Payment gateway/provider.

Driver settlement timing.

Refund workflow.

Final KYC requirements.

Emergency-service integrations.

Notification providers.

Launch city.

Launch date.

Initial launch scale.

Data retention period.

Admin role hierarchy.

These are TBD, not assumptions.

63. Relationship to Business Rules

This PRD defines what VISTAAR provides.

The separate:

docs/02-business/business-rules.md

defines detailed business behavior and edge cases.

The business-rules document is the detailed source of truth for approved operational rules.

Where the PRD is intentionally high-level, the business-rules document may contain the precise operational behavior.

64. Relationship to Technical Architecture

The PRD defines what the product must do.

Technical architecture defines how it is implemented.

Architecture must be derived from the approved product and business rules rather than allowing existing implementation assumptions to override approved business decisions.

The following technical areas must therefore be reconciled with this PRD before implementation:

Ride service

Matching service

Wallet service

Payment service

Promotion service

Referral service

Cancellation/penalty service

GPS verification

Notification service

Safety service

Support/AI service

Advertisement service

Admin service

65. Document Status

Version: 2.0
Status: Draft — Updated with Approved Business Rules
Product Owner: TBD
Engineering Owner: TBD
Launch City: TBD
Launch Date: TBD

This PRD must be updated when a business decision changes.

Major architectural consequences must be documented through an ADR.
