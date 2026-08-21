VISTAAR — API Contracts

Document Version: 1.0
Status: Draft — Derived from PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, Domain Design v1.0, and Database Design v1.0
API Version: /api/v1
Currency: INR (₹)

1. Purpose

This document defines the external and internal API contracts for VISTAAR.

It specifies:

Endpoints

HTTP methods

Authentication

Authorization

Request bodies

Response bodies

Validation

Error codes

Idempotency

Pagination

State-transition requirements

Customer APIs

Driver APIs

Ride APIs

Wallet APIs

Payment APIs

Promotion/referral APIs

Safety/support APIs

Admin APIs

Internal domain APIs

The API layer must implement the business rules already approved in the PRD and Business Rules documents.

2. API Principles

2.1 Versioning

All public APIs begin with:

/api/v1

Breaking changes require a new API version.

2.2 Authentication

Customer and driver APIs require authenticated sessions unless explicitly marked public.

Admin APIs require admin authentication and authorization.

2.3 Authorization

Roles:

CUSTOMER
DRIVER
ADMIN
SAFETY_ADMIN
FINANCE_ADMIN
SUPER_ADMIN

A user may access only resources they are authorized to access.

2.4 Server Authority

The server is authoritative for:

Fare

Wallet balance

Payment status

Ride state

Driver eligibility

GPS verification

Promotion usage

Penalties

The client must never be trusted for these values.

3. Standard Response Format

Successful response:

{
  "data": {},
  "error": null,
  "request_id": "req_123"
}

Error response:

{
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
  },
  "request_id": "req_123"
}

4. HTTP Status Codes

Use:

200 OK
201 Created
202 Accepted
204 No Content
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
422 Unprocessable Entity
429 Too Many Requests
500 Internal Server Error
502 Bad Gateway
503 Service Unavailable

5. Idempotency

The following operations require:

Idempotency-Key: <unique-key>

Required for:

Ride creation

Ride acceptance

Ride cancellation

Fare confirmation

Payment creation

Payment confirmation

Cash confirmation

Wallet recharge

Wallet debit/credit commands

Promotion usage

Promotion restoration

Referral reward

Penalty application

Refund requests

The server stores the key and operation result.

If the same key is reused with a different request body:

409 IDEMPOTENCY_KEY_REUSE

6. Authentication APIs

6.1 Request OTP

POST /api/v1/auth/otp/request

Request:

{
  "phone": "+919999999999",
  "account_type": "CUSTOMER"
}

Response:

{
  "data": {
    "challenge_id": "uuid",
    "expires_in": 300
  },
  "error": null,
  "request_id": "req_123"
}

7. Verify OTP

POST /api/v1/auth/otp/verify

Request:

{
  "challenge_id": "uuid",
  "otp": "123456"
}

Response:

{
  "data": {
    "access_token": "token",
    "refresh_token": "token",
    "expires_in": 3600
  },
  "error": null,
  "request_id": "req_124"
}

Errors:

OTP_INVALID
OTP_EXPIRED
OTP_MAX_ATTEMPTS
ACCOUNT_SUSPENDED

8. Customer Profile APIs

Get Profile

GET /api/v1/customers/me

Update Profile

PATCH /api/v1/customers/me

Request:

{
  "full_name": "Customer Name",
  "language": "en"
}

9. Driver Profile APIs

Get Driver Profile

GET /api/v1/drivers/me

Update Driver Profile

PATCH /api/v1/drivers/me

Submit Driver Document

POST /api/v1/drivers/me/documents

Request:

{
  "document_type": "DRIVING_LICENSE",
  "document_number": "XXXXXX",
  "evidence_uri": "uploaded-file-reference"
}

10. Driver Availability

Go Online

POST /api/v1/drivers/me/online

Server validates:

Driver approved
AND
Vehicle approved
AND
Vehicle active
AND
Required documents valid
AND
Driver not suspended

Response:

{
  "data": {
    "status": "ONLINE",
    "vehicle_id": "uuid"
  },
  "error": null,
  "request_id": "req_200"
}

Go Offline

POST /api/v1/drivers/me/offline

A driver with a pending ride offer must first reject or allow the request to expire.

A driver cannot go offline while an active ride is in progress.

11. Vehicle APIs

Add Vehicle

POST /api/v1/drivers/me/vehicles

Request:

{
  "category": "BIKE",
  "registration_number": "BR01AB1234",
  "make": "Example",
  "model": "Example"
}

List Vehicles

GET /api/v1/drivers/me/vehicles

Activate Vehicle

POST /api/v1/drivers/me/vehicles/{vehicle_id}/activate

Requirements:

Vehicle approved
AND
Driver OFFLINE

Deactivate Vehicle

POST /api/v1/drivers/me/vehicles/{vehicle_id}/deactivate

Vehicle switching is not allowed while ONLINE or ON_RIDE.

12. Ride Creation

Customer Requests Ride

POST /api/v1/rides

Headers:

Authorization: Bearer <token>
Idempotency-Key: <unique-key>

Request:

{
  "pickup": {
    "latitude": 25.5941,
    "longitude": 85.1376
  },
  "destination": {
    "latitude": 25.6120,
    "longitude": 85.1580
  },
  "vehicle_category": "CAB",
  "payment_method": "ONLINE"
}

Server performs:

Validate customer
→ Validate coordinates
→ Calculate fare
→ Apply eligible promotion
→ Create ride
→ Start matching

Response:

{
  "data": {
    "ride_id": "uuid",
    "status": "SEARCHING",
    "fare": {
      "base": 180,
      "discount": 20,
      "total": 160,
      "currency": "INR"
    }
  },
  "error": null,
  "request_id": "req_301"
}

The client-provided fare is ignored.

13. Get Ride

GET /api/v1/rides/{ride_id}

Customer may access their own ride.

Driver may access rides assigned to them.

Response:

{
  "data": {
    "ride_id": "uuid",
    "status": "ACCEPTED",
    "pickup": {},
    "destination": {},
    "driver": {},
    "vehicle": {},
    "fare": {},
    "payment": {}
  },
  "error": null,
  "request_id": "req_302"
}

14. Ride Tracking

GET /api/v1/rides/{ride_id}/tracking

Returns authorized real-time location data.

WebSocket:

wss://api.vistaar.example/api/v1/rides/{ride_id}/stream

The exact production host is TBD.

15. Driver Location Update

POST /api/v1/drivers/me/location

Request:

{
  "latitude": 25.5941,
  "longitude": 85.1376,
  "accuracy_meters": 8,
  "recorded_at": "2026-08-18T10:00:00Z"
}

Server validates:

Authenticated driver

Valid coordinates

Driver state

Timestamp sanity

Operational location is written to Redis GEO.

16. Ride Offer APIs

Get Current Offers

GET /api/v1/drivers/me/ride-offers

Accept Offer

POST /api/v1/drivers/me/ride-offers/{offer_id}/accept

Headers:

Idempotency-Key: <unique-key>

Server atomically validates:

Offer PENDING
AND
not expired
AND
Ride SEARCHING
AND
Driver eligible
AND
Vehicle eligible
AND
Wallet balance sufficient

Then:

Debit platform fee
→ Assign driver
→ Offer ACCEPTED
→ Ride ACCEPTED

Possible errors:

OFFER_EXPIRED
OFFER_ALREADY_RESPONDED
RIDE_ALREADY_ASSIGNED
DRIVER_NOT_ELIGIBLE
VEHICLE_NOT_ELIGIBLE
INSUFFICIENT_WALLET_BALANCE

Reject Offer

POST /api/v1/drivers/me/ride-offers/{offer_id}/reject

No platform fee is deducted.

17. Driver Arrival

POST /api/v1/rides/{ride_id}/arrived

Server verifies driver location against pickup radius.

Response:

{
  "data": {
    "status": "ARRIVED",
    "waiting_started_at": "timestamp"
  },
  "error": null,
  "request_id": "req_401"
}

If GPS verification fails:

NOT_WITHIN_PICKUP_RADIUS

18. Ride Start OTP

Generate/Refresh OTP

POST /api/v1/rides/{ride_id}/otp/refresh

Authorized driver/customer according to product flow.

Start Ride

POST /api/v1/rides/{ride_id}/start

Request:

{
  "otp": "123456"
}

Server validates:

Ride = ARRIVED
AND
OTP valid
AND
OTP not expired
AND
attempt limit not exceeded

Then:

Ride → STARTED

19. Customer Cancellation

POST /api/v1/rides/{ride_id}/cancel

Request:

{
  "reason": "CUSTOMER_CHANGED_PLANS"
}

Server determines:

2-minute grace
→ no charge

First qualifying cancellation
→ ₹0

Second+
→ ₹15

The client cannot choose the penalty amount.

Response:

{
  "data": {
    "ride_status": "CANCELLED",
    "charge": {
      "amount": 15,
      "currency": "INR",
      "expires_at": "timestamp"
    }
  },
  "error": null,
  "request_id": "req_500"
}

20. Driver Cancellation

POST /api/v1/rides/{ride_id}/driver-cancel

Request:

{
  "reason": "UNWILLING_TO_PROCEED"
}

Normal qualifying cancellation:

₹30 penalty
+
strike

Special changed-pickup pass:

{
  "reason": "CHANGED_PICKUP_OVER_250M"
}

This reason:

₹0 penalty
No strike
Rematch ride

21. No Driver Found

GET /api/v1/rides/{ride_id}/no-driver-options

Response:

{
  "data": {
    "options": [
      {
        "type": "RETRY"
      },
      {
        "type": "INCREASE_FARE",
        "amount": 10
      },
      {
        "type": "INCREASE_FARE",
        "amount": 20
      },
      {
        "type": "INCREASE_FARE",
        "amount": 40
      },
      {
        "type": "CUSTOM_INCREASE"
      }
    ]
  },
  "error": null,
  "request_id": "req_600"
}

Increase Fare

POST /api/v1/rides/{ride_id}/fare-increase

Request:

{
  "amount": 20
}

Server validates configured custom limits.

The increase belongs to the driver.

The normal platform fee remains applicable.

22. Pickup Change

POST /api/v1/rides/{ride_id}/pickup-change

Request:

{
  "latitude": 25.6000,
  "longitude": 85.1400
}

Server calculates distance.

≤250m

Change may proceed normally.

>250m

Driver receives:

PROCEED
PASS

23. Driver Pickup-Change Decision

POST /api/v1/rides/{ride_id}/pickup-change/driver-decision

Request:

{
  "decision": "PROCEED"
}

or:

{
  "decision": "PASS"
}

PASS result:

No ₹30 driver penalty
No strike
Ride rematched

PROCEED:

Pricing calculates additional charge
→ Customer must see charge
→ Customer confirms
→ Driver proceeds

24. Customer Pickup-Change Confirmation

POST /api/v1/rides/{ride_id}/pickup-change/confirm

Request:

{
  "confirmed": true
}

If false:

Changed pickup request cancelled

No charge is silently added.

25. Destination Change

POST /api/v1/rides/{ride_id}/destination-change

Request:

{
  "latitude": 25.6200,
  "longitude": 85.1700
}

Server determines:

Within original route
→ original fare

Beyond original destination
→ ₹8/km additional

Materially different route
→ recalculate from current location

If payable amount changes, customer confirmation is required.

26. Destination Change Confirmation

POST /api/v1/rides/{ride_id}/destination-change/confirm

Request:

{
  "change_request_id": "uuid",
  "confirmed": true
}

Response:

{
  "data": {
    "fare": {
      "previous_total": 250,
      "additional_charge": 40,
      "new_total": 290,
      "currency": "INR"
    }
  },
  "error": null,
  "request_id": "req_701"
}

27. Early Drop

Request

POST /api/v1/rides/{ride_id}/early-drop

Request:

{
  "reason": "CUSTOMER_REQUESTED"
}

Confirm

POST /api/v1/rides/{ride_id}/early-drop/confirm

Request:

{
  "confirmed": true
}

Server records:

GPS

Timestamp

Customer confirmation

Driver confirmation

The original fare remains payable under the approved rule.

28. Ride Completion

POST /api/v1/rides/{ride_id}/complete

Server verifies destination GPS.

If valid:

STARTED → COMPLETED

If invalid:

NOT_WITHIN_DESTINATION_RADIUS

29. Customer Payment

Create Payment

POST /api/v1/rides/{ride_id}/payment

Request:

{
  "method": "ONLINE"
}

Response:

{
  "data": {
    "payment_id": "uuid",
    "amount": 130,
    "currency": "INR",
    "gateway": {
      "provider": "TBD",
      "checkout_reference": "reference"
    }
  },
  "error": null,
  "request_id": "req_800"
}

30. Payment Breakdown

Before online payment, the customer must receive:

{
  "data": {
    "ride_fare": 100,
    "vistaar_charges": 30,
    "discount": 0,
    "total": 130,
    "currency": "INR"
  },
  "error": null,
  "request_id": "req_801"
}

31. Payment Gateway Webhook

Internal endpoint:

POST /api/v1/payments/webhooks/{provider}

Authentication:

Provider signature

Provider event ID

The webhook must be idempotent.

The client must never mark a payment successful by itself.

32. Offline Payment

Get Cash Requirement

GET /api/v1/rides/{ride_id}/cash-payment

Response:

{
  "data": {
    "ride_fare": 100,
    "vistaar_charges": 30,
    "total_cash_required": 130,
    "currency": "INR"
  },
  "error": null,
  "request_id": "req_810"
}

33. Driver Confirms Cash Payment

POST /api/v1/rides/{ride_id}/cash-payment/confirm

Headers:

Idempotency-Key: <unique-key>

Request:

{
  "confirmed_amount": 130
}

Server obtains authoritative expected amount.

Validation:

confirmed_amount == expected_amount

If not:

409 FULL_PAYMENT_NOT_RECEIVED

If valid:

Payment → CONFIRMED
→ Create VISTAAR settlement
→ Debit driver wallet

34. Wallet

Get Wallet

GET /api/v1/drivers/me/wallet

Response:

{
  "data": {
    "balance": 170,
    "currency": "INR",
    "outstanding_settlement": 30
  },
  "error": null,
  "request_id": "req_900"
}

Wallet Transactions

GET /api/v1/drivers/me/wallet/transactions

Query:

?page=1
&page_size=20
&type=PLATFORM_FEE

35. Wallet Recharge

POST /api/v1/drivers/me/wallet/recharge

Request:

{
  "amount": 200,
  "payment_method": "UPI"
}

Validation:

amount >= ₹200

The wallet is credited only after successful payment verification.

36. Outstanding Cash Settlement

GET /api/v1/drivers/me/wallet/outstanding-settlements

Response:

{
  "data": {
    "total_outstanding": 30,
    "items": [
      {
        "id": "uuid",
        "amount": 30,
        "reason": "CASH_SETTLEMENT",
        "status": "OPEN"
      }
    ]
  },
  "error": null,
  "request_id": "req_910"
}

37. Promotions

Get Promotions

GET /api/v1/customers/me/promotions

Response:

{
  "data": {
    "promotions": [
      {
        "type": "WELCOME",
        "discount_percent": 50,
        "remaining_uses": 2,
        "expires_at": "timestamp"
      }
    ]
  },
  "error": null,
  "request_id": "req_1000"
}

38. Referral

Get Referral Code

GET /api/v1/customers/me/referral

Attach Referral

POST /api/v1/referrals/attach

Request:

{
  "code": "ABC123"
}

Referral activation must happen only once.

39. Parking Proof

POST /api/v1/rides/{ride_id}/parking-proof

Request:

{
  "evidence_uri": "uploaded-file-reference"
}

Response:

{
  "data": {
    "verification_status": "PENDING"
  },
  "error": null,
  "request_id": "req_1100"
}

Verification results may be:

APPROVED
REJECTED
MANUAL_REVIEW

40. Rating

POST /api/v1/rides/{ride_id}/rating

Request:

{
  "rating": 5,
  "comment": "Good ride"
}

Validation:

rating >= 1
rating <= 5

A user cannot submit multiple ratings for the same ride and role.

41. SOS

POST /api/v1/rides/{ride_id}/sos

Request:

{
  "incident_type": "EMERGENCY",
  "latitude": 25.5941,
  "longitude": 85.1376
}

Response:

{
  "data": {
    "incident_id": "uuid",
    "status": "OPEN"
  },
  "error": null,
  "request_id": "req_1200"
}

42. Ride Sharing

POST /api/v1/rides/{ride_id}/share

Response:

{
  "data": {
    "share_token": "token",
    "expires_at": "timestamp"
  },
  "error": null,
  "request_id": "req_1210"
}

The share token must expire.

43. Lost and Found

Report Lost Item

POST /api/v1/rides/{ride_id}/lost-item

Request:

{
  "description": "Black wallet"
}

Get Case

GET /api/v1/lost-items/{case_id}

44. Support

Create Support Case

POST /api/v1/support/cases

Request:

{
  "category": "PAYMENT",
  "ride_id": "uuid",
  "message": "Payment issue"
}

Get Support Case

GET /api/v1/support/cases/{case_id}

45. AI Support

POST /api/v1/support/ai/message

Request:

{
  "message": "Why was I charged ₹30?",
  "ride_id": "uuid"
}

AI may read authorized information.

Restricted financial actions require explicit authorization.

Possible response:

{
  "data": {
    "message": "The ₹30 charge is your no-show charge.",
    "confidence": 0.91,
    "escalation_required": false
  },
  "error": null,
  "request_id": "req_1300"
}

46. Admin APIs

Admin APIs require role authorization.

Search Rides

GET /api/v1/admin/rides

Query:

?status=COMPLETED
&driver_id=uuid
&customer_id=uuid
&page=1
&page_size=50

Get Ride

GET /api/v1/admin/rides/{ride_id}

Driver Review

GET /api/v1/admin/drivers/{driver_id}

Approve Driver

POST /api/v1/admin/drivers/{driver_id}/approve

Approve Vehicle

POST /api/v1/admin/vehicles/{vehicle_id}/approve

Every admin mutation creates an audit log.

47. Admin Financial Review

GET /api/v1/admin/wallets/{driver_id}
GET /api/v1/admin/payments/{payment_id}
GET /api/v1/admin/settlements

Admin cannot silently edit historical financial transactions.

Corrections must create compensating transactions.

48. Admin Penalty Review

GET /api/v1/admin/penalties
POST /api/v1/admin/penalties/{penalty_id}/resolve

Resolution requires:

{
  "action": "WAIVE",
  "reason": "Verified system error"
}

The original penalty remains immutable.

A reversal/waiver record is created.

49. Error Codes

Core errors:

AUTH_REQUIRED
AUTH_INVALID
FORBIDDEN
RESOURCE_NOT_FOUND

INVALID_REQUEST
VALIDATION_FAILED
INVALID_STATE_TRANSITION

RIDE_NOT_FOUND
RIDE_ALREADY_ASSIGNED
RIDE_NOT_CANCELLABLE
RIDE_NOT_COMPLETABLE

OFFER_EXPIRED
OFFER_ALREADY_RESPONDED

DRIVER_NOT_ELIGIBLE
VEHICLE_NOT_ELIGIBLE
DRIVER_NOT_ONLINE

INSUFFICIENT_WALLET_BALANCE
WALLET_TRANSACTION_FAILED

PAYMENT_REQUIRED
PAYMENT_FAILED
PAYMENT_ALREADY_CONFIRMED
FULL_PAYMENT_NOT_RECEIVED

FARE_CONFIRMATION_REQUIRED
FARE_CHANGED
PROMOTION_EXPIRED
PROMOTION_ALREADY_USED

REFERRAL_INVALID
REFERRAL_ALREADY_ATTACHED

PENALTY_ALREADY_APPLIED
PENALTY_EXPIRED

GPS_VERIFICATION_FAILED
NOT_WITHIN_PICKUP_RADIUS
NOT_WITHIN_DESTINATION_RADIUS

OTP_INVALID
OTP_EXPIRED
OTP_MAX_ATTEMPTS

IDEMPOTENCY_KEY_REUSE
RATE_LIMITED

SAFETY_INCIDENT_ERROR
SUPPORT_ESCALATION_REQUIRED

50. Pagination

List endpoints use:

?page=1&page_size=20

Response:

{
  "data": {
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 100,
      "total_pages": 5
    }
  },
  "error": null,
  "request_id": "req_1400"
}

Maximum page size should be server-configured.

51. Filtering and Sorting

Filtering must use allow-listed fields.

Example:

GET /api/v1/admin/rides?
status=COMPLETED
&vehicle_category=CAB
&created_from=...
&created_to=...

Clients cannot inject arbitrary SQL fields into sorting/filtering.

52. Rate Limiting

Rate limits should apply to:

OTP requests

Login attempts

Ride creation

Ride cancellation

Fare increase

Support messages

SOS endpoints

Admin endpoints

Payment endpoints

SOS must receive priority handling and should not be blocked by normal application rate limits.

53. API Security

All production APIs require HTTPS.

Sensitive headers:

Authorization
Idempotency-Key
X-Request-ID

Never log:

OTP

Payment secrets

Access tokens

Full card information

Sensitive identity documents

54. Request IDs

Every request receives:

X-Request-ID

If supplied by the client, validate and propagate it.

Request IDs must appear in:

Logs

Error responses

Audit records

Relevant events

55. Internal Domain APIs

Internal services use explicit commands.

Examples:

POST /internal/wallet/debit
POST /internal/wallet/credit
POST /internal/pricing/calculate
POST /internal/penalties/apply
POST /internal/promotions/reserve
POST /internal/promotions/restore
POST /internal/referrals/qualify

Internal endpoints require service authentication.

They must not be publicly exposed.

56. Internal Wallet Debit

POST /internal/wallet/debit

Request:

{
  "driver_id": "uuid",
  "amount": 20,
  "transaction_type": "PLATFORM_FEE",
  "ride_id": "uuid",
  "idempotency_key": "ride:uuid:platform-fee"
}

Wallet service validates and atomically debits.

57. Internal Wallet Credit

POST /internal/wallet/credit

Request:

{
  "driver_id": "uuid",
  "amount": 100,
  "transaction_type": "JOINING_BONUS",
  "idempotency_key": "joining-bonus:driver-uuid"
}

58. Internal Pricing

POST /internal/pricing/fare

Request:

{
  "ride_id": "uuid",
  "vehicle_category": "CAB",
  "pickup": {},
  "destination": {},
  "context": {}
}

Response:

{
  "data": {
    "fare_quote_id": "uuid",
    "version": 1,
    "total": 250,
    "currency": "INR"
  },
  "error": null,
  "request_id": "req_internal"
}

59. API State Transition Rules

The API must reject invalid transitions.

Examples:

SEARCHING → STARTED

is invalid.

ARRIVED → ACCEPTED

is invalid.

COMPLETED → STARTED

is invalid.

The server checks the current authoritative state before every transition.

60. Payment State Rules

Example:

PENDING
  ↓
PROCESSING
  ↓
SUCCEEDED
  ↓
SETTLED

Failure:

PENDING
  ↓
FAILED

A successful payment cannot be changed back to pending by a client request.

61. Offline Payment State Rules

EXPECTED
 ↓
DRIVER_CONFIRMING
 ↓
CONFIRMED
 ↓
SETTLEMENT_PENDING
 ↓
SETTLED

If full amount was not received:

DRIVER_CONFIRMING
 ↓
REJECTED

The driver must not confirm partial payment through the full-payment endpoint.

62. Fare Confirmation Rules

A customer must confirm a fare change when required by business rules.

Example:

Current total = ₹250
New total = ₹290

API response:

FARE_CONFIRMATION_REQUIRED

The system must not silently charge ₹290.

63. Client Responsibilities

Client applications should:

Display authoritative server data

Show loading states

Retry safe requests

Use idempotency keys

Handle expired sessions

Handle state changes received over WebSocket

Show required fare/payment confirmations

Client applications must not:

Calculate final payable amounts as authoritative

Modify wallet balances

Mark payment successful

Mark ride completed without server verification

Decide penalty amounts

64. WebSocket Events

Ride stream may publish:

DRIVER_LOCATION_UPDATED
RIDE_STATUS_CHANGED
DRIVER_ASSIGNED
DRIVER_ARRIVED
FARE_CHANGED
PAYMENT_STATUS_CHANGED
SAFETY_ALERT

WebSocket events are notifications.

The REST API remains authoritative for state retrieval.

65. API Retry Rules

Safe retries:

GET

Mutation retries require idempotency.

For example:

POST payment

must use the same idempotency key when retried.

Do not generate a new key for every retry of the same logical operation.

66. API Observability

Every request should record:

request_id
user_id
endpoint
method
status_code
latency
service
error_code

Financial endpoints additionally record:

idempotency_key
transaction_id
payment_id
wallet_transaction_id

Never log sensitive credentials.

67. API Contract Testing

Every endpoint requires:

Request validation tests

Authorization tests

State transition tests

Idempotency tests

Error tests

Concurrency tests where applicable

Contract tests between services

Critical flows:

Ride acceptance
Payment
Cash confirmation
Wallet recharge
Promotion usage
Referral reward
Penalty application
Fare change

68. End-to-End Ride API Flow

POST /rides
       ↓
SEARCHING
       ↓
Matching
       ↓
Driver offer
       ↓
POST /ride-offers/{id}/accept
       ↓
ACCEPTED
       ↓
POST /rides/{id}/arrived
       ↓
ARRIVED
       ↓
POST /rides/{id}/start
       ↓
STARTED
       ↓
Optional:
pickup change
destination change
early drop
       ↓
POST /rides/{id}/complete
       ↓
COMPLETED
       ↓
Payment
       ↓
CLOSED
       ↓
Rating

69. Critical Payment Flow

Online

POST /rides/{id}/payment
       ↓
Payment Gateway
       ↓
Webhook
       ↓
Payment SUCCEEDED
       ↓
Allocation
       ↓
Settlement
       ↓
Payment CONFIRMED

Offline

GET /rides/{id}/cash-payment
       ↓
Customer pays driver
       ↓
POST /rides/{id}/cash-payment/confirm
       ↓
Expected amount validation
       ↓
Payment CONFIRMED
       ↓
VISTAAR settlement
       ↓
Wallet debit

70. Critical Pickup Change Flow

POST /rides/{id}/pickup-change
       ↓
Calculate distance
       ↓
≤250m?
 ├── YES → normal change
 └── NO
      ↓
Driver decision
 ├── PASS
 │    ↓
 │  Rematch
 │
 └── PROCEED
      ↓
Pricing
      ↓
Customer confirmation
      ↓
Apply change

71. Critical Destination Change Flow

POST /rides/{id}/destination-change
       ↓
Calculate route/fare
       ↓
No fare increase?
 ├── YES → apply
 └── NO
      ↓
Customer confirmation
      ↓
Apply new fare

72. Critical Promotion Flow

Ride creation
 ↓
Promotion eligibility
 ↓
Reserve entitlement
 ↓
Fare quote
 ↓
Ride outcome
 ├── qualifying early cancellation → restore
 ├── late cancellation → consume
 └── completed ride → consume

73. API Documentation Format

Implementation should generate OpenAPI documentation.

Recommended:

docs/06-api/openapi.yaml

This document remains the human-readable contract.

The OpenAPI specification should be generated/maintained from the same approved contract and must not contradict it.

74. API Naming Rules

Use nouns for resources:

/rides
/drivers
/vehicles
/wallet
/payments
/promotions
/referrals

Use explicit action endpoints only when a domain command is clearer:

/rides/{id}/start
/rides/{id}/complete
/rides/{id}/cancel

Avoid ambiguous endpoints such as:

/doRide
/processThing
/updateStatus

75. API Contract Invariants

Server owns business state.

Client cannot set final fare.

Client cannot set wallet balance.

Client cannot confirm a payment without server verification.

Driver cash confirmation must match the authoritative expected amount.

Fare increases requiring confirmation cannot be silently applied.

Ride transitions must be valid.

Financial mutations require idempotency.

Admin financial corrections use compensating records.

Internal APIs are authenticated and not public.

76. Open API Decisions

The following remain TBD:

Final authentication provider.

Payment gateway.

Payout/settlement provider.

Notification provider.

Production API hostname.

Exact rate limits.

Exact GPS radius values.

Exact fare-rule fields.

Final admin role matrix.

Final WebSocket provider/implementation.

API gateway/load-balancer choice.

Public vs internal service deployment topology.

77. Next Document

Document chain (corrected to match actual repository folder names — see docs/14-decisions/ for the numbering-reconciliation record):

05-api/api-contracts.md   ← THIS
        ↓
06-events/event-contracts.md
        ↓
07-state-machines/state-machines.md
        ↓
08-security/security.md
        ↓
10-testing/testing-strategy.md
        ↓
Implementation

docs/09-errors/ is a reserved, currently-empty folder for a future error-catalog document; it is not yet part of this chain.

78. Document Status

Version: 1.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, Domain Design v1.0, Database Design v1.0