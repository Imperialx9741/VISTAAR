VISTAAR — Business Rules

Document Version: 1.0
Status: Draft — Business Decisions Captured
Market: India
Currency: INR (₹)

This document defines the business rules approved for VISTAAR during product-definition discussions. Technical implementation details belong in the architecture, API, database, event, and state-machine documents. Any item explicitly marked TBD is not yet a finalized business decision.

1. Core Business Principles
BR-001 — Affordability

VISTAAR's primary product objective is to provide affordable transportation while maintaining a sustainable business model.

BR-002 — Pricing Transparency

Any charge that changes the amount payable by the customer must be clearly displayed before the customer is required to accept it.

BR-003 — Customer and Driver Choice

Where a business rule gives both customer and driver an option, neither party should be forced into an unexpected additional charge or route.

BR-004 — Financial Separation

VISTAAR must maintain separate accounting for:

Customer ride fare
VISTAAR platform fees
Customer penalties
Driver penalties
Parking charges
Pickup-change charges
Destination-change charges
Promotional discounts
Bonuses
Referral rewards
Wallet transactions
Cash collected on behalf of VISTAAR
2. Supported Vehicle Categories

Initial VISTAAR vehicle categories:

Bike
Auto
Cab

The architecture must allow additional vehicle categories to be introduced later.

3. Fare Calculation
BR-005 — Base Fare Model

VISTAAR will use a distance + time based pricing model.

The conceptual fare is:

Base Fare
+ Distance Charge
+ Time Charge
+ Applicable Waiting Charge
+ Applicable Parking Charge
+ Applicable Toll
+ Applicable Taxes
= Final Fare

Exact base rates are TBD and must be determined through unit-economics analysis.

BR-006 — Vehicle-Specific Pricing

Pricing may differ between:

Bike
Auto
Cab

Exact rates are TBD.

4. Parking Charges
BR-007 — Parking Only When Actually Incurred

A parking charge may be added only when the driver actually incurs a paid parking expense.

BR-008 — Parking Proof Required

The driver must:

Pay the parking charge.
Take a photograph/snapshot of the parking proof.
Upload the proof through the Driver App.
Provide the claimed parking amount.

No proof means the parking charge must not be automatically added.

BR-009 — AI Parking Verification

VISTAAR will use AI to verify parking proof.

The target verification time is:

≤ 5 seconds under normal operating conditions.

The AI should verify factors such as:

Readability
Parking receipt/ticket presence
Amount
Relevant information
Potential duplication/manipulation
BR-010 — AI Verification Outcome
Proof uploaded
      ↓
AI verification
      ↓
Verified → Parking charge approved
      ↓
Customer sees charge

If the AI cannot confidently verify the proof, the case may be sent to Admin for review.

5. Driver Platform Fee
BR-011 — Fixed Driver Platform Fee

VISTAAR will not use a percentage commission on the customer's ride fare as its primary ride platform fee.

The platform fee is deducted from the driver's VISTAAR wallet when the driver accepts a ride.

Vehicle	Fee
Bike	₹10
Auto	₹20
Cab	₹20
BR-012 — Wallet Balance Requirement

A driver may accept a ride only if their wallet has sufficient balance for the applicable platform fee.

Example:

Cab fee = ₹20
Wallet = ₹15


₹15 < ₹20
→ Driver cannot accept
→ Driver must recharge
BR-013 — Atomic Platform Fee Deduction

The platform fee deduction and ride acceptance must be treated as one reliable financial operation.

The system must prevent:

Double deductions
Duplicate ride acceptance
Negative balance caused by concurrency
Missing wallet transactions
6. Driver Wallet
BR-014 — Wallet Purpose

The driver wallet is a platform transaction wallet, not a general-purpose bank account.

It may be used for:

Platform fees
Driver penalties
Joining bonuses
Referral bonuses
Other approved VISTAAR credits/debits
BR-015 — Minimum Recharge

Minimum wallet recharge:

₹200

BR-016 — Wallet Recharge Methods

Drivers can recharge using:

UPI
Credit card
Debit card

Payment must be successfully verified before the wallet is credited.

BR-017 — Wallet Withdrawal

Drivers cannot withdraw VISTAAR wallet funds to a bank account or UPI during MVP.

BR-018 — Zero Wallet Balance

A driver with ₹0 wallet balance:

May remain online.
May receive ride requests.
Cannot accept a ride requiring a platform fee.
Must recharge before accepting the next applicable ride.
BR-019 — Recharge During Ride

A driver may recharge the wallet while an active ride is in progress.

The recharge does not modify the already accepted ride's platform fee.

7. Driver Joining Bonus
BR-020 — New Driver Bonus

A new driver receives:

₹100 wallet credit

only after:

Registration
→ Verification
→ Approval
→ ₹100 credited

Rejected drivers do not receive the bonus.

BR-021 — Bonus Expiry

The ₹100 joining bonus expires after:

30 days

The expiry applies to the bonus credit, not the driver's entire wallet.

8. Driver Referral
BR-022 — Driver Referral Reward

When an existing driver successfully refers a new driver:

Existing driver → ₹100
New driver      → ₹100
BR-023 — Referral Activation

A driver referral becomes successful only after the new driver:

Registers through the referral.
Completes required onboarding.
Passes verification.
Is approved.
BR-024 — Referral Bonus Expiry

Driver referral bonuses expire after:

30 days

BR-025 — Referral Abuse

Duplicate, fake, self-referral, or fraudulent accounts must not generate referral rewards.

9. Driver Matching
BR-026 — Nearest Eligible Driver

VISTAAR will prioritize the nearest eligible driver.

Eligibility includes appropriate vehicle category and driver availability.

BR-027 — Driver Request Timer

Each driver receives:

20 seconds

to respond to a ride request.

BR-028 — Driver Accepts

If the driver accepts within 20 seconds:

Driver → Ride assigned
BR-029 — Driver Rejects

If the driver rejects:

Reject
→ Next nearest eligible driver
BR-030 — Driver Does Not Respond

If the driver does not respond within 20 seconds:

Request expires
→ Next nearest eligible driver
10. No Driver Accepts
BR-031 — Customer Options

If no driver accepts the ride, the customer receives exactly two primary options:

Retry
Increase Fare
BR-032 — Fare Increase

Available predefined increases:

+₹10
+₹20
+₹40
Custom
BR-033 — Fare Increase Is Voluntary

VISTAAR must not automatically increase the customer's fare.

The customer must explicitly choose the increase.

BR-034 — Increased Fare Goes to Driver

The entire customer-approved fare increase goes to the driver.

VISTAAR still collects its normal driver platform fee.

Example:

Original fare = ₹180
Customer increases to = ₹220


Driver ride fare = ₹220
VISTAAR platform fee remains:
Cab/Auto → ₹20
Bike → ₹10

Custom increase limits are TBD.

11. Customer Payment
BR-035 — Customer Ride Payment Methods

Customers may pay the ride fare using:

UPI
Cash
BR-036 — Two Payment Modes

VISTAAR supports two payment flows:

Online
Customer
   ↓
VISTAAR Payment Gateway
   ↓
VISTAAR keeps applicable VISTAAR charges
   ↓
Ride-fare amount transferred to driver
Offline
Customer
   ↓
Driver
   ↓
Driver confirms full payment
   ↓
VISTAAR settles its applicable charge
through driver wallet

This supersedes the earlier assumption that VISTAAR would never process ride-fare payments.

12. Online Payment
BR-037 — Combined Online Amount

If the customer has an outstanding VISTAAR charge:

Ride Fare + Outstanding VISTAAR Charges
= Total Online Payment

Example:

Ride fare = ₹100
Penalty = ₹30


Total = ₹130

Customer pays ₹130 through VISTAAR.

VISTAAR separates:

₹100 → Driver
₹30  → VISTAAR
BR-038 — Customer Payment Display

Before payment, the customer must see:

Ride Fare                 ₹100
Outstanding Charges        ₹30
─────────────────────────────
Total                     ₹130
13. Offline Payment
BR-039 — Full Cash Amount

If the customer chooses offline payment:

Ride fare + VISTAAR charges

must be paid to the driver.

Example:

Ride fare = ₹100
VISTAAR charge = ₹30


Customer gives driver = ₹130
BR-040 — Driver Payment Confirmation

The Driver App must clearly show:

Ride fare              ₹100
VISTAAR charge          ₹30
─────────────────────────
Total cash required    ₹130


[ CONFIRM ₹130 RECEIVED ]

The driver must press the confirmation button only after receiving the complete amount.

BR-041 — Partial Payment

If the customer pays less than the displayed total:

Driver must NOT confirm payment.

The driver must request the remaining amount.

BR-042 — Payment Confirmation Finality

Once the driver confirms the complete payment:

The payment is considered confirmed for that transaction and the driver cannot subsequently claim that the customer failed to provide the confirmed amount.

14. Cash Collection for VISTAAR
BR-043 — Separate Accounting

If the driver collects VISTAAR's charge in cash:

Ride fare → Driver earnings
VISTAAR charge → VISTAAR settlement liability

The VISTAAR portion is not driver income.

BR-044 — Wallet Settlement

After the driver confirms receiving the complete amount, VISTAAR settles its portion by deducting the applicable amount from the driver's wallet.

BR-045 — Insufficient Wallet

If the driver's wallet does not contain enough balance:

Cash collected
→ Settlement remains outstanding
→ Driver continues according to applicable rules
→ Amount recovered from future wallet recharge

Example:

Recharge = ₹200
Outstanding settlement = ₹30


Usable wallet credit = ₹170
15. Customer Cancellation
BR-046 — Cancellation Grace Period

After driver acceptance, the customer receives a:

2-minute cancellation grace period.

Cancellation within this period does not create the ₹15 cancellation charge.

The driver's platform fee is refunded when the customer cancels.

BR-047 — First Qualifying Cancellation

The customer's first qualifying cancellation:

Penalty = ₹0

The driver's platform fee is returned.

BR-048 — Second and Subsequent Qualifying Cancellations

From the second qualifying cancellation onward:

Customer penalty = ₹15

The driver's platform fee is refunded.

BR-049 — Customer Cancellation Charge Expiry

Each ₹15 charge is valid for:

30 days

After 30 days, an unpaid charge expires.

16. Customer No-Show
BR-050 — Free Waiting

When the driver reaches the pickup location:

First 3 minutes = Free
BR-051 — Additional Waiting

The driver waits for an additional:

10 minutes

after the initial 3-minute period.

Total maximum waiting period:

13 minutes

BR-052 — No-Show

If the customer does not arrive after the waiting period:

No-show charge = ₹30 total

The customer is not charged ₹30 + ₹30.

Total charge for the no-show event is:

₹30

BR-053 — No-Show Expiry

The ₹30 no-show charge is valid for:

30 days

17. Customer Outstanding Charges

Outstanding charges may include:

₹15 cancellation charges
₹30 no-show charges
Other approved VISTAAR-owned charges

Each charge is independently tracked and has its own expiry date.

BR-054 — Multiple Outstanding Charges

Multiple valid outstanding charges may accumulate.

Example:

₹15 cancellation
₹30 no-show
₹15 cancellation
──────────────
₹60 outstanding
BR-055 — Customer Can Pay Online

Customers can pay outstanding VISTAAR charges directly through the VISTAAR app.

BR-056 — Outstanding Charges on Next Ride

Outstanding charges may also be included in the next ride's total payable amount.

BR-057 — Unpaid Outstanding Charges

If the customer does not settle an outstanding charge:

The customer is still allowed to continue booking rides.

The outstanding amount remains attached to the account until:

Paid
Expired
Otherwise resolved according to future policy
18. Customer Promotions
BR-058 — New Customer Welcome Offer

A new customer receives:

50% off the first 3 rides.

BR-059 — Customer Referral Offer

A customer referred by another customer receives:

3 additional rides at 50% off.

Therefore, a referred new customer may have:

Welcome → 3 × 50% OFF
Referral → 3 × 50% OFF

Total potential promotional rides:

6

BR-060 — Referring Customer Reward

The referring customer receives:

2 × 50% off rides

after the new customer downloads the application and successfully logs in through the referral.

A completed first ride is not required to activate the referral benefit.

BR-061 — Promotion Activation

Customer referral benefits activate when the new customer:

Downloads VISTAAR
→ Registers/logs in successfully
→ Referral is associated with account
BR-062 — Promotion Expiry

Customer promotional benefits expire:

30 days after activation.

BR-063 — Promotion Discount Cap

50% promotional discounts are subject to a maximum per-ride discount.

The exact cap is:

TBD — determined through unit economics before launch.

BR-064 — Promotional Benefits

A customer may receive both welcome and referral promotional entitlements.

However:

Two separate 50% discounts cannot be stacked onto the same ride.

19. Promotional Cancellation
BR-065 — Early Cancellation

If a promotional ride is cancelled during the defined early-cancellation period:

Promotion restored
BR-066 — Late Cancellation

If a promotional ride is cancelled after the early-cancellation boundary:

Promotion consumed

The exact early/late cancellation boundary is:

TBD

20. Driver Cancellation
BR-067 — Driver Cancellation Penalty

A driver cancellation normally results in:

₹30 penalty

deducted from the driver's wallet.

BR-068 — Driver Cancellation Strike

Every applicable driver cancellation also records a behavioral strike.

Financial penalties and behavioral strikes are separate records.

BR-069 — Repeated Driver Cancellation

Repeated cancellations may result in:

Cancellation
→ Strike
→ Warning
→ Repeated abuse
→ Temporary suspension

Exact thresholds and suspension duration are:

TBD

21. Driver Cancellation and Rematching
BR-070 — Automatic Rematching

If a driver accepts and subsequently cancels before the ride starts:

Driver cancellation
→ ₹30 penalty
→ Driver removed from booking
→ VISTAAR searches next nearest eligible driver

The customer does not need to create a new booking.

BR-071 — Driver Changed-Pickup Pass

If a customer changes pickup by more than 250 meters and the driver does not want to travel to the new pickup:

Driver may pass/cancel the ride
→ No ₹30 penalty
→ No cancellation strike
→ VISTAAR searches for nearby driver

This is a special cancellation reason and must not be treated as normal driver cancellation.

22. Pickup Location Changes
BR-072 — Pickup Change

Customers may change their pickup location after booking.

BR-073 — Pickup Within 250m

If the new pickup is within 250 meters of the driver's relevant current location:

Ride continues normally
BR-074 — Pickup More Than 250m Away

If the new pickup is more than 250 meters away:

Driver gets choice:
1. Accept new pickup
2. Pass/cancel without penalty
BR-075 — Driver Accepts Changed Pickup

If the driver accepts:

Additional charge is calculated.
Customer sees the additional charge.
Customer must confirm the charge.
Driver proceeds only after customer confirmation.
BR-076 — Additional Pickup Charge

An additional pickup charge applies for the additional distance beyond the 250-meter threshold.

The exact vehicle-specific rate is:

TBD

The intended range discussed is approximately ₹10–₹20/km.

BR-077 — Customer Must See Charge

The driver must not proceed toward the changed pickup until the customer has seen and confirmed the additional charge.

BR-078 — Driver Passes Changed Pickup

If the driver does not want to travel to a pickup more than 250 meters away:

No ₹30 penalty
No cancellation strike
→ Find nearby driver at new pickup
23. Destination Changes
BR-079 — Destination Change Along Original Route

If the customer changes the destination to a point between the original pickup and original destination:

Original fare remains unchanged.
BR-080 — Destination Beyond Original Destination

If the new destination is beyond the original destination:

Additional distance × ₹8/km

is added.

Example:

Original fare = ₹250
Additional distance = 5 km
Additional = ₹40


Final = ₹290
BR-081 — Destination on a Different Route

If the new destination is not along the original route or simply beyond the original destination:

Recalculate fare
from current location
to new destination.
BR-082 — Customer Confirmation

If destination change causes the fare to change:

New fare calculated
→ Customer sees revised fare
→ Customer confirms
→ Driver sees updated destination/fare
→ Ride continues

No fare change may be silently applied.

24. Ride Start OTP
BR-083 — OTP Required

The ride cannot transition to STARTED until OTP verification succeeds.

BR-084 — Incorrect OTP

If the OTP is incorrect:

Retry current OTP
OR
Generate/refresh new OTP

When a new OTP is generated, the previous OTP becomes invalid.

BR-085 — OTP Escalation

If OTP verification continues to fail:

Retry
→ New OTP
→ Still failing
→ Admin Support
25. Driver Arrival
BR-086 — GPS-Verified Arrival

The driver must be sufficiently close to the pickup location before the ride can be marked ARRIVED.

The exact permitted GPS radius is:

TBD

BR-087 — Waiting Timer

The customer waiting timer begins from a verified ARRIVED event.

26. Early Drop
BR-088 — Customer-Requested Early Drop

If the customer requests to be dropped before the original destination:

Customer requests early drop
→ Driver records reason
→ Customer confirms
→ GPS/location + timestamp recorded
→ Ride can complete
BR-089 — Two-Sided Confirmation

The customer must confirm the early-drop request.

BR-090 — Early-Drop Fare

Under the current business decision:

The original fare remains payable even when the customer requests an early drop.

27. Normal Ride Completion
BR-091 — Destination GPS Verification

For normal destination completion:

Driver selects Complete
→ VISTAAR verifies GPS
→ Destination verified
→ Ride completed

The exact destination radius is:

TBD

28. Payment Confirmation
BR-092 — Driver Confirmation

The driver must confirm that the complete payable amount has been received.

BR-093 — No Partial Confirmation

If the customer pays less than the required amount:

Driver must not confirm payment.

The customer must provide the remaining amount.

BR-094 — Confirmed Payment

Once the driver confirms the complete amount:

Payment = Confirmed

The transaction is considered settled for the payment event.

29. Unauthorized Extra Charges
BR-095 — Driver Cannot Demand Unauthorized Money

The driver cannot demand an amount greater than the final VISTAAR-approved payable amount.

Allowed additional amounts must be generated through VISTAAR, such as:

Verified parking
Approved pickup-change charge
Approved destination-change charge
Other explicitly supported charges
BR-096 — Unauthorized Charge Complaint

If a driver demands unauthorized additional money:

Customer complaint
→ Admin investigation
→ Driver warning/strike/penalty

Exact penalty:

TBD

30. Driver Onboarding
BR-097 — Driver Registration

Driver onboarding may require:

Personal
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
Vehicle registration number
Vehicle photo
Vehicle category
Payment
UPI/payment details where required

Exact KYC requirements are subject to applicable Indian regulatory requirements and final compliance review.

BR-098 — Driver Approval

A driver must be:

Registered
→ Documents submitted
→ Verified
→ Approved

before receiving rides.

31. Vehicle Verification
BR-099 — Separate Vehicle Verification

Each vehicle must be separately verified.

A driver may have multiple vehicles.

Example:

Driver
├── Auto → Approved
├── Bike → Approved
└── Cab → Pending

Only approved vehicles may receive matching requests.

BR-100 — Vehicle Add/Change

A driver may add another vehicle without creating another driver account.

The new vehicle must go through its own verification.

BR-101 — Vehicle Deactivation

A driver may temporarily deactivate an approved vehicle.

Deactivation does not remove its verification.

BR-102 — Vehicle Switching

A driver cannot switch vehicles while:

ONLINE

or:

ON_RIDE

The driver must:

Go OFFLINE
→ Select approved vehicle
→ Activate it
→ Go ONLINE
32. Driver Document Expiry
BR-103 — Expiring Documents

VISTAAR should notify drivers before required documents expire.

BR-104 — Expired Document

After expiry:

Driver becomes temporarily ineligible
→ Cannot receive new rides
→ Renew document
→ Verification
→ Approval
→ Eligible again
BR-105 — Document Expiry During Active Ride

If a document expires while the driver is already on a ride:

Current ride continues
→ Ride completes
→ Driver becomes ineligible

Special legal/safety restrictions may override this rule where required.

33. Driver Online/Offline
BR-106 — Driver States

The driver may be:

OFFLINE
ONLINE
ON_RIDE
BR-107 — Pending Ride Request

A driver cannot immediately go offline while a ride request is pending.

The driver must:

Reject
OR
Allow the 20-second timer to expire

Then:

Request → Next driver
Driver → OFFLINE

If the driver accepts:

Ride assigned
→ Driver cannot go offline until ride completion.
34. Driver Ratings
BR-108 — Two-Way Rating

After a completed ride:

Customer → Driver rating
Driver → Customer rating

Rating scale:

1–5 stars

BR-109 — Rating Comments

Written comments may be provided optionally.

BR-110 — Rating Visibility

Ratings are not immediately exposed to the other party before they submit their own rating or the rating period expires.

BR-111 — Rating Immutability

Submitted ratings cannot be edited by the submitting user.

Admin may review ratings for abuse.

35. Customer Safety / SOS
BR-112 — SOS

Both customers and drivers must have access to SOS functionality.

An SOS incident should capture relevant information such as:

Ride ID
Customer/driver ID
Current GPS
Vehicle information
Ride status
Timestamp

The exact emergency-service integrations are:

TBD

36. Lost and Found
BR-113 — Lost Item Case

Customers can report lost belongings associated with a ride.

The case is linked to the ride.

BR-114 — Driver Notification

The driver is notified and can report whether the item was found.

BR-115 — Admin Escalation

Unresolved or disputed lost-item cases may be escalated to Admin/Safety.

Drivers may not demand arbitrary return fees.

37. Customer Cancellation Abuse
BR-116 — Customer Strike

Customer cancellation behavior is tracked separately from financial penalties.

BR-117 — Progressive Enforcement

Repeated abuse may result in:

Cancellation
→ Strike
→ Warning
→ Temporary booking restriction
→ Temporary suspension
→ Admin review

Exact thresholds and suspension duration:

TBD

38. Driver Cancellation Abuse
BR-118 — Driver Strike

Driver cancellation penalties and behavioral strikes are separate records.

BR-119 — Progressive Enforcement

Repeated cancellations may result in:

₹30 penalty
→ Strike
→ Warning
→ Temporary suspension

Exact thresholds:

TBD

39. Refunds and Disputes
BR-120 — Platform Financial Errors

VISTAAR may correct/reverse verified platform-related errors such as:

Duplicate wallet deduction
Failed recharge
Incorrect platform fee
System-generated financial error
BR-121 — Ride Fare Disputes

Because ride fares may be paid directly to drivers, ride-fare disputes require a support/admin process.

VISTAAR must not automatically remove money from a driver's wallet to compensate a customer without an authorized/verified process.

40. Driver Earnings Transparency

The Driver App should display:

Ride earnings
Platform fees
Penalties
Bonuses
Referral rewards
Wallet balance
VISTAAR cash collected
Wallet settlements

Example:

Ride fare                 ₹200
Parking                   ₹30
Pickup-change charge      ₹20
────────────────────────────
Customer total            ₹250


Platform fee              ₹20
Driver ride earnings      ₹230
41. Cash Collection Transparency

When a driver collects money on behalf of VISTAAR:

Driver earnings             ₹200
VISTAAR cash collected       ₹30
────────────────────────────
Total cash received         ₹230

The ₹30 must never be represented as driver earnings.

42. Account and Promotional Integrity

The system should prevent:

Duplicate accounts
Self-referrals
Repeated joining bonuses
Referral farming
Promotional abuse
Duplicate wallet credits
Duplicate payment settlement

All financial/promotional rewards should be idempotent.

43. Items Still TBD

These are intentionally not finalized:

Pricing
Exact base fare
₹/km
₹/minute
Waiting rate
Vehicle-specific pricing
Toll handling
Taxes
Promotional discount cap
Pickup-change ₹/km rate
Custom fare-increase limits
Cancellation
Exact strike thresholds
Suspension duration
Promotional early/late cancellation boundary
Geolocation
ARRIVED GPS radius
Completion GPS radius
Definition of "far" beyond the 250m pickup-change threshold where applicable
Driver
Final KYC document list
Verification provider
Document-specific safety rules
Payments
Final payment gateway
Driver settlement mechanism
Payment settlement timing
Refund settlement process
Safety
Emergency contact workflow
Police/emergency-service integration
Safety-team operating procedure
Admin
Admin roles
Permission hierarchy
Escalation rules
Fraud investigation workflow
44. Business Rule Change Policy

Business rules are expected to evolve.

A future change must not be implemented casually in code.

The expected process is:

Business decision
      ↓
Update Business Rules
      ↓
Identify affected domains
      ↓
Update architecture
      ↓
Update API contracts
      ↓
Update database/events/state machines
      ↓
Update tests
      ↓
Implement

Major architectural changes should also receive an Architecture Decision Record (ADR).

45. Source of Truth

For VISTAAR:

PRD
  ↓
What the product does


Business Rules
  ↓
What rules the product must follow


Architecture
  ↓
How the system is structured


API Contracts
  ↓
How systems communicate


Events
  ↓
How asynchronous changes are communicated


State Machines
  ↓
How important entities transition


Database
  ↓
How persistent data is represented


Tests
  ↓
How the rules are verified

When the older technical architecture conflicts with a newly approved business rule, the business rule must be explicitly reconciled into the technical architecture rather than leaving contradictory documentation.

46. Document Status

Version: 1.0
Status: Draft — Business Rules Captured
Market: India
Currency: INR
Languages: English, Hindi
