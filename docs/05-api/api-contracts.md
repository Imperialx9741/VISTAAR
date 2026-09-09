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

Response (an account with no ACTIVE MFA credential — every customer/
driver, and every admin who hasn't enrolled — unchanged from before
ADR-0051):

{
  "data": {
    "access_token": "token",
    "refresh_token": "token",
    "expires_in": 3600
  },
  "error": null,
  "request_id": "req_124"
}

Response (ADR-0051, 2026-08-28 — an account WITH an ACTIVE MFA
credential gets this instead, never a real token pair):

{
  "data": {
    "mfa_required": true,
    "mfa_token": "token",
    "expires_in": 300
  },
  "error": null,
  "request_id": "req_124"
}

mfa_token is a distinct, short-lived (5 minute) JWT — it cannot be used
as a bearer access token against any other endpoint (rejected by its
`purpose` claim). Present it to §7.3's Verify MFA endpoint instead.

Errors:

OTP_INVALID
OTP_EXPIRED
OTP_MAX_ATTEMPTS
ACCOUNT_SUSPENDED

7.1 Refresh Token

Added in Phase 2 / Task 2.1 (Identity & Authentication Foundation), per
docs/04-domain-design/domain-design.md §5.3's RefreshSession command and
docs/08-security/security.md §6 ("Refresh tokens must be ... Rotated
where supported").

POST /api/v1/auth/refresh

Request:

{
  "refresh_token": "token"
}

Response: same shape as 7. Verify OTP's response (a new access_token +
refresh_token pair). The refresh token is single-use: a successful refresh
rotates it, and the old refresh token becomes invalid immediately.

Errors:

AUTH_INVALID (refresh token invalid, revoked, or already rotated)
ACCOUNT_SUSPENDED

7.2 Logout

Added in the same change, per domain-design.md §5.3's Logout command and
security.md §6 ("Refresh tokens must be ... Revoked on account
compromise").

POST /api/v1/auth/logout

Headers:

Authorization: Bearer <access-token>

Request:

{
  "refresh_token": "token"
}

refresh_token is optional — omitting it revokes only the access token
(via a denylist keyed on its jti until natural expiry); providing it also
revokes that refresh-token-backed session.

Response:

{
  "data": {"status": "LOGGED_OUT"},
  "error": null,
  "request_id": "req_125"
}

7.3 Admin MFA (ADR-0051, 2026-08-28)

A generic identity-layer capability (any account type could enroll —
see the ADR's Decision 1) gated to ADMIN accounts only at the router
layer, since that's the only account type asked for. Enroll/Confirm/
Disable require a real bearer access token (an already-authenticated
admin managing their own second factor); Verify is the one exception —
it's part of the login flow itself and takes the short-lived mfa_token
from §7 instead of a bearer token.

Enroll

POST /api/v1/auth/mfa/enroll

Headers: Authorization: Bearer <access-token> (ADMIN account)

Response:

{
  "data": {
    "secret": "base32string",
    "otpauth_uri": "otpauth://totp/VISTAAR:+91...?secret=...&issuer=VISTAAR"
  },
  "error": null,
  "request_id": "req_126"
}

Generates a new PENDING secret — render otpauth_uri as a QR code for an
authenticator app to scan (or let the admin type `secret` in manually).
Calling this again before confirming replaces the PENDING secret.
Rejected (INVALID_STATE_TRANSITION) if this account already has an
ACTIVE credential — disable it first (which itself requires a valid
current code), so a bearer token alone can never downgrade existing MFA
protection.

Confirm

POST /api/v1/auth/mfa/confirm

Headers: Authorization: Bearer <access-token>

Request:

{"code": "123456"}

Response:

{"data": {"status": "ACTIVE"}, "error": null, "request_id": "req_127"}

PENDING -> ACTIVE, once the admin proves they recorded the secret
correctly by producing a real code from it. From this point, this
account's login requires the Verify step below.

Errors: RESOURCE_NOT_FOUND (nothing enrolled), INVALID_STATE_TRANSITION
(already ACTIVE), OTP_INVALID (wrong code).

Verify

POST /api/v1/auth/mfa/verify

No Authorization header — mfa_token itself is the proof the first
factor already succeeded.

Request:

{"mfa_token": "token", "code": "123456"}

Response: same shape as §7's normal token-pair response.

Errors: AUTH_INVALID (mfa_token invalid/expired), OTP_INVALID (wrong
code), ACCOUNT_SUSPENDED.

Disable

POST /api/v1/auth/mfa/disable

Headers: Authorization: Bearer <access-token>

Request:

{"code": "123456"}

Response:

{"data": {"status": "DISABLED"}, "error": null, "request_id": "req_128"}

Requires a valid current code, not just a bearer token — proves the
caller still holds the second factor before removing it.

Errors: RESOURCE_NOT_FOUND (nothing enrolled), OTP_INVALID (wrong code).

8. Customer Profile APIs

Implemented in Phase 2 / Task 2.2. A customer.customers +
customer.preferences row is auto-provisioned on first access by either
endpoint below — there is no separate creation endpoint.

Get Profile

GET /api/v1/customers/me

Update Profile

PATCH /api/v1/customers/me

Request (all fields optional — PATCH semantics; an omitted field is left
unchanged, a field explicitly sent as null clears it where nullable):

{
  "full_name": "Customer Name",
  "profile_photo_uri": "uploaded-file-reference",
  "language": "en",
  "notification_enabled": true
}

Response (both Get and Update):

{
  "data": {
    "customer_id": "uuid",
    "phone": "+919999999999",
    "full_name": "Customer Name",
    "profile_photo_uri": null,
    "language": "en",
    "notification_enabled": true,
    "status": "ACTIVE",
    "created_at": "timestamp",
    "updated_at": "timestamp"
  },
  "error": null,
  "request_id": "req_126"
}

language is restricted to {"en", "hi"} per PRD.md §6's initially supported
languages — an application-layer allow-list, not a database constraint,
so adding a language later does not require a migration.

Errors:

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-CUSTOMER account type)
VALIDATION_FAILED

9. Driver Profile APIs

Get Driver Profile and Update Driver Profile implemented in Phase 2 /
Task 2.3. Submit Driver Document implemented in Phase 2 / Task 2.5
(record-keeping only — document verification/approval is a later task).

Driver document retrieval (List My Driver Documents, below) and vehicle-
document endpoints (§11) are IMPLEMENTED — ADR-0072, 2026-09-04, closing
the gap ADR-0007-document-type-and-endpoint-scope.md originally left
open. Neither invents a document_type vocabulary or a replacement/
versioning policy — both remain open per ADR-0007 item A and item B's
second half.

Get Driver Profile

GET /api/v1/drivers/me

Unlike GET /api/v1/customers/me, this does not auto-provision: it
returns RESOURCE_NOT_FOUND if no driver profile exists yet for the
authenticated driver account. driver.drivers.full_name is NOT NULL
(database-design.md §7.1) and identity.accounts has no name field to
default from, so there is no value this endpoint could return before the
driver has supplied one via Update Driver Profile. This creation
mechanism is formally recorded as an implementation/API decision (not a
business rule) in docs/14-decisions/ADR-0004-driver-profile-creation-semantics.md
— see that ADR before adding a dedicated registration endpoint.

Update Driver Profile

PATCH /api/v1/drivers/me

Request (full_name required only on the first call for a given driver
account, to create the profile; optional thereafter — PATCH semantics,
an omitted field is left unchanged):

{
  "full_name": "Driver Name",
  "profile_photo_uri": "uploaded-file-reference"
}

Response (both Get and Update):

{
  "data": {
    "driver_id": "uuid",
    "phone": "+919999999999",
    "full_name": "Driver Name",
    "profile_photo_uri": null,
    "verification_status": "PENDING",
    "operational_status": "OFFLINE",
    "strikes": 0,
    "created_at": "timestamp",
    "updated_at": "timestamp"
  },
  "error": null,
  "request_id": "req_127"
}

verification_status, operational_status, and strikes are server-controlled
and read-only through this endpoint — they cannot be set via the request
body. Nothing in Phase 2 / Task 2.3 transitions them away from their
documented defaults; ApproveDriver/RejectDriver (admin approval),
GoOnline/GoOffline (driver availability), and RecordDriverStrike
(penalty) are later tasks' responsibility (domain-design.md §7.4).

Errors:

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-DRIVER account type)
RESOURCE_NOT_FOUND (Get, before any profile has been created)
VALIDATION_FAILED (including: full_name missing on first-ever Update)

Submit Driver Document

POST /api/v1/drivers/me/documents

Request (document_type is validated as a non-blank string up to 40
characters, normalized to uppercase — there is no canonical
document_type vocabulary yet; see ADR-0007. document_number and
evidence_uri are optional; expires_at is optional and stored as-is with
no expiry processing attached):

{
  "document_type": "DRIVING_LICENSE",
  "document_number": "XXXXXX",
  "evidence_uri": "uploaded-file-reference",
  "expires_at": "2028-01-01T00:00:00Z"
}

Response (verification_case_id added in Phase 2 / Task 2.6 — see below):

{
  "data": {
    "document_id": "uuid",
    "document_type": "DRIVING_LICENSE",
    "document_number": "XXXXXX",
    "evidence_uri": "uploaded-file-reference",
    "verification_status": "PENDING",
    "expires_at": "2028-01-01T00:00:00Z",
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "verification_case_id": "uuid"
  },
  "error": null,
  "request_id": "req_128"
}

Each submission creates a new, independent document record — resubmitting
the same document_type does not replace or supersede a prior record (no
versioning/replacement policy is documented; see ADR-0007).
verification_status is always PENDING on creation and is server-controlled
— nothing in Phase 2 / Task 2.5 transitions it.

verification_case_id (Phase 2 / Task 2.6): non-null only when
evidence_uri was supplied in the request — submitting evidence creates a
verification.cases row (SubmitEvidence) in the documented PENDING state.
If evidence_uri is omitted, verification_case_id is null and no
verification case is created — no placeholder evidence is invented to
force one into existence (verification.evidence.evidence_uri is NOT
NULL; document_type submission itself never requires evidence_uri). A
verification case existing is not a verification outcome: nothing in
Phase 2 / Task 2.6 transitions the case away from PENDING, and nothing
writes the case's eventual outcome back onto this response's
verification_status — the two are intentionally separate, unreconciled
status systems (see docs/14-decisions/ADR-0008-verification-case-scope-and-open-items.md,
items 5 and 9).

Errors:

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-DRIVER account type)
RESOURCE_NOT_FOUND (no driver profile exists yet — call
PATCH /api/v1/drivers/me first)
VALIDATION_FAILED

List My Driver Documents (IMPLEMENTED — ADR-0072, 2026-09-04)

GET /api/v1/drivers/me/documents

Every document the caller has ever submitted, newest first — no
filtering, no pagination (a driver's own document count is small and
bounded). Same per-item shape as Submit Driver Document's own response
above, except `verification_case_id` is always null (a list read has
no single submission event to report one against):

{
  "data": {
    "documents": [
      {
        "document_id": "uuid",
        "document_type": "DRIVING_LICENSE",
        "document_number": "XXXXXX",
        "evidence_uri": "uploaded-file-reference",
        "verification_status": "PENDING",
        "expires_at": "2028-01-01T00:00:00Z",
        "created_at": "timestamp",
        "updated_at": "timestamp",
        "verification_case_id": null
      }
    ]
  },
  "error": null,
  "request_id": "req_130"
}

Errors:

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-DRIVER account type)

List My Strikes (IMPLEMENTED — ADR-0073, 2026-09-04)

GET /api/v1/drivers/me/strikes?page=&page_size=

The caller's own strikes, newest first, paginated (§50's shared
pagination shape) — the self-service counterpart to §46.18's admin-only
Driver Strike History, scoped to the caller instead of an admin-supplied
driver_id. Same item shape as that admin route:

{
  "data": {
    "items": [
      {
        "strike_id": "uuid",
        "driver_id": "uuid",
        "ride_id": "uuid",
        "reason": "DRIVER_CANCELLATION",
        "created_at": "timestamp"
      }
    ],
    "pagination": {...}
  },
  "error": null,
  "request_id": "req_131"
}

`driver.drivers.strikes` (the existing bare counter, already returned
on Get My Profile above) remains the at-a-glance summary; this is the
underlying detail view. Immutable by construction (no update/delete
path exists for a strike). Errors:

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-DRIVER account type)
RESOURCE_NOT_FOUND (no driver profile created yet)

Request Upload URL

POST /api/v1/drivers/me/uploads

Implementation status (ADR-0031, 2026-08-25; upload mechanism updated to
presigned POST by ADR-0065, 2026-09-03): COMPLETE. Fills the gap
"uploaded-file-reference" above always stood in for — neither this
endpoint's request/response bodies existed before, nor did any
canonical document ever specify how a client obtains a real
evidence_uri/profile_photo_uri. Driver-only, no driver profile required
to exist yet (a photo/document may be uploaded before the first PATCH
/me call that references it).

Request:

{
  "content_type": "image/jpeg"
}

`content_type` must be one of `image/jpeg`, `image/png`, `image/webp`,
`application/pdf` — VALIDATION_FAILED otherwise.

Response:

{
  "data": {
    "upload_url": "https://vistaar-storage.s3.ap-south-1.amazonaws.com/",
    "upload_fields": {
      "key": "driver-uploads/<uuid>.jpg",
      "Content-Type": "image/jpeg",
      "policy": "<base64>",
      "x-amz-algorithm": "AWS4-HMAC-SHA256",
      "x-amz-credential": "...",
      "x-amz-date": "...",
      "x-amz-signature": "..."
    },
    "uri": "s3://vistaar-storage/driver-uploads/<uuid>.jpg",
    "expires_at": "timestamp"
  },
  "error": null,
  "request_id": "req_129"
}

**Presigned POST, not PUT (ADR-0065, 2026-09-03)** — the client submits
a standard multipart form POST directly to `upload_url`, with every key
in `upload_fields` included as a form field, and the file itself as the
**last** field in the form (S3's own requirement for a POST upload;
fields after the file are ignored). This is a real security fix, not a
naming change: S3 itself enforces a `content-length-range` (max 10 MB),
an exact `Content-Type` match, and the exact `key` — all embedded in the
signed `policy` field — so an oversized upload, a mismatched content
type, or an attempt to upload under a different key are all rejected by
S3, not merely undocumented. Valid for 5 minutes. The file's bytes never
pass through this application server. `uri` is then supplied as-is as
`evidence_uri` (Submit Driver Document, above) or `profile_photo_uri`
(Update Driver Profile) — neither of those two request bodies changes
shape. See ADR-0065 for the full design (including what security.md
§16-17's evidence-security controls this presigned-upload pattern can
and cannot enforce).

Errors:

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-DRIVER account type)
VALIDATION_FAILED (unsupported content_type)

10. Driver Availability

Implemented in Phase 2 / Task 2.7B. Both endpoints only ever transition
driver.drivers.operational_status between OFFLINE and ONLINE
(database-design.md §7.1) — see
docs/07-state-machines/state-machines.md §67 for the full state
picture (ON_RIDE, SUSPENDED, and INELIGIBLE remain untransitioned by
this task; see below).

Go Online

POST /api/v1/drivers/me/online

Server validates, in order:

Driver currently OFFLINE
AND
Driver approved
AND
Driver's own required documents valid (business-rules.md BR-123)
AND
Vehicle approved
AND
Vehicle active
AND
That vehicle's required documents valid (BR-123)

("Required documents valid" is checked separately for the driver and for
the vehicle — each against its own BR-123 required set,
modules.driver/vehicle.domain.required_documents — since either can
regress independently, e.g. a vehicle document expiring after the
vehicle was already approved.)

Response:

{
  "data": {
    "status": "ONLINE",
    "vehicle_id": "uuid"
  },
  "error": null,
  "request_id": "req_200"
}

"Driver not suspended" is not separately checked: SUSPENDED
(domain-design.md §7.3) is only reachable via SuspendDriver
(§7.4), an Admin-domain command not yet implemented
(state-machines.md §67) — the precondition holds by construction until
that command exists, so implementing an explicit check now would be
unreachable dead code, not a stronger guarantee.

Go Offline

POST /api/v1/drivers/me/offline

Response:

{
  "data": {
    "status": "OFFLINE"
  },
  "error": null,
  "request_id": "req_201"
}

Requires the driver to currently be ONLINE. A driver with a pending ride
offer must first reject or allow the request to expire, and a driver
cannot go offline while an active ride is in progress — both rules are
enforced by this same "must currently be ONLINE" check today, returning
DRIVER_NOT_ONLINE identically whether the driver is already OFFLINE or is
ON_RIDE. This codebase has no ride/offer model yet (Phase 3), so there is
nothing to distinguish "cancel my active ride to go offline" from "I'm
already offline" — collapsing the two is a scope limitation tracked as a
Phase 3 dependency (give ON_RIDE its own, more specific error or
release-the-ride flow once rides exist), not a business-rule decision
made here.

Concurrency: both endpoints lock the driver's row (SELECT ... FOR UPDATE)
before checking or writing operational_status, serializing concurrent Go
Online/Go Offline calls for the same driver — same mechanism as Activate
Vehicle's row locking (§11, database-design.md §8.1.1).

Errors (Go Online/Go Offline):

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-DRIVER account type)
RESOURCE_NOT_FOUND (no driver profile exists yet)
INVALID_STATE_TRANSITION (Go Online, driver not currently OFFLINE)
DRIVER_NOT_ELIGIBLE (Go Online: driver not approved; or driver's/
  vehicle's required documents not valid; or no approved+active vehicle)
DRIVER_NOT_ONLINE (Go Offline, driver not currently ONLINE — covers
  "already offline" and "on a ride" identically, see above)

11. Vehicle APIs

Add/List/Activate/Deactivate implemented in Phase 2 / Task 2.4. Get
Single Vehicle and Update Vehicle added by the subsequent Vehicle
Lifecycle Decision & API Contract Clarification task
(docs/14-decisions/ADR-0006-vehicle-lifecycle-single-active-vehicle.md).

Add Vehicle

POST /api/v1/drivers/me/vehicles

Requires the caller's own driver profile (GET/PATCH
/api/v1/drivers/me, §9) to already exist — vehicle.vehicles.driver_id
has a foreign key to driver.drivers.id (database-design.md §8.1).

Request:

{
  "category": "BIKE",
  "cab_tier": null,
  "registration_number": "BR01AB1234",
  "make": "Example",
  "model": "Example"
}

Response (201 Created):

{
  "data": {
    "vehicle_id": "uuid",
    "category": "BIKE",
    "cab_tier": null,
    "registration_number": "BR01AB1234",
    "make": "Example",
    "model": "Example",
    "verification_status": "PENDING",
    "operational_status": "INACTIVE",
    "created_at": "timestamp",
    "updated_at": "timestamp"
  },
  "error": null,
  "request_id": "req_128"
}

verification_status and operational_status are server-controlled and
always start at their documented defaults — this endpoint accepts no
field for either. registration_number must be globally unique
(database-design.md §8.1).

cab_tier (added 2026-08-24, ADR-0020 Decision 1) is required — one of
"ECO"/"PREMIUM"/"PREMIUM_PLUS" — when category is "CAB", and must be
omitted/null for every other category; VALIDATION_FAILED otherwise.
Self-declared by the driver, the same mechanism category itself uses.

List Vehicles

GET /api/v1/drivers/me/vehicles

Response:

{
  "data": {"vehicles": [ /* zero or more objects shaped as above */ ]},
  "error": null,
  "request_id": "req_129"
}

Returns only the authenticated driver's own vehicles. A driver may have
any number of vehicles (business-rules.md BR-099/BR-100) — no maximum is
enforced.

Get Single Vehicle

GET /api/v1/drivers/me/vehicles/{vehicle_id}

Response: a single object shaped as in Add Vehicle's response above.
Returns RESOURCE_NOT_FOUND if the vehicle does not exist or belongs to a
different driver (same response for both — see Errors below).

Update Vehicle

PATCH /api/v1/drivers/me/vehicles/{vehicle_id}

Request (both fields optional — PATCH semantics; an omitted field is left
unchanged):

{
  "make": "Example",
  "model": "Example"
}

Only make and model are editable. category and registration_number are
not accepted by this endpoint — changing either is a materially
different vehicle-identity change (and, once document verification
exists, would invalidate that vehicle's verification), not a profile
edit; there is no documented flow for it, so business-rules.md
BR-099/BR-100's "add another vehicle" remains the only supported path for
a different category or registration number. driver_id,
verification_status, operational_status, and the timestamps are
server-controlled and likewise not accepted.

Activate Vehicle

POST /api/v1/drivers/me/vehicles/{vehicle_id}/activate

Requirements:

Vehicle approved
AND
Driver OFFLINE

APPROVED (business-rules.md BR-122): activating this vehicle
deactivates any other vehicle belonging to this driver that is currently
ACTIVE, as part of the same atomic, concurrency-safe operation — a driver
never has more than one ACTIVE vehicle. Enforced server-side via row
locking plus a database partial unique index
(database-design.md §8.1's uq_vehicles_one_active_per_driver); the mobile
client is not trusted to enforce this. See
docs/07-state-machines/state-machines.md §68.2.

The driver-offline check reads driver.drivers.operational_status
(§9) — the same field GET/PATCH /api/v1/drivers/me already exposes,
not a second availability mechanism. Admin approval of a vehicle
(verification_status -> APPROVED) is now IMPLEMENTED — §46's
`POST /api/v1/admin/vehicles/{vehicle_id}/approve` — corrected here;
this section previously (incorrectly) described it as not yet built.

Deactivate Vehicle

POST /api/v1/drivers/me/vehicles/{vehicle_id}/deactivate

Vehicle switching is not allowed while ONLINE or ON_RIDE — same
driver-offline check as Activate.

Submit Vehicle Document (IMPLEMENTED — ADR-0072, 2026-09-04)

POST /api/v1/drivers/me/vehicles/{vehicle_id}/documents

Mirrors §9's Submit Driver Document field-for-field — same request
shape (`document_type`, `document_number`, `evidence_uri`,
`expires_at`), same response shape (adding `verification_case_id`,
non-null only when `evidence_uri` was supplied, same
`verification.cases` composition as §9, `subject_type: "VEHICLE_
DOCUMENT"`), same "no document_type vocabulary, no replacement/
versioning policy" scope (ADR-0007 items A/B, still open). Ownership-
checked: `vehicle_id` must belong to the caller (RESOURCE_NOT_FOUND
otherwise, same IDOR-safe pattern as Get/Update/Activate/Deactivate
above).

{
  "document_type": "RC",
  "document_number": "XXXXXX",
  "evidence_uri": "uploaded-file-reference",
  "expires_at": "2028-01-01T00:00:00Z"
}

Response — same shape as §9's Submit Driver Document, minus
`updated_at` (vehicle.documents has no such column,
database-design.md §8.2):

{
  "data": {
    "document_id": "uuid",
    "document_type": "RC",
    "document_number": "XXXXXX",
    "evidence_uri": "uploaded-file-reference",
    "verification_status": "PENDING",
    "expires_at": "2028-01-01T00:00:00Z",
    "created_at": "timestamp",
    "verification_case_id": "uuid"
  },
  "error": null,
  "request_id": "req_131"
}

List Vehicle Documents (IMPLEMENTED — ADR-0072, 2026-09-04)

GET /api/v1/drivers/me/vehicles/{vehicle_id}/documents

Newest first, same ownership check as the POST above. Same per-item
shape, `verification_case_id` always null (same reasoning as §9's List
My Driver Documents).

{
  "data": {
    "documents": [ /* same item shape as the POST response above */ ]
  },
  "error": null,
  "request_id": "req_132"
}

Errors (Add/Get/Update/Activate/Deactivate/Submit Document/List
Documents):

AUTH_REQUIRED
FORBIDDEN (authenticated as a non-DRIVER account type)
RESOURCE_NOT_FOUND (no driver profile yet for Add; or the vehicle does
  not exist or belongs to a different driver, for Get/Update/Activate/
  Deactivate/Submit Document/List Documents — the same response in
  every such case, to avoid revealing another driver's vehicle IDs)
VALIDATION_FAILED (invalid category/registration_number/make/model, a
  duplicate registration_number, or a blank document_type)
VEHICLE_NOT_ELIGIBLE (Activate, vehicle not approved)
INVALID_STATE_TRANSITION (Activate/Deactivate, driver not OFFLINE; also
  used for the defensive concurrency-conflict backstop described in
  database-design.md §8.1.1, which should not occur in normal operation)

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
  "cab_tier": "ECO"
}

Server performs:

Validate customer
→ Validate coordinates
→ Calculate fare
→ Apply eligible promotion
→ Create ride
→ Start matching

This is the target end-to-end flow. As of ADR-0020 (2026-08-24), "Calculate
fare" and "Apply eligible promotion" are both implemented — see below —
closing the gap ADR-0010/ADR-0011 originally left open. "Start matching"
happens synchronously within this same request — the ride is created,
then the nearest eligible driver (if any) receives a `PENDING` offer
(§16) before the response is returned. Accept Offer is implemented
(ADR-0014); the ride stays `SEARCHING` regardless of matching's outcome.

`payment_method` — **removed from the request 2026-09-03, owner
decision**: "Do NOT display or ask the User to select UPI or CASH in
the VISTAAR app... the User has freedom to choose how they settle the
ride amount directly with the Sarthi." It was accepted-and-validated
(non-empty string, no enum) but never persisted or acted upon since
Task 3.1 (ADR-0010 Decision 2), and briefly re-scoped by ADR-0025 as a
customer-preference display field — never built out, and now removed
entirely rather than built. A client sending it is harmless (Pydantic's
default "extra field ignored" behavior, unchanged from every other
schema in this codebase), but no client should send it.

`vehicle_category` is required and validated against the documented
BIKE/AUTO/CAB categories. Task 3.1 did not persist it (ADR-0010 §8);
Task 3.2 added `ride.rides.requested_vehicle_category` (database-design.md
§9.1) and persists it — see ADR-0011 Decision 1.

`cab_tier` (added 2026-08-24, ADR-0020 Decision 1) is required — one of
"ECO"/"PREMIUM"/"PREMIUM_PLUS" — when `vehicle_category` is "CAB", and
must be omitted/null for every other category; VALIDATION_FAILED
otherwise. Determines both the fare rule applied (below) and which
drivers' vehicles are eligible to be matched to this ride (§16) — a
CAB vehicle only ever matches a ride requesting the exact tier its
driver self-declared.

Response:

{
  "data": {
    "ride_id": "uuid",
    "status": "SEARCHING",
    "fare": {
      "base": 89.25,
      "discount": 0,
      "total": 89.25,
      "currency": "INR"
    },
    "outstanding_penalty": {
      "amount": 30,
      "currency": "INR"
    },
    "total_payable": {
      "ride_fare": 89.25,
      "outstanding_penalty": 30,
      "total": 119.25,
      "currency": "INR"
    }
  },
  "error": null,
  "request_id": "req_301"
}

`outstanding_penalty`/`total_payable` (ADR-0026, 2026-08-26, Option A —
IMPLEMENTED 2026-09-02, `PenaltyService.get_outstanding_penalty_total()`
composed at `modules/ride/router.py`'s Create Ride): this is "the customer's next
eligible ride booking" rule 3 requires exposing a combined "ride fare +
outstanding penalty = total" figure at. `outstanding_penalty` is `null`
when the customer has no OUTSTANDING `penalty.penalties` row (the common
case); otherwise `{amount, currency}` summing every OUTSTANDING charge
attached to this ride (BR-054, multiple charges may accumulate — this
is their total, not one row; ADR-0066, 2026-09-03: also durably
attaches these rows to this ride, not just reads them). `total_payable`
breaks the combined figure back down (`ride_fare` mirrors `fare.total`,
`outstanding_penalty` mirrors the field above, `0` if none) so the
client never has to re-derive it — BR-002's "must be clearly displayed"
transparency requirement.

**This total genuinely is what the customer pays, as one payment — to
the Sarthi, never to VISTAAR (ADR-0066, 2026-09-03).** Both
`fare.total`/`ride_fare` and `outstanding_penalty` are paid P2P,
combined, directly to the driver (ADR-0025's settlement mode, extended
by ADR-0066 to cover the penalty too) — VISTAAR recovers its own
penalty share separately, via a driver-wallet debit at that ride's
completion (§28's `customer_penalty_settled`), never from the customer.
Booking itself is never blocked by an outstanding penalty (BR-057).

`fare` (ADR-0020, resolving ADR-0010 Decision 1's `fare: null` placeholder)
is calculated synchronously at ride-creation time from `pricing.fare_rules`
(database-design.md §15.1), keyed by `vehicle_category`/`cab_tier`:
`total = max(minimum_fare, base_fare + per_km × distance) - discount`.
`base` is every pre-discount fare_quotes line item summed (currently just
base_fare + distance_charge — time/waiting/parking/toll/tax all stay 0,
no live composition point exists for any of them yet). `discount` reflects
an automatically-reserved eligible promotion, if the customer has one
(§37) — the customer does not choose which entitlement to apply; the one
expiring soonest is picked. Distance is an interim straight-line
(haversine) calculation, not real road distance (no Mapbox credential
configured — technical-architecture.md's Maps choice remains unintegrated,
§0.4). The client-provided fare is still always ignored.

`Idempotency-Key` is enforced against `shared.idempotency_keys`
(database-design.md §35): replaying the same key with the same request
body returns the original response instead of creating a second ride;
the same key with a different body is rejected with
`IDEMPOTENCY_KEY_REUSE`. This does not limit how many distinct
`SEARCHING` rides a customer may have at once — no such rule is
documented anywhere, and none is invented (ADR-0010 Decision 5).

12.1 Schedule a Ride & Book for Someone Else (IMPLEMENTED — ADR-0057,
2026-08-31)

The request above gains two independent optional fields:

{
  "pickup": {...}, "destination": {...},
  "vehicle_category": "CAB", "cab_tier": "ECO",
  "scheduled_for": "2026-09-01T14:00:00Z",
  "linked_contact": {"name": "Priya Singh", "phone": "+91XXXXXXXXXX"}
}

`scheduled_for` (BR-135-137): an ISO 8601 timestamp 1-24 hours in the
future; `VALIDATION_FAILED` outside that range. When present, the
response's `"status"` is `"SCHEDULED"` instead of `"SEARCHING"`, and
`"fare"` reflects a `pricing.fare_quotes` row locked at this moment
(never recomputed later, even if `pricing.fare_rules` changes before
the ride actually happens). Matching does not begin until 30 minutes
before `scheduled_for` — see state-machines.md §3.9.

`linked_contact` (BR-138-140): both `name` and `phone` required
together, picked from the booker's own phone contacts client-side.
When present, the ride-start OTP (§18) is sent by SMS to both the
booker and this phone number. The booker's own payment method is still
charged by default (§4.5) — the rider paying cash instead needs §33's
cash-payment-confirmation endpoint, which does not exist yet.

New: List My Rides

GET /api/v1/rides?status=SCHEDULED

Paginated (shared/pagination.py's standard envelope), the caller's own
rides only. Added specifically to make Schedule a Ride usable — a
customer can otherwise only ever fetch a ride by an id they already
have (§13 below), with no way to browse upcoming scheduled rides they
booked in an earlier session.

13. Get Ride

GET /api/v1/rides/{ride_id}

Customer may access their own ride.

Driver may access rides assigned to them.

Implementation status (Phase 04, ADR-0024, 2026-08-25): COMPLETE. Same
response for missing and unauthorized (IDOR-safe, RIDE_NOT_FOUND either
way). `pickup`/`destination` are the ride's current (not original)
coordinates. `driver`/`vehicle` are `null` until a driver is assigned
(SEARCHING); once assigned, `driver` is `{driver_id, full_name,
profile_photo_uri}` — deliberately excludes phone number, no source
document describes a masked-calling feature or other justification for
exposing it — and `vehicle` is `{vehicle_id, category,
registration_number, make, model}`. `fare` is the same shape §12
documents (`null` if no active fare quote exists yet). `payment` is
always `null` — no Payment domain exists anywhere in this codebase
(Phase 10, blocked), the same "genuinely unknown, not fabricated"
treatment ADR-0010 Decision 1 originally gave `fare: null`.
`scheduled_for` (ADR-0057, 2026-08-31) is `null` for every ride except
one created as SCHEDULED (§12.1) — added so a customer viewing their
own scheduled ride's detail can see when it's actually for.

Response:

{
  "data": {
    "ride_id": "uuid",
    "status": "ACCEPTED",
    "scheduled_for": null,
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

Task 3.2 (ADR-0011): "Driver state" means ONLINE — DRIVER_NOT_ONLINE if
not (reuses the existing code). `accuracy_meters`/`recorded_at` are
accepted but not deeply validated beyond basic type checking — no
documented "timestamp sanity" rule (e.g. a max allowed clock skew)
exists anywhere, so none is invented; both fields are accepted-and-
currently-unused, the same treatment Task 3.1 originally gave
`payment_method` (ADR-0010 Decision 2 — that field was later removed
entirely, 2026-09-03; unlike it, these two fields haven't been). The
driver's currently ACTIVE vehicle (BR-122: at
most one) determines which `geo:drivers:{category}` set the location is
written into — VEHICLE_NOT_ELIGIBLE if none exists.

Response (added by Task 3.2 — not previously documented with an
example):

{
  "data": {
    "status": "OK"
  },
  "error": null,
  "request_id": "req_501"
}

16. Ride Offer APIs

Task 3.2 (ADR-0011 Decision 2) evaluates the 20-second offer expiry
lazily rather than via a background worker: Get Current Offers and
Reject Offer both first check whether the driver's PENDING offer has
expired and, if so, transition it to EXPIRED and dispatch a new offer to
the next eligible driver before doing anything else. Accept Offer is not
implemented by Task 3.2 (ADR-0011 Decision 3 — blocked on the Wallet
domain, Phase 5); calling it returns 404 until a later task implements
it. The documentation below for Accept Offer describes the target
contract that later task must implement, not current behavior.

Get Current Offers

GET /api/v1/drivers/me/ride-offers

Response (added by Task 3.2 — not previously documented with an
example):

{
  "data": {
    "offers": [
      {
        "offer_id": "uuid",
        "ride_id": "uuid",
        "status": "PENDING",
        "expires_at": "2026-08-22T10:00:20Z",
        "pickup": {
          "latitude": 25.5941,
          "longitude": 85.1376
        }
      }
    ]
  },
  "error": null,
  "request_id": "req_401"
}

Only this driver's own PENDING offers are returned (an offer already
EXPIRED/REJECTED by this lazy-evaluation pass is excluded from the
response, not merely marked).

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
AND
Sarthi Wallet Low-Balance Rule satisfied (ADR-0058, 2026-09-02,
  IMPLEMENTED — WALLET_RECHARGE_REQUIRED if the driver's balance is at
  or below ₹20 and they've already used their one grace-ride
  acceptance since the last recharge; checked before "Wallet balance
  sufficient" above, since it can block an acceptance the platform fee
  itself would still cover)

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
WALLET_RECHARGE_REQUIRED (ADR-0058)

Implemented exactly as documented above (Phase 3 / Task 3.4, ADR-0014).
The wallet row lock (now `WalletService.enforce_low_balance_policy()`,
ADR-0058 — same lock `get_wallet()` used to take purely for its side
effect, now also enforcing the low-balance rule — before any status
re-validation) is the atomicity/concurrency mechanism — see ADR-0014
and modules/matching/router.py's module docstring for the full design.
Response (not previously documented with an example):

{
  "data": {
    "offer_id": "uuid",
    "ride_id": "uuid",
    "status": "ACCEPTED",
    "wallet_balance": 80.00
  },
  "error": null,
  "request_id": "req_403"
}

`wallet_balance` is the driver's wallet balance immediately after the
platform-fee debit. The platform fee amount itself is BR-011's fixed,
already-approved per-category constant (ADR-0014 Decision 1) — not read
from any config table. The vehicle assigned to the ride (`Assign
driver`, above) is the vehicle currently returned by a fresh eligibility
re-check at accept time, not necessarily the vehicle originally captured
on the offer at dispatch time (ADR-0014 Decision 2).

Reject Offer

POST /api/v1/drivers/me/ride-offers/{offer_id}/reject

No platform fee is deducted.

Response (added by Task 3.2 — not previously documented with an
example):

{
  "data": {
    "offer_id": "uuid",
    "status": "REJECTED"
  },
  "error": null,
  "request_id": "req_402"
}

Rejecting immediately dispatches a new offer to the next eligible driver
(BR-029), synchronously within this request — same as the lazy-expiry
path.

Possible errors:

RESOURCE_NOT_FOUND (offer does not exist or belongs to another driver)
OFFER_ALREADY_RESPONDED (offer is not PENDING — already ACCEPTED,
  REJECTED, EXPIRED, or CANCELLED)

17. Driver Arrival

POST /api/v1/rides/{ride_id}/arrived

Server verifies driver location against pickup radius.

Request (not previously documented with an example — the driver's
current GPS reading has to travel to the server somehow):

{
  "latitude": 25.5941,
  "longitude": 85.1376
}

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

NOT_WITHIN_PICKUP_RADIUS (attempts 1 through
RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW - 1 for this ride — retriable)
GPS_VERIFICATION_FAILED (RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW-th+ failure —
terminal, needs manual review; no review queue/endpoint exists yet)

Implementation status (Phase 06/07, ADR-0028): COMPLETE. Driver-only
(ownership-checked — same driver the ride was ACCEPTED by). Every
attempt, pass or fail, is recorded in ride.gps_verifications before this
endpoint decides what to do about it (audit-trail-first design) — even a
FAIL response leaves that row committed. A PASS also auto-issues the
ride-start OTP (§18) in the same request — its plaintext is never
included in this endpoint's own response (the driver must ask the
customer to read it aloud, not see it in-app). Publishes ride.arrived
(event-contracts.md §10.3) on success.

18. Ride Start OTP

Generate/Refresh OTP

POST /api/v1/rides/{ride_id}/otp/refresh

Authorized driver/customer according to product flow.

Implementation status (Phase 06/07, ADR-0028): COMPLETE, customer-only
(narrower than "driver/customer according to product flow" above — see
the ADR's "Who sees the OTP" section for why: the OTP is only ever
persisted as its HMAC, never in plaintext, so the driver can never
recover it through any endpoint; only the customer, via this one, ever
sees the plaintext). No request body. Response (not previously
documented with an example):

{
  "data": {
    "otp": "123456"
  },
  "error": null,
  "request_id": "req_405"
}

This is the ONLY response that ever carries the plaintext OTP — no
other endpoint (including Get Ride) exposes it, since the plaintext is
never stored anywhere to expose later. Invalidates the ride's current
ACTIVE OTP (if any) and issues a fresh one — doubles as "get my current
code" and "get a new one," since no notification channel exists yet
(Phase 15, blocked) to push the code auto-generated by Driver Arrival to
the customer unprompted.

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

Implementation status (Phase 06/07, ADR-0028): COMPLETE. Driver-only
(ownership-checked). A wrong code increments the OTP's attempt counter
and returns OTP_INVALID; RIDE_OTP_MAX_ATTEMPTS reached returns
OTP_MAX_ATTEMPTS; an expired code returns OTP_EXPIRED (and is marked
EXPIRED on that response, not silently left ACTIVE). A correct code
marks the OTP USED and publishes ride.started (event-contracts.md
§10.4).

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

Implemented in full (Phase 3 / Task 3.3 for `SEARCHING → CANCELLED`;
Task 3.5, ADR-0015, for `ACCEPTED`/`ARRIVED → CANCELLED`). The
2-minute-grace/₹0-first/₹15-subsequent logic above presupposes a driver
was already assigned (BR-046: "the driver's platform fee is refunded") —
it does not apply to a `SEARCHING` cancellation, which is unconditionally
free and does not count toward the "first vs. second+" counter (ADR-0012
Decision 1). If the ride has an outstanding `PENDING` matching offer, it
is cancelled (ADR-0012 Decision 2). For a post-acceptance cancellation,
the driver's platform fee is always refunded (a `WalletService.credit()`
reversing the exact amount their original `PLATFORM_FEE` debit took —
ADR-0015 Decision 3), and, only outside the 2-minute grace period, the
customer's qualifying-cancellation penalty is recorded in
`penalty.penalties` (ADR-0015's Minimal Penalty Foundation).

**Cancelling a SCHEDULED ride** (IMPLEMENTED — ADR-0057, 2026-08-31):
this endpoint's gate extends to also accept `SCHEDULED`
(state-machines.md §3.9). The charge
is sourced from `scheduled_for`, not `accepted_at` (BR-135) — ≥3 hours
before: ₹0; <3 hours before: ₹30 — and never records a strike, distinct
from the driver-assigned logic above. Once the ride has already been
promoted to `SEARCHING` (past its lock-in window), this rule no longer
applies; an ordinary `SEARCHING` cancellation stays free.

Response:

{
  "data": {
    "ride_status": "CANCELLED",
    "charge": null
  },
  "error": null,
  "request_id": "req_500"
}

`charge` is `null` only for a `SEARCHING` cancellation (ADR-0012 Decision
1) — there is no chargeable event for it. For a post-acceptance
cancellation, `charge` is always populated (not just when the customer
actually owes something): a grace-period cancellation returns
`{"amount": 0, "currency": "INR"}` (no
`penalty.penalties` row is created for it at all — ADR-0015 Decision 1);
a qualifying cancellation returns
`{"amount": 0 or 15, "currency": "INR",
"penalty_id": "uuid"}` reflecting the actual `penalty.penalties` row
created (this exact shape completes what this document left
underspecified for the amount-0/grace cases — not a new business rule,
ADR-0015 §4). `penalty_id` (ADR-0029 Decision 3, 2026-08-25) is the
customer's own reference for later disputing this specific penalty via
§44's Create Support Case (`category: "PENALTY_DISPUTE"`) — absent
whenever `charge.amount` has no real row behind it (the grace-period
case above). There is no `expires_at` field: per BR-049 (corrected
2026-09-04, ADR-0069) a customer penalty never expires — it remains
OUTSTANDING and collectible indefinitely until paid, so there is
nothing to report an expiry for.

**SCHEDULED cancellation charge shape** (IMPLEMENTED — ADR-0057): the same
`{"amount": 0 or 30, "currency": "INR",
"penalty_id": "uuid" or null}` shape as the post-acceptance
case — `penalty_id` populated only for the ₹30 case
(no `penalty.penalties` row for a ₹0 charge, same ADR-0015 Decision 1
treatment). No `expires_at` field, same BR-049/ADR-0069 correction.

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

Implementation status (Phase 3 / Task 3.6, ADR-0016): the `ACCEPTED →
CANCELLED` transition, the ₹30 wallet penalty, the strike, and the
changed-pickup-pass exemption above are all implemented exactly as
documented. "Rematch ride" is NOT implemented — ADR-0016 Item 2 records
a genuine, unresolved ambiguity between BR-070 ("the customer does not
need to create a new booking") and state-machines.md §13's literal
`ACCEPTED → CANCELLED` transition; a driver-cancelled ride is left
simply `CANCELLED`, with no automatic rematch or replacement ride, until
that ambiguity is resolved. If the driver's wallet cannot cover the ₹30
penalty, the cancellation is refused with `INSUFFICIENT_WALLET_BALANCE`
(ADR-0016 Decision 2) rather than left partially applied.

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

Implementation status: superseded design as of ADR-0056 (owner
decision, 2026-08-31) — PROPOSED, not yet implemented. §23-24 below are
both removed under the new design (no driver decision, no customer
confirmation step for pickup change — see their own superseded notes).
§25-26 (Destination Change) are unaffected by ADR-0056 and remain
IMPLEMENTED as documented (ADR-0033 Decision 9, 2026-08-25).

POST /api/v1/rides/{ride_id}/pickup-change

Request (unchanged):

{
  "latitude": 25.6000,
  "longitude": 85.1400
}

Server calculates distance from the ride's current confirmed pickup.

≤100m (ADR-0056 — threshold lowered from 250m)

Change applies immediately. Response, unchanged from the original
≤threshold shape:

{
  "data": {
    "applied": true,
    "distance_meters": 42.0
  },
  "error": null,
  "request_id": "req_700"
}

>100m (ADR-0056 — previously routed to a driver PROCEED/PASS decision;
now rejected outright, no driver involved)

{
  "data": null,
  "error": {
    "code": "PICKUP_CHANGE_TOO_FAR",
    "message": "This pickup is too far from your current one. Cancel this ride and book a new one to change it by this much."
  },
  "request_id": "req_700"
}

The ride is left completely unchanged by a rejection — no state
transition, no rematch, no fare change. A customer who needs a farther
pickup cancels this ride (§19, Customer Cancellation — existing
penalty/grace-period rules apply, no exemption) and books a new one.

23. Driver Pickup-Change Decision — SUPERSEDED

Superseded 2026-08-31 (ADR-0056) — removed. There is no longer a
driver-decision step for pickup change; a change beyond the threshold
is rejected outright at the §22 endpoint itself, never handed to a
driver. Kept below as the historical record of the original design
(ADR-0033, 2026-08-25).

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

24. Customer Pickup-Change Confirmation — SUPERSEDED

Superseded 2026-08-31 (ADR-0056) — removed. No pickup-change request is
ever left pending a customer decision anymore (the §22 endpoint itself
either applies the change immediately or rejects it outright). Kept
below as the historical record of the original design (ADR-0033,
2026-08-25).

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

GAP-8 (found 2026-08-31, while building the mobile UI for this
endpoint): verified directly against `modules/ride/router.py` that the
response below, for a payable-amount-changing case, never includes the
computed fare — only §26's confirm response does, *after* the customer
has already answered `confirmed`. BR-082 requires "Customer sees
revised fare → Customer confirms," in that order; as implemented, there
is no way for a client to show the fare before the customer decides.
`apps/mobile` does not build a "confirm blind" screen around this — see
`lib/features/rides/ride_status_screen.dart`'s `_changeDestination()`
doc comment for how it handles this instead (auto-rejects the pending
request and tells the customer honestly). Not yet resolved as a backend
fix; flagged here rather than worked around silently.

Request:

{
  "latitude": 25.6200,
  "longitude": 85.1700
}

Response (WITHIN_ROUTE — applied immediately, no confirmation needed):

{
  "data": {
    "applied": true,
    "case": "WITHIN_ROUTE"
  },
  "error": null,
  "request_id": "req_700"
}

Response (BEYOND_ORIGINAL/DIFFERENT_ROUTE — not previously documented
with an example; note GAP-8 above, no fare included here):

{
  "data": {
    "applied": false,
    "case": "BEYOND_ORIGINAL",
    "change_request_id": "uuid",
    "status": "AWAITING_CUSTOMER_CONFIRMATION",
    "requested_at": "2026-08-25T10:00:00Z"
  },
  "error": null,
  "request_id": "req_700"
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

See §25's GAP-8 note — this endpoint's response is the *only* place the
revised fare is ever returned, meaning it only appears once the
customer has already answered `confirmed`.

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

Response:

{
  "data": {
    "status": "REQUESTED"
  },
  "error": null,
  "request_id": "req_407"
}

Confirm

POST /api/v1/rides/{ride_id}/early-drop/confirm

Request:

{
  "confirmed": true,
  "latitude": 25.6050,
  "longitude": 85.1480
}

`latitude`/`longitude` (not previously documented) are required when the
caller is the driver, ignored otherwise — see the ADR below for why.

Response (once both parties have confirmed):

{
  "data": {
    "status": "CLOSED"
  },
  "error": null,
  "request_id": "req_408"
}

Response (this caller's own confirmation recorded, the other party's
still pending):

{
  "data": {
    "status": "PENDING"
  },
  "error": null,
  "request_id": "req_408"
}

Server records:

GPS

Timestamp

Customer confirmation

Driver confirmation

The original fare remains payable under the approved rule.

Implementation status (Phase 08, ADR-0030, 2026-08-25): COMPLETE.
Customer-only for Request (ride must be STARTED; only one pending
request at a time per ride — a second Request while one is already
pending is rejected). Confirm is customer-or-driver, ownership-checked;
the caller's own account_type determines which of `customer_confirmed`/
`driver_confirmed` this call sets, never a client-supplied role.
`confirmed: false` discards the pending request (state-machines.md §21's
"Customer/Driver rejects → STARTED") — no separate reject endpoint
exists. GPS/timestamp are RECORDED as evidence only — no verification
PASS/FAIL step exists anywhere in this rule, this endpoint, or technical-
architecture.md §43; state-machines.md §19-21's added verification-gate
language does not govern here (see the ADR for the full source-of-truth
reconciliation). Once both parties confirm: STARTED → COMPLETED → CLOSED
in the same request (ADR-0028 Decision 3's precedent — no separate CLOSED
trigger exists), publishing `ride.early_drop_confirmed` (event-
contracts.md §10.7). No fare recalculation (BR-090) — `active_fare_
quote_id` is untouched.

28. Ride Completion

POST /api/v1/rides/{ride_id}/complete

Server verifies destination GPS.

Request (not previously documented with an example — same shape as
§17's Driver Arrival request):

{
  "latitude": 25.6120,
  "longitude": 85.1580
}

If valid:

STARTED → COMPLETED

If invalid:

NOT_WITHIN_DESTINATION_RADIUS (retriable, same 3-attempts rule as §17)
GPS_VERIFICATION_FAILED (terminal — manual review)

Implementation status (Phase 06/07, ADR-0028): COMPLETE. Driver-only
(ownership-checked). Unlike the two-step description above, a successful
call transitions STARTED → COMPLETED → CLOSED in the same request
(state-machines.md §10: CLOSED is automatic/immediate, no separate
trigger or event — two ride.state_history rows are still written, one
per step). Publishes ride.completed (event-contracts.md §10.8); no
ride.closed event is documented anywhere, so none is published.

Customer Outstanding Penalty Settlement (ADR-0066, 2026-09-03, owner
decision): if this ride was carrying forward an OUTSTANDING customer
penalty (attached at its own Create Ride — §12's `outstanding_penalty`),
completion also settles it and debits the driver's wallet for the same
amount (`TransactionType.CASH_SETTLEMENT`) — "the User pays the Sarthi
directly [fare + penalty combined]... Apply the corresponding Sarthi
wallet/platform accounting." Never blocks completion, including on
insufficient driver wallet balance (`WalletService.
debit_or_record_as_debt()`, same mechanism ADR-0062 introduced, reused
here for a second reason). Response:

{
  "data": {
    "status": "CLOSED",
    "customer_penalty_settled": 30.0
  },
  "error": null,
  "request_id": "req_406"
}

`customer_penalty_settled` is `null` for the overwhelming common case
(no penalty was attached to this ride).

29. Customer Payment

SUPERSEDED FOR THE RIDE FARE (ADR-0025, 2026-08-25 — approved P2P
Payment Model); PARTIALLY REVIVED FOR OUTSTANDING PENALTIES ONLY
(ADR-0026, 2026-08-26, Option A). §29-32 below describe VISTAAR
collecting the *ride fare* from the customer (online via gateway, or
offline in cash including VISTAAR's own charge) — none of that is
implemented anywhere in this codebase, and none of it should be, ever:
the customer always pays the driver directly for the ride fare, and
VISTAAR's platform fee was already deducted from the driver's wallet at
ride acceptance (§12, BR-011, technical-architecture.md §18, already
implemented).

ADR-0026 originally left open whether a narrower "Create Payment"/
"Payment Breakdown" scoped to the customer's OUTSTANDING PENALTY alone
might be a legitimate future concept, with the mechanism/provider
genuinely undecided. **Resolved 2026-09-03 by ADR-0066: no such
customer-facing endpoint will be built.** The outstanding penalty is
settled automatically, without any customer action, at the next ride's
completion (§28) — the customer pays the combined fare-plus-penalty
amount to the Sarthi directly, and VISTAAR recovers its share via the
driver's wallet. See §12's `outstanding_penalty`/`total_payable` (the
display, unchanged) and §28's `customer_penalty_settled` (the
settlement, new). §31 (Payment Gateway
Webhook) and §32 (Offline Payment/Get Cash Requirement) stay fully
superseded — those described a customer-facing payment *request/
confirmation* flow (a client calling an endpoint to pay), which never
exists for either the ride fare or, as of ADR-0066, the outstanding
penalty either: the penalty amount is now physically handed to the
Sarthi alongside the fare (no separate customer action, no endpoint),
with VISTAAR's own recovery happening entirely server-side via the
driver's wallet at ride completion. (Note: this is a narrower reading
than ADR-0026 rule 6's original "never routed through the driver" —
that rule predates ADR-0066 and is now superseded by it; see ADR-0066
§5 for exactly what changed.)

As originally written (superseded for the ride fare; not a target shape
for a future penalty-only endpoint either):

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

CORRECTED (ADR-0026, 2026-08-26): this breakdown concept is exactly
what §12's now-documented `total_payable` response field already
provides, at ride-creation time — see there for the corrected shape
(`ride_fare`/`outstanding_penalty`/`total`, no `vistaar_charges` bundled
into the ride fare itself). Kept below for historical record.

As originally written (superseded):

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

CORRECTED (ADR-0025, 2026-08-25): unlike §29-32, a driver fare-received
confirmation endpoint could still have a legitimate, much simpler form
under the approved model — the driver confirming they received the ride
fare directly from the customer, as a pure record/UX affordance with
NO wallet-side effect (the platform fee was already debited at
acceptance; there is nothing left to settle here). If ever built:
`expected_amount` is the ride fare only (not "ride fare + VISTAAR
charges"), and the flow ends at "confirmed" — no settlement or wallet
step follows. Not built today; kept here as the corrected target shape,
superseding the steps below.

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

If valid (as originally written — superseded, see above):

Payment → CONFIRMED
→ Create VISTAAR settlement
→ Debit driver wallet

34. Wallet

Get Wallet

GET /api/v1/drivers/me/wallet

Minimal Wallet Foundation implementation status (ADR-0013): implemented
exactly as documented below. `outstanding_settlement` is always `0` —
not a placeholder, genuinely accurate, since `wallet.
outstanding_settlements` doesn't exist yet (ADR-0013 §4 Item 3).
Reconciled by ADR-0025 (2026-08-25): this field's `0` value is not
merely "not yet built" — the scenario it modeled (VISTAAR settling its
own charge out of cash the driver collected on VISTAAR's behalf, §36) no
longer exists under the approved P2P Payment Model. `wallet.
outstanding_settlements` should not be built as originally designed;
see §36's own annotation.
`WalletService.debit()`/`credit()` are composed by
`modules/matching/router.py`'s accept-offer endpoint and
`modules/ride/router.py`'s cancellation endpoints (Tasks 3.4-3.6), the
same way `modules/ride/router.py` composes `modules.matching`. §55–57's
"internal service" HTTP endpoints for debit/credit are not implemented —
ADR-0013 Decision 1 treats them as the target shape for a future
microservice extraction, not something built now; `WalletService.
debit()`/`credit()` are plain in-process methods instead.

`outstanding_debt` (ADR-0062, 2026-09-03, IMPLEMENTED) — unlike
`outstanding_settlement` above, this one is genuinely real: an unpaid
driver-cancellation penalty the wallet balance couldn't cover at
cancellation time, awaiting recovery from a future WALLET_RECHARGE
credit. `0` for the common case (no unpaid penalty).

Response:

{
  "data": {
    "balance": 170,
    "currency": "INR",
    "outstanding_settlement": 0,
    "outstanding_debt": 0
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

Implementation status (Phase 11, "Financial audit trail", ADR-0024,
2026-08-25): COMPLETE — driver's own ledger only, no ownership
ambiguity. `type` is validated against the documented TransactionType
enum (database-design.md §17.2), VALIDATION_FAILED for an unrecognized
value. Paginated per §50. Response item shape (undocumented beyond the
route + query params, filled in): `transaction_id`, `ride_id`,
`transaction_type`, `amount`, `direction`, `balance_before`,
`balance_after`, `reference_type`, `reference_id`, `created_at` —
`idempotency_key`/`metadata` excluded (internal plumbing, the latter
never populated by anything in this codebase).

35. Wallet Recharge

IMPLEMENTED 2026-09-02 (ADR-0060) — Sarthi wallet top-up, behind a
provider abstraction (Razorpay TEST/DEVELOPMENT gateway today,
`WALLET_RECHARGE_PROVIDER=dev` by default; ADR-0060 documents exactly
what changes when SBI replaces Razorpay in production). This is not the
ride-fare payment — VISTAAR never collects ride fare (ADR-0025/
ADR-0026); this only lets a Sarthi top up the platform-fee wallet
already debited at ride acceptance.

Step 1 — Create Recharge Order

POST /api/v1/drivers/me/wallet/recharge

Auth: driver only.

Request:

{
  "amount": "500.00"
}

Validation:

amount >= WALLET_RECHARGE_MINIMUM_AMOUNT (₹200 by default) — otherwise
422 RECHARGE_AMOUNT_TOO_LOW.

Response (201):

{
  "data": {
    "order_id": "order_abc123",
    "amount": 500.0,
    "currency": "INR",
    "client_key": "rzp_test_..."
  },
  "error": null,
  "request_id": "req_..."
}

No wallet effect yet — `client_key`/`order_id` are handed to the
mobile app's Razorpay Checkout SDK. A gateway-side failure (e.g.
Razorpay unreachable, misconfigured keys) returns 502
PAYMENT_GATEWAY_ERROR.

Step 2 — Confirm Recharge

POST /api/v1/drivers/me/wallet/recharge/confirm

Auth: driver only. Called by the mobile app once Razorpay Checkout
reports a completed payment.

Request:

{
  "order_id": "order_abc123",
  "payment_id": "pay_xyz789",
  "signature": "<razorpay checkout signature>"
}

The backend never trusts this report on its own — it re-verifies the
payment server-side against the gateway (HMAC signature check, then a
direct `GET /v1/payments/{payment_id}` call to Razorpay) and credits
the wallet using the *gateway's own reported amount*, never a
client-supplied one. An unverified/uncaptured payment returns 402
PAYMENT_VERIFICATION_FAILED and credits nothing; a gateway error while
verifying returns 502 PAYMENT_GATEWAY_ERROR.

Response (200):

{
  "data": {
    "status": "CREDITED",
    "wallet_balance": 500.0
  },
  "error": null,
  "request_id": "req_..."
}

`debt_recovered`/`outstanding_debt_remaining` (ADR-0062, 2026-09-03,
IMPLEMENTED) — present only when this driver had an
`outstanding_debt` (an unpaid driver-cancellation penalty) and this
recharge paid some or all of it down before crediting `wallet_balance`.
Absent from the response entirely for a plain recharge with no debt —
the shape above is unchanged for that common case. Example when a ₹500
recharge pays off a ₹30 debt:

{
  "data": {
    "status": "CREDITED",
    "wallet_balance": 470.0,
    "debt_recovered": 30.0,
    "outstanding_debt_remaining": 0.0
  },
  "error": null,
  "request_id": "req_..."
}

Idempotent: a retried confirm call for the same `payment_id` credits
the wallet exactly once (`WalletService.credit()`'s existing
idempotency-key guarantee, keyed on `f"razorpay:{payment_id}"`) — the
second call returns the same result without a second credit.

Step 3 — Webhook (resilient backup path)

POST /api/v1/webhooks/wallet-recharge/razorpay

No auth (Razorpay's own servers call this, not an authenticated
driver) — instead verifies the `X-Razorpay-Signature` header against
the raw request body using a separate webhook secret
(`RAZORPAY_WEBHOOK_SECRET`) before trusting anything in the payload.
Missing/invalid signature: 401 INVALID_WEBHOOK_SIGNATURE.

Exists so a real successful payment still reaches the wallet even if
the mobile app's own confirm call never arrives (e.g. a dropped
connection right after payment). Shares the exact same idempotency key
as Step 2, so whichever of the two arrives first credits the wallet and
the other is a safe no-op replay — never a double credit.

A `payment.captured` event credits the wallet and responds
`{"status": "PROCESSED"}`; any other event type (e.g.
`payment.failed`) is acknowledged but ignored — `{"status": "IGNORED"}`
— never acted on.

Every recharge credit is recorded as an ordinary, auditable
`wallet.transactions` row (`transaction_type: WALLET_RECHARGE`,
`direction: CREDIT`), visible through §34's existing Wallet
Transactions endpoint like any other transaction; `metadata` carries
`{"provider": "razorpay", "order_id", "payment_id"}` for traceability.

36. Outstanding Cash Settlement

SUPERSEDED (ADR-0025, 2026-08-25): this endpoint modeled VISTAAR's own
charge going unsettled because it was bundled into cash the driver
collected from the customer. Under the approved P2P Payment Model,
VISTAAR's charge is always collected from the driver's wallet at ride
acceptance (never from customer cash), so no such outstanding liability
can ever be created. Not to be built as documented below.

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

`campaign_id` (added ADR-0041) is `null` for a welcome/referral grant,
and set to the originating campaign's id for one created by Redeem
Campaign Code below.

Redeem Campaign Code (ADR-0041 Decision 2)

POST /api/v1/customers/me/promotions/redeem

Request:

{
  "code": "SAVE50",
  "vehicle_category": "CAB",
  "fare": 500
}

`vehicle_category`/`fare` are the caller's in-progress ride draft's own
values — this endpoint does not create or touch a ride, it only
validates the code against them and creates a new entitlement row.
Validates, in order: the campaign exists (by `code`) and is `ACTIVE`
within its `[starts_at, ends_at)` window; `vehicle_category` matches
the campaign's own (if set); the caller is eligible (always true for
`eligible_scope: "ALL"`, membership-checked for `"SELECTED"`); `fare`
meets `minimum_fare` (if set); the caller's own redemption count for
this campaign is under `per_customer_use_limit`; the campaign's total
redemption count is under `total_usage_limit` (if set). Response 201,
same shape as a Get Promotions list item.

Errors: AUTH_REQUIRED, RESOURCE_NOT_FOUND (unknown code),
CAMPAIGN_NOT_ACTIVE, CAMPAIGN_NOT_ELIGIBLE,
CAMPAIGN_MINIMUM_FARE_NOT_MET, CAMPAIGN_USAGE_LIMIT_EXCEEDED.

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

Implemented (ADR-0022, 2026-08-24). The caller must be the ride's
customer or driver (RIDE_NOT_FOUND otherwise, IDOR-safe — same response
for "does not exist" and "not a participant"). `incident_type` has no
canonical enum documented anywhere — shape-validated only (non-blank,
≤50 chars), same treatment `document_type` already gets. Acknowledge/
Escalate/Resolve (domain-design.md §19.3) have no documented HTTP
endpoint anywhere — `SafetyService.acknowledge_incident()`/
`escalate_incident()`/`resolve_incident()` exist and are tested, ready
for whichever future task gets a real endpoint to compose them into.
`EscalateSOS` never contacts a real emergency service — BR-112's exact
integrations remain TBD.

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

List My Support Cases (IMPLEMENTED — 2026-09-04, the previously-missing
list endpoint)

GET /api/v1/support/cases?status=&page=&page_size=

Customer/driver only (403 for admin — Admin Web's own case search is
the separate, already-existing search_cases()/admin surface, not this
one). Always scoped to the caller's own cases — never another user's.
`status` optional, validated against CaseStatus's documented values
(state-machines.md §46). Same paginated envelope shape as every other
list endpoint (§50):

{
  "data": {
    "items": [ /* same shape as one case below, without "messages" */ ],
    "pagination": {"page": 1, "page_size": 20, "total": 3, "total_pages": 1}
  },
  "error": null,
  "request_id": "req_..."
}

Get Support Case

GET /api/v1/support/cases/{case_id}

Response (not previously specified — filled in by ADR-0022):

{
  "data": {
    "case_id": "uuid",
    "ride_id": "uuid",
    "category": "PAYMENT",
    "priority": "NORMAL",
    "status": "OPEN",
    "assigned_admin_id": null,
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "messages": [
      {
        "sender_type": "CUSTOMER",
        "sender_id": "uuid",
        "message": "Payment issue",
        "created_at": "timestamp"
      }
    ]
  },
  "error": null,
  "request_id": "req_1310"
}

Both implemented (ADR-0022, 2026-08-24). `ride_id` (Create request) is
additive beyond database-design.md §30.1's original `support.cases`
schema — see that document. The request's `message` becomes the case's
first `support.messages` row automatically. `ride_id`, when supplied,
must belong to the caller (RIDE_NOT_FOUND otherwise, same IDOR-safe
pattern as §41). Get Support Case: a customer/driver may view only their
own case (RESOURCE_NOT_FOUND otherwise); an admin may view any case.
`category` has no canonical enum documented anywhere — shape-validated
only, same treatment `document_type` already gets. Assign/Resolve/
PostMessage (domain-design.md §21.3, plus ADR-0022's own
`AssignSupportCase`/`PostSupportMessage` additions covering the roadmap's
"Support assignment"/"Support conversation"/"Human escalation" tasks)
have no documented HTTP endpoint anywhere — the corresponding
`SupportService` methods exist and are tested, ready for whichever
future task gets a real endpoint to compose them into.

Dispute-as-Support (Phase 13, ADR-0029, 2026-08-25): this endpoint is
also how both documented dispute concepts are filed — no separate
`/disputes` endpoint or table exists, per ADR-0028/ADR-0029. Two
`category` conventions, documentation-only (still shape-validated free
text, not a database enum):

- `"RIDE_FARE_DISPUTE"` — BR-121's "ride-fare disputes require a
  support/admin process." `ride_id` should be supplied.
- `"PENALTY_DISPUTE"` — domain-design.md §17.3's `DisputePenalty`
  command. `ride_id` should be supplied (the disputed penalty's own
  `ride_id`, returned as `charge.penalty_id`'s sibling field by §19's
  Customer Cancellation response). An admin resolves it via §48's
  already-existing `POST /api/v1/admin/penalties/{penalty_id}/resolve`
  (`action: "WAIVE"` for a dispute upheld); a dispute decided against the
  customer has no state-machine action to take — the penalty stays
  OUTSTANDING, and only the underlying support case is resolved
  (`resolve_case()`, still with no HTTP endpoint of its own — Decision 5
  above, unchanged).

45. AI Support

BLOCKED (ADR-0022 Decision 4, 2026-08-24) — needs a real LLM (technical-
architecture.md names "Groq/OpenAI-compatible LLM" as the intended
stack) to produce a genuine `message`/`confidence` response; no
provider/credential is configured anywhere in this environment (§0.4).
Not built, not stubbed — a fabricated response would look AI-generated
without being one.

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

45.1 Push Notifications — Device Registration (ADR-0052, 2026-08-28)

The first customer/driver-facing Notification endpoint documented
anywhere — every prior notification feature (§46.10/§46.13, ADR-0034/
ADR-0038/ADR-0044) was Admin-only or composed internally with no HTTP
surface at all. Reachable by any authenticated account (any account
type — device registration is generic, not tied to being a customer,
driver, or admin).

Register/Refresh a Device

POST /api/v1/notifications/me/devices

Request:

{
  "platform": "ANDROID",
  "token": "fcm-device-token-string"
}

platform is one of ANDROID | IOS | WEB. Upsert keyed on `token` itself
(globally unique per app install) — re-registering the same token (e.g.
the app reopened) refreshes it and re-associates it with whichever
account is currently authenticated, rather than erroring or duplicating.

Response:

{
  "data": {
    "device_id": "uuid",
    "platform": "ANDROID",
    "token": "fcm-device-token-string",
    "created_at": "timestamp",
    "updated_at": "timestamp"
  },
  "error": null,
  "request_id": "req_1301"
}

Errors: AUTH_REQUIRED, VALIDATION_FAILED (unknown platform).

Unregister a Device

DELETE /api/v1/notifications/me/devices/{token}

Response:

{"data": {"status": "UNREGISTERED"}, "error": null, "request_id": "req_1302"}

No-op (200, not 404) if this account never registered `token`, or if
`token` belongs to a different account — same idempotent-delete
convention this codebase uses elsewhere (e.g. shared/geo.py's
remove_driver_location()).

Actual push delivery: `Channel.PUSH` in `NotificationService.send()` is
real now too — a registered device with the user's push preference
enabled receives a real send attempt via whichever provider is
configured (`PUSH_PROVIDER=dev` by default, logs only; `=fcm` for a
real Firebase project once a service-account credential is supplied).
No new endpoint for this — it composes into whichever future caller
sends a PUSH-channel notification, the same way SMS already does.

46. Admin APIs

Admin APIs require role authorization (require_admin — an authenticated
ADMIN-type account) plus, per module, a real permission check
(require_permission() — ADR-0040/BR-126/BR-127, 2026-08-25: resolved
business-rules.md §43's "Admin roles"/"Permission hierarchy" TBD
markers). A Super Admin passes every check implicitly; an employee
ADMIN account needs a matching `admin.permissions` row (database-design.
md §33.3) — see §46.1 below for the endpoints that manage those grants.

Search Rides / Get Ride implementation status (Phase 16, ADR-0023,
2026-08-25): both built, admin-only. Response shape (undocumented here)
is filled in as an implementation decision: `ride_id`, `status`,
`customer_id`, `driver_id`, `vehicle_id`, `requested_vehicle_category`,
`requested_cab_tier`, `pickup`/`destination` (current), `fare` (same
shape §12 documents, null if no active fare quote), the full lifecycle
timestamp set, `created_at`/`updated_at`. Search Rides paginates per §50
and validates `status` against the documented RideStatus enum
(VALIDATION_FAILED for an unrecognized value).

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

Response (Phase 2 / Task 2.7A — includes the driver's submitted
documents and, for each, any verification cases, for admin visibility
only; approval does not gate on either — ADR-0009 point C):

{
  "data": {
    "driver_id": "uuid",
    "phone": "+919999999999",
    "full_name": "Driver Name",
    "profile_photo_uri": null,
    "verification_status": "PENDING",
    "operational_status": "OFFLINE",
    "strikes": 0,
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "documents": [
      {
        "document_id": "uuid",
        "document_type": "DRIVING_LICENSE",
        "verification_status": "PENDING",
        "verification_cases": [
          {"case_id": "uuid", "status": "PENDING"}
        ]
      }
    ]
  },
  "error": null,
  "request_id": "req_1400"
}

Approve Driver

POST /api/v1/admin/drivers/{driver_id}/approve

Sets driver.drivers.verification_status PENDING -> APPROVED only.
operational_status is never touched by this endpoint (stays OFFLINE) —
see ADR-0009. Requires verification_status == PENDING; already-decided
drivers return INVALID_STATE_TRANSITION.

business-rules.md BR-123 (Phase 2 / Task 2.6C — enforced) requires the
driver's required documents (Government ID, Driving Licence) to each be
APPROVED and unexpired before approval is permitted. If any required
document is missing, or present but not in that state, this endpoint
returns DRIVER_NOT_ELIGIBLE and verification_status is not changed. No
automatic mechanism yet moves a document into APPROVED (Task 2.6B built
CompleteManualReview + the write-back, but nothing triggers it
automatically — see ADR-0009 point C); a document must reach APPROVED by
some other means (today, only tests/ops-level intervention) before this
endpoint can succeed.

Response: the same shape as Get Driver Profile
(docs/05-api/api-contracts.md §9), with verification_status now
APPROVED.

Reject Driver (Phase 2 / Task 2.7A addition — not part of the original
documented contract; added per ADR-0009 point A)

POST /api/v1/admin/drivers/{driver_id}/reject

Request:

{
  "reason": "Document illegible"
}

reason is optional (no source document requires it) but recorded in the
audit log when supplied. Sets verification_status PENDING -> REJECTED
only. Requires verification_status == PENDING. Rejection reversibility is
not documented anywhere and is not implemented (ADR-0009).

Response: the same shape as Approve Driver, with verification_status now
REJECTED.

Approve Vehicle

POST /api/v1/admin/vehicles/{vehicle_id}/approve

Sets vehicle.vehicles.verification_status PENDING -> APPROVED only.
operational_status is never touched (stays INACTIVE) — approval does not
activate a vehicle; Activate Vehicle (§11) remains a separate,
driver-initiated, OFFLINE-only action (BR-102, ADR-0006). Requires
verification_status == PENDING.

business-rules.md BR-123 (Phase 2 / Task 2.6C — enforced) requires the
vehicle's required documents (RC, Insurance — Vehicle Photo deliberately
excluded, see BR-123) to each be APPROVED and unexpired before approval
is permitted. If any required document is missing, or present but not
in that state, this endpoint returns VEHICLE_NOT_ELIGIBLE and
verification_status is not changed — same automatic-trigger caveat as
Approve Driver, see above.

Response: the same shape as Get Vehicle (§11), with verification_status
now APPROVED.

Reject Vehicle (Phase 2 / Task 2.7A addition — added per ADR-0009 point A)

POST /api/v1/admin/vehicles/{vehicle_id}/reject

Request:

{
  "reason": "RC does not match registration_number"
}

Same optionality/audit/state-guard behavior as Reject Driver. Sets
verification_status PENDING -> REJECTED only.

Every admin mutation creates an audit log (admin.audit_logs —
database-design.md §33.2), written in the same transaction as the
mutation.

Not yet documented or implemented (flagged, not invented — ADR-0009):
Vehicle Review (GET /api/v1/admin/vehicles/{vehicle_id} — no such route
exists anywhere in this contract, meaning a vehicle can currently only
be approved/rejected sight-unseen through this API), and a list/search
endpoint for drivers or vehicles pending review (only Search Rides
documents pagination/filter query params anywhere in this section).
Also not documented anywhere in this contract, per Phase 16/ADR-0023's
reconciliation against the roadmap's broader "Admin" task list: an
aggregate admin dashboard view, any `/api/v1/admin/customers*` route,
`/api/v1/admin/promotions*`/`/api/v1/admin/referrals*`, a dispute
dashboard or GPS-evidence-review route (coupled to ADR-0002's unresolved
Dispute-domain question), admin-facing pricing/fare-rule configuration,
a safety/support dashboard beyond §41/§44's real endpoints, advertisement
management (ADR-0018), and an audit-log viewer (`admin.audit_logs` is a
real, populated table, but no route reads it back).

Errors (Driver Review, Approve/Reject Driver, Approve/Reject Vehicle):

AUTH_REQUIRED
FORBIDDEN (non-ADMIN account, or an ADMIN account whose admin.users
record is not ACTIVE)
RESOURCE_NOT_FOUND (no driver/vehicle with that id, or an ADMIN account
with no admin.users record yet — see ADR-0009 point B for how
admin.users is provisioned)
INVALID_STATE_TRANSITION (verification_status is not PENDING)
DRIVER_NOT_ELIGIBLE (Approve Driver only — BR-123, required document(s)
not APPROVED/unexpired)
VEHICLE_NOT_ELIGIBLE (Approve Vehicle only — BR-123, same as above)

46.1 Admin Management (ADR-0040, BR-126/BR-127, 2026-08-26)

Every route below requires ADMIN_MANAGEMENT MANAGE/VIEW access — never
grantable to an employee admin (BR-126), so in practice these are
Super-Admin-only. The Super Admin level itself has no HTTP endpoint at
all — provisioned exclusively via `scripts/provision_admin.py --role
super_admin`, run out-of-band (BR-127), same restraint ADR-0009 already
established for the single ADMIN account type before this ADR.

Create Employee Admin

POST /api/v1/admin/admins

Request:

{
  "phone": "+919999999999",
  "permissions": [
    {"module": "DRIVERS", "access_level": "MANAGE"},
    {"module": "RIDES", "access_level": "VIEW"}
  ]
}

`permissions` may be empty (create with no access yet, grant later via
Update Permissions). Reuses or creates the target `identity.accounts`
row (account_type=ADMIN) the same way `scripts/provision_admin.py`
already does — no credential is generated, printed, or returned; the
new account authenticates through the ordinary phone+OTP flow. Response
201, same shape as Get Admin below.

List Admins

GET /api/v1/admin/admins?page=1&page_size=20

Paginated per §50. Response items omit each admin's own permission list
(avoids an N+1 query) — use Get Admin for one admin's full detail.

Get Admin

GET /api/v1/admin/admins/{admin_id}

{
  "data": {
    "admin_id": "uuid",
    "role": "ADMIN",
    "status": "ACTIVE",
    "created_at": "timestamp",
    "permissions": [
      {"module": "DRIVERS", "access_level": "MANAGE"}
    ]
  },
  "error": null,
  "request_id": "req_..."
}

`permissions` is always `[]` for a `role: "SUPER_ADMIN"` admin (implicit
full access — nothing is ever actually written to admin.permissions for
one).

Update Permissions

PATCH /api/v1/admin/admins/{admin_id}/permissions

Request:

{
  "permissions": [
    {"module": "SAFETY", "access_level": "MANAGE"}
  ]
}

Replaces the target admin's entire permission set — not an incremental
add/remove. `ADMIN_MANAGEMENT`/`SETTINGS` in the request body are
rejected (VALIDATION_FAILED), never silently dropped. Targeting a
SUPER_ADMIN account returns FORBIDDEN — Super Admin accounts are not
managed through this endpoint (BR-127).

Disable Admin / Enable Admin

POST /api/v1/admin/admins/{admin_id}/disable
POST /api/v1/admin/admins/{admin_id}/enable

Sets admin.users.status to DISABLED/ACTIVE. A disabled admin's existing
access token stops working on their very next request (ACCOUNT_SUSPENDED,
same as `require_active_admin()` already returns for any inactive admin
account). Targeting a SUPER_ADMIN account returns FORBIDDEN, same as
Update Permissions.

Get My Admin Profile

GET /api/v1/admin/me

Not gated by ADMIN_MANAGEMENT — every active admin (Super or employee)
may read their own role/permission set. Intended for the Admin Web to
call once at login to gate its own navigation/controls
(docs/15-admin-web/admin-web-implementation-plan.md §2.2) — the actual
enforcement is still server-side on every other route, regardless of
what this returns. Same response shape as Get Admin.

Errors (Admin Management, all routes):

AUTH_REQUIRED
FORBIDDEN (non-ADMIN account; an employee admin without ADMIN_MANAGEMENT
access — i.e. any employee admin; targeting a SUPER_ADMIN account via
Update Permissions/Disable/Enable)
ACCOUNT_SUSPENDED (the caller's own admin.users record is not ACTIVE)
RESOURCE_NOT_FOUND (Get/Update Permissions/Disable/Enable, unknown
admin_id; or the caller's own admin.users record does not exist yet —
see §46's own RESOURCE_NOT_FOUND note)
VALIDATION_FAILED (Create Employee Admin: phone already provisioned as
a non-ADMIN account, or already has an admin.users row; either endpoint:
ADMIN_MANAGEMENT/SETTINGS present in a permissions list)

46.2 Campaigns / Offers & Coupons (ADR-0041, 2026-08-26)

Every route below requires OFFERS_COUPONS VIEW/MANAGE access
(read/write endpoints respectively, per ADR-0040's per-module
granularity). Composes modules.promotion's new `promotion.campaigns`
table — a materially different concept from `promotion.entitlements`
(§37): a campaign is an authored, many-times-redeemable coupon
definition; an entitlement is one customer's own grant, including one
created by redeeming a campaign code (§37's Redeem Campaign Code).

Create Campaign

POST /api/v1/admin/campaigns

Request:

{
  "code": "SAVE50",
  "name": "50% off launch week",
  "vehicle_category": "CAB",
  "discount_type": "PERCENT",
  "discount_value": 50,
  "max_discount_amount": 100,
  "minimum_fare": null,
  "eligible_scope": "ALL",
  "per_customer_use_limit": 1,
  "total_usage_limit": null,
  "ride_count_limit": null,
  "starts_at": "timestamp",
  "ends_at": "timestamp",
  "eligible_customer_ids": null
}

`code` is `null` for an auto-applied campaign with no customer-entered
code; `vehicle_category` is `null` to apply to every category.
`discount_type` is `"PERCENT"` or `"FLAT"` — a FLAT campaign's
`discount_value` (e.g. ₹50 off) is represented on the redeemed
entitlement as `discount_percent=100, max_discount_amount=<value>`
(ADR-0041 §6.1), not a distinct stored shape. `eligible_scope:
"SELECTED"` requires `code` to be set and populates
`eligible_customer_ids`. Always starts `status: "DRAFT"` — see Activate
Campaign below to make it redeemable. Response 201, same shape as Get
Campaign.

List Campaigns

GET /api/v1/admin/campaigns?status=ACTIVE&page=1&page_size=20

Paginated per §50. `status` filters to one of
DRAFT/ACTIVE/PAUSED/ENDED; omitted returns all statuses.

Get Campaign

GET /api/v1/admin/campaigns/{campaign_id}

{
  "data": {
    "campaign_id": "uuid",
    "code": "SAVE50",
    "name": "50% off launch week",
    "vehicle_category": "CAB",
    "discount_type": "PERCENT",
    "discount_value": 50,
    "max_discount_amount": 100,
    "minimum_fare": null,
    "eligible_scope": "ALL",
    "per_customer_use_limit": 1,
    "total_usage_limit": null,
    "ride_count_limit": null,
    "starts_at": "timestamp",
    "ends_at": "timestamp",
    "status": "DRAFT",
    "created_by": "uuid",
    "created_at": "timestamp"
  },
  "error": null,
  "request_id": "req_..."
}

Edit Campaign

PATCH /api/v1/admin/campaigns/{campaign_id}

Same request shape as Create Campaign. Succeeds only while `status:
"DRAFT"` (INVALID_STATE_TRANSITION otherwise) — once ACTIVE/PAUSED a
campaign may already have real redemptions, so only its status itself
can change from then on (Activate/Pause/End below), never its discount
terms, same "never rewrite history" principle Fare Management applies
to published fares.

Activate Campaign / Pause Campaign / End Campaign

POST /api/v1/admin/campaigns/{campaign_id}/activate   (DRAFT/PAUSED -> ACTIVE)
POST /api/v1/admin/campaigns/{campaign_id}/pause       (ACTIVE -> PAUSED)
POST /api/v1/admin/campaigns/{campaign_id}/end         (any non-terminal -> ENDED, terminal)

Only a campaign with `status: "ACTIVE"` and within its
`[starts_at, ends_at)` window is redeemable (§37's Redeem Campaign
Code). Each is audited (admin.audit_logs), same as every other admin
mutation.

Errors (Campaigns, all routes): AUTH_REQUIRED, FORBIDDEN (no
OFFERS_COUPONS access at the required level), RESOURCE_NOT_FOUND
(unknown campaign_id), VALIDATION_FAILED (Create/Edit: invalid field
combination — e.g. negative discount_value, ends_at before starts_at,
eligible_scope="SELECTED" without a code), INVALID_STATE_TRANSITION
(Edit outside DRAFT; an activate/pause/end call from a status that
does not allow it).

46.3 Audit Logs (Admin Web module #18, 2026-08-26)

Read-only search over the `admin.audit_logs` rows every mutating admin
route already writes (§46/§46.1/§46.2's own "audited" notes) — no new
schema, no new writes, this section only adds a way to read them back.
Requires `AUDIT_LOGS` VIEW access; there is no MANAGE action for this
module — audit log rows are never editable, so nothing needs a higher
access level.

Search Audit Logs

GET /api/v1/admin/audit-logs?admin_id=&target_type=&target_id=&action=&created_after=&created_before=&page=1&page_size=20

Every filter is optional and combinable; omitted filters are not
applied. `created_after`/`created_before` bound `created_at`
(inclusive), matching the Admin Web plan's own "date range" filter.
Paginated per §50, newest first. Response item shape:

{
  "id": 123,
  "admin_id": "uuid",
  "action": "RESOLVE_PENALTY",
  "target_type": "PENALTY",
  "target_id": "uuid",
  "reason": "Verified system error",
  "before_state": {"status": "OUTSTANDING"},
  "after_state": {"status": "WAIVED"},
  "request_id": "req_...",
  "created_at": "timestamp"
}

Errors: AUTH_REQUIRED, FORBIDDEN (no AUDIT_LOGS access).

46.4 Customers / Drivers / Vehicles / Verification search+detail
     (Admin Web §4.1-§4.4, 2026-08-26)

Closes the plan's own "biggest immediate gap": Driver Review/Approve/
Reject already existed, but only reachable by an admin who already had
the id. All read endpoints require VIEW; Suspend/Reactivate require
MANAGE. Paginated endpoints follow §50.

Search Customers

GET /api/v1/admin/customers?query=&page=1&page_size=20

`query` matches `full_name` only — customer.customers has no phone
column (it lives in identity.accounts, a separate module); list rows
omit `phone` for the same reason (no extra per-row lookup). Response
item: `customer_id`, `full_name`, `profile_photo_uri`, `status`,
`language`, `created_at`, `updated_at`.

Customer Detail

GET /api/v1/admin/customers/{customer_id}

Same shape as a Search Customers item, plus `phone`. Ride history is
the existing `GET /api/v1/admin/rides?customer_id=` (§46), not
duplicated here. RESOURCE_NOT_FOUND for an unknown id (no auto-
provisioning, unlike the customer's own self-service `GET
/api/v1/customers/me`).

Search Drivers

GET /api/v1/admin/drivers?query=&status=&page=1&page_size=20

`query` matches `full_name`; `status` matches `verification_status`
exactly. Response items omit `phone` (Driver Review, the existing
detail endpoint, already includes it).

Suspend Driver / Reactivate Driver

POST /api/v1/admin/drivers/{driver_id}/suspend
POST /api/v1/admin/drivers/{driver_id}/reactivate

Composes `DriverService.suspend_driver()`/`reactivate_driver()`
(ADR-0021) — already built and tested at the service layer; only the
HTTP route was missing. Suspend request body same shape as Reject
Driver (`{"reason": "..."}`, optional). Reactivate always lands on
OFFLINE, never directly ONLINE (mirrors ApproveDriver/ApproveVehicle's
own "approval does not change eligibility" precedent, ADR-0009).
Suspend from any operational_status except SUSPENDED itself;
Reactivate only from SUSPENDED — otherwise INVALID_STATE_TRANSITION.
Both audited.

Search Vehicles

GET /api/v1/admin/vehicles?query=&status=&page=1&page_size=20

`query` matches `registration_number`; `status` matches
`verification_status`.

Vehicle Detail

GET /api/v1/admin/vehicles/{vehicle_id}

Same shape as a Search Vehicles item — no ownership restriction,
admin-only (unlike the driver-facing `GET /api/v1/drivers/me/vehicles/
{id}`).

Vehicle Documents

GET /api/v1/admin/vehicles/{vehicle_id}/documents

Vehicle documents had no admin visibility anywhere before this (driver
documents are already nested inside Driver Review). RESOURCE_NOT_FOUND
for an unknown vehicle_id.

Verification Queue

GET /api/v1/admin/verification/queue?status=&page=1&page_size=20

Pending-review queue across every subject (driver + vehicle documents)
— `status` omitted returns every case regardless of status; the Admin
Web's own screen is expected to default its query to status=PENDING
client-side. Response item: `case_id`, `subject_type`, `subject_id`,
`verification_type`, `status`, `created_at`, `completed_at`.

Errors (this whole subsection): AUTH_REQUIRED, FORBIDDEN (missing
module/level access), RESOURCE_NOT_FOUND (Customer/Vehicle Detail,
Vehicle Documents — unknown id), INVALID_STATE_TRANSITION
(Suspend/Reactivate Driver from a status that doesn't allow it).

46.5 Wallet Transaction History (Admin Web §4.7, 2026-08-26)

GET /api/v1/admin/wallets/{driver_id}/transactions?type=&page=1&page_size=20

The admin-side equivalent of the driver-facing `GET /api/v1/drivers/me/
wallet/transactions` (§34, Phase 11/ADR-0024) — both share
`WalletService.list_transactions()`. `type` is validated against the
documented TransactionType enum (VALIDATION_FAILED for an unrecognized
value). Requires FINANCE VIEW. Response item shape matches §34's own
Wallet Transactions exactly.

46.6 Referrals (Admin Web §4.11, 2026-08-26)

GET /api/v1/admin/referrals?status=&page=1&page_size=20

No admin read surface over `referral.referrals` existed before this.
`status` matches `ReferralStatus` exactly (`ATTACHED` | `ACTIVATED`).
Each row composes its own reward(s) (typically zero or one). Requires
REFERRALS VIEW. Response item shape:

{
  "referral_id": "uuid",
  "referrer_id": "uuid",
  "referred_id": "uuid",
  "referred_type": "CUSTOMER",
  "status": "ACTIVATED",
  "activated_at": "timestamp",
  "created_at": "timestamp",
  "rewards": [
    {
      "reward_id": "uuid",
      "recipient_id": "uuid",
      "reward_type": "CUSTOMER_REFERRAL_PROMOTION",
      "amount": null,
      "promotion_uses": 3,
      "status": "ISSUED",
      "created_at": "timestamp"
    }
  ]
}

Errors: AUTH_REQUIRED, FORBIDDEN, VALIDATION_FAILED (unrecognized
`status`).

46.7 Fare Management (Admin Web §4.8, ADR-0042, 2026-08-26)

`pricing.fare_rules` had no admin write path at all before this — the
only five rows that exist were seeded directly by a migration.
Requires FARE_MANAGEMENT VIEW/MANAGE (read/write respectively).

Create Draft Fare Rule

POST /api/v1/admin/fare-rules

Request:

{
  "vehicle_category": "CAB_ECO",
  "base_fare": 55.00,
  "per_km": 12.00,
  "per_minute": 0,
  "waiting_per_minute": 0,
  "minimum_fare": 79.00
}

Always starts `status: "DRAFT"`. `effective_from`/`effective_until` are
not client-supplied here — Publish is the only action that sets
`effective_from` (see below). Response 201.

List Fare Rules

GET /api/v1/admin/fare-rules?vehicle_category=&status=&page=1&page_size=20

With version history — every status is returned by default, not only
PUBLISHED; `status` optionally narrows to one stage.

Get Fare Rule

GET /api/v1/admin/fare-rules/{rule_id}

{
  "data": {
    "rule_id": "uuid",
    "vehicle_category": "CAB_ECO",
    "base_fare": 55.00,
    "per_km": 12.00,
    "per_minute": 0,
    "waiting_per_minute": 0,
    "minimum_fare": 79.00,
    "status": "DRAFT",
    "effective_from": null,
    "effective_until": null,
    "created_at": "timestamp"
  },
  "error": null,
  "request_id": "req_..."
}

Submit for Review

POST /api/v1/admin/fare-rules/{rule_id}/submit-for-review

DRAFT -> IN_REVIEW only.

Publish

POST /api/v1/admin/fare-rules/{rule_id}/publish

Request (both fields optional; body may be `{}`):

{
  "effective_from": "timestamp"
}

Accepts a rule in DRAFT or IN_REVIEW (Submit for Review is not a
mandatory gate) and moves it to PUBLISHED. `effective_from` defaults to
"now" when omitted; a caller-supplied future timestamp schedules a
rollout (e.g. a rate change effective next Monday). In the same
operation, closes out the rule's own vehicle_category's previously-
live PUBLISHED rule (if any) by setting that rule's `effective_until`
to this rule's `effective_from` — at most one rule is ever live per
category at a time.

No Edit-while-DRAFT, Reject, or Unpublish endpoint exists — only the
transitions named above.

Errors: AUTH_REQUIRED, FORBIDDEN, RESOURCE_NOT_FOUND (unknown
rule_id), VALIDATION_FAILED (Create: non-positive rate; List: unknown
`status`), INVALID_STATE_TRANSITION (Submit for Review/Publish from a
status that doesn't allow it).

46.8 Safety / SOS (Admin Web §4.13, 2026-08-26)

Composes `SafetyService`'s existing `acknowledge_incident()`/
`escalate_incident()`/`resolve_incident()` (ADR-0022, already built and
tested) — only the HTTP routes were missing. Requires SAFETY
VIEW/MANAGE.

Incident Queue

GET /api/v1/admin/safety/incidents?status=&page=1&page_size=20

Incident Detail

GET /api/v1/admin/safety/incidents/{incident_id}

{
  "data": {
    "incident_id": "uuid",
    "ride_id": "uuid",
    "reporter_id": "uuid",
    "incident_type": "OTHER",
    "status": "OPEN",
    "location": {"latitude": 25.5941, "longitude": 85.1376},
    "created_at": "timestamp",
    "resolved_at": null
  },
  "error": null,
  "request_id": "req_..."
}

Acknowledge / Escalate / Resolve

POST /api/v1/admin/safety/incidents/{incident_id}/acknowledge  (OPEN -> ACKNOWLEDGED)
POST /api/v1/admin/safety/incidents/{incident_id}/escalate     (ACKNOWLEDGED -> IN_PROGRESS)
POST /api/v1/admin/safety/incidents/{incident_id}/resolve      (IN_PROGRESS -> RESOLVED)

Each is audited. Escalate never contacts a real emergency service
(BR-112's exact integrations are TBD) — it only transitions
`safety.incidents.status`.

Errors: AUTH_REQUIRED, FORBIDDEN, RESOURCE_NOT_FOUND, VALIDATION_FAILED
(unknown `status` filter), INVALID_STATE_TRANSITION.

46.9 Support / Disputes (Admin Web §4.14, 2026-08-26)

Composes `SupportService`. Requires SUPPORT VIEW/MANAGE. GPS Dispute
queue/resolve is the separate, already-existing §77 (BR-124/125). No
"Assign case" endpoint exists here — not named as an Admin Web screen,
even though `SupportService.assign_case()` also already exists.

Search Support Cases

GET /api/v1/admin/support/cases?status=&page=1&page_size=20

Case Detail

GET /api/v1/admin/support/cases/{case_id}

Same shape as a Search Support Cases item, plus `messages` (the full
conversation) — distinct from the existing owner-only `GET
/api/v1/support/cases/{id}`, which an admin using their own admin_id
would fail the IDOR ownership check against.

{
  "data": {
    "case_id": "uuid",
    "user_id": "uuid",
    "ride_id": null,
    "category": null,
    "priority": "NORMAL",
    "status": "OPEN",
    "assigned_admin_id": null,
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "messages": [
      {
        "message_id": "uuid",
        "sender_type": "CUSTOMER",
        "sender_id": "uuid",
        "message": "My ride overcharged me.",
        "created_at": "timestamp"
      }
    ]
  },
  "error": null,
  "request_id": "req_..."
}

Resolve Case

POST /api/v1/admin/support/cases/{case_id}/resolve

Valid from any status except already RESOLVED/CLOSED. Audited.

Errors: AUTH_REQUIRED, FORBIDDEN, RESOURCE_NOT_FOUND, VALIDATION_FAILED
(unknown `status` filter), INVALID_STATE_TRANSITION.

46.10 Notifications (Admin Web §4.12, 2026-08-26)

Requires NOTIFICATIONS VIEW/MANAGE. This section documents only
"Notification history / delivery status" (read-only, VIEW) —
`notification.deliveries` already exists and is populated by real
triggers (ride accepted/arrived events via the Kafka consumer,
ADR-0034/ADR-0038); the admin read endpoint was the only missing
piece. Template management (draft/publish, versioned per-channel
content) is documented separately in §46.13 (ADR-0044, implemented);
device-token registration in §45.1 (ADR-0052, implemented); Compose/
Send/Schedule Broadcast + Audience Selection in §46.21 (ADR-0055,
implemented) — none of these three remain unbuilt or NEEDS SCOPING as
of 2026-08-29.

Notification History

GET /api/v1/admin/notifications/deliveries?user_id=&channel=&status=&page=1&page_size=20

{
  "data": {
    "items": [
      {
        "delivery_id": "uuid",
        "user_id": "uuid",
        "channel": "IN_APP",
        "template_key": "RIDE_ACCEPTED",
        "event_id": null,
        "status": "SENT",
        "provider_reference": null,
        "created_at": "timestamp",
        "delivered_at": "timestamp",
        "retry_count": 0
      }
    ],
    "pagination": {"page": 1, "page_size": 20, "total": 1, "total_pages": 1}
  },
  "error": null,
  "request_id": "req_..."
}

`retry_count` (IMPLEMENTED — ADR-0075, 2026-09-04): 0 (never retried) or
1 (retried once, whichever way it landed) — a FAILED SMS/PUSH delivery
gets exactly one automatic retry attempt (a Celery Beat task, every 5
minutes; IN_APP/WHATSAPP are never FAILED in the first place, so always
0 for those). No admin-triggered manual retry exists — this is the only
way a FAILED delivery is ever revisited.

Errors: AUTH_REQUIRED, FORBIDDEN, VALIDATION_FAILED (unknown `channel`
or `status` filter).

46.11 Dashboard (Admin Web §3, 2026-08-26)

One aggregate endpoint computing every cleanly-sourceable dashboard
widget server-side in a single round trip, per the Admin Web plan's own
recommendation. Requires DASHBOARD VIEW.

GET /api/v1/admin/dashboard/summary

{
  "data": {
    "pending_driver_approvals": 3,
    "pending_vehicle_approvals": 1,
    "open_gps_disputes": 0,
    "open_sos_incidents": 2,
    "open_support_cases": 5,
    "outstanding_penalties": 4,
    "platform_fee_collected_today": 1250.00,
    "rides_today_by_status": {"REQUESTED": 2, "COMPLETED": 14, "...": 0},
    "online_drivers": 22
  },
  "error": null,
  "request_id": "req_..."
}

Both `rides_today_by_status` and `online_drivers` were NOT included as
of 2026-08-26 (this row's original scope). `rides_today_by_status` was
added the same day (server-side, superseding the original "client-side
aggregation over Search Rides" plan). `online_drivers` followed
2026-08-28: `shared/geo.py`'s own docstring had documented that a
driver's Redis `driver:online:{id}` entry was never removed on
go_offline (ADR-0011), so a raw count of that key space would have
overcounted indefinitely — fixed the same day
(`modules/driver/router.py`'s `go_offline` endpoint now calls `geo.
remove_driver_location()`), so this field is real and accurate. See
§46.20/ADR-0054 for the identical figure's own per-category breakdown.

Errors: AUTH_REQUIRED, FORBIDDEN.

46.12 Referral Reward Configuration (ADR-0043, 2026-08-26, implemented)

Requires REFERRALS VIEW/MANAGE. Two independent config streams — see
the ADR for why they're separate.

POST/GET   /api/v1/admin/referral-config/driver-bonus[/{id}]
POST       /api/v1/admin/referral-config/driver-bonus/{id}/submit-for-review
POST       /api/v1/admin/referral-config/driver-bonus/{id}/publish

Create Draft request: `{"referred_amount": 100, "referrer_amount": 100}`.

POST/GET   /api/v1/admin/referral-config/customer-rewards[/{id}]?reward_type=
POST       /api/v1/admin/referral-config/customer-rewards/{id}/submit-for-review
POST       /api/v1/admin/referral-config/customer-rewards/{id}/publish

Create Draft request: `{"reward_type": "REFERRAL_REFERRED", "discount_percent": 50, "total_uses": 3}`.

Same DRAFT → IN_REVIEW → PUBLISHED lifecycle as Fare Management (§46.7)
— Publish closes out the prior live row for the same key. A published
row applies only to referrals qualifying afterward; an already-issued
`referral.rewards` row never changes. Errors: AUTH_REQUIRED, FORBIDDEN,
RESOURCE_NOT_FOUND, VALIDATION_FAILED, INVALID_STATE_TRANSITION.

46.13 Notification Template Management (ADR-0044, 2026-08-26, implemented)

Requires NOTIFICATIONS VIEW/MANAGE.

POST /api/v1/admin/notifications/templates
  {"template_key": "RIDE_ACCEPTED", "channel": "SMS", "event_key": "ride.accepted",
   "title": null, "body": "Your VISTAAR ride has been accepted..."}
  Creates version 1, or the next version of an existing (template_key,
  channel) pair. Always starts DRAFT.

GET  /api/v1/admin/notifications/templates?template_key=&channel=&status=
  Version history — every version, not only PUBLISHED, by default.

GET  /api/v1/admin/notifications/templates/{id}

POST /api/v1/admin/notifications/templates/{id}/publish
  DRAFT -> PUBLISHED; archives (not deletes) the prior PUBLISHED
  version for the same (template_key, channel), if any.

No Edit-in-place — an edit is always a new Create (new DRAFT version).
Never returns or accepts provider credentials of any kind. Errors:
AUTH_REQUIRED, FORBIDDEN, RESOURCE_NOT_FOUND, VALIDATION_FAILED.

46.14 Platform Fee Management (ADR-0045, 2026-08-26, implemented)

Requires FINANCE VIEW/MANAGE. Identical shape to Fare Management
(§46.7), a separate table/endpoint family (driver economics, not
customer fare).

POST/GET /api/v1/admin/platform-fee-rules[/{id}]?vehicle_category=&status=
POST     /api/v1/admin/platform-fee-rules/{id}/submit-for-review
POST     /api/v1/admin/platform-fee-rules/{id}/publish

Create Draft request: `{"vehicle_category": "BIKE", "fee_amount": 2}`
(`vehicle_category` one of `BIKE`/`AUTO`/`CAB` — no per-CAB-tier
variant, matching BR-011). Errors: same shape as §46.7.

46.15 Advertisements (ADR-0046, 2026-08-26, implemented; resolves
      ADR-0018 Item 2)

Requires ADVERTISEMENTS VIEW/MANAGE. Composes the already-implemented
`AdvertisementService` (ADR-0018) — no domain/service logic changes,
only the HTTP surface and the campaign PAUSED/ENDED lifecycle
(previously ACTIVE-only) are new.

POST /api/v1/admin/advertisements/campaigns
  {"partner_name": "...", "payout_amount": 500, "driver_share_percent": 80,
   "vistaar_share_percent": 20, "starts_at": null, "ends_at": null}
  Always starts ACTIVE (unchanged — no draft/approval gate before a
  campaign is usable, ADR-0018 Decision 2).

GET  /api/v1/admin/advertisements/campaigns?status=
GET  /api/v1/admin/advertisements/campaigns/{id}
POST /api/v1/admin/advertisements/campaigns/{id}/pause    (ACTIVE -> PAUSED)
POST /api/v1/admin/advertisements/campaigns/{id}/resume   (PAUSED -> ACTIVE)
POST /api/v1/admin/advertisements/campaigns/{id}/end      (-> ENDED, terminal)

POST /api/v1/admin/advertisements/campaigns/{id}/assignments
  {"driver_id": "uuid"} — AssignDriver; rejected (CAMPAIGN_NOT_ACTIVE) if
  the campaign is PAUSED/ENDED.

GET  /api/v1/admin/advertisements/assignments?campaign_id=&driver_id=&status=
  Installation/proof review queue.
GET  /api/v1/admin/advertisements/assignments/{id}
  Includes `proof_uri`, `verification_status` — the field colloquially
  called "Admoto verification status"; set manually here, not by a live
  Admoto call (ADR-0018 Item 3 stays deferred).
POST /api/v1/admin/advertisements/assignments/{id}/verify
  {"approved": true|false} — Approve/Reject proof.

POST /api/v1/admin/advertisements/assignments/{id}/payouts/calculate
GET  /api/v1/admin/advertisements/payouts?status=
  Payout/settlement monitoring.
POST /api/v1/admin/advertisements/payouts/{id}/settle
  Composes `WalletService.credit(ADVERTISEMENT_PAYOUT)` then
  `mark_payout_paid()` — the exact sequence ADR-0018's own worked-
  example integration test already demonstrates.

The 80%/20% driver/VISTAAR split is unchanged — exposed as Create
Campaign parameters, not altered. Errors: AUTH_REQUIRED, FORBIDDEN,
RESOURCE_NOT_FOUND, VALIDATION_FAILED, INVALID_STATE_TRANSITION,
CAMPAIGN_NOT_ACTIVE (new — assigning a driver to a PAUSED/ENDED
campaign).

46.16 Reports / Analytics MVP (ADR-0047, 2026-08-26, implemented)

Requires REPORTS VIEW. Nine fixed-shape aggregate reports, each
accepting an optional `from`/`to` date range (defaulting to the last
30 days if omitted; both bounds are always echoed back in the
response) — not a generic query builder (ADR-0047 §2). Every
`*_by_status`/`*_by_type`/`*_by_channel` field is a sparse object —
only values with at least one matching row appear, never zeroed out
for the rest. Field names match each domain's own real enum values
exactly (e.g. `rides_by_status` uses `RideStatus`'s values); see the
ADR for the full shape of each of the nine:

GET /api/v1/admin/reports/rides?from=&to=
GET /api/v1/admin/reports/customers?from=&to=
GET /api/v1/admin/reports/drivers?from=&to=
GET /api/v1/admin/reports/financial?from=&to=
GET /api/v1/admin/reports/penalties?from=&to=
GET /api/v1/admin/reports/promotions-referrals?from=&to=
GET /api/v1/admin/reports/safety-support?from=&to=
GET /api/v1/admin/reports/notifications?from=&to=
GET /api/v1/admin/reports/matching?from=&to=

No "online drivers"/live operational figures — same reasoning as
§46.11's Dashboard. Errors: AUTH_REQUIRED, FORBIDDEN.

46.17 Settings MVP (ADR-0048, 2026-08-26, implemented)

Requires SETTINGS (Super-Admin-only, never grantable — BR-126,
unchanged). Fare/platform-fee/referral/notification settings are
managed through their own dedicated screens (§46.7/§46.14/§46.12/
§46.13) — this surface covers only what has no dedicated home:
promotion defaults, operational thresholds, feature flags, general
platform settings.

GET   /api/v1/admin/settings?category=
GET   /api/v1/admin/settings/{key}
PATCH /api/v1/admin/settings/{key}
  {"value": ...} — audited (before_state/after_state capture the full
  old/new value).

No Create/Delete — the key set is fixed by what the implementing
migration seeds (ADR-0048 §2: `welcome_discount_percent`,
`welcome_total_uses` at launch — BR-058's own approved values; no
operational threshold, feature flag, or general setting is seeded yet,
each being its own future decision). Never returns or accepts any
credential-shaped value. Errors: AUTH_REQUIRED, FORBIDDEN,
RESOURCE_NOT_FOUND (unknown key), VALIDATION_FAILED.

46.18 Driver Strike History (2026-08-26, implemented 2026-08-29 — no
      dedicated ADR — a pure read over already-existing data, the same
      treatment Audit Logs/Wallet Transaction History already got)

Requires DRIVERS VIEW (reuses the existing module — this is driver
data, not a new module).

GET /api/v1/admin/drivers/{driver_id}/strikes?page=&page_size=

{
  "data": {
    "items": [
      {
        "strike_id": "uuid",
        "driver_id": "uuid",
        "ride_id": "uuid",
        "reason": "DRIVER_CANCELLATION",
        "created_at": "timestamp"
      }
    ],
    "pagination": {...}
  }
}

Reads `penalty.strikes` (§26.2) as-is — no new column. Immutable by
construction (no update/delete path exists in the Penalty domain for a
strike). `driver.drivers.strikes` (the existing bare counter) remains
the at-a-glance summary shown on Driver Review (§46); this is the
underlying detail view. Errors: AUTH_REQUIRED, FORBIDDEN,
RESOURCE_NOT_FOUND (unknown driver_id).

46.19 Coupon/Campaign CSV Bulk Customer Targeting (ADR-0041 §9,
      2026-08-26, implemented 2026-08-29)

Requires OFFERS_COUPONS MANAGE (same as Create/Edit Campaign, §46.2).

POST /api/v1/admin/campaigns/{campaign_id}/eligible-customers/bulk
  multipart/form-data, field `file`: CSV, header `phone`, one Indian
  phone number per row.

{
  "data": {
    "added": 97,
    "already_eligible": 2,
    "unmatched": [{"row": 14, "phone": "+91...", "reason": "no customer account"}]
  }
}

Additive to the campaign's existing eligible-customer set (unlike
`eligible_customer_ids` on Create/Edit, which replaces the whole set —
ADR-0041 §9 explains why bulk upload needs the opposite semantics).
Only valid while the campaign is DRAFT and `eligible_scope='SELECTED'`.
Audited. Errors: AUTH_REQUIRED, FORBIDDEN, RESOURCE_NOT_FOUND,
VALIDATION_FAILED (wrong eligible_scope, campaign not DRAFT, malformed
CSV), INVALID_STATE_TRANSITION.

46.20 Matching / Offers Admin Visibility (ADR-0054, 2026-08-29,
      implemented — Tier C, no driver-location map)

Requires MATCHING VIEW — the first real consumer of this permission
key anywhere in the codebase. Read-only: no mutation exists in this
module, and none is proposed (the matching algorithm itself stays
entirely driver-facing, `modules/matching/router.py`, untouched here).

```
GET /api/v1/admin/matching/online-drivers
```

```
{
  "data": {
    "by_category": {"BIKE": 3, "AUTO": 5, "CAB:ECO": 12,
                     "CAB:PREMIUM": 2, "CAB:PREMIUM_PLUS": 0},
    "total": 22
  }
}
```

Keyed by the real `matching_category_key()` values (ADR-0020 Decision
1) — CAB's tiers are genuinely separate Redis keys, not collapsed into
one "CAB" figure. `total` is the sum. Reuses the same accurate
`geo.count_online_drivers()` count Dashboard's own summary (§46.11)
already sums — real since the ADR-0011 go_offline-cleanup fix — via a
new per-category variant that doesn't collapse it.

```
GET /api/v1/admin/matching/offers?status=&ride_id=&driver_id=&from=&to=&page=&page_size=
```

Every filter optional and independent. `status` validated against the
documented `OfferStatus` enum (PENDING/ACCEPTED/REJECTED/EXPIRED/
CANCELLED). `from`/`to` filter on `created_at` — unlike Reports' own
30-day default, an omitted bound here means "no filter on that side"
(this is a search screen, not a report). Ordered newest-first.

```
{
  "data": {
    "items": [
      {
        "offer_id": "uuid",
        "ride_id": "uuid",
        "driver_id": "uuid",
        "vehicle_id": "uuid",
        "status": "PENDING",
        "expires_at": "timestamp",
        "responded_at": null,
        "created_at": "timestamp"
      }
    ],
    "pagination": {...}
  }
}
```

```
GET /api/v1/admin/matching/offers/{offer_id}
```

Same single-object shape as one item above. Admin-only, no
driver-ownership restriction — same "no ownership restriction,
admin-only" split Get Ride (§46) already has relative to the
driver/customer-facing ride lookup.

Documented/safe fields only, both endpoints (`database-design.md`
§10.1's actual columns) — no coordinates, no Redis-derived driver
location or availability data. A live driver-location map was
explicitly excluded from this decision (ADR-0054 §5) and remains a
separate, undecided future question. Errors: AUTH_REQUIRED, FORBIDDEN,
VALIDATION_FAILED (unknown status), RESOURCE_NOT_FOUND (unknown
offer_id).

46.21 Compose/Send Broadcast + Audience Selection (ADR-0055, Tier C,
      2026-08-29, implemented)

Closes out the last three open rows anywhere in the Admin Web
implementation plan's original scope. `POST` requires NOTIFICATIONS
MANAGE (this sends real messages to real users, the same bar Template
create/publish already sets); both `GET`s require VIEW.

```
POST /api/v1/admin/notifications/broadcasts
{"channel": "IN_APP", "subject": "Maintenance notice",
 "body": "VISTAAR will be briefly unavailable tonight...",
 "audience_type": "ALL_CUSTOMERS", "audience_user_ids": null,
 "scheduled_at": null}
```

`channel` one of `IN_APP`/`SMS`/`PUSH` (`WHATSAPP` is rejected —
`VALIDATION_FAILED` — same "no BSP chosen yet" reason `Notification
Service.send()` already raises `CHANNEL_NOT_AVAILABLE` for). `audience_
type` one of `ALL_CUSTOMERS`/`ALL_DRIVERS`/`ONLINE_DRIVERS`/`SELECTED`;
`audience_user_ids` required and non-empty only when `audience_type=
'SELECTED'`, rejected (`VALIDATION_FAILED`) if supplied otherwise.
`scheduled_at` omitted or in the past means "send now" — the response
already reflects the real dispatch result:

```
{
  "data": {
    "broadcast_id": "uuid",
    "channel": "IN_APP",
    "subject": "Maintenance notice",
    "body": "VISTAAR will be briefly unavailable tonight...",
    "audience_type": "ALL_CUSTOMERS",
    "audience_user_ids": null,
    "status": "SENT",
    "scheduled_at": null,
    "sent_count": 4213,
    "failed_count": 2,
    "created_by": "uuid",
    "created_at": "timestamp",
    "sent_at": "timestamp"
  }
}
```

A future `scheduled_at` instead returns `status: "SCHEDULED"`,
`sent_count`/`failed_count` both `0`, `sent_at: null` — a Celery Beat
task polls every 5 minutes and dispatches it when due, resolving the
audience fresh at that time (never a snapshot taken at compose time,
except SELECTED's own fixed id list).

```
GET /api/v1/admin/notifications/broadcasts?status=&page=&page_size=
GET /api/v1/admin/notifications/broadcasts/{broadcast_id}
```

Same response shape as the `POST` above (single object for the
`{id}` route, `{"items": [...], "pagination": {...}}` for the search
route). `status` filter one of `SCHEDULED`/`SENT`. No FAILED status at
the broadcast level — an individual recipient's send failing is
tracked in `failed_count`, not the whole broadcast.

Every send is audited (`admin.audit_logs`) with the channel, audience
type, resulting status, and sent/failed counts — never the full
recipient id list, keeping the audit row bounded even for an "all
customers"-sized audience. Errors: AUTH_REQUIRED, FORBIDDEN,
VALIDATION_FAILED, RESOURCE_NOT_FOUND (unknown broadcast_id on the
`{id}` route).

47. Admin Financial Review

GET /api/v1/admin/wallets/{driver_id}
GET /api/v1/admin/payments/{payment_id}
GET /api/v1/admin/settlements

Admin cannot silently edit historical financial transactions.

Corrections must create compensating transactions.

Implementation status (Phase 16, ADR-0023, 2026-08-25): only Get Wallet
is built — same response shape as the driver-facing `GET
/api/v1/drivers/me/wallet` (§34), just admin-accessible for any
`driver_id`; RESOURCE_NOT_FOUND if that `driver_id` has no
`driver.drivers` row. Get Payment / Get Settlements are NOT built — no
`modules/payment` exists anywhere in this codebase (Phase 10, blocked)
and "settlements" has no backing table/concept documented anywhere.
Reconciled by ADR-0025 (2026-08-25): Get Payment specifically is no
longer just "blocked" — it has no ride-fare-collection concept left to
build (VISTAAR never collects the ride fare, §29's supersession note).
Get Settlements stays merely blocked/undocumented, not superseded — it
may still have a legitimate future meaning for other settlement types
(e.g. advertisement payouts, ADR-0018), not ride-fare specific.

48. Admin Penalty Review

GET /api/v1/admin/penalties
POST /api/v1/admin/penalties/{penalty_id}/resolve

Implementation status (Phase 16, ADR-0023, 2026-08-25): both built,
admin-only. Search Penalties paginates per §50 with `status`/`user_id`
filters (neither documented here explicitly — modeled on Search Rides'
own filter shape) and validates `status` against the Penalty State
Machine's documented values (state-machines.md §40). `action` below is
validated to equal exactly "WAIVE" — the only documented value —
otherwise VALIDATION_FAILED. The "reversal/waiver record" is the
`admin.audit_logs` row this mutation writes in the same transaction
(§46's "every admin mutation creates an audit log," reused rather than
a second table); `amount`/`issued_at` are never rewritten.
Response shape: same fields as the seeded penalty row (`penalty_id`,
`user_id`, `ride_id`, `penalty_type`, `amount`, `status`, `issued_at`,
`settled_at` — always `null` for a WAIVED result, since
WAIVED is not SETTLED). There is no `expires_at` field: per BR-049
(corrected 2026-09-04, ADR-0069) a customer penalty never expires —
`PenaltyStatus` has no EXPIRED value, and OUTSTANDING penalties stay
collectible indefinitely until paid or waived.

Resolution requires:

{
  "action": "WAIVE",
  "reason": "Verified system error"
}

The original penalty remains immutable.

A reversal/waiver record is created.

Dispute-as-Support (Phase 13, ADR-0029, 2026-08-25): this same endpoint
is how a `DisputePenalty` (domain-design.md §17.3) filed via §44's
Create Support Case (`category: "PENALTY_DISPUTE"`) gets decided in the
customer's favor — `action: "WAIVE"` here IS the dispute-upheld outcome;
no separate dispute-specific action or endpoint exists.

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
WALLET_RECHARGE_REQUIRED (ADR-0058, 2026-09-02, IMPLEMENTED — Accept
  Offer only, when the driver's wallet balance is at or below ₹20 and
  they have already used their one grace-ride acceptance since the last
  time it crossed that threshold; HTTP 409)

RECHARGE_AMOUNT_TOO_LOW (ADR-0060, 2026-09-02, IMPLEMENTED — §35 Create
  Recharge Order, amount below WALLET_RECHARGE_MINIMUM_AMOUNT; HTTP 422)
PAYMENT_VERIFICATION_FAILED (ADR-0060, IMPLEMENTED — §35 Confirm
  Recharge, the gateway could not verify the payment as captured; HTTP
  402)
PAYMENT_GATEWAY_ERROR (ADR-0060, IMPLEMENTED — §35 Create/Confirm
  Recharge, the payment gateway itself errored/was unreachable; HTTP
  502)
INVALID_WEBHOOK_SIGNATURE (ADR-0060, IMPLEMENTED — §35 webhook, a
  missing or invalid X-Razorpay-Signature header; HTTP 401)

PAYMENT_REQUIRED
PAYMENT_FAILED
PAYMENT_ALREADY_CONFIRMED
FULL_PAYMENT_NOT_RECEIVED
(scoped to §29-33/§60-61's superseded customer-payment flows — ADR-0025,
2026-08-25; FULL_PAYMENT_NOT_RECEIVED could still apply to a future
fare-only driver-confirmation endpoint, §33)

FARE_CONFIRMATION_REQUIRED
FARE_CHANGED
PROMOTION_EXPIRED
PROMOTION_ALREADY_USED
CAMPAIGN_NOT_ACTIVE
CAMPAIGN_NOT_ELIGIBLE
CAMPAIGN_MINIMUM_FARE_NOT_MET
CAMPAIGN_USAGE_LIMIT_EXCEEDED

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
RATE_LIMITED (ADR-0061, 2026-09-02, IMPLEMENTED — HTTP 429. Previously
  OTP request/verify only; now also Create Ride, Cancel Ride
  (customer/driver), Ride Offer accept/reject, Pickup Change,
  Destination Change, Wallet Recharge (create + confirm), Redeem
  Campaign Code, Attach Referral, Create Support Case, the driver/GPS-
  dispute evidence upload-url endpoints, and a blanket per-admin-account
  limit across every /api/v1/admin/* endpoint — each per authenticated
  account, application-level, not per IP)

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

SUPERSEDED (ADR-0025, 2026-08-25): this online-gateway state machine
described VISTAAR's own payment collection from the customer, which
does not exist under the approved P2P Payment Model. Not applicable to
the ride fare.

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

CORRECTED (ADR-0025, 2026-08-25): if a driver fare-received confirmation
is ever built (§33), it ends at CONFIRMED — there is no
SETTLEMENT_PENDING/SETTLED step, since no VISTAAR settlement follows a
customer's cash/UPI payment (the platform fee was already collected
from the driver's wallet at acceptance):

EXPECTED
 ↓
DRIVER_CONFIRMING
 ↓
CONFIRMED

As originally written (superseded — the SETTLEMENT_PENDING/SETTLED
steps below modeled a VISTAAR settlement that no longer applies):

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

CORRECTED (ADR-0025, 2026-08-25): the actual critical flow, under the
approved P2P Payment Model, is the Accept-Ride Transaction (§16;
technical-architecture.md §18) — the platform fee is debited from the
driver's wallet there, before the ride happens:

POST .../ride-offers/{id}/accept
       ↓
Lock driver wallet row
       ↓
Debit platform fee (BR-011)
       ↓
Ride ACCEPTED

After the ride, the customer pays the driver directly (cash or UPI, per
BR-035) — no VISTAAR-facing flow follows. The "Online"/"Offline" flows
below are superseded (no VISTAAR Payment Gateway, no VISTAAR
settlement/allocation from a customer payment).

Online (superseded)

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

Offline (superseded)

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

Payment gateway (narrowed — ADR-0025, 2026-08-25: only the driver
wallet-recharge gateway remains TBD; no customer-facing ride-fare
gateway is needed).

Payout/settlement provider.

Notification provider — RESOLVED (ADR-0031, 2026-08-25): MSG91.

Production API hostname.

Exact rate limits.

Exact GPS radius values — RESOLVED (ADR-0028, 2026-08-25): 50m arrival /
100m completion. Exact early-drop GPS tolerance — RESOLVED AS N/A
(ADR-0030): no tolerance check exists. Exact GPS-dispute evidence
window — RESOLVED (BR-124, 2026-08-25): 24 hours.

Exact fare-rule fields.

Final admin role matrix.

Final WebSocket provider/implementation.

API gateway/load-balancer choice.

Public vs internal service deployment topology.

77. GPS Dispute Manual Review

Implementation status (BR-124/BR-125, ADR-0032, 2026-08-25): COMPLETE.
Auto-opened by §17 (Driver Arrival) / §28 (Ride Completion) when GPS
verification reaches its terminal `GPS_VERIFICATION_FAILED` outcome — not
a client-initiated command. That error response's `details` field
(shared/api_envelope.py) carries `{"dispute_id": "uuid"}` so the caller
can discover and act on the dispute.

List Disputes for a Ride (IMPLEMENTED — ADR-0074, 2026-09-04)

GET /api/v1/rides/{ride_id}/gps-disputes

Customer/driver (own ride). The discovery endpoint a customer needs —
unlike the driver, who receives `dispute_id` directly in the
`GPS_VERIFICATION_FAILED` error that opened it, nothing else tells a
customer a dispute exists on their own ride. Not paginated — a ride
has at most two GPS verifications (pickup, destination) and therefore
at most two disputes ever.

{
  "data": {
    "disputes": [
      { ... same per-item shape as Get Dispute below, including "evidence" ... }
    ]
  },
  "error": null,
  "request_id": "req_409"
}

Errors:

AUTH_REQUIRED
FORBIDDEN (authenticated as neither CUSTOMER nor DRIVER)
RIDE_NOT_FOUND (unknown ride_id, or authenticated but not this ride's
customer/driver — IDOR-safe, same response either way)

Get Dispute

GET /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}

Customer/driver (own ride) or admin.

{
  "data": {
    "dispute_id": "uuid",
    "ride_id": "uuid",
    "gps_verification_id": "uuid",
    "verification_type": "ARRIVAL",
    "opened_at": "timestamp",
    "evidence_deadline": "timestamp",
    "status": "OPEN",
    "decision": null,
    "decided_by": null,
    "decided_reason": null,
    "decided_at": null,
    "evidence": [
      {
        "submitted_by": "uuid",
        "evidence_type": "PHOTO",
        "uri": "s3://vistaar-storage/...",
        "text_explanation": null,
        "submitted_at": "timestamp"
      }
    ]
  },
  "error": null,
  "request_id": "req_410"
}

`status` is lazily transitioned OPEN → EXPIRED here if `evidence_deadline`
has passed and no admin has resolved it yet (state-machines.md §69) — no
background worker recomputes it independently.

Request Evidence Upload URL

POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence/upload-url

Customer/driver (own ride). Same request/response shape as §9's Request
Upload URL (ADR-0031; presigned POST since ADR-0065, 2026-09-03) —
`{"content_type": "image/jpeg"}` → `{"upload_url": "...",
"upload_fields": {"key": "...", "Content-Type": "...", "policy": "...",
...}, "uri": "s3://...", "expires_at": "timestamp"}`. One difference:
the object key here is scoped under `gps-dispute-evidence/`, not
`driver-uploads/` — a distinct namespace per ADR-0065's "authorized
object-key scope" fix, so evidence uploads and driver-document uploads
can never collide.

Submit Evidence

POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/evidence

Customer/driver (own ride).

{
  "evidence_type": "PHOTO",
  "uri": "s3://vistaar-storage/..."
}

or, for a text explanation:

{
  "evidence_type": "TEXT",
  "text": "I was standing at the correct gate, GPS was inaccurate indoors."
}

`evidence_type` must be one of PHOTO, VIDEO, DOCUMENT, TEXT (BR-125);
`uri` is required for the first three, `text` for TEXT. Rejected
(INVALID_STATE_TRANSITION) once the dispute is no longer OPEN (already
RESOLVED, or lazily EXPIRED by this same call observing the deadline has
passed).

Admin: Search Disputes

GET /api/v1/admin/gps-disputes

Admin-only. Paginates per §50, `status` filter — same shape as §48's
Search Penalties (ADR-0023).

Admin: Get Dispute (Admin Web §4.14, added 2026-08-29)

GET /api/v1/admin/gps-disputes/{dispute_id}

Admin-only, no ownership restriction. Same shape as the customer/driver
Get Dispute above (including `evidence`) — `RideService.
get_gps_dispute()`'s own `is_admin` flag, just composed at
modules/admin/router.py this time; the service method and its lazy-
expiry behavior were already built and tested, only the HTTP route
itself was missing.

Admin: Resolve Dispute

POST /api/v1/admin/gps-disputes/{dispute_id}/resolve

Admin-only.

{
  "action": "APPROVE",
  "reason": "Evidence confirms driver was at the correct pickup point."
}

`action` is exactly "APPROVE" or "REJECT" (VALIDATION_FAILED otherwise).
APPROVE performs the exact ride transition the original GPS verification
would have on a PASS (→ ARRIVED for an arrival dispute; → COMPLETED →
CLOSED for a completion dispute, per ADR-0028 Decision 3's existing
"COMPLETED → CLOSED automatic/immediate" rule) and publishes
`ride.gps_dispute_resolved` (event-contracts.md §10.11). REJECT only
records the decision — the ride does not transition (BR-124). Both leave
`ride.gps_verifications`' original FAIL row untouched (BR-124: "not
erased or altered").

Errors (all six endpoints):

AUTH_REQUIRED
FORBIDDEN
RIDE_NOT_FOUND (dispute does not exist, or belongs to a ride the caller
does not own — same IDOR-safe treatment used throughout)
VALIDATION_FAILED
INVALID_STATE_TRANSITION (dispute not OPEN)

77A. Next Document

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