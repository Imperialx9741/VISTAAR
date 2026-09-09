VISTAAR — Security Design

Document Version: 1.0
Status: Draft
API Version: v1
Security Model: Zero-trust application security
Currency: INR (₹)

1. Purpose

This document defines the security controls for VISTAAR.

It covers:

Authentication

Authorization

Session security

API security

Driver/customer account protection

Wallet and payment security

Financial transaction protection

GPS and location security

Dispute security

Admin security

Secrets management

Encryption

Data protection

Fraud prevention

Rate limiting

Audit logging

Security monitoring

Incident response

Security controls must protect both VISTAAR users and VISTAAR's financial and operational systems without changing the approved business rules.

2. Security Principles

VISTAAR follows:

Never trust the client
Least privilege
Server-authoritative state
Defense in depth
Secure by default
Fail safely
Audit sensitive actions
Minimize sensitive data
Encrypt sensitive data
Idempotent financial operations

The mobile application is considered an untrusted client.

3. Server Authority

The server is authoritative for:

Ride state
Fare
Additional charges
Penalty amount
Wallet balance
Payment status
Promotion usage
Referral qualification
Driver eligibility
Vehicle eligibility
GPS verification
Dispute outcome
Settlement

The client cannot directly modify these values.

Example:

Client says:
fare = ₹100

Server calculates:
fare = ₹130

The server value wins.

4. Authentication

Customer and driver authentication uses:

Phone number
+
OTP

OTP requirements:

Short expiration period

Limited verification attempts

Rate-limited requests

One-time use

Secure random generation

Never stored in plaintext where avoidable

Never included in application logs

Example flow:

Request OTP
   ↓
Challenge created
   ↓
OTP delivered
   ↓
OTP verification
   ↓
Session/token issued

5. OTP Security

OTP requests must be rate limited by:

Phone number
IP address
Device/session

Repeated failures may trigger:

Temporary lock
Additional verification
Security alert

The exact thresholds are configuration values.

OTP must never be returned by the API.

6. Session Security

Access tokens must:

Have limited lifetime

Be transmitted only over HTTPS

Never appear in URLs

Never be logged

Be revocable when necessary

Refresh tokens must be:

Stored securely

Rotated where supported

Revoked on account compromise

Bound to the appropriate session/device context

7. Role-Based Access Control

Supported account types:

CUSTOMER
DRIVER
ADMIN

Superseded (BR-126, 2026-08-26): the fixed SAFETY_ADMIN/FINANCE_ADMIN/
SUPER_ADMIN role list this section originally sketched as an example is
not how admin authorization actually works — there is one Super Admin
level plus granular, per-module permissions on employee ADMIN accounts,
not a fixed role enum. See ADR-0040 for the permission model and
`admin.permissions`' actual shape.

Authorization is enforced server-side.

Example:

Customer A
→ can access Customer A's rides

Customer A
→ cannot access Customer B's rides

Driver A
→ can access rides assigned to Driver A

Driver A
→ cannot access another driver's wallet

8. Resource Ownership

Every resource request must verify ownership or explicit authorization.

Examples:

GET /rides/{ride_id}

requires:

customer_id == authenticated_user

or:

driver_id == authenticated_driver

unless the requester is an authorized administrator.

9. Admin Authorization

Administrative permissions are separated by role.

Example:

SAFETY_ADMIN
→ safety incidents

FINANCE_ADMIN
→ payments and settlements

ADMIN
→ operational support

SUPER_ADMIN
→ privileged configuration

High-risk actions require stronger authorization.

10. Privileged Actions

The following actions require elevated authorization:

Manual GPS dispute decision
Penalty waiver
Financial correction
Refund
Driver suspension
Driver reactivation
Vehicle approval
Promotion configuration
Pricing configuration
Wallet adjustment

Every privileged action must create an audit record.

11. Admin GPS Override

Admin may override GPS verification when supported by evidence.

Required:

Admin identity
Ride ID
Original GPS result
Evidence reviewed
Decision
Reason
Timestamp

Allowed decisions:

APPROVE
REJECT

An admin override does not erase the original GPS data.

It creates an additional decision record.

12. GPS Security

GPS data must be:

Timestamped

Associated with a ride/driver/session

Validated server-side

Protected against obvious spoofed coordinates

Stored according to retention policy

The authoritative GPS verification uses server-side logic.

Verification radius: TBD. PRD.md §62 and business-rules.md §43 explicitly list
the arrival and completion GPS radii as unresolved business decisions — no
approved radius currently exists, and none must be assumed. 50m is used as an
illustrative placeholder elsewhere in this documentation set for worked
examples and test scenarios only; it is not a configured or approved value.
The final radius (for arrival, completion, and early drop) requires an
explicit product/business decision before this control can be implemented.

13. GPS Anomaly Detection

The system should detect suspicious patterns such as:

Impossible movement speed
Large coordinate jumps
Repeated identical coordinates
Missing timestamps
Future timestamps
Old timestamps
GPS accuracy outside configured limits
Location inconsistent with ride progression

An anomaly should trigger:

Flag

rather than automatically accusing the user of fraud.

14. GPS Retry Security

For failed GPS verification, the server allows a configured number of retry
attempts before opening a manual dispute. The exact retry count is TBD — it
is not established in PRD.md or business-rules.md. 3 additional attempts is
used as an illustrative placeholder elsewhere in this documentation set for
worked examples and test scenarios only; it must not be treated as approved
or configured.

After all attempts fail:

Manual dispute

The server controls retry count.

The client cannot reset the retry counter.

15. GPS Dispute Security

NOTE: whether GPS-verification "dispute" handling belongs to a dedicated
Dispute domain, an existing domain (e.g. Verification), or is otherwise
scoped is not yet established in the canonical architecture/domain-design/
database-design/api-contracts/event-contracts/state-machines documents — see
docs/14-decisions/ADR-0002-dispute-domain-status.md. The security controls
below apply regardless of how that is eventually resolved.

When a dispute is opened, VISTAAR preserves:

Driver GPS history
Customer/ride GPS data
Timestamps
Ride details
Uploaded evidence
Admin decision
Admin reason

Evidence submission window: TBD. Not established in PRD.md or business-rules.md.
72 hours is used as an illustrative placeholder elsewhere in this documentation
set for worked examples and test scenarios only; it must not be treated as
approved or configured. The final window requires an explicit product/business
decision.

After the configured evidence window elapses without evidence:

Dispute closes
Original GPS result stands

16. Evidence Security

Uploaded evidence must:

Be virus/malware scanned where applicable

Have size limits

Have MIME/type validation

Use private object storage

Use randomized object names

Be accessible only to authorized parties

Have access logs

Allowed evidence:

Photos
Videos
Documents
Text explanation

Public permanent file URLs must not be used for private dispute evidence.

17. File Upload Security

Never trust the filename or client MIME type.

Validate:

Extension
Actual content type
File signature
File size
Image/video/document parsing

Reject executable content.

Store uploads outside the application executable directory.

18. API Transport Security

Production traffic must use:

HTTPS / TLS

Plain HTTP must redirect or be disabled.

Internal service traffic must also use secure transport where it crosses trust boundaries.

19. API Authentication Headers

Use:

Authorization: Bearer <token>

For mutations requiring idempotency:

Idempotency-Key: <unique-key>

Request tracing:

X-Request-ID: <request-id>

20. API Rate Limiting

Rate limits apply to:

OTP requests
OTP verification
Login attempts
Ride creation
Ride cancellation
Ride offers
Fare changes
Payment creation
Wallet recharge
Cash confirmation
Promotion usage
Referral attachment
Support messages
Evidence uploads
Admin APIs

SOS must have a dedicated high-priority path so ordinary rate limiting does not prevent emergency reporting.

21. Brute-Force Protection

Protect:

OTP verification
Admin login
Payment operations
Wallet operations
Promotion operations

Controls:

Rate limits
Attempt counters
Temporary lockouts
Monitoring
Alerting

22. Idempotency Security

Financial mutations require idempotency.

Examples:

payment creation
cash confirmation
wallet debit
wallet credit
wallet recharge
penalty application
promotion consumption
promotion restoration
referral reward
refund

The same logical request must not create duplicate financial effects.

23. Wallet Security

Wallet balance must never be accepted from the client.

The wallet service calculates:

previous balance
+
credits
-
debits
=
new balance

Every mutation creates an immutable ledger entry.

24. Wallet Transaction Protection

A wallet transaction must use:

Database transaction
Row lock or equivalent concurrency control
Unique idempotency key
Ledger record
Audit information

Example:

BEGIN
 ↓
Lock wallet
 ↓
Validate balance
 ↓
Debit
 ↓
Create ledger transaction
 ↓
Create outbox event
 ↓
COMMIT

25. Negative Wallet Protection

Normal wallet balance cannot become negative.

If a driver owes VISTAAR more than the available balance:

Available balance
→ debit what is available

Remaining amount
→ outstanding settlement

Example:

Wallet = ₹10
VISTAAR charge = ₹30

Debit = ₹10
Outstanding = ₹20

26. Recharge and Outstanding Debt

When a driver recharges:

Recharge succeeds
 ↓
Wallet credit
 ↓
Outstanding settlement recovered

Example:

Recharge = ₹200
Outstanding = ₹30
Remaining available balance = ₹170

The recovery must be recorded as a separate ledger transaction.

27. Payment Gateway Security

PARTIALLY SUPERSEDED (ADR-0025/ADR-0026, 2026-08-25/26 — annotated
2026-09-02, closing the follow-up ADR-0025 §5 itself explicitly flagged
as still outstanding for this section). VISTAAR does not collect the
customer's ride fare at all — there is no ride-fare gateway to secure.
The controls below remain real requirements, but only for whichever
gateway is eventually chosen for (a) driver wallet recharge (ADR-0013
Item 3, still TBD) and (b) customer outstanding-penalty collection
(ADR-0026, still TBD, a separate decision from (a)) — not for the ride
fare, which stays permanently outside any gateway (peer-to-peer,
cash/UPI, ADR-0025).

Payment processing must use a trusted payment provider.

VISTAAR must verify:

Gateway signature
Payment ID
Order/reference ID
Amount
Currency
Payment status

A client-side success screen is not proof of payment.

Only a verified server-side gateway response can establish payment success.

28. Payment Webhook Security

PARTIALLY SUPERSEDED (ADR-0025/ADR-0026, annotated 2026-09-02) — same
scope correction as §27: relevant only to a future driver-recharge or
customer-penalty-collection webhook, never a ride-fare webhook (none
will ever exist).

Webhook endpoint must verify:

Provider signature
Provider event ID
Expected payment reference
Expected amount
Expected currency

Webhook processing must be idempotent.

Duplicate webhooks must not create duplicate:

Payment
Wallet credit
Settlement
Refund

29. Online Payment Flow

SUPERSEDED IN FULL (ADR-0025, 2026-08-25 — annotated 2026-09-02; penalty
settlement mechanism further updated 2026-09-03, ADR-0066). This flow
describes VISTAAR collecting the combined "ride fare + VISTAAR charges"
from the customer — the model ADR-0025 explicitly rejected. The real
flow: the customer pays the Sarthi the ride fare AND any outstanding
VISTAAR penalty directly, combined into one payment (cash/UPI, P2P, no
VISTAAR involvement in the payment itself — ADR-0066, 2026-09-03,
extending ADR-0025's settlement mode to cover the penalty too);
api-contracts.md §12's `outstanding_penalty`/`total_payable` durably
attaches that penalty to the ride at booking, not just displays it, and
§28's `customer_penalty_settled` marks it settled at completion.
VISTAAR recovers its own penalty share separately, server-side, by
debiting the Sarthi's wallet at that same moment
(`TransactionType.CASH_SETTLEMENT`) — never from the customer, and with
no customer-facing payment surface at all; the collection-mechanism
question ADR-0026 §5 originally left open is resolved by ADR-0066, not
by picking a provider but by determining none is needed.

Customer
   ↓
VISTAAR calculates total
   ↓
Customer sees:
Ride fare + VISTAAR charges
   ↓
Customer pays VISTAAR
   ↓
Payment gateway
   ↓
Server verifies payment
   ↓
VISTAAR records payment
   ↓
VISTAAR settlement

The customer must see additional charges before payment.

30. Offline Payment Security

CORRECTED (ADR-0025, annotated 2026-09-02) — the "VISTAAR charge"
component below no longer exists in the expected cash amount. The
driver's platform fee is already debited from their wallet at ride
acceptance (BR-011, unaffected by this correction); nothing about the
customer's cash payment settles it. The example below should now read
"Expected cash = ₹100" (ride fare only) — left as originally written,
struck through only by this note, to preserve the audit trail rather
than silently editing the worked numbers:

Example (ORIGINAL, now inaccurate — see correction above):

Ride fare = ₹100
VISTAAR charge = ₹30
Expected cash = ₹130

Driver can confirm payment only after receiving:

₹130

If driver reports:

₹100

the server rejects full-payment confirmation.

The client cannot override the expected amount.

31. Driver Payment Confirmation

CORRECTED (ADR-0025, annotated 2026-09-02) — this control's own logic
stays valid; only "expected amount" changes meaning, from "ride fare +
VISTAAR charge" to "ride fare only" (no VISTAAR settlement component
exists to include). Not yet implemented anywhere in the real backend as
of this annotation — a driver fare-confirmation endpoint matching this
corrected shape is real, scoped future work, not something this
annotation builds.

The confirmation endpoint must compare:

Driver confirmed amount
==
Server authoritative expected amount

If false:

FULL_PAYMENT_NOT_RECEIVED

No VISTAAR settlement should be finalized through the full-confirmation path.

32. Payment Dispute Rule

CORRECTED (ADR-0025, annotated 2026-09-02) — "Payment" here means the
ride-fare confirmation described in the corrected §31 above, not a
VISTAAR-tracked payment record (none exists). BR-121 already documents
that ride-fare disputes go through the general support/admin process,
consistent with this section's own dispute-review principle.

After driver confirms the full payment:

Payment = CONFIRMED

Normal driver-side payment confirmation is treated as authoritative.

If a dispute is raised:

VISTAAR Admin

may review and override according to the dispute process.

33. Fare Security

Fare must be calculated server-side.

Fare components may include:

Base fare
Distance
Time
Vehicle category
Promotion
Pickup-change charge
Destination extension
Other approved VISTAAR charges

The client may display a quote but cannot alter it.

34. Fare Revision Security

When a fare increases:

Server calculates new fare
 ↓
Customer sees new amount
 ↓
Customer explicitly confirms
 ↓
New fare becomes authoritative

No hidden fare increase is permitted.

35. Pickup Change Security

For pickup change >250m:

Driver chooses PROCEED or PASS

If:

PASS

then:

No ₹30 penalty
No strike
Ride rematched

If:

PROCEED

then:

Additional charge (rate: TBD — business-rules.md BR-076 and PRD.md §20/§62
leave the exact pickup-change rate unresolved; the only discussed figure is
an approximate ₹10–₹20/km range, not an approved rate)
→ Customer sees charge
→ Customer confirms
→ Pickup changes

The pickup-change rate must be a server-side configurable pricing rule once
an explicit business decision establishes its value.

36. Destination Change Security

If the new destination is beyond the original destination:

₹8/km additional charge

The server calculates the amount.

Customer must see and confirm the revised amount before the change becomes effective when a charge is added.

37. Promotion Security

Promotion usage must be protected against:

Double redemption
Race conditions
Expired usage
Unauthorized usage
Replay attacks

Use:

Row locking
Unique constraints
Reservation records
Idempotency
Expiry validation

38. Referral Security

Prevent self-referral through:

Account relationship checks
Phone/account uniqueness
Device/session signals where appropriate
Fraud rules

Referral rewards must be issued only once.

Use a unique reward/qualification key.

39. Driver Offer Security

Driver offer acceptance must be atomic.

Example:

Driver A accepts
Driver B accepts

Only one can transition the ride:

SEARCHING → ACCEPTED

The other receives:

RIDE_ALREADY_ASSIGNED

40. Offer Expiry Security

Offer expiry is controlled server-side.

Client timers are informational only.

The server checks:

expires_at
current server time
offer status
ride status

A client cannot accept an expired offer by manipulating its device clock.

41. Ride State Security

Only authorized domain operations can transition:

SEARCHING
ACCEPTED
ARRIVED
STARTED
COMPLETED
CANCELLED
CLOSED

The client cannot submit:

{
  "status": "COMPLETED"
}

and expect the server to accept it.

42. Cancellation Security

Penalty amounts are calculated server-side.

The client sends:

Cancellation reason

The server determines:

Whether cancellation is allowed
Whether penalty applies
Penalty amount
Whether a strike applies

43. Driver Cancellation Security

Normal driver cancellation:

₹30 penalty
+
strike

Changed-pickup PASS is explicitly exempt:

No ₹30 penalty
No strike

The reason must be recorded to prevent fraudulent use of the exception.

44. Promotion Expiry

Promotion validity:

30 days from grant

The server evaluates expiry.

The client cannot extend the expiration timestamp.

45. Audit Logging

Audit logs are required for:

Admin login
Admin role changes
GPS override
GPS dispute decision
Penalty waiver
Penalty correction
Refund
Wallet adjustment
Pricing configuration
Promotion configuration
Driver suspension
Driver reactivation
Vehicle approval
Document approval
Security configuration changes

46. Audit Log Fields

Minimum:

audit_id
actor_id
actor_role
action
resource_type
resource_id
before_value
after_value
reason
request_id
ip_address where appropriate
timestamp

Sensitive values must be redacted.

47. Immutable Financial Records

Historical financial transactions must not be edited destructively.

If an error occurs:

Original transaction
+
Compensating transaction

Example:

Incorrect debit ₹30
        ↓
Compensating credit ₹30

The original transaction remains visible in the audit trail.

48. Secrets Management

Secrets must not be stored in:

Source code
Git repository
Mobile application
Logs
Public configuration

Use a secure secret manager/environment configuration.

Examples:

Database credentials
JWT secrets
Payment gateway secrets
Kafka credentials
Object-storage credentials
SMS provider secrets
AI provider keys

49. Environment Separation

Use separate environments:

development
staging
production

Credentials and databases must not be shared between environments.

Production data should not be copied into development without approved anonymization.

50. Database Security

Database access must follow least privilege.

Application services should receive only the permissions they need.

Production database should not be directly exposed to the public internet.

Use:

Private network
Firewall/security groups
TLS where applicable
Restricted service accounts

51. SQL Injection Protection

Use parameterized queries/ORM APIs.

Never construct SQL using untrusted strings.

Bad:

"SELECT * FROM rides WHERE id = " + user_input

Good:

Parameterized query

52. Object-Level Authorization

Prevent IDOR/BOLA vulnerabilities.

For every:

/ride/{id}
/wallet/{id}
/payment/{id}
/support/{id}
/evidence/{id}

the server must verify that the authenticated user has access to that exact resource.

53. Mass Assignment Protection

Do not bind arbitrary JSON fields directly to database models.

For example, a customer request must not be able to submit:

{
  "wallet_balance": 100000,
  "role": "ADMIN",
  "status": "COMPLETED"
}

Only allow-listed fields are accepted.

54. Input Validation

Validate:

Coordinates
Amounts
IDs
Enums
Dates
File types
Text length
Pagination
Sorting
Phone numbers
Vehicle registration

Reject invalid input before business processing.

55. Monetary Amount Validation

Use integer minor units or a precise decimal representation.

For INR:

₹30

must not depend on binary floating-point arithmetic.

Recommended:

amount_paise = 3000

or a database numeric/decimal type with strict rules.

56. Currency Validation

All financial records include:

currency = INR

Do not allow the mobile client to choose arbitrary currencies.

57. Location Privacy

Location data is sensitive.

Access should be limited according to purpose.

Examples:

Active ride
→ Customer can see assigned driver's relevant location

Driver
→ Can see required customer/pickup information

Admin
→ Can access authorized historical location data

Unrelated user
→ No access

58. Location Retention

Exact retention period is a configurable policy decision.

Retention should balance:

Safety
Dispute resolution
Fraud prevention
Legal/compliance requirements
Privacy
Storage cost

Expired location data should be deleted or anonymized according to the final retention policy.

59. Data Minimization

Only collect information required for:

Identity
Ride operation
Payment
Safety
Verification
Support
Legal obligations
Analytics where appropriately governed

Do not collect unnecessary personal data.

60. Password Policy

Where passwords are introduced for administrative accounts:

Use strong password requirements

Hash with a modern password hashing algorithm

Never store plaintext passwords

Rate-limit login attempts

Require MFA for privileged accounts

61. Admin MFA

IMPLEMENTED (ADR-0051, 2026-08-28) — TOTP (RFC 6238), self-service/
opt-in enrollment via `POST /api/v1/auth/mfa/enroll`/`confirm`/`verify`/
`disable` (api-contracts.md §7.3). A generic identity-layer capability,
not gated to a specific admin tier — the fixed SUPER_ADMIN/
FINANCE_ADMIN/SAFETY_ADMIN role list below predates and is superseded by
ADR-0040's real permission model (one Super Admin level + granular
per-module permissions, no fixed role set — see security.md §7's own
correction). Enrollment is not mandatory for any admin; making it
mandatory for some or all admins remains an open policy question ADR-
0051 does not resolve.

Privileged administrative accounts should use MFA.

Especially (original, now-superseded example list — see the
IMPLEMENTED note above):

SUPER_ADMIN
FINANCE_ADMIN
SAFETY_ADMIN

High-risk financial actions may require step-up authentication.

62. CSRF Protection

For browser-based authenticated sessions using cookies:

CSRF protection
SameSite cookies
Secure cookies
HttpOnly cookies

For bearer-token APIs without browser cookies, use appropriate token-based protections.

63. CORS

Production CORS must allow only approved application origins.

Avoid:

Access-Control-Allow-Origin: *

for authenticated APIs.

64. Security Headers

Web interfaces should use appropriate headers such as:

Content-Security-Policy
X-Content-Type-Options
Referrer-Policy
Strict-Transport-Security
Frame restrictions

Exact policy depends on the deployed frontend architecture.

Implementation status (ADR-0036, 2026-08-25): IMPLEMENTED —
`shared/security_headers.py`'s `SecurityHeadersMiddleware`, registered
in `main.py`, applies all five headers to every response except the
interactive-docs paths (`/docs`, `/redoc`, `/openapi.json`), which are
exempt from Content-Security-Policy only (FastAPI's built-in Swagger/
ReDoc pages load their own JS/CSS from a CDN and would break under the
strict `default-src 'none'` policy applied everywhere else) — see the
ADR for why CSP specifically needed a judgment call while the other
four headers did not.

65. Logging Security

Never log:

OTP
Access tokens
Refresh tokens
Payment credentials
Private keys
Full identity documents
Sensitive evidence contents

Logs may contain:

User/driver ID
Ride ID
Payment ID
Request ID
Event ID
Error code

where operationally necessary.

66. Monitoring

IMPLEMENTED (ADR-0053, 2026-08-28) — the underlying infrastructure only:
Sentry (application error tracking, `SENTRY_DSN` empty/disabled by
default until a real account exists), Prometheus (`GET /metrics`, real
and functional immediately, no credential needed), and self-hosted
Grafana (dashboards over Prometheus). None of the specific business-
signal detections listed below are wired as alerts yet — no source
document specifies the thresholds/routing that would require (ADR-0053
Decision 5), so none were invented; this ADR built the pipes, not the
alert rules.

Security monitoring should detect:

Repeated OTP failures
Unusual login patterns
Large wallet activity
Repeated payment failures
Repeated promotion attempts
Referral abuse
Impossible GPS movement
Repeated GPS anomalies
Excessive cancellations
Suspicious driver behavior
Admin privilege changes
Repeated API authorization failures

67. Fraud Prevention

Fraud detection should use multiple signals.

Examples:

Account history
Device/session signals
IP patterns
Payment behavior
GPS anomalies
Cancellation patterns
Promotion usage
Referral relationships
Wallet activity

Fraud detection should flag suspicious behavior for review where confidence is insufficient.

Do not automatically punish solely from an uncertain fraud score.

68. Driver Fraud Controls

Monitor:

Repeated offer manipulation
GPS spoofing indicators
Unusual cancellation rate
Unusual route behavior
Cash-payment disputes
Promotion abuse
Referral abuse
Impossible travel

The system may flag the driver for review.

69. Customer Fraud Controls

Monitor:

Repeated cancellation abuse
Promotion abuse
Referral abuse
Payment abuse
False dispute patterns
Multiple suspicious accounts

Actions must follow the approved policy.

70. Payment Fraud Controls

Monitor:

Repeated failed payments
Multiple accounts using suspicious payment instruments
Unusual refund patterns
Rapid payment/reversal patterns
High-risk transactions

Payment-provider fraud tools should be used where available.

71. Security Incident Response

Incident workflow:

Detect
 ↓
Classify
 ↓
Contain
 ↓
Investigate
 ↓
Remediate
 ↓
Recover
 ↓
Post-incident review

Critical incidents include:

Account takeover
Payment compromise
Wallet manipulation
Credential leakage
Database exposure
Admin compromise
Mass API abuse

72. Account Compromise

If an account is suspected compromised:

Revoke sessions
Invalidate refresh tokens
Require re-authentication
Review sensitive actions
Notify user where appropriate
Investigate related activity

For privileged accounts:

Immediate suspension
+
security review

73. Dependency Security

Production dependencies must be:

Version controlled
Regularly scanned
Patched
Reviewed for known vulnerabilities

Use automated dependency vulnerability scanning in CI.

74. Container Security

If Docker/container deployment is used:

Use minimal base images

Do not run as root where avoidable

Scan images

Pin important dependency versions

Do not embed secrets

Restrict container permissions

75. CI/CD Security

CI/CD must include:

Secret scanning
Dependency scanning
Static analysis
Unit tests
Security tests
Container scanning where applicable

Production deployment should require controlled authorization.

76. Code Review

Changes involving:

Payments
Wallet
Authentication
Authorization
Penalties
Promotions
Referrals
GPS verification
Admin permissions
Security configuration

require mandatory code review.

77. Security Testing

Security testing must include:

Authentication tests
Authorization tests
IDOR/BOLA tests
Rate-limit tests
Injection tests
CSRF tests where applicable
File-upload tests
JWT/session tests
Payment webhook tests
Wallet concurrency tests
Race-condition tests
Replay tests
Privilege-escalation tests

78. Financial Concurrency Testing

Test:

Two wallet debits at once
Two cash confirmations
Two payment webhooks
Two promotion reservations
Two referral rewards
Two ride acceptances

Expected behavior:

Exactly one valid business effect

No duplicate financial effect is permitted.

79. Backup Security

Backups must be:

Encrypted
Access controlled
Monitored
Tested for restoration

Backup credentials must be separate from application credentials.

80. Disaster Recovery

Critical services should have documented recovery procedures for:

Database failure
Kafka failure
Payment-provider outage
Redis failure
Object-storage failure
Authentication outage

Financial records must be recoverable without duplicate settlement.

81. Payment Provider Failure

If the payment gateway is unavailable:

Do not mark payment successful
Do not release financial effects based only on client state
Show retry/failure state

Webhook reconciliation should recover payments that were successful at the provider but temporarily unavailable to VISTAAR.

82. Kafka Failure

If Kafka is temporarily unavailable:

Business transaction may still commit
Outbox event remains unpublished
Publisher retries later

Core database state must not be lost because Kafka is unavailable.

83. Redis Failure

Redis is not the authoritative source for:

Wallet
Payment
Ride state
Financial ledger

If Redis fails, authoritative PostgreSQL state remains intact.

Realtime/matching behavior may degrade until Redis recovers.

84. Database Failure

The application must fail safely.

Do not:

Assume payment succeeded
Assume wallet debit succeeded
Assume ride completed

when the authoritative transaction cannot be confirmed.

85. Security Configuration

Security-sensitive values should be configurable:

OTP expiry
OTP retry limits
API rate limits
GPS anomaly thresholds
Promotion expiry
Session expiry
Payment timeout
Admin session timeout
Evidence size limits

Business values such as:

₹8/km destination extension
₹30 driver cancellation penalty
₹15 customer cancellation penalty
250m pickup-change threshold

must be server-side controlled and versioned. The pickup-change rate is a
further such value but is not yet approved — see PRD.md §62 and
business-rules.md §43 (discussed range: ₹10–₹20/km, no final figure).

86. Configuration Change Security

Pricing and policy configuration changes require:

Authorized admin
Reason
Old value
New value
Timestamp
Admin identity
Audit record

Where financially significant, configuration changes should be versioned so historical rides continue to use the correct pricing version.

87. Historical Pricing

A completed ride must retain the pricing rules/version used when the fare was calculated.

Example (illustrative only — pickup_change_rate is not yet approved; see
PRD.md §62 and business-rules.md §43):

fare_rule_version = 3
pickup_change_rate = <TBD>/km
destination_extension_rate = ₹8/km

Changing future configuration must not silently rewrite historical fares.

88. Security Invariants

Client input is never authoritative.

Financial records are immutable.

Wallet balances cannot be directly set by clients.

Payment success requires server verification.

Cash confirmation requires full authoritative amount.

Admin overrides are audited.

GPS evidence cannot be deleted by users.

Privileged actions are audited.

Sensitive data is encrypted/protected.

All critical mutations are idempotent.

Object-level authorization is mandatory.

Production secrets never live in source code.

No admin API response ever includes a provider credential, password,
cloud secret, database credential, or private key — added 2026-08-26
as an explicit invariant (owner decision, ADR-0044 §4/ADR-0048 §5:
Notification Templates and Settings) rather than left implicit; the
generic `admin.settings` key-value table and `notification.templates`
content columns are the two places this codebase now has where a
careless future addition could otherwise leak one.

Invalid state transitions are rejected.

Security failures fail closed where practical.

Historical financial/rule data remains traceable.

89. Open Security Configuration

The following are implementation/configuration choices rather than unresolved business rules:

Exact OTP expiry
Exact API rate limits
JWT/access-token lifetime
Refresh-token lifetime
Exact location retention period
Exact evidence retention period
Exact fraud thresholds
Exact backup retention
Exact Kafka retention
Exact admin session timeout
Exact MFA provider — RESOLVED (ADR-0051, 2026-08-28): TOTP (RFC 6238,
  via pyotp), no external provider — a standard authenticator app
  implements the same RFC client-side
Exact payment gateway
Exact secret manager

These should be finalized during infrastructure/security implementation without changing the approved VISTAAR business model.

90. Security Document Status

Version: 1.0
Status: Draft
Derived from: PRD, Business Rules, Technical Architecture, Domain Design, Database Design, API Contracts, Event Contracts, State Machines, and finalized business decisions.

91. Security Review History

A code-level review pass against this document's controls was performed
2026-09-02 — see `docs/08-security/security-review-2026-09-02.md`. It
found and fixed two real issues (a JWT_SECRET placeholder that could
silently reach production; Sentry not explicitly configured to avoid
capturing Authorization/Cookie headers) and one open, unfixed gap
requiring a decision (§20's rate limiting exists only for OTP request/
verify, not the ~13 other endpoint categories this section lists). That
review covered a targeted subset of this document's 90 sections, not all
of them — see its own §6 for exactly what a further pass still needs to
check. This document's own Status stays Draft: a review pass is not the
same as the "security approved" production-readiness gate.
