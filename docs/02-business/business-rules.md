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

(Resolved 2026-08-24 — ADR-0020: Cab gained three owner-approved fare/eligibility
sub-tiers — Eco, Premium, Premium+ — selected by the customer at booking time and
self-declared by the driver on their vehicle. This is additive: the category list
above is still exactly Bike/Auto/Cab; Eco/Premium/Premium+ are not new categories.)

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

(Resolved 2026-08-24 — ADR-0020, owner-approved rates. Time Charge is not yet
implemented — v1 fare is Base + Distance, floored at Minimum Fare, no time-in-motion
component. Currency INR.)

|                  | 2W (Bike) | Auto | Cab: Eco | Cab: Premium | Cab: Premium+ |
| ---------------- | --------: | ---: | -------: | -----------: | ------------: |
| Minimum fare     |       ₹39 |  ₹59 |      ₹79 |          ₹99 |         ₹129 |
| Base fare        |       ₹29 |  ₹39 |      ₹55 |          ₹65 |          ₹85 |
| Per km           |        ₹7 | ₹10 |      ₹12 |          ₹14 |          ₹18 |
| Free waiting     |     3 min | 5 min |   5 min |        5 min |        5 min |
| Waiting/min      |        ₹1 |  ₹2 |       ₹2 |           ₹2 |           ₹3 |

Free waiting / Waiting-per-minute are recorded here as the approved rate, but are
not yet applied to any fare quote — no waiting-time tracking mechanism exists yet
(ADR-0020 §7).

BR-006 — Vehicle-Specific Pricing

Pricing may differ between:

Bike
Auto
Cab (and its three sub-tiers — see BR-005's table)

Exact rates are TBD.

(Resolved 2026-08-24 — ADR-0020. See BR-005's table.)

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
Bike	₹2
Auto	₹5
Cab	₹10

(Updated 2026-08-24 — ADR-0020 Decision 2: superseded by the owner's fare table.
Was Bike ₹10 / Auto ₹20 / Cab ₹20. Cab's ₹10 fee applies uniformly across its Eco/
Premium/Premium+ sub-tiers — the source table gave all three the same platform fee.)

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

SUPERSEDED IN PART (ADR-0025, 2026-08-25 — approved P2P Payment Model):
VISTAAR does not collect the ride fare, in any flow. The customer always
pays the driver directly (BR-035 stays accurate: UPI or cash, paid
directly). BR-036's "Two Payment Modes" below described VISTAAR
inserting itself into fare collection — that model is superseded; see
the corrected flow at the end of this section.

BR-035 — Customer Ride Payment Methods

Customers may pay the ride fare using:

UPI
Cash

Clarified 2026-09-03 (owner decision): this describes what the customer
and Sarthi may freely agree between themselves — it does NOT mean the
app asks the customer to select UPI or Cash. No such selection exists
anywhere in the app; `payment_method` was removed from the Create Ride
request entirely (was ADR-0010 Decision 2, see ADR-0025's addendum).
BR-036 — Two Payment Modes (SUPERSEDED — ADR-0025)

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

Correction (ADR-0025, 2026-08-25): the above is itself now superseded —
that earlier assumption was right, and this rule was wrong. VISTAAR does
NOT process ride-fare payments in either an "Online" or "Offline" mode.
There is exactly one flow:

Customer
   ↓
Driver (direct payment — UPI or cash, per BR-035)

VISTAAR is never in this path. VISTAAR's own platform fee is charged
separately, only to the driver, deducted from the driver's wallet during
ride acceptance (BR-011; technical-architecture.md §18; already
implemented, ADR-0014) — before the ride even happens, and independent
of whatever amount the customer later pays the driver. The "Online"
mode above (a VISTAAR Payment Gateway collecting the fare) does not
exist. The "Offline" mode's "VISTAAR settles its applicable charge
through driver wallet" is not wrong about the mechanism (the wallet IS
how VISTAAR is paid) but wrong about the timing and trigger — the wallet
debit already happened at acceptance, not as a settlement step following
the customer's cash payment.

12. Online Payment (RE-CORRECTED — ADR-0026, 2026-08-26, Option A: partly
revived)

BR-037/038 below were marked fully superseded by ADR-0025 (2026-08-25),
on the reasoning that VISTAAR never collects money from the customer in
any online flow. ADR-0026 resolved the specific question ADR-0025 left
open (what happens to a customer's outstanding cancellation/no-show
penalty) with Option A: the DISPLAY concept below — a combined "ride
fare + outstanding charges = total" figure shown to the customer — is
CORRECT and revived. **The settlement mechanics have now changed twice**:
ADR-0026 (2026-08-26) first corrected them to a split-settlement model
(fare → Driver, penalty → VISTAAR, as two independent flows); ADR-0066
(2026-09-03, owner decision) corrected them again, this time to a
**combined** payment:

Ride Fare + Outstanding Penalty = Total the customer physically pays
the Sarthi (P2P, cash/UPI, BR-035, ADR-0025's own settlement mode
unchanged — only what's included in the total changed). VISTAAR is
never the recipient of either amount; instead, VISTAAR recovers its
penalty share automatically by debiting the driver's wallet the moment
the ride completes (`TransactionType.CASH_SETTLEMENT`, ADR-0066).

"Total = ₹130" is still shown to the customer for transparency (BR-038,
"what you'll owe this trip, all in") — and, unlike ADR-0026's original
correction, it now genuinely IS what the customer pays, in one
transaction, to one recipient (the Sarthi) — just never to VISTAAR.

The trigger for surfacing this combined figure is the customer's next
ride-booking request (BR-056), which — as of ADR-0066 — also durably
attaches the outstanding penalty to that specific ride, not just
displays it. Booking itself is never blocked by an outstanding penalty
(BR-057, unchanged).

BR-037 — Combined Online Amount (superseded — the "Total Online
Payment... through VISTAAR" framing below described a single payment
collected BY VISTAAR; ADR-0066 revives the "single combined payment"
shape but to the Sarthi, not VISTAAR — see the correction above)

If the customer has an outstanding VISTAAR charge:

Ride Fare + Outstanding VISTAAR Charges
= Total paid to the Sarthi directly (ADR-0066; was "through VISTAAR"
  in this rule's original, now-corrected wording)

Example (ADR-0066's own worked case):

Ride fare = ₹200
Outstanding penalty = ₹30


Total = ₹230, paid by the customer to the Sarthi directly.

VISTAAR then separately debits the Sarthi's wallet ₹30 at ride
completion — not a split of the customer's payment itself, a
server-side accounting entry that happens afterward.
BR-038 — Customer Payment Display (revived — ADR-0026: this display
shape is correct; the settlement mechanics behind it have since been
corrected twice, see above — most recently to reflect that this total
is now genuinely a single combined payment to the Sarthi, ADR-0066)

Before payment, the customer must see:

Ride Fare                 ₹100
Outstanding Charges        ₹30
─────────────────────────────
Total                     ₹130
13. Offline Payment

CORRECTED (ADR-0025, 2026-08-25): BR-039/BR-040 below required the
customer to pay the driver "ride fare + VISTAAR charges." That is now
wrong — the customer pays the driver the ride fare only. VISTAAR's
charge (the platform fee) is never part of what the customer pays;
it was already deducted from the driver's own wallet at ride acceptance
(BR-011, technical-architecture.md §18). BR-041/BR-042 are otherwise
unaffected (general confirmation-integrity rules) — they now apply to
the ride-fare-only amount.

BR-039 — Full Cash Amount (corrected)

If the customer chooses offline payment:

The ride fare only

must be paid to the driver. VISTAAR's platform fee is not part of this
amount — it was already collected from the driver's wallet at
acceptance, not from the customer.

As originally written (superseded):

Example:

Ride fare = ₹100
VISTAAR charge = ₹30


Customer gives driver = ₹130
BR-040 — Driver Payment Confirmation (corrected)

The Driver App must clearly show:

Ride fare               ₹100
─────────────────────────
Total cash required     ₹100


[ CONFIRM ₹100 RECEIVED ]

The driver must press the confirmation button only after receiving the complete amount.

As originally written (superseded — bundled a VISTAAR charge into the
displayed total that the customer never owes):

Ride fare              ₹100
VISTAAR charge          ₹30
─────────────────────────
Total cash required    ₹130

BR-041 — Partial Payment

If the customer pays less than the displayed total:

Driver must NOT confirm payment.

The driver must request the remaining amount.

BR-042 — Payment Confirmation Finality

Once the driver confirms the complete payment:

The payment is considered confirmed for that transaction and the driver cannot subsequently claim that the customer failed to provide the confirmed amount.

14. Cash Collection for VISTAAR (SUPERSEDED IN FULL — ADR-0025,
2026-08-25)

This entire section described the driver collecting VISTAAR's charge in
cash from the customer, then VISTAAR clawing that portion back via the
wallet. That scenario cannot occur under the approved P2P Payment Model:
VISTAAR's charge is already collected from the driver's wallet at ride
acceptance (BR-011, before the ride happens), never bundled into what
the customer pays. There is nothing left for the driver to "collect on
behalf of VISTAAR," and therefore no "cash collected but wallet
insufficient" scenario for BR-045's outstanding-settlement recovery to
apply to. (The already-implemented `InsufficientWalletBalanceError` at
ride acceptance — see modules/wallet — already prevents acceptance
outright when the wallet cannot cover the fee; it does not defer
collection to later.)

BR-043 — Separate Accounting (superseded)

If the driver collects VISTAAR's charge in cash:

Ride fare → Driver earnings
VISTAAR charge → VISTAAR settlement liability

The VISTAAR portion is not driver income.

BR-044 — Wallet Settlement (superseded)

After the driver confirms receiving the complete amount, VISTAAR settles its portion by deducting the applicable amount from the driver's wallet.

BR-045 — Insufficient Wallet (superseded)

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

BR-049 — Customer Cancellation Charge Never Expires

**Corrected 2026-09-04 (owner decision, ADR-0069) — this rule previously
read "each ₹15 charge is valid for 30 days; after 30 days, an unpaid
charge expires." That is reversed:**

Customer penalties in VISTAAR never expire. Once created, a charge
remains OUTSTANDING indefinitely until the customer actually pays it —
no automatic expiry date, no cancellation of the charge due to time
passing, and no expiry-enforcement job exists or will be built for
this.

This is specific to customer penalties (`penalty.penalties` —
BR-047/048/052 cancellation/no-show charges). It is unrelated to, and
must not be confused with, Sarthi cancellation-penalty debt
(`wallet.wallets.outstanding_debt`, ADR-0062) — a separate mechanism
for a different party that has never had an expiry concept either; see
ADR-0069 for the explicit distinction.

Clarification (ADR-0012, added 2026-08-22): BR-046–BR-049 are all written
in terms of a cancellation "after driver acceptance" — the 2-minute grace
period, the "qualifying cancellation" counter, and "the driver's platform
fee is refunded" all presuppose a driver was already assigned and a
platform fee already debited. Cancelling a ride before any driver has
been assigned (i.e. while still searching for a driver) has neither of
those, so it is unconditionally free (₹0, no charge) and does not
increment the "first vs. second+ qualifying cancellation" counter these
rules describe. This is a clarification of what BR-046–049 already imply
by their own stated preconditions, not a new rule.

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

BR-053 — No-Show Charge Never Expires

**Corrected 2026-09-04 (owner decision, ADR-0069), same correction as
BR-049**: the ₹30 no-show charge never expires — it remains OUTSTANDING
indefinitely until paid, no automatic expiry, no enforcement job. (This
rule describes the charge amount/expiry only — no-show charges
themselves are not yet implemented in code, per `modules/penalty/
__init__.py`'s own "what this deliberately does not do yet" list; this
correction is recorded now so the rule is right whenever that task is
built, not left to be gotten wrong twice.)

17. Customer Outstanding Charges

RESOLVED (ADR-0026, 2026-08-26, Option A — this closes the exact
question ADR-0025 flagged as unresolved for BR-055), settlement
mechanism updated (ADR-0066, 2026-09-03, owner decision). A qualifying
cancellation (BR-047/048) or no-show (BR-052) creates an OUTSTANDING
penalty liability for that customer — `penalty.penalties`, already
implemented exactly this way — surfaced at the customer's next ride
booking (BR-056, detailed in §12's revived BR-037/038).

**How it's actually collected, as of ADR-0066**: the customer pays the
combined ride-fare-plus-outstanding-penalty amount to the Sarthi
directly (e.g. fare ₹200 + penalty ₹30 = ₹230 paid to the Sarthi), and
VISTAAR recovers its own share automatically by debiting the driver's
wallet the moment that ride completes — no VISTAAR-facing payment step
for the customer at all. This reverses this section's original
framing ("VISTAAR collects it directly from the customer... never
routed through, or debited from, the driver's wallet") — that was
ADR-0026's original design, superseded by ADR-0066 specifically on
*how* collection happens, not *that* the penalty is owed or *when* it's
surfaced. BR-055 below ("directly through the VISTAAR app") is
correspondingly stale — see its own note.

Outstanding charges may include:

₹15 cancellation charges
₹30 no-show charges
Other approved VISTAAR-owned charges

Each charge is independently tracked. **Corrected 2026-09-04**: none of
them expire (BR-049/BR-053) — each remains outstanding until paid,
independent of the others.

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

**Superseded 2026-09-03 (ADR-0066)**: no in-app payment flow exists or
will be built for this — see this section's header note above. The
customer settles the charge by paying the Sarthi directly (BR-056), not
through the app.

BR-056 — Outstanding Charges on Next Ride

Outstanding charges may also be included in the next ride's total payable amount.

As of ADR-0066 (2026-09-03), this is the *only* settlement path — the
outstanding amount is durably attached to the customer's next ride at
booking (not just displayed) and settled, via the driver's wallet, the
moment that ride completes.

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

₹100 per ride — RESOLVED (ADR-0049, 2026-08-28, owner decision).

BR-064 — Promotional Benefits

A customer may receive both welcome and referral promotional entitlements.

However:

Two separate 50% discounts cannot be stacked onto the same ride.

BR-128 — Campaign/Coupon Discounts (ADR-0041, 2026-08-26)

Admin-authored campaigns (Admin Web's Offers/Coupons module) are a
separate concept from the welcome/referral entitlements above: a
campaign is defined once (code, eligible vehicle category, discount
type/value, minimum fare, eligible-customer scope, per-customer and
total redemption limits, an active date window) and redeemed by many
customers, each redemption creating its own entitlement. A campaign's
discount terms may be edited only while it is in DRAFT — once
activated (and so potentially already redeemed), only its status
(active/paused/ended) may change, never its discount value, minimum
fare, or eligibility — the same never-rewrite-history principle the
Admin Web spec states for Fare Management's own published fares
(docs/15-admin-web/admin-web-implementation-plan.md), applied
consistently here even though the spec only stated it explicitly for
fares. BR-063's discount-cap question is unaffected by this rule — it
concerns the welcome/referral 50% discounts specifically and stays
exactly as open as before.

19. Promotional Cancellation
BR-065 — Early Cancellation

If a promotional ride is cancelled during the defined early-cancellation period:

Promotion restored
BR-066 — Late Cancellation

If a promotional ride is cancelled after the early-cancellation boundary:

Promotion consumed

The exact early/late cancellation boundary is:

TBD

Implementation note (2026-09-04, ADR-0070): since the boundary above is
genuinely undetermined, the current implementation does not guess at
one — every cancellation of a ride carrying a reserved promotion
restores it (BR-065's outcome, unconditionally), and BR-066's "late
cancellation instead consumes it" case stays unenforced until the
boundary is actually decided. This is a deliberate, flagged interim
behavior, not an assumption that BR-066 doesn't apply.

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

SUPERSEDED (project owner, 2026-08-31; see ADR-0056-pickup-change-
simplification-hard-threshold.md): a pickup change beyond the threshold
is now rejected outright, with no driver decision of any kind — see
BR-074's own superseded note below. This rule's trigger condition (a
driver passing on a >threshold pickup change) can no longer occur, so
its ₹0-penalty/no-strike exemption is never reached. Kept below,
unmodified, as the historical record of the original design ADR-0033
implemented.

If a customer changes pickup by more than 250 meters and the driver does not want to travel to the new pickup:

Driver may pass/cancel the ride
→ No ₹30 penalty
→ No cancellation strike
→ VISTAAR searches for nearby driver

This is a special cancellation reason and must not be treated as normal driver cancellation.

22. Pickup Location Changes
BR-072 — Pickup Change

Customers may change their pickup location after booking, subject to
BR-073's threshold and BR-074's rejection rule (updated 2026-08-31, see
ADR-0056).

BR-073 — Pickup Within 250m

UPDATED (project owner, 2026-08-31; see ADR-0056-pickup-change-
simplification-hard-threshold.md): the threshold is now **100 meters**,
not 250. Below is the original rule, otherwise unchanged in shape —
within the threshold, the change still applies immediately, no driver
or customer confirmation step involved.

If the new pickup is within 250 meters of the driver's relevant current location:

Ride continues normally
BR-074 — Pickup More Than 250m Away

SUPERSEDED (project owner, 2026-08-31; see ADR-0056-pickup-change-
simplification-hard-threshold.md): there is no longer a driver choice.
A pickup change beyond the threshold (now 100m, see BR-073) is
**rejected outright** — the ride is left completely unchanged, no
matching/rematching, no fare change. The customer's only path to a
genuinely-far pickup is to cancel the current ride (BR-046-049's
existing, unrelated cancellation-penalty rules apply normally) and book
a new one. BR-075/076/077/078 below are superseded for the same reason
— none of their trigger conditions can occur anymore. All four are kept
below, unmodified, as the historical record of the original design.

If the new pickup is more than 250 meters away:

Driver gets choice:
1. Accept new pickup
2. Pass/cancel without penalty
BR-075 — Driver Accepts Changed Pickup

SUPERSEDED 2026-08-31 — see BR-074's note above and ADR-0056.

If the driver accepts:

Additional charge is calculated.
Customer sees the additional charge.
Customer must confirm the charge.
Driver proceeds only after customer confirmation.
BR-076 — Additional Pickup Charge

SUPERSEDED 2026-08-31 — see BR-074's note above and ADR-0056. There is
no longer any scenario in which a pickup change carries a charge; the
rate below (itself only resolved 2026-08-25 by ADR-0033) is now unused.

An additional pickup charge applies for the additional distance beyond the 250-meter threshold.

The exact vehicle-specific rate is:

RESOLVED (project owner, 2026-08-25; see ADR-0033-ride-modifications-
pickup-and-destination-change.md): the same per-km rate as the ride's
own base fare — i.e. the vehicle category's existing `pricing.fare_rules.
per_km` value, not a new flat number. This was originally discussed in
the ₹10–₹20/km range but the owner chose to reuse the base fare rate
instead once asked directly.

BR-077 — Customer Must See Charge

SUPERSEDED for pickup change specifically, 2026-08-31 — see BR-074's
note above and ADR-0056. The general principle this rule embodies ("no
fare change may be silently applied") is untouched everywhere else it
already applies, e.g. destination change, BR-082.

The driver must not proceed toward the changed pickup until the customer has seen and confirmed the additional charge.

BR-078 — Driver Passes Changed Pickup

SUPERSEDED 2026-08-31 — see BR-074's note above and ADR-0056.

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

GAP-8 (found 2026-08-31, while building the mobile destination-change
UI; see api-contracts.md §25): as implemented, `POST .../destination-
change`'s response never includes the computed fare for a payable
case — only `POST .../destination-change/confirm`'s response does,
after the customer has already answered `confirmed`. This rule's own
ordering ("Customer sees revised fare → Customer confirms") is not
satisfiable by the current API as built. Not yet resolved; `apps/
mobile` does not confirm blind around it (see that app's own
`RideStatusScreen._changeDestination()`).

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

RESOLVED (ADR-0028, 2026-08-25): 50 meters, with 3 attempts before the
ride enters manual review — see BR-124.

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

Implementation status (Phase 08, ADR-0030, 2026-08-25): COMPLETE —
api-contracts.md §27. "GPS/location + timestamp recorded" above is
implemented exactly as written: recorded as evidence, not verified
against a distance/tolerance threshold — state-machines.md §19-21's added
"GPS verification PASS/FAIL" language is not corroborated by this rule,
api-contracts.md, or technical-architecture.md, and does not govern (see
the ADR for the full reconciliation).

27. Normal Ride Completion
BR-091 — Destination GPS Verification

For normal destination completion:

Driver selects Complete
→ VISTAAR verifies GPS
→ Destination verified
→ Ride completed

The exact destination radius is:

RESOLVED (ADR-0028, 2026-08-25): 100 meters, with 3 attempts before the
ride enters manual review — see BR-124.

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

BR-123 — Document/Verification Gate on Admin Approval (approved;
numbered out of sequence — placed here with BR-098/BR-099 since it
belongs to the same Driver/Vehicle Approval topic, same reasoning as
BR-122)

An admin must not approve a driver or vehicle while any required
document or verification case for that driver/vehicle is PENDING,
REJECTED, EXPIRED, or otherwise not in an approved/valid state.

Required documents must first reach an approved/valid verification state
before admin approval of the driver or vehicle itself is permitted.

This rule distinguishes five separate concepts, none of which it
collapses into another:

1. Document verification validity — is an individual document
   approved/valid (driver.documents.verification_status /
   vehicle.documents.verification_status).
2. Verification case state — verification.cases.status (Phase 2 /
   Task 2.6).
3. Admin approval — driver.drivers.verification_status /
   vehicle.vehicles.verification_status (Phase 2 / Task 2.7A).
4. Driver eligibility — whether a driver may go ONLINE (Phase 2 /
   Task 2.7B, this document §10 of api-contracts.md).
5. Driver ONLINE/OFFLINE status — operational availability only,
   unaffected by this rule.

This rule does not itself define the mechanism by which a document or
verification case moves out of PENDING (manual admin review vs. an
authoritative/AI provider vs. something else) — that mechanism is not
yet defined by any source document and remains a separate, unresolved
implementation decision (see docs/14-decisions/ADR-0009 and ADR-0008).

BR-123 enforcement (Phase 2 / Task 2.6C — approved). The set of
"required documents" this rule blocks admin approval on is:

Driver: Government ID, Driving Licence
Vehicle: RC, Insurance

Derived from BR-097's "Identity"/"Vehicle" onboarding fields — the only
items in BR-097 with an inherent legal-validity concept. Vehicle photo
is explicitly NOT part of this required set: no authoritative source
requires a photo to reach an approved/valid verification state before
admin approval, unlike RC/Insurance, and a photo has no natural expiry.
This does not finalize the "Final KYC document list" §43 still marks as
TBD — it is the working set enforced by code today, carrying the same
"subject to applicable Indian regulatory requirements and final
compliance review" caveat BR-097 itself states.

`DriverService.approve_driver()`/`VehicleService.approve_vehicle()`
(Phase 2 / Task 2.7A) enforce this rule as of Task 2.6C: approval is
rejected (reusing the existing `DRIVER_NOT_ELIGIBLE`/
`VEHICLE_NOT_ELIGIBLE` codes, api-contracts.md §49) if any required
document is missing, or present but not `APPROVED` and unexpired.
Rejecting a driver/vehicle (as opposed to approving) is not gated by
this rule.

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

BR-122 — Single Active Vehicle (approved; numbered out of sequence —
added after BR-121 was already in use, but placed here with BR-099–BR-102
since it belongs to the same Vehicle Verification topic)

At most one of a driver's vehicles may be ACTIVE at any time.

One driver
    ↓
Multiple registered vehicles allowed
    ↓
Maximum ONE ACTIVE vehicle per driver
    ↓
Vehicle switching is allowed only while the driver is OFFLINE

Activating a different vehicle while one is already ACTIVE deactivates
the previously ACTIVE vehicle as part of the same operation — a driver
is never left with, nor briefly passes through, more than one ACTIVE
vehicle. This must be enforced server-side, safely under concurrent
requests, and must not be trusted to the mobile client.

This rule resolves what BR-102's "Select approved vehicle → Activate it"
(singular) already implied but did not state explicitly; it does not
change BR-099–BR-102 in any other way.

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

RESOLVED (ADR-0050, 2026-08-28): none — SOS escalates to VISTAAR's own
internal safety/call-center team (every Super Admin plus every employee
admin with SAFETY MANAGE access), not a real police/emergency-service
API. Notified over IN_APP + SMS the moment an incident is triggered.

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

Implementation status (Phase 13, ADR-0028 + ADR-0029, 2026-08-25): the
"support/admin process" this rule names is the already-built Support
Case flow (api-contracts.md §44, `category: "RIDE_FARE_DISPUTE"`) — no
dedicated dispute endpoint/table exists, matching ADR-0028's "Dispute is
a Support/Admin capability, not a new domain" decision. Penalty disputes
(domain-design.md §17.3's DisputePenalty) follow the same pattern —
`category: "PENALTY_DISPUTE"`, decided via the already-built admin
Resolve Penalty endpoint (§48).

BR-124 — GPS Verification Manual Review (Dispute)

APPROVED (project owner, 2026-08-25; see ADR-0032 for the implementation
that followed). Formalizes, as an actual business rule, the GPS-dispute
workflow security.md §11/§15 and testing-strategy.md §20-22/§89-90
already describe in detail but which ADR-0002 found was never ratified
through business-rules.md itself — this record is that ratification.

When server-side GPS verification for Driver Arrival (BR-086) or
Destination Completion (BR-091) has failed the maximum configured number
of retriable attempts (3, per BR-086/BR-091 — the terminal,
`GPS_VERIFICATION_FAILED` outcome), the ride enters manual review instead
of staying permanently blocked:

Retries exhausted (terminal GPS failure)
→ Manual review opens automatically
→ Evidence window: 24 hours
→ Customer and driver may each submit evidence (photo, video, document,
  or text explanation)
→ An admin reviews the submitted evidence and the ride's full GPS
  verification history
→ Admin decision: APPROVE or REJECT, with a required reason

If APPROVE:

→ The disputed GPS verification is treated as if it had PASSED
→ The ride transition that was blocked (→ ARRIVED for BR-086, →
  COMPLETED for BR-091) proceeds
→ The original failed GPS verification record is not erased or altered —
  the admin decision is an additional record alongside it, not a
  replacement

If REJECT, or if the 24-hour evidence window elapses with no evidence
submitted:

→ The original GPS result stands; the ride does not transition
→ The dispute is marked resolved/rejected for the historical record
→ No automatic financial consequence follows from the rejection alone —
  any penalty/charge implication is decided separately, through the
  existing cancellation/penalty rules (BR-046-049) or Support (BR-121),
  as applicable to whatever the driver/customer do next

This rule applies only to Driver Arrival and Destination Completion GPS
verification. It does NOT apply to Early Drop (BR-088-090): Early Drop
has no GPS verification step to fail in the first place (ADR-0030) — its
`gps_location`/timestamp are recorded as evidence only, with nothing to
dispute.

BR-125 — GPS Dispute Evidence

APPROVED (project owner, 2026-08-25), companion to BR-124; see ADR-0032.

Evidence submitted for a GPS manual review (BR-124) must be one of:
photo, video, document, or text explanation. Evidence is private to the
ride's customer, driver, and the reviewing admin(s) — never exposed via
a public URL. For the life of the dispute, VISTAAR preserves: the full
driver/customer GPS history for the ride, timestamps, ride details,
every piece of uploaded evidence, and the admin's decision and reason.
An admin decision never deletes or overwrites the original GPS
verification record it reviews.

BR-126 — Admin Roles & Permission Model

APPROVED (project owner, 2026-08-26 — confirmed "continue" after
review). Resolves §43's "Admin roles" and "Permission hierarchy"
items; see ADR-0040 for the implementation that follows.

There is no fixed set of admin roles (no separate SAFETY_ADMIN/
FINANCE_ADMIN/SUPER_ADMIN-as-distinct-account-types) — security.md §7's
example role list is superseded by this rule. Instead:

There is exactly one Super Admin level, controlled by the core team.
The Super Admin can create employee admin accounts, assign each one a
set of individual feature permissions, and later increase or decrease
those permissions or disable the account entirely.

Permissions are granted per admin module, not per fixed role. The
module catalog is the same list the Admin Web's own navigation uses:
Dashboard, Customers, Drivers, Vehicles, Verification/Documents, Rides,
Matching/Offers, Finance/Wallet, Fare Management, Penalties/Strikes,
Offers/Coupons, Referrals, Notifications, Safety/SOS, Support/Disputes,
Advertisements, Reports/Analytics, Audit Logs, Admin Management,
Settings. For each module, an employee admin has one of: no access,
view-only access, or manage access (view + the module's own mutating
actions) — a two-level granularity, not full per-action permissions;
this can be split more finely later without a schema-breaking change if
a real need for it appears. "Admin Management" and "Settings" (module
access to grant/revoke other admins' permissions) are never grantable
to an employee admin — only the Super Admin ever holds them, and this
is not configurable.

Permission changes take effect immediately and are enforced server-side
on every request, not only hidden in the Admin Web's own navigation.

Every admin-permission change (grant, revoke, account creation,
disabling) is itself an audited action (admin.audit_logs), the same as
every other privileged admin action this codebase already audits.

BR-127 — Admin Account Provisioning

APPROVED (project owner, 2026-08-26 — confirmed "continue" after
review), companion to BR-126; see ADR-0040.

The Super Admin level has no self-service registration path — the same
"who is allowed to grant admin status" restraint ADR-0009 already
applied to the single ADMIN account type this codebase had before this
rule. The first Super Admin account for a given environment is
provisioned by whoever already holds deployment/infrastructure access
for that environment, via an ops-only script (extending
`scripts/provision_admin.py`'s existing pattern) — never through a
public HTTP endpoint. Every employee admin account after that is
created through a real, authenticated HTTP endpoint, but one reachable
only by an already-active Super Admin — never self-service, never by
another employee admin.

40. Driver Earnings Transparency

The Driver App should display:

Ride earnings
Platform fees
Penalties
Bonuses
Referral rewards
Wallet balance

"VISTAAR cash collected" and "Wallet settlements" (superseded — ADR-0025,
2026-08-25) are removed from this list: the driver never collects money
on VISTAAR's behalf (§41), so there is nothing of this kind to display.

Example:

Ride fare                 ₹200
Parking                   ₹30
Pickup-change charge      ₹20
────────────────────────────
Customer total            ₹250


Platform fee              ₹20
Driver ride earnings      ₹230
41. Cash Collection Transparency (SUPERSEDED — ADR-0025, 2026-08-25)

This described a driver collecting money "on behalf of VISTAAR" — no
longer possible under the approved P2P Payment Model: VISTAAR's charge
is collected from the driver's wallet at ride acceptance, never from
cash the driver receives from the customer. All cash/UPI the driver
receives directly from the customer is the ride fare, and belongs
entirely to the driver.

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
ARRIVED GPS radius — RESOLVED (ADR-0028, 2026-08-25): 50 meters (BR-086)
Completion GPS radius — RESOLVED (ADR-0028, 2026-08-25): 100 meters (BR-091)
GPS manual review / dispute evidence window — RESOLVED (BR-124,
  2026-08-25): 24 hours (was untouched/TBD before this rule;
  security.md/testing-strategy.md's own "72 hours" was always explicitly
  an illustrative placeholder, never approved)
Definition of "far" beyond the 250m pickup-change threshold where applicable
Driver
Final KYC document list
Verification provider
Document-specific safety rules
Payments (reconciled — ADR-0025, 2026-08-25)
Final payment gateway — narrowed further: the driver wallet-recharge
  gateway is now IMPLEMENTED for TEST/DEVELOPMENT (Razorpay, ADR-0060,
  2026-09-02) behind a provider abstraction; the PRODUCTION gateway
  (SBI) is still TBD, pending SBI credentials/integration — ADR-0060 §5
  documents exactly which components will need replacing when that
  happens. No customer-facing ride-fare gateway is needed under the
  approved P2P Payment Model, and none was added.
Driver settlement mechanism — RESOLVED: platform fee debited from the
  driver's wallet at ride acceptance (BR-011, technical-architecture.md
  §18, ADR-0014, already implemented)
Payment settlement timing — RESOLVED: at ride acceptance (same as above)
Refund settlement process — N/A for the customer (VISTAAR never
  collects a ride-fare payment from the customer, so there is nothing to
  refund them); the driver-side platform-fee reversal on cancellation
  was already resolved separately (BR-046-049, ADR-0015, `FEE_REVERSAL`)
Customer outstanding-charge (penalty) online payment — RESOLVED
  2026-09-03 (ADR-0066): no VISTAAR-app payment surface for this is
  built or needed. BR-055's "directly through the VISTAAR app" is
  superseded — the customer pays the Sarthi directly (combined with the
  ride fare) and VISTAAR recovers its share via the driver's wallet at
  ride completion; see BR-055/BR-056's own updated notes above.
Safety
Emergency contact workflow — still genuinely TBD, unaffected by ADR-0050
  (a different concept: in-app emergency contacts, not VISTAAR's own
  escalation path)
Police/emergency-service integration — RESOLVED (ADR-0050, 2026-08-28):
  none; SOS escalates internally to VISTAAR's own safety/call-center
  team instead (see BR-112 above)
Safety-team operating procedure — the recipient is now resolved
  (ADR-0050), but what staff actually do after being notified (SOPs,
  response-time targets, hand-off to a human call center) remains
  genuinely TBD
Admin
Admin roles — RESOLVED (BR-126, 2026-08-26): Super Admin + granular
  per-module permissions, no fixed role set
Permission hierarchy — RESOLVED (BR-126/BR-127, 2026-08-26): Super
  Admin sole authority over admin accounts/permissions; enforced
  server-side
Escalation rules — still genuinely TBD, not addressed by BR-126/BR-127
Fraud investigation workflow — still genuinely TBD, not addressed by
  BR-126/BR-127
Promotion / Growth
Coupon/campaign schema — RESOLVED (BR-128, ADR-0041, 2026-08-26):
  promotion.campaigns is additive to promotion.entitlements, not a
  replacement; editable only in DRAFT
Promotion discount cap (BR-063) — RESOLVED (ADR-0049, 2026-08-28): ₹100
  per ride, applied to all three 50%-off welcome/referral entitlement
  types; unaffected by BR-128 (Campaign/Coupon discounts have their own,
  separate admin-authored cap)
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

47. Admin-Configurable Reward / Fee / Template Policy (2026-08-26)

Owner-approved decision batch (2026-08-26) resolving several
previously-TBD "should this be admin-editable" questions raised across
earlier ADRs. Design only at the time of recording — see each
referenced ADR for exact schema/API shape; runtime implementation is a
separate, later task per the owner's own explicit instruction on this
batch.

BR-129 — Referral Reward Configuration

The driver referral bonus (BR-022/023, currently ₹100/₹100) and the
customer referral reward shape (BR-059/060, currently 50%/3 uses
referred, 50%/2 uses referring) become admin-editable, versioned, and
effective-dated (ADR-0043). A change applies only to referrals that
qualify after publication — a referral already qualified, and any
reward already issued, is never retroactively altered. BR-058's
WELCOME promotion is explicitly unaffected (see BR-131 instead).

BR-130 — Notification Template Management

Notification/SMS/push/broadcast message templates become admin-
editable with a draft/publish workflow and full version history
(ADR-0044). A notification already sent keeps whatever content was
live at send time — editing or republishing a template never alters a
historical delivery record. Provider credentials (MSG91, Firebase,
any future WhatsApp BSP) are never exposed through any template
endpoint.

BR-131 — Platform Fee Configuration

The per-vehicle-category platform fee (BR-011, currently ₹2 Bike / ₹5
Auto / ₹10 Cab, uniform across all three CAB tiers) becomes admin-
editable, versioned, and effective-dated, using the identical
DRAFT → IN_REVIEW → PUBLISHED workflow Fare Management already
established (ADR-0042/ADR-0045). A fee change
applies only to rides accepted after publication — the platform fee
already debited for a historical ride is never altered.

BR-132 — Advertisement Admin Management

The Admin Web gains a full campaign/assignment/payout management
surface over the Advertisement domain (ADR-0018's already-built
domain/service layer) — campaign creation and status (ACTIVE ⇄ PAUSED
→ ENDED, newly added), driver assignment, installation-proof review
and approve/reject, the existing manual `verification_status` field
(loosely referred to as "Admoto verification status" — the actual
Admoto integration remains a separate, deferred decision, ADR-0018
Item 3), and payout/settlement monitoring (ADR-0046). The documented
80%/20% driver/VISTAAR payout split is unchanged — no new ad economics
are introduced.

BR-133 — Driver Strike History

`penalty.strikes` (already recorded on every applicable driver
cancellation, BR-068) becomes queryable and visible in the Admin Web —
date, reason, related ride when available, and full audit trail. The
existing `driver.drivers.strikes` counter remains the at-a-glance
summary; the new history view is the underlying detail, not a
replacement. No new data is captured — this is a read surface over
data already recorded.

BR-134 — Coupon/Campaign Customer Targeting

Extends BR-128/ADR-0041's campaign eligibility model with a third
targeting input alongside "all eligible customers" and admin
search/select: bulk targeting via CSV upload (one `phone` column per
row), additive to a campaign's existing selected-customer set rather
than replacing it (ADR-0041 §9). No new targeting concept (tag-based,
behavioral, or otherwise) is introduced.

Decision Register update:

Referral reward amount editability — RESOLVED (BR-129, ADR-0043,
  2026-08-26): admin-editable, versioned/effective-dated
Notification template editability — RESOLVED (BR-130, ADR-0044,
  2026-08-26): admin-editable, draft/publish, versioned
Platform fee editability — RESOLVED (BR-131, ADR-0045, 2026-08-26):
  admin-editable, versioned/effective-dated, same workflow as Fare
  Management
Advertisement admin HTTP surface (ADR-0018 Item 2) — RESOLVED
  (BR-132, ADR-0046, 2026-08-26); Admoto integration (ADR-0018 Item 3)
  stays deferred, unaffected by this resolution
Driver strike history — RESOLVED (BR-133, 2026-08-26): queryable,
  immutable, read-only over existing `penalty.strikes` data
Reports/Analytics MVP scope — RESOLVED (ADR-0047, 2026-08-26): nine
  fixed report areas over existing data, no data warehouse
Settings MVP scope — RESOLVED (ADR-0048, 2026-08-26): navigation over
  the four dedicated config screens above, plus one new generic
  key-value table for promotion defaults/operational thresholds/
  feature flags/general settings, seeded minimally
Coupon/campaign customer targeting — RESOLVED (BR-134, ADR-0041 §9,
  2026-08-26): all / selected (search) / bulk (CSV), additive upload
WhatsApp BSP selection — still NOT resolved by this batch; the owner
  explicitly reserved this decision for separately
Payment gateway (SBI Bank) selection — still NOT resolved by this
  batch; same treatment

48. Schedule a Ride & Book for Someone Else (2026-08-31)

Owner-approved decision batch (2026-08-31, ADR-0057) resolving the open
questions `docs/16-mobile/mobile-app-implementation-plan.md` §4.10/
§4.11 flagged when both features were added to scope 2026-08-29. Backend
IMPLEMENTED the same day — see ADR-0057 for exact schema/API shape and
the full implementation write-up (§8 of that ADR). Only the mobile
app's own screens for both features remain.

BR-135 — Scheduled Ride Cancellation

A ride scheduled for a future pickup time may be cancelled before that
time arrives. Distinct from BR-046-049 (which presuppose a driver was
already assigned) — a scheduled ride's own cancellation is charged
against its scheduled pickup time, not against driver acceptance:

Cancelling ≥3 hours before the scheduled pickup time
→ ₹0

Cancelling <3 hours before the scheduled pickup time
→ ₹30

Neither case records a behavioral strike (PRD §33) — a different
(advance-notice) failure mode than an ordinary last-second cancellation
or a driver-side cancellation.

Once a scheduled ride has begun active matching (i.e. transitioned to
the ordinary SEARCHING state, ADR-0057 Decision 1), this rule no longer
applies — an ordinary SEARCHING cancellation stays free per BR-046's
own precondition, since no driver has been assigned yet either way.

BR-136 — Scheduled Ride Matching Timing

Matching for a scheduled ride begins a fixed window before the
scheduled pickup time (ADR-0057: 30 minutes, an engineering default,
not independently re-derived as a business value) — not at booking
time. Once matching begins, the ride follows the ordinary SEARCHING →
ACCEPTED → ... lifecycle unchanged, including the ordinary retry
behavior if no driver is immediately available (same as an immediate
ride; §21's no-driver-found retry/fare-increase flow, once built,
applies identically here — no scheduled-specific version is created).

BR-137 — Scheduled Ride Window

A ride may be scheduled no less than 1 hour and no more than 24 hours
in advance (ADR-0057, engineering defaults the owner approved as a
starting point — revisit if real usage shows either bound is wrong).

BR-138 — Book for Someone Else: Billing and Payment

The booker's own payment method is charged by default, regardless of
who is physically in the vehicle. The rider may instead pay the driver
directly, in cash, at the vehicle — but only once the driver's
cash-payment-confirmation capability (§33, a separate, already-tracked
gap — not built anywhere in the backend as of this decision) exists;
until then, Book for Someone Else supports the booker-billed path only.

BR-139 — Book for Someone Else: Rider Identity and OTP

The actual rider is picked from the booker's own phone contacts (name
and phone number) — not required to hold a VISTAAR account. The
ride-start OTP (§18) is delivered by SMS to both the booker and the
linked contact. The linked contact receives no other visibility into
the ride in this first version (no shared/read-only ride view) —
deferred to whenever Ride Sharing (§42, a separate unbuilt capability)
exists.

BR-140 — Book for Someone Else: Promotion Eligibility

Welcome/referral discount eligibility is evaluated against the
booker's own account — the booker is billed and is the ride's
customer_id for every other purpose this feature touches; the linked
contact's own account status (if any) is never checked.

Decision Register update:

Schedule a Ride — matching timing, fare timing, scheduling window,
  driver lock-in, no-driver-found handling — RESOLVED (BR-135–137,
  ADR-0057, 2026-08-31): matched 30 minutes before pickup via the
  ordinary SEARCHING flow (no new offer type), fare locked at booking
  via the existing pricing.fare_quotes mechanism, 1-24 hour scheduling
  window, ≥3h/₹0-<3h/₹30 cancellation with no strike.
Book for Someone Else — billing, rider visibility, promotion
  eligibility — RESOLVED (BR-138–140, ADR-0057, 2026-08-31):
  booker-billed by default (cash-on-spot deferred to when cash-payment-
  confirm exists), booker-only visibility for now, promotions apply to
  the booker's account.

49. Sarthi Wallet Low-Balance Rule (2026-09-02)

BR-141 — Low-Balance Threshold and Grace Ride

RESOLVED (ADR-0058, 2026-09-02, IMPLEMENTED — owner decision). When a
Sarthi's wallet balance is at or below ₹20:

The Sarthi is notified that the balance is low and a recharge is
required.

The Sarthi may accept exactly one more ride (the "grace ride").

After that acceptance, the Sarthi cannot accept another ride until the
wallet balance is recharged back above ₹20.

No partial-debit mechanism and no new outstanding-balance/liability
concept are introduced — this is a yes/no gate on top of the existing
wallet balance, layered on top of (not replacing) the pre-existing
BR-012 insufficient-balance check.

Distinct from the still-unresolved driver-cancellation insufficient-
balance question (see the "Known functional gaps" register below) —
that concerns the *cancellation* path and BR-141 does not resolve it.

Decision Register update:

Sarthi wallet low-balance ride-acceptance behavior — RESOLVED (BR-141,
  ADR-0058, 2026-09-02): ₹20 threshold, one grace ride, then blocked
  until recharge; no partial debit, no outstanding-balance concept.
Driver-cancellation insufficient-wallet-balance behavior — RESOLVED
  2026-09-03, see §51/BR-143 below (ADR-0062) — no longer open.

50. Sarthi Wallet Recharge (2026-09-02)

BR-142 — Wallet Recharge, Minimum Amount and Verification

RESOLVED (ADR-0060, 2026-09-02, IMPLEMENTED — owner decision). A Sarthi
may top up their own VISTAAR wallet (the same wallet the platform fee
is debited from at ride acceptance — BR-011) with a minimum recharge
amount of ₹200 per transaction (`WALLET_RECHARGE_MINIMUM_AMOUNT`,
engineering configuration, not a business value requiring its own
settings-table entry). Below the minimum, the request is rejected
(`RECHARGE_AMOUNT_TOO_LOW`) before any payment gateway interaction.

The wallet is credited only after the payment is verified server-side
against the payment gateway's own record of it — never on the strength
of a client/mobile-reported "success" alone. A payment that cannot be
verified as captured credits nothing.

This is unrelated to, and does not resolve, the still-undecided
customer outstanding-penalty *collection* mechanism (§17 above,
ADR-0026 §5) — this rule is scoped to a Sarthi's own wallet top-up,
not a customer-facing payment of any kind.

Payment gateway: for TEST/DEVELOPMENT only, VISTAAR uses Razorpay,
behind a provider abstraction (`WalletRechargeGateway`) specifically so
the production gateway (SBI, not yet integrated — credentials pending)
can replace it without a business-logic change. See ADR-0060 for the
full provider-abstraction design and exactly which components the SBI
switch will touch.

Decision Register update:

Sarthi wallet recharge, TEST-mode gateway — RESOLVED (BR-142, ADR-0060,
  2026-09-02): Razorpay TEST/DEVELOPMENT only, behind a provider
  abstraction; production gateway remains SBI, still TBD pending
  credentials.

51. Sarthi Unpaid Cancellation-Penalty Recovery (2026-09-03)

BR-143 — Cancellation Never Blocked; Unpaid Penalty Recovered at Next
Recharge

RESOLVED (ADR-0062, 2026-09-03, IMPLEMENTED — owner decision, resolving
the driver-cancellation insufficient-balance blocker this document's own
"Known functional gaps" register previously tracked as open). When a
Sarthi cancels an ACCEPTED ride and the ₹30 driver-cancellation penalty
(BR-011) exceeds the wallet balance:

The cancellation still succeeds — the ride transitions to CANCELLED and
the driver strike is recorded exactly as it would with a sufficient
balance. Cancellation is never blocked by an insufficient balance.

No partial debit occurs — the wallet balance is left completely
untouched.

The full unpaid penalty becomes a tracked outstanding debt
(`wallet.wallets.outstanding_debt`), recovered automatically from the
Sarthi's next wallet recharge specifically — not from any other credit
(a bonus or fee reversal never pays down this debt).

An outstanding debt does not, by itself, affect ride-acceptance
eligibility — that remains governed solely by the existing ₹20
low-balance rule (BR-141/ADR-0058), confirmed independent of this rule.
A Sarthi with debt but at least ₹20 in spendable balance can still
accept rides normally.

Decision Register update:

Driver-cancellation insufficient-wallet-balance behavior — RESOLVED
  (BR-143, ADR-0062, 2026-09-03): cancellation never blocked; unpaid
  penalty tracked as outstanding debt, recovered from the next wallet
  recharge. No longer an open item.
