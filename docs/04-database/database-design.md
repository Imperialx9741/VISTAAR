VISTAAR — Database Design

Document Version: 1.0
Status: Draft — Derived from PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, and Domain Design v1.0
Database: PostgreSQL 15+
Spatial: PostGIS 3.4+
Currency: INR (₹)

1. Purpose

This document defines the production database model for VISTAAR.

It translates the domain boundaries into:

Tables

Columns

Primary keys

Foreign keys

Enums

Relationships

Constraints

Indexes

Financial ledgers

Idempotency controls

Audit records

Migration order

The database must preserve the business invariants defined in the PRD and Business Rules.

2. Database Principles

2.1 PostgreSQL is the durable source of truth

PostgreSQL owns durable business state.

Redis is not the source of truth for:

Wallet balance

Payment status

Ride lifecycle

Promotions

Penalties

2.2 PostGIS

PostGIS is used for:

Pickup coordinates

Destination coordinates

GPS verification

Spatial queries

Geo-fencing

2.3 Redis

Redis is used for:

Online driver GEO index

Short-lived driver availability

Request timers

Real-time state

Cache

2.4 Kafka

Kafka is used for:

Domain events

Asynchronous projections

Notifications

Reconciliation workflows

3. PostgreSQL Schemas

Use logical schemas to separate domains:

identity
customer
driver
vehicle
ride
matching
pricing
wallet
payment
promotion
referral
penalty
verification
safety
notification
support
advertisement
admin
shared

Each service/domain owns its schema.

Cross-schema foreign keys should be used selectively. Critical ownership should remain clear even if all schemas live in one PostgreSQL cluster.

4. Shared Types

Recommended UUID primary keys:

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

Money:

NUMERIC(12,2)

Never use floating-point types for money.

Timestamps:

TIMESTAMPTZ

Coordinates:

GEOMETRY(Point, 4326)

5. Identity Tables

5.1 identity.accounts

CREATE TABLE identity.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_type VARCHAR(20) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Allowed account types:

CUSTOMER
DRIVER
ADMIN

5.2 identity.otp_challenges

CREATE TABLE identity.otp_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES identity.accounts(id),
    account_type VARCHAR(20) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

account_type and max_attempts were added during Phase 2 / Task 2.1
(Identity & Authentication Foundation) — not in the original table above.
account_type records the account type chosen when the OTP was requested,
so it does not need to be (and per api-contracts.md §7 is not) resent by
the client at Verify OTP time — necessary for creating a new account with
the right type on first-ever verification for a phone number, since
account_id is null until then. max_attempts is stored per-challenge
(rather than only as a global setting) so a challenge's attempt limit is
fixed at issuance time even if the global configuration changes later.

Indexes:

CREATE INDEX idx_otp_phone_status
ON identity.otp_challenges(phone, status);

5.3 identity.sessions

Added during Phase 2 / Task 2.1 (Identity & Authentication Foundation) —
not in the original identity schema. Backs refresh-token issuance/rotation
and logout/revocation (domain-design.md §5.3's RefreshSession/Logout
commands; security.md §6's "Refresh tokens must be ... Rotated ...
Revoked on account compromise").

CREATE TABLE identity.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES identity.accounts(id),
    refresh_token_hash VARCHAR(180) UNIQUE NOT NULL,
    device_metadata TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Only a SHA-256 hash of the refresh token is stored, never the token
itself (security.md §4: "Never stored in plaintext where avoidable").

Indexes:

CREATE INDEX idx_sessions_account
ON identity.sessions(account_id);

5.4 identity.mfa_credentials (ADR-0051, 2026-08-28)

A generic, account-type-agnostic TOTP credential store — not admin-
specific at the schema level, even though only admin accounts enroll
today (ADR-0051 Decision 1). At most one row per account (account_id is
the primary key, not a separate id column).

CREATE TABLE identity.mfa_credentials (
    account_id UUID PRIMARY KEY REFERENCES identity.accounts(id),
    secret VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING | ACTIVE
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

`secret` is stored as plain base32 text, not application-level
encrypted — no envelope-encryption/KMS infrastructure exists anywhere in
this codebase for any field; every other secret-shaped value (JWT
signing key, MSG91/S3 credentials) lives in environment configuration,
never a database column. Building one now, for this one column, would be
new infrastructure beyond "add MFA" — flagged explicitly in ADR-0051
Decision 2 as a disclosed scope trim, the same class ADR-0035 already
made for production-grade secret management.

6. Customer Tables

6.1 customer.customers

CREATE TABLE customer.customers (
    id UUID PRIMARY KEY REFERENCES identity.accounts(id),
    full_name VARCHAR(150),
    profile_photo_uri TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

6.2 customer.preferences

CREATE TABLE customer.preferences (
    customer_id UUID PRIMARY KEY REFERENCES customer.customers(id),
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    notification_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

7. Driver Tables

7.1 driver.drivers

CREATE TABLE driver.drivers (
    id UUID PRIMARY KEY REFERENCES identity.accounts(id),
    full_name VARCHAR(150) NOT NULL,
    profile_photo_uri TEXT,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    operational_status VARCHAR(30) NOT NULL DEFAULT 'OFFLINE',
    strikes INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

7.2 driver.documents

CREATE TABLE driver.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    document_type VARCHAR(40) NOT NULL,
    document_number VARCHAR(100),
    evidence_uri TEXT,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Indexes:

CREATE INDEX idx_driver_documents_expiry
ON driver.documents(expires_at);

CREATE INDEX idx_driver_documents_driver
ON driver.documents(driver_id);

8. Vehicle Tables

8.1 vehicle.vehicles

CREATE TABLE vehicle.vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    category VARCHAR(20) NOT NULL,
    cab_tier VARCHAR(20),  -- added 2026-08-24, ADR-0020: CAB-only sub-tier
                            -- (ECO/PREMIUM/PREMIUM_PLUS), NULL for every other
                            -- category. Self-declared by the driver at creation.
    registration_number VARCHAR(30) UNIQUE NOT NULL,
    make VARCHAR(100),
    model VARCHAR(100),
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    operational_status VARCHAR(20) NOT NULL DEFAULT 'INACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Allowed categories:

BIKE
AUTO
CAB

Indexes:

CREATE INDEX idx_vehicles_driver
ON vehicle.vehicles(driver_id);

CREATE INDEX idx_vehicles_category_status
ON vehicle.vehicles(category, verification_status, operational_status);

Added by the Vehicle Lifecycle decision (business-rules.md BR-122,
domain-design.md §8.4): a partial unique index enforcing "at most one
ACTIVE vehicle per driver" at the database level, so the invariant holds
even under concurrent activation requests — application-level row
locking (see the Vehicle Activation Transaction below) is the primary
mechanism; this index is the unconditional backstop.

CREATE UNIQUE INDEX uq_vehicles_one_active_per_driver
ON vehicle.vehicles(driver_id)
WHERE operational_status = 'ACTIVE';

8.1.1 Vehicle Activation Transaction

Activating a vehicle is atomic and enforces BR-122:

BEGIN
 ↓
Lock all of this driver's vehicles (SELECT ... FOR UPDATE)
 ↓
Verify the target vehicle exists, belongs to this driver, and is
verification_status = APPROVED
 ↓
Verify the driver is not ONLINE or ON_RIDE
 ↓
Deactivate any other vehicle for this driver currently ACTIVE
 ↓
Activate the target vehicle
 ↓
COMMIT

If two activation requests for the same driver race, the row lock
serializes them; the losing request proceeds only after the winning one
commits, and re-reads the now-current state before applying its own
change. uq_vehicles_one_active_per_driver guarantees no interleaving can
ever leave two rows ACTIVE for the same driver_id even if the locking
above were bypassed.

8.2 vehicle.documents

CREATE TABLE vehicle.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id UUID NOT NULL REFERENCES vehicle.vehicles(id),
    document_type VARCHAR(40) NOT NULL,
    document_number VARCHAR(100),
    evidence_uri TEXT,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

9. Ride Tables

9.1 ride.rides

CREATE TABLE ride.rides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    customer_id UUID NOT NULL REFERENCES customer.customers(id),
    driver_id UUID REFERENCES driver.drivers(id),
    vehicle_id UUID REFERENCES vehicle.vehicles(id),

    status VARCHAR(30) NOT NULL,
    requested_vehicle_category VARCHAR(20) NOT NULL,
    requested_cab_tier VARCHAR(20),  -- added 2026-08-24, ADR-0020: mirrors
                                      -- vehicle.vehicles.cab_tier — required when
                                      -- requested_vehicle_category is CAB, NULL
                                      -- otherwise. Customer-selected at booking.

    original_pickup GEOMETRY(Point, 4326) NOT NULL,
    current_pickup GEOMETRY(Point, 4326) NOT NULL,

    original_destination GEOMETRY(Point, 4326) NOT NULL,
    current_destination GEOMETRY(Point, 4326) NOT NULL,

    active_fare_quote_id UUID,

    -- IMPLEMENTED (ADR-0057, 2026-08-31, migration a3f7c8d1e2b4) —
    -- Schedule a Ride / Book for Someone Else. All four NULL for every
    -- ordinary ride; zero behavior change to the existing flow.
    scheduled_for TIMESTAMPTZ,     -- customer-chosen future pickup time;
                                    -- NULL means an ordinary immediate ride
    lock_in_at TIMESTAMPTZ,        -- = scheduled_for - 30 minutes, computed
                                    -- and stored at scheduling time so the
                                    -- polling task can index/query it cheaply
    linked_contact_name VARCHAR(200),
    linked_contact_phone VARCHAR(20),  -- both set together or both NULL;
                                        -- required together when the booker
                                        -- names someone else (Book for
                                        -- Someone Else)

    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    arrived_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- IMPLEMENTED (ADR-0057) — supports the Beat task's (modules/ride/
-- tasks.py) "find SCHEDULED rides whose lock_in_at has arrived" poll
-- efficiently.
CREATE INDEX idx_rides_lock_in_at
ON ride.rides(lock_in_at) WHERE status = 'SCHEDULED';

`requested_vehicle_category` added by Phase 3 / Task 3.2 (ADR-0011
Decision 1) — not present when this table was first created in Task 3.1
(ADR-0010 §8 flagged the gap and deferred the decision to whichever task
first built Matching).

Spatial indexes:

CREATE INDEX idx_rides_pickup_geo
ON ride.rides USING GIST(original_pickup);

CREATE INDEX idx_rides_destination_geo
ON ride.rides USING GIST(original_destination);

9.2 ride.state_history

CREATE TABLE ride.state_history (
    id BIGSERIAL PRIMARY KEY,
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    reason VARCHAR(100),
    actor_type VARCHAR(30),
    actor_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Every authoritative ride-state transition must create a history record.

10. Ride Offers

10.1 matching.ride_offers

CREATE TABLE matching.ride_offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    vehicle_id UUID NOT NULL REFERENCES vehicle.vehicles(id),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    expires_at TIMESTAMPTZ NOT NULL,
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Offer statuses:

PENDING
ACCEPTED
REJECTED
EXPIRED
CANCELLED

Indexes:

CREATE INDEX idx_offers_driver_status
ON matching.ride_offers(driver_id, status);

CREATE INDEX idx_offers_ride_status
ON matching.ride_offers(ride_id, status);

CREATE INDEX idx_offers_expiry
ON matching.ride_offers(expires_at)
WHERE status = 'PENDING';

The application must enforce the 20-second expiration.

11. Ride Change Requests

11.1 ride.change_requests

CREATE TABLE ride.change_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    request_type VARCHAR(30) NOT NULL,
    requested_by UUID NOT NULL,
    old_location GEOMETRY(Point, 4326),
    new_location GEOMETRY(Point, 4326),
    old_fare_quote_id UUID,
    new_fare_quote_id UUID,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    driver_decision VARCHAR(30),
    customer_decision VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

Request types:

PICKUP_CHANGE
DESTINATION_CHANGE

Implementation status: IMPLEMENTED for both PICKUP_CHANGE and
DESTINATION_CHANGE (ADR-0033, 2026-08-25 and ADR-0033 Decision 9,
2026-08-25 respectively) — table unmodified from what was already
documented here; no migration was needed for DESTINATION_CHANGE since
the schema was deliberately kept unified from the start. ADR-0056
(owner decision, 2026-08-31) simplified pickup change to a flat 100m
hard threshold with no driver decision — no PICKUP_CHANGE row is ever
created anymore, either within or beyond the threshold (previously,
only the ≤threshold case skipped the row). The table/columns
themselves are unmodified — `status='AWAITING_DRIVER_DECISION'`/
`'PASSED'` and any non-null `driver_decision` remain valid values only
for a PICKUP_CHANGE row that predates ADR-0056; DESTINATION_CHANGE is
unaffected and continues to use this table exactly as before.

12. Early Drop

12.1 ride.early_drop_requests

CREATE TABLE ride.early_drop_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    requested_by UUID NOT NULL,
    reason VARCHAR(100),  -- added 2026-08-25, ADR-0030 Decision 4: api-
                          -- contracts.md §27's documented Request body
                          -- includes `reason`, with nowhere in the
                          -- original schema to store it otherwise — same
                          -- gap ADR-0022 Decision 1 already fixed for
                          -- support.cases.ride_id.
    customer_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    driver_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    gps_location GEOMETRY(Point, 4326),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

Implementation status (Phase 08, ADR-0030, 2026-08-25): COMPLETE. No
`result`/status column exists here because none is needed — GPS/location
is recorded as evidence only, never verified against a threshold (see
the ADR for the full reconciliation against state-machines.md §19-21's
added verification-gate language, which this schema's own shape already
contradicted before this task: there was never a column here to store a
PASS/FAIL result in).

13. OTP for Ride Start

13.1 ride.ride_otps

CREATE TABLE ride.ride_otps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    otp_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Only the latest valid OTP can start the ride.

14. GPS Verification

14.1 ride.gps_verifications

CREATE TABLE ride.gps_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    verification_type VARCHAR(30) NOT NULL,
    latitude NUMERIC(10,7) NOT NULL,
    longitude NUMERIC(10,7) NOT NULL,
    reference_latitude NUMERIC(10,7),
    reference_longitude NUMERIC(10,7),
    distance_meters NUMERIC(12,3),
    result VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Verification types:

ARRIVAL
COMPLETION
EARLY_DROP

Implementation status (§13/§14, Phase 06/07, ADR-0028): COMPLETE — both
tables match the schema above exactly (migration
9d0f47a4fe18_gps_verifications_and_ride_otps). This task's code only
ever writes ARRIVAL/COMPLETION rows to gps_verifications; EARLY_DROP is
reserved for a future Early Drop task (§27) that hasn't been built.

14.2 ride.gps_disputes

CREATE TABLE ride.gps_disputes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    gps_verification_id UUID NOT NULL REFERENCES ride.gps_verifications(id),
    verification_type VARCHAR(30) NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evidence_deadline TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    decision VARCHAR(20),
    decided_by UUID,
    decided_reason VARCHAR(500),
    decided_at TIMESTAMPTZ
);

14.3 ride.gps_dispute_evidence

CREATE TABLE ride.gps_dispute_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dispute_id UUID NOT NULL REFERENCES ride.gps_disputes(id),
    submitted_by UUID NOT NULL,
    evidence_type VARCHAR(20) NOT NULL,
    uri TEXT,
    text_explanation TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Implementation status (§14.2/§14.3, BR-124/BR-125, ADR-0032, 2026-08-25):
COMPLETE. `gps_verification_id` always references the exact terminal-FAIL
row (BR-124: "the original failed GPS verification record is not erased
or altered"). `status`: OPEN, RESOLVED, EXPIRED (state-machines.md §69).
`decision`/`decided_by`/`decided_reason`/`decided_at` are all NULL until
RESOLVED. `submitted_by` is a bare UUID, no foreign key — the same
polymorphic-actor precedent as `penalty.penalties.user_id`/
`support.cases.user_id` (either the ride's customer or driver).
`evidence_type` values: PHOTO, VIDEO, DOCUMENT, TEXT (BR-125) — `uri` set
for the first three, `text_explanation` set for TEXT.

15. Pricing Tables

15.1 pricing.fare_rules

CREATE TABLE pricing.fare_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_category VARCHAR(20) NOT NULL,
    base_fare NUMERIC(12,2) NOT NULL,
    per_km NUMERIC(12,2) NOT NULL,
    per_minute NUMERIC(12,2) NOT NULL,
    waiting_per_minute NUMERIC(12,2) NOT NULL DEFAULT 0,
    minimum_fare NUMERIC(12,2) NOT NULL,  -- added 2026-08-24, ADR-0020: the
                                           -- floor on base_fare + distance charge;
                                           -- the table's own "Minimum fare" line
                                           -- item had no column otherwise.
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | IN_REVIEW | PUBLISHED
                                                   -- (ADR-0042, replaces `active`)
    effective_from TIMESTAMPTZ,  -- NULL until Publish (ADR-0042 Decision 2)
    effective_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Exact fare values remain TBD.

(Resolved 2026-08-24 — ADR-0020: seeded via migration 61a5a80a044e with the
owner-approved rates (business-rules.md BR-005's table), keyed by vehicle_category
= BIKE / AUTO / CAB_ECO / CAB_PREMIUM / CAB_PREMIUM_PLUS — an engineering choice
for this already-generic VARCHAR(20) key's content, not a schema change.)

Fare Management Workflow (ADR-0042, 2026-08-26): `status` replaces the
original `active` boolean — "is this rule live" is now
`status = 'PUBLISHED' AND effective_from <= now() AND (effective_until
IS NULL OR effective_until > now())`, computed at query time rather
than stored as an independent column that could disagree with it.
Migration d9a2976f73d9 backfills every previously `active = TRUE` row
to `status = 'PUBLISHED'` before dropping `active`, so no live rate
changes as a result of this migration. `effective_from` is nullable —
a DRAFT/IN_REVIEW row has none yet; Publish is the action that sets it
(defaulting to "now," or a caller-supplied future rollout moment) and,
in the same operation, closes out the previously-published rule for
that `vehicle_category` by setting its own `effective_until` to the
new rule's `effective_from` — at most one rule is ever live per
category.

15.2 pricing.fare_quotes

CREATE TABLE pricing.fare_quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    version INT NOT NULL,

    base_fare NUMERIC(12,2) NOT NULL DEFAULT 0,
    distance_charge NUMERIC(12,2) NOT NULL DEFAULT 0,
    time_charge NUMERIC(12,2) NOT NULL DEFAULT 0,
    waiting_charge NUMERIC(12,2) NOT NULL DEFAULT 0,
    parking_charge NUMERIC(12,2) NOT NULL DEFAULT 0,
    toll_charge NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    promotion_discount NUMERIC(12,2) NOT NULL DEFAULT 0,
    additional_charge NUMERIC(12,2) NOT NULL DEFAULT 0,

    total NUMERIC(12,2) NOT NULL,

    reason VARCHAR(50),
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Unique:

CREATE UNIQUE INDEX uq_fare_quote_version
ON pricing.fare_quotes(ride_id, version);

ADR-0057, 2026-08-31 (Schedule a Ride): a SCHEDULED ride's quote reuses
`reason = 'INITIAL_QUOTE'` completely unchanged — genuinely no new
`reason` value needed. `calculate_fare()` already runs unconditionally
right after ride creation regardless of status, so this row is created
as `version 1` at scheduling time (before the ride's own `SEARCHING`
entry, unlike every other quote here today) simply by virtue of when
that already-unconditional call happens, not because of any change to
it. `total` is what `ride.rides.active_fare_quote_id` locks onto
immediately — never
recomputed even if `pricing.fare_rules` changes before the ride
actually happens.

15.3 pricing.platform_fee_rules (ADR-0045, 2026-08-26, implemented)

The per-vehicle-category platform fee (BR-011/BR-131), debited at
Accept Offer time. Seeded BIKE ₹2 / AUTO ₹5 / CAB ₹10 at migration
time — the old hardcoded `dict[VehicleCategory, Decimal]` in
`matching/router.py` remains only as a last-resort fallback if no
PUBLISHED row exists for a category. A
separate table from §15.1, not an additive column on it — a driver-
side platform fee and a customer-facing fare are different concepts
that happen to share a versioning shape (same reasoning ADR-0041 §7
and ADR-0043 §2 already apply to their own table pairs), and their key
granularity already differs: 3 keys here (BIKE/AUTO/CAB, uniform
across every CAB tier per BR-011) vs. §15.1's 5 keys
(BIKE/AUTO/CAB_ECO/CAB_PREMIUM/CAB_PREMIUM_PLUS).

CREATE TABLE pricing.platform_fee_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_category VARCHAR(20) NOT NULL,
    fee_amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | IN_REVIEW | PUBLISHED
    effective_from TIMESTAMPTZ,  -- NULL until Publish
    effective_until TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Identical DRAFT → IN_REVIEW → PUBLISHED lifecycle to §15.1 (ADR-0042):
Publish closes out the previously-live rule for the same
`vehicle_category`, at most one live per category. The already-
immutable `wallet.transactions` row Accept Offer writes (§17.2) is
why historical rides never change once this ships — only the *lookup*
Accept Offer performs needs to move from the hardcoded dict to this
table.

16. Pricing Configuration

16.1 pricing.additional_charge_rules

CREATE TABLE pricing.additional_charge_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_type VARCHAR(50) NOT NULL,
    vehicle_category VARCHAR(20),
    threshold_meters NUMERIC(12,2),
    amount_per_km NUMERIC(12,2),
    fixed_amount NUMERIC(12,2),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_until TIMESTAMPTZ
);

Current approved rules include:

Pickup change threshold = 250m
Destination extension = ₹8/km

The exact pickup-change rate remains TBD.

17. Wallet Tables

17.1 wallet.wallets

CREATE TABLE wallet.wallets (
    driver_id UUID PRIMARY KEY REFERENCES driver.drivers(id),
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02, IMPLEMENTED,
    -- migration d4e8f1a52c6b): whether this driver has already used
    -- their one allowed ride-acceptance while balance <= ₹20
    -- (LOW_BALANCE_THRESHOLD). Reset to false by any credit that
    -- brings the balance back above the threshold.
    low_balance_grace_ride_used BOOLEAN NOT NULL DEFAULT false,
    -- Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062, 2026-09-03,
    -- IMPLEMENTED, migration f2a9c6e18b3d): the unpaid portion of a
    -- driver-cancellation penalty the balance couldn't cover at
    -- cancellation time (WalletService.debit_or_record_as_debt()).
    -- Never partially debited from `balance` — recovered automatically
    -- from this driver's next WALLET_RECHARGE credit only
    -- (WalletService.credit()). Independent of low_balance_grace_ride_
    -- used above — an outstanding debt does not, by itself, affect
    -- ride-acceptance eligibility.
    outstanding_debt NUMERIC(12,2) NOT NULL DEFAULT 0,
    CONSTRAINT wallet_balance_nonnegative CHECK (balance >= 0),
    CONSTRAINT wallet_outstanding_debt_nonnegative CHECK (outstanding_debt >= 0)
);

17.2 wallet.transactions

CREATE TABLE wallet.transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    ride_id UUID REFERENCES ride.rides(id),

    transaction_type VARCHAR(50) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    direction VARCHAR(10) NOT NULL,

    balance_before NUMERIC(12,2) NOT NULL,
    balance_after NUMERIC(12,2) NOT NULL,

    idempotency_key VARCHAR(180) UNIQUE NOT NULL,
    reference_type VARCHAR(50),
    reference_id UUID,
    metadata JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Direction:

CREDIT
DEBIT

Transaction types may include:

PLATFORM_FEE
WALLET_RECHARGE (ADR-0060, 2026-09-02, IMPLEMENTED: now genuinely
  produced by `POST /api/v1/drivers/me/wallet/recharge/confirm` and the
  Razorpay webhook, `direction: CREDIT`; `metadata` carries
  `{"provider": "razorpay", "order_id", "payment_id"}` for
  traceability — no schema change was needed, this column and enum
  value already existed. ADR-0062, 2026-09-03: when this driver has an
  `outstanding_debt`, the recharge pays it down first — `amount` still
  records the full amount actually paid, but `balance_after` reflects
  only what landed in the spendable balance, with
  `metadata.outstanding_debt_recovered`/`outstanding_debt_remaining`
  explaining the difference in the same row)
JOINING_BONUS
DRIVER_REFERRAL_BONUS
ADVERTISEMENT_PAYOUT
DRIVER_PENALTY (ADR-0062, 2026-09-03: also now produced with
  `balance_before == balance_after` and `metadata:
  {"outstanding_debt_incurred": ..., "reason":
  "insufficient_balance_at_cancellation"}` when a driver-cancellation
  penalty couldn't be paid from the balance — the amount lands in
  `wallet.wallets.outstanding_debt` instead, not this transaction's own
  balance delta; see WalletService.debit_or_record_as_debt())
CASH_SETTLEMENT (dormant-since-ADR-0025 concept made real again by
  ADR-0066, 2026-09-03: the customer's outstanding cancellation/no-show
  penalty is now paid to the Sarthi directly, combined with the ride
  fare, and VISTAAR recovers its own share by debiting the driver's
  wallet at ride completion — exactly the "driver collected money on
  VISTAAR's behalf" scenario this value was originally modeled for. The
  ride *fare* itself stays untouched/P2P (ADR-0025 unchanged) — only the
  penalty portion produces this transaction type. See RideService's
  complete_ride() composition at modules/ride/router.py and
  PenaltyService.settle_penalties_for_completed_ride())
FEE_REVERSAL
PENALTY_REVERSAL
ADMIN_ADJUSTMENT

18. Wallet Outstanding Settlements

SUPERSEDED (ADR-0025, 2026-08-25 — approved P2P Payment Model): this
table modeled VISTAAR's own charge going unsettled when it was bundled
into cash the driver collected on VISTAAR's behalf. That scenario no
longer exists — the platform fee is always collected from the driver's
wallet at ride acceptance, before the ride happens (technical-
architecture.md §18, already implemented, ADR-0014), never from
customer cash. Not implemented in this codebase (confirmed accurate by
api-contracts.md §34's `outstanding_settlement: 0`); should not be built
as designed below. No schema change is made by this ADR — this is a
documentation annotation only.

18.1 wallet.outstanding_settlements

CREATE TABLE wallet.outstanding_settlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    ride_id UUID REFERENCES ride.rides(id),
    amount NUMERIC(12,2) NOT NULL,
    reason VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ
);

Used when:

Offline cash collected
AND
driver wallet is insufficient

The amount is recovered on future recharge.

19. Wallet Recharge

19.1 wallet.recharges

CREATE TABLE wallet.recharges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    amount NUMERIC(12,2) NOT NULL,
    payment_id UUID,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    idempotency_key VARCHAR(180) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

Minimum recharge:

₹200

20. Payment Tables

SUPERSEDED FOR THE RIDE FARE (ADR-0025, 2026-08-25 — approved P2P
Payment Model); PARTIALLY REVIVED FOR OUTSTANDING PENALTIES ONLY
(ADR-0026, 2026-08-26, Option A). This `payment` schema (§20-23)
modeled VISTAAR collecting the ride fare from the customer
(`payment.payments.customer_id NOT NULL`, "Methods: ONLINE/OFFLINE")
and allocating/settling it between the driver and VISTAAR. None of this
is implemented anywhere in this codebase (no `payment` schema exists in
any migration). The ride-fare-collection design is dead — VISTAAR never
collects the ride fare; the platform fee is collected separately, from
the driver's own wallet, at ride acceptance (§17.2's `PLATFORM_FEE`
transaction type, already implemented).

`payment.payments`/`payment.allocations` specifically (§20.1/20.2),
however, may still be substantially the right shape for a narrower
purpose ADR-0026 introduces: collecting a customer's OUTSTANDING PENALTY
(never the ride fare). Notably, `VISTAAR_PENALTY` was already a
documented allocation type below — this table appears to have
anticipated exactly this narrower need, just bundled together with the
now-dead ride-fare-collection design. If ever built for penalty
collection only: `gross_amount` would be the penalty total, not
fare+penalty; `DRIVER_RIDE_FARE` would never be a real allocation (the
fare is never collected here at all — see business-rules.md §40's own
example, where parking/pickup-change charges are also owed to the
driver, not VISTAAR); `VISTAAR_PARKING`/`VISTAAR_OTHER`/`TAX` stay
out of ADR-0026's scope (unresolved, not decided either way). No schema
change is made by either ADR — this is a documentation annotation only.
`payment.webhooks` (§21) is the other table here that could still be
relevant in a different, narrower form — see its own note below — for
the driver wallet-recharge gateway (a separate, still-TBD flow, §19).

20.1 payment.payments

CREATE TABLE payment.payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID REFERENCES ride.rides(id),
    customer_id UUID NOT NULL REFERENCES customer.customers(id),

    method VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL,

    gross_amount NUMERIC(12,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',

    gateway_name VARCHAR(50),
    gateway_reference VARCHAR(180),

    idempotency_key VARCHAR(180) UNIQUE NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Methods:

ONLINE
OFFLINE

20.2 payment.allocations

CREATE TABLE payment.allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID NOT NULL REFERENCES payment.payments(id),
    allocation_type VARCHAR(50) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    beneficiary_type VARCHAR(30),
    beneficiary_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Allocation types:

DRIVER_RIDE_FARE (superseded — ADR-0025: the ride fare is never
  collected here at all, so this allocation can never be real)
VISTAAR_PENALTY (revived — ADR-0026, 2026-08-26: this is the one
  allocation type this schema needs if built for penalty collection)
VISTAAR_PARKING (out of scope — neither ADR resolves this; parking is
  currently documented as owed to the driver, business-rules.md §40)
VISTAAR_OTHER (out of scope — undecided)
PROMOTION_DISCOUNT (unrelated to either ADR — a ride-fare discount, not
  a collection allocation; N/A here regardless, since no fare is
  collected here)
TAX (out of scope — undecided)

21. Payment Webhooks

Not superseded outright, unlike §20/§22/§23 — a webhook-receipt table
of this general shape (provider, external_event_id, idempotent
processing) could still be the right design for the driver
wallet-recharge gateway (§19, api-contracts.md §35), the one payment
flow ADR-0025 (2026-08-25) preserves (rule 7). If ever built for that
purpose, it should live under a schema name that reflects its actual
scope (e.g. `wallet.recharge_webhooks`), not the generic `payment`
schema this table currently sits under alongside the now-superseded
ride-fare tables — a naming decision for whichever future task actually
builds it, not decided here.

21.1 payment.webhooks

CREATE TABLE payment.webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider VARCHAR(50) NOT NULL,
    external_event_id VARCHAR(180) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

Unique provider event:

CREATE UNIQUE INDEX uq_payment_webhook_event
ON payment.webhooks(provider, external_event_id);

22. Cash Confirmations

SUPERSEDED AS DESIGNED (ADR-0025, 2026-08-25): `expected_amount` here
was meant to include VISTAAR's own charge (§23) — no longer correct,
since that charge is never part of what the customer pays. If a driver
fare-received confirmation is ever built, `expected_amount` is the ride
fare only, and no `payment.settlements` row (§23) should ever follow
from it.

22.1 payment.cash_confirmations

CREATE TABLE payment.cash_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    expected_amount NUMERIC(12,2) NOT NULL,
    confirmed_amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

The driver must confirm only after receiving the full displayed amount.

The server must reject:

confirmed_amount != expected_amount

23. Settlement Tables

SUPERSEDED (ADR-0025, 2026-08-25): modeled settling VISTAAR's own charge
out of a customer payment. Under the approved model, VISTAAR's charge
is always settled at ride acceptance, from the driver's wallet
(`PLATFORM_FEE` transaction type, §17.2) — there is no separate
settlement step following a customer payment for this table to record.

23.1 payment.settlements

CREATE TABLE payment.settlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID REFERENCES payment.payments(id),
    driver_id UUID REFERENCES driver.drivers(id),
    settlement_type VARCHAR(40) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    external_reference VARCHAR(180),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

24. Promotion Tables

24.1 promotion.entitlements

CREATE TABLE promotion.entitlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customer.customers(id),
    promotion_type VARCHAR(50) NOT NULL,
    total_uses INT NOT NULL,
    remaining_uses INT NOT NULL,
    discount_percent NUMERIC(5,2) NOT NULL,
    max_discount_amount NUMERIC(12,2),
    activated_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    campaign_id UUID REFERENCES promotion.campaigns(id)
);

`campaign_id` (ADR-0041, additive/nullable): NULL for a welcome/
referral grant (unchanged); set only for an entitlement created by
redeeming a §24.4 campaign's code — the discount fields above are
copied from the campaign at redemption time, not read live, so editing
or pausing a campaign afterward never retroactively changes a discount
a customer already holds.

24.2 promotion.usage

CREATE TABLE promotion.usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entitlement_id UUID NOT NULL REFERENCES promotion.entitlements(id),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    discount_amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Unique:

CREATE UNIQUE INDEX uq_promotion_ride_use
ON promotion.usage(entitlement_id, ride_id);

24.3 promotion.reservations

CREATE TABLE promotion.reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entitlement_id UUID NOT NULL REFERENCES promotion.entitlements(id),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    status VARCHAR(20) NOT NULL DEFAULT 'RESERVED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

24.4 promotion.campaigns (ADR-0041, Admin Web "Offers/Coupons")

An authored, many-times-redeemable coupon definition — distinct from
§24.1's entitlement (one customer's own grant). Redeeming a campaign's
code (§37's Redeem Campaign Code) creates a new promotion.entitlements
row with campaign_id set, copying the discount fields at that moment;
this table is never read live at ride time.

CREATE TABLE promotion.campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(30) UNIQUE,
    name VARCHAR(100) NOT NULL,
    vehicle_category VARCHAR(20),
    discount_type VARCHAR(10) NOT NULL,
    discount_value NUMERIC(12,2) NOT NULL,
    max_discount_amount NUMERIC(12,2),
    minimum_fare NUMERIC(12,2),
    eligible_scope VARCHAR(20) NOT NULL DEFAULT 'ALL',
    per_customer_use_limit INT NOT NULL DEFAULT 1,
    total_usage_limit INT,
    ride_count_limit INT,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

code: NULL for an auto-applied campaign with no customer-entered code.
vehicle_category: NULL applies to every category. discount_type:
'PERCENT' | 'FLAT'. eligible_scope: 'ALL' | 'SELECTED' (populates
§24.5 when 'SELECTED'; requires code to be set). status: DRAFT | ACTIVE
| PAUSED | ENDED — DRAFT/PAUSED -> ACTIVE (Activate), ACTIVE -> PAUSED
(Pause), any non-terminal -> ENDED (End, terminal). Editable (PATCH)
only while DRAFT — once ACTIVE/PAUSED, only status itself may change,
matching Fare Management's own never-rewrite-history principle.

24.5 promotion.campaign_eligible_customers (ADR-0041)

Populated only when a campaign's eligible_scope = 'SELECTED'.

CREATE TABLE promotion.campaign_eligible_customers (
    campaign_id UUID NOT NULL REFERENCES promotion.campaigns(id),
    customer_id UUID NOT NULL REFERENCES customer.customers(id),
    PRIMARY KEY (campaign_id, customer_id)
);

25. Referral Tables

25.1 referral.codes

CREATE TABLE referral.codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_type VARCHAR(20) NOT NULL,
    owner_id UUID NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

25.2 referral.referrals

CREATE TABLE referral.referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_code_id UUID NOT NULL REFERENCES referral.codes(id),
    referrer_id UUID NOT NULL,
    referred_id UUID NOT NULL,
    referred_type VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ATTACHED',
    activated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Prevent self-referral at application and database policy level where practical.

25.3 referral.rewards

CREATE TABLE referral.rewards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id UUID NOT NULL REFERENCES referral.referrals(id),
    recipient_id UUID NOT NULL,
    reward_type VARCHAR(40) NOT NULL,
    amount NUMERIC(12,2),
    promotion_uses INT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    idempotency_key VARCHAR(180) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

25.4 referral.driver_bonus_rules (ADR-0043, 2026-08-26, implemented)

Versioned/effective-dated config for BR-022/023's driver referral
bonus (seeded ₹100/₹100 at migration time; the old hardcoded constant
in `admin/router.py` remains only as a last-resort fallback if no
PUBLISHED row exists). A single global policy, not per-category — no
key column.

CREATE TABLE referral.driver_bonus_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referred_amount NUMERIC(12,2) NOT NULL,
    referrer_amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | IN_REVIEW | PUBLISHED
    effective_from TIMESTAMPTZ,
    effective_until TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

25.5 referral.customer_reward_rules (ADR-0043, 2026-08-26, implemented)

Versioned/effective-dated config for BR-059/060's customer referral
promotion grants (seeded 50%/3 uses referred, 50%/2 uses referring at
migration time; `PromotionService`'s old hardcoded constants remain
only as a last-resort fallback if no PUBLISHED row exists).
`reward_type` matches `promotion.entitlements.
promotion_type` exactly (§24.1) — two independent config streams,
since the referred/referring values already differ.

CREATE TABLE referral.customer_reward_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reward_type VARCHAR(30) NOT NULL,  -- 'REFERRAL_REFERRED' | 'REFERRAL_REFERRING'
    discount_percent NUMERIC(5,2) NOT NULL,
    total_uses INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    effective_from TIMESTAMPTZ,
    effective_until TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Both §25.4/§25.5 use the identical DRAFT → IN_REVIEW → PUBLISHED
lifecycle ADR-0042 established for `pricing.fare_rules` (§15.1) — see
ADR-0043. `referral.rewards` (§25.3) itself is unchanged: it still
records whatever `amount`/`promotion_uses` were actually issued,
copied from the live config row at qualification time, never read
live again afterward.

26. Penalty Tables

26.1 penalty.penalties

CREATE TABLE penalty.penalties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    ride_id UUID REFERENCES ride.rides(id),
    penalty_type VARCHAR(50) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'OUTSTANDING',
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ,
    settlement_ride_id UUID REFERENCES ride.rides(id)
);

`expires_at` — **removed 2026-09-04** (BR-049/BR-053 correction, owner
decision, ADR-0069: "Customer penalties in VISTAAR NEVER EXPIRE"). This
table previously had a `NOT NULL expires_at TIMESTAMPTZ` column, always
computed as `issued_at + 30 days` at creation, and an
`idx_open_penalties` index on `(user_id, expires_at)`. Neither the
column nor a value derived from it was ever actually enforced by any
code path — no expiry-collection job existed — but the stored value
itself was real and misleading (Admin Web displayed it as if it meant
something). Both are gone now, not just unused: the column is dropped,
and `idx_open_penalties` is narrowed to `(user_id) WHERE status =
'OUTSTANDING'`, still supporting the real "does this user have any
outstanding penalty" query pattern, which never needed `expires_at`
itself. See `migrations/versions/
b1d4e7f9a2c3_customer_penalties_never_expire.py`.

`settlement_ride_id` (ADR-0066, 2026-09-03, owner decision — Customer
Outstanding Penalty Settlement) — distinct from `ride_id` above, which
is the ride this penalty was originally *incurred* on and never
changes. `settlement_ride_id` is the *later* ride carrying an
OUTSTANDING penalty forward: set at that ride's own Create Ride (the
"attach" step); cleared back to `NULL` if that ride is cancelled before
completion (a future ride can then attach it instead); left in place
once that ride actually completes, alongside `status` moving to
`SETTLED`/`settled_at` being stamped (the "settle" step) — see
modules/penalty/domain/entities.py's `attach_to_ride()`/
`release_from_ride()`/`settle_via_ride()` for the full state machine,
and ADR-0066 for the business decision this implements. A partial index
(`ix_penalties_settlement_ride_id`, `WHERE settlement_ride_id IS NOT
NULL`) supports the two lookups that matter: "what's attached to this
ride" (release-on-cancel, settle-on-complete).

`penalty_type` values produced by this codebase: `CUSTOMER_CANCELLATION`
(Task 3.5, ADR-0015) and, since ADR-0057 (2026-08-31),
`SCHEDULED_RIDE_LATE_CANCELLATION` — BR-135's <3h/₹30 case only; no row
at all for the ≥3h/₹0 case (same
"no row for a ₹0 charge" treatment ADR-0015 Decision 2 already
established for `CUSTOMER_CANCELLATION`'s own grace-period case).

`status` values produced by this codebase: OUTSTANDING, SETTLED, and,
since Phase 16 (ADR-0023), WAIVED — the result of an admin's `POST
/api/v1/admin/penalties/{id}/resolve` (action: "WAIVE"),
state-machines.md §40's own documented sibling of SETTLED. EXPIRED was
removed entirely 2026-09-04 (BR-049/BR-053 correction, ADR-0069) — it
was never actually produced by any code path even before this
correction (no expiry-collection job ever existed), so removing it
deletes dead code, not a behavior change; customer penalties now never
expire, by design, not merely "not yet." No plain SQL CHECK constrains
this column — it stays a
free-form VARCHAR, same treatment every other status-like column in this
codebase gets. `settled_at` is left NULL for a WAIVED row (WAIVED is not
"settled"); the timestamp of a waiver lives in `admin.audit_logs.
created_at` for the corresponding RESOLVE_PENALTY row instead (§33.2) —
that audit-log row is also what api-contracts.md §48 means by
"a reversal/waiver record is created," not a second table.

26.2 penalty.strikes

CREATE TABLE penalty.strikes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    ride_id UUID REFERENCES ride.rides(id),
    reason VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

27. Verification Tables

27.1 verification.cases

CREATE TABLE verification.cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type VARCHAR(30) NOT NULL,
    subject_id UUID NOT NULL,
    verification_type VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

27.2 verification.evidence

CREATE TABLE verification.evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES verification.cases(id),
    evidence_uri TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

27.3 verification.results

CREATE TABLE verification.results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES verification.cases(id),
    result VARCHAR(30) NOT NULL,
    confidence NUMERIC(6,5),
    model_name VARCHAR(100),
    reviewer_id UUID,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

28. Safety Tables

28.1 safety.incidents

CREATE TABLE safety.incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID REFERENCES ride.rides(id),
    reporter_id UUID NOT NULL,
    incident_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    location GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

28.2 safety.events

CREATE TABLE safety.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES safety.incidents(id),
    event_type VARCHAR(50) NOT NULL,
    actor_id UUID,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

29. Lost and Found

29.1 support.lost_item_cases

CREATE TABLE support.lost_item_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    reporter_id UUID NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

30. Support Tables

30.1 support.cases

CREATE TABLE support.cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    ride_id UUID REFERENCES ride.rides(id),  -- added 2026-08-24, ADR-0022:
                                              -- api-contracts.md §44's documented
                                              -- request body includes ride_id,
                                              -- with no column to store it
                                              -- otherwise.
    category VARCHAR(50),
    priority VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    assigned_admin_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Implementation status (Phase 13, ADR-0029, 2026-08-25): `category` and
`ride_id` above are also how both documented dispute concepts (BR-121,
domain-design.md §17.3's DisputePenalty) are filed — `category:
"RIDE_FARE_DISPUTE"` / `"PENALTY_DISPUTE"` — no new `dispute.*` schema or
column was added; see the ADR.

30.2 support.messages

CREATE TABLE support.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES support.cases(id),
    sender_type VARCHAR(20) NOT NULL,
    sender_id UUID,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

31. Advertisement Tables

31.1 advertisement.campaigns

CREATE TABLE advertisement.campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_name VARCHAR(150) NOT NULL,
    status VARCHAR(30) NOT NULL,
    payout_amount NUMERIC(12,2) NOT NULL,
    driver_share_percent NUMERIC(5,2) NOT NULL DEFAULT 80,
    vistaar_share_percent NUMERIC(5,2) NOT NULL DEFAULT 20,
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

`status` (ADR-0018 Decision 2: `ACTIVE` only, "a campaign is
immediately usable once created"). Extended by ADR-0046 (2026-08-26,
implemented — the owner's Admin Web decision names "campaign status"
as a required admin capability): `ACTIVE ⇄ PAUSED → ENDED` (terminal).
A PAUSED/ENDED campaign accepts no new driver assignments; assignments
already in flight are unaffected. `driver_campaigns.status`/
`verification_status` (§31.2) and `payouts.status` (§31.3) are
unchanged by ADR-0046 — their existing state machines already cover
"installation/proof review," "approve/reject proof," and "payout/
settlement monitoring."

31.2 advertisement.driver_campaigns

CREATE TABLE advertisement.driver_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES advertisement.campaigns(id),
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    status VARCHAR(30) NOT NULL DEFAULT 'ASSIGNED',
    proof_uri TEXT,
    verification_status VARCHAR(30),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

31.3 advertisement.payouts

CREATE TABLE advertisement.payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_campaign_id UUID NOT NULL REFERENCES advertisement.driver_campaigns(id),
    gross_amount NUMERIC(12,2) NOT NULL,
    driver_amount NUMERIC(12,2) NOT NULL,
    vistaar_amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

32. Notification Tables

Implementation status: IMPLEMENTED (ADR-0034, 2026-08-25) — both tables
unmodified from what's documented here. Only IN_APP and SMS have a real
provider (SMS reuses modules.identity.sms's MSG91 integration,
generalized beyond OTP-only, itself unverified against a live account —
same caveat as ADR-0031). PUSH (no device-token data source exists
anywhere in this codebase) and WHATSAPP (no BSP chosen — owner
instruction) have no provider; `whatsapp_enabled`/`push_enabled` stay
real, populated columns with no live sender behind them yet.

32.1 notification.preferences

CREATE TABLE notification.preferences (
    user_id UUID PRIMARY KEY,
    push_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sms_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    whatsapp_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

32.2 notification.deliveries

CREATE TABLE notification.deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    channel VARCHAR(20) NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    event_id UUID,
    status VARCHAR(30) NOT NULL,
    provider_reference VARCHAR(180),
    template_version_id UUID REFERENCES notification.templates(id),  -- added
                                -- ADR-0044, 2026-08-26, implemented; NULL for
                                -- every row predating §32.3, and also whenever
                                -- no PUBLISHED template row existed at send
                                -- time (the old SMS_TEMPLATES dict fallback
                                -- was used instead) — records exactly which
                                -- template version was rendered, so editing/
                                -- republishing a template afterward can never
                                -- appear to change a historical send.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ
);

Unique delivery key should prevent duplicate notification processing.

32.3 notification.templates (ADR-0044, 2026-08-26, implemented)

An admin-editable, versioned store across every channel. Editing
creates a new row (`version = previous + 1`, `status = 'DRAFT'`)
rather than mutating one in place — the version chain itself is the
"version history" the owner's decision asked for. `SMS_TEMPLATES` (the
old static Python dict, ADR-0034 Decision 4, SMS-only, two entries)
remains in the codebase only as a last-resort fallback for
`NotificationService.send()` when no PUBLISHED row exists yet for a
given (template_key, channel) — the migration seeds one PUBLISHED
version-1 row per its two entries so nothing changes the moment this
ships.

CREATE TABLE notification.templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_key VARCHAR(50) NOT NULL,
    channel VARCHAR(20) NOT NULL,       -- IN_APP | SMS | PUSH | WHATSAPP
    event_key VARCHAR(50),              -- nullable — the triggering domain event,
                                         -- if any (a template may exist for
                                         -- manual/admin-broadcast use only)
    title VARCHAR(200),                 -- nullable (SMS has no title)
    body TEXT NOT NULL,
    version INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',  -- DRAFT | PUBLISHED | ARCHIVED
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_notification_templates_one_published
ON notification.templates (template_key, channel)
WHERE status = 'PUBLISHED';

No provider secrets (MSG91/Firebase/any future WhatsApp BSP
credentials) are ever stored here or exposed through any endpoint over
this table — those remain exclusively in environment configuration
(`core/config.py`), an explicit hard boundary (ADR-0044 §4), not an
oversight.

32.4 notification.device_tokens (ADR-0052, 2026-08-28, implemented)

Push Notifications device registration — the first customer/driver-
facing Notification table. One row per registered FCM token; a user
with multiple devices gets multiple rows.

CREATE TABLE notification.device_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,       -- no FK, same reasoning as §32.1/§32.2's
                                  -- own user_id columns (no single users table)
    platform VARCHAR(10) NOT NULL,  -- ANDROID | IOS | WEB
    token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_notification_device_tokens_token
ON notification.device_tokens (token);

CREATE INDEX idx_notification_device_tokens_user
ON notification.device_tokens (user_id);

The unique index on `token` (not `(user_id, platform)`) is deliberate —
an FCM token is globally unique per app install, so registering the
same token again is always an upsert of the same row, correctly
re-associating a device with whichever account is currently logged in
if it changes.

32.5 notification.broadcasts (ADR-0055, 2026-08-29, implemented)

Compose/Send Broadcast + Audience Selection. One row per admin-composed
broadcast — its own free-text `subject`/`body`, not a reference to a
reusable template; under the hood the same request also publishes a
one-off, broadcast-only `notification.templates` row (`event_key=
NULL`) so every recipient's actual send still goes through
`NotificationService.send()`'s existing content-resolution path
unchanged.

CREATE TABLE notification.broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel VARCHAR(20) NOT NULL,          -- IN_APP | SMS | PUSH
    template_key VARCHAR(50) NOT NULL,     -- the auto-published Template's key
    subject VARCHAR(200),
    body TEXT NOT NULL,
    audience_type VARCHAR(30) NOT NULL,    -- ALL_CUSTOMERS | ALL_DRIVERS |
                                            -- ONLINE_DRIVERS | SELECTED
    audience_user_ids JSONB,               -- only populated when
                                            -- audience_type='SELECTED'
    status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED',  -- SCHEDULED | SENT
    scheduled_at TIMESTAMPTZ,              -- NULL = dispatched immediately
    sent_count INT NOT NULL DEFAULT 0,
    failed_count INT NOT NULL DEFAULT 0,
    created_by UUID NOT NULL REFERENCES admin.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);

CREATE INDEX idx_notification_broadcasts_status_scheduled
ON notification.broadcasts (status, scheduled_at);

No FAILED status at the broadcast level — an individual recipient's
send failing is tracked in `failed_count`, not the whole row; `status`
starts SCHEDULED even for an immediate broadcast (the same request
dispatches and flips it to SENT before returning). `audience_user_ids`
is a bare JSONB array, not a join table — this list is fixed at
compose time and never queried/filtered on, the same reasoning
`admin.settings.value`'s own bare JSONB scalar/object (ADR-0048 §4)
already established for this codebase.

33. Admin Tables

33.1 admin.users

CREATE TABLE admin.users (
    id UUID PRIMARY KEY REFERENCES identity.accounts(id),
    role VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

`role` (BR-126/BR-127, ADR-0040, 2026-08-26): exactly `'SUPER_ADMIN'` or
`'ADMIN'` (an "employee admin" in BR-126's own terms) — still no DB-level
CHECK constraint (the closed set is enforced at the application layer,
`modules.admin.domain.entities.AdminRole`), same convention `status`
already used. A Super Admin has implicit full access to every module (no
`admin.permissions` rows are ever written for one); an employee admin's
access is entirely determined by their own rows in §33.3 below.

33.2 admin.audit_logs

CREATE TABLE admin.audit_logs (
    id BIGSERIAL PRIMARY KEY,
    admin_id UUID NOT NULL REFERENCES admin.users(id),
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id UUID,
    reason TEXT,
    before_state JSONB,
    after_state JSONB,
    request_id VARCHAR(180),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

33.3 admin.permissions

Added ADR-0040 (BR-126/BR-127, 2026-08-26) — the Admin Permission
Model. One row per (admin_id, module) an employee admin has some
access to; absence of a row means no access at all for that module. A
Super Admin (§33.1) never has rows here — implicit full access.

CREATE TABLE admin.permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id UUID NOT NULL REFERENCES admin.users(id),
    module VARCHAR(40) NOT NULL,
    access_level VARCHAR(10) NOT NULL,  -- 'VIEW' | 'MANAGE'
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Unique:

CREATE UNIQUE INDEX uq_admin_permissions_admin_module
ON admin.permissions(admin_id, module);

33.4 admin.settings (ADR-0048, 2026-08-26, implemented — migration
     f2c6a819e3b4)

MVP Settings — a generic key-value store for the categories with no
dedicated screen of their own: promotion defaults, operational
thresholds, feature flags, general platform settings. Fare/platform-
fee/referral/notification settings each already have (or, per this
same decision batch, are gaining) their own dedicated versioned table
(§15.1/§15.3/§25.4-§25.5/§32.3) — Settings links to those rather than
duplicating their data (ADR-0048 §2).

CREATE TABLE admin.settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    category VARCHAR(30) NOT NULL,  -- 'PROMOTION_DEFAULT' | 'OPERATIONAL_THRESHOLD'
                                     -- | 'FEATURE_FLAG' | 'GENERAL'
    description TEXT NOT NULL,
    updated_by UUID NOT NULL REFERENCES admin.users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

No Create/Delete via the admin API — the valid key set is fixed by
what the implementing migration seeds (ADR-0048 §2: only
`welcome_discount_percent`/`welcome_total_uses`, BR-058's own approved
values, at launch); a key not already present returns
RESOURCE_NOT_FOUND on update, the same closed-vocabulary treatment
this codebase gives every other fixed enum. Never holds API
keys/passwords/cloud secrets/DB credentials/private keys — those stay
exclusively in environment configuration, never read from or written
to by any admin endpoint (ADR-0048 §5).

`module` is a plain string, not an enum with a DB constraint — the
closed set (20 modules — Dashboard, Customers, Drivers, Vehicles,
Verification/Documents, Rides, Matching/Offers, Finance/Wallet, Fare
Management, Penalties/Strikes, Offers/Coupons, Referrals,
Notifications, Safety/SOS, Support/Disputes, Advertisements, Reports/
Analytics, Audit Logs, Admin Management, Settings — BR-126, matching
docs/15-admin-web/admin-web-implementation-plan.md §2.1's navigation
exactly) is enforced at the application layer
(`modules.admin.domain.entities.AdminModule`), same convention
`admin.users.role` uses. `ADMIN_MANAGEMENT` and `SETTINGS` are never
actually written here — BR-126: "never grantable to an employee
admin... only the Super Admin ever holds them."

34. Outbox Tables

Each domain requiring transactional event publishing should have an outbox.

A shared implementation can use:

CREATE TABLE shared.outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    event_version INT NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Index:

CREATE INDEX idx_outbox_unpublished
ON shared.outbox_events(created_at)
WHERE published_at IS NULL;

34.1 Outbox Retry/Backoff/Dead-Letter Columns (IMPLEMENTED — ADR-0071,
     2026-09-04, migration c2e6a9f4d7b1)

Extends 34's table with the per-row retry/backoff/dead-letter tracking
§30/§31's retry policy and Dead Letter Topics need — previously absent
(a failed publish just retried forever at a fixed poll interval, no
backoff, no attempt limit, no DLQ):

ALTER TABLE shared.outbox_events
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    ADD COLUMN attempt_count INT NOT NULL DEFAULT 0,
    ADD COLUMN last_attempt_at TIMESTAMPTZ,
    ADD COLUMN first_failure_at TIMESTAMPTZ,
    ADD COLUMN next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN last_error TEXT,
    ADD COLUMN dead_lettered_at TIMESTAMPTZ;

`status` values this codebase produces: PENDING (default — due for a
publish attempt once `next_attempt_at` arrives), PUBLISHED (published_at
also set), DEAD_LETTERED (dead_lettered_at also set, after `attempt_count`
reaches `settings.EVENT_RETRY_MAX_ATTEMPTS` and a subsequent publish to
`vistaar.dlq.<domain>` succeeds — event-contracts.md §31). `published_at`/
`created_at` (34, above) are unchanged and still authoritative for "when";
`status` is the authoritative enum for filtering.

idx_outbox_unpublished is replaced by the query the publisher actually
runs now:

CREATE INDEX idx_outbox_due
ON shared.outbox_events(next_attempt_at)
WHERE status = 'PENDING';

35. Idempotency Table

For API commands with financial or state-changing consequences:

CREATE TABLE shared.idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(180) UNIQUE NOT NULL,
    actor_id UUID,
    operation VARCHAR(100) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    response_code INT,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

The request hash prevents the same idempotency key being reused for a different payload.

35.1 Consumer Event Idempotency Table (IMPLEMENTED — ADR-0071, 2026-09-04,
     migration d8f1c3a6e9b2)

A distinct concept from 35's `shared.idempotency_keys` above — that
table dedupes a client's own retried *HTTP request* by its
Idempotency-Key header (shared/idempotency.py); this one dedupes a
Kafka *event* a consumer might see more than once under at-least-once
delivery (event-contracts.md §29). Exactly the recommended schema:

CREATE TABLE shared.processed_events (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

`modules/notification/consumer.py`'s `NotificationConsumer` is the one
real consumer using it today (`consumer_name = 'notification-consumer'`)
— checked before, and recorded in the same commit as, every handler
dispatch.

36. Audit Events

Important non-admin actions should also be auditable.

CREATE TABLE shared.audit_events (
    id BIGSERIAL PRIMARY KEY,
    actor_type VARCHAR(30),
    actor_id UUID,
    action VARCHAR(100) NOT NULL,
    aggregate_type VARCHAR(100),
    aggregate_id UUID,
    metadata JSONB,
    request_id VARCHAR(180),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

37. Driver Location Architecture

High-frequency driver location should not be written to PostgreSQL on every update.

Primary operational state:

Redis GEO

Example:

geo:drivers:BIKE
geo:drivers:AUTO
geo:drivers:CAB

Periodic durable snapshots may be stored if required for audit/analytics.

38. Driver Location History

If durable location history is required:

CREATE TABLE ride.driver_location_points (
    id BIGSERIAL PRIMARY KEY,
    ride_id UUID,
    driver_id UUID NOT NULL REFERENCES driver.drivers(id),
    location GEOMETRY(Point, 4326) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);

This table may become very large.

Recommended:

Time partitioning

Retention policy

Batch insertion

Appropriate spatial indexes

Exact retention is TBD.

39. Key Constraints

Ride

A ride cannot be assigned to multiple active drivers.

Offer

A single offer cannot be both accepted and expired.

Wallet

Balance cannot become negative.

Payment

A payment cannot have two successful terminal states.

Promotion

A single ride cannot consume the same entitlement twice.

Referral

A reward idempotency key must be unique.

Penalty

One qualifying business event must not create duplicate penalties.

40. Important Partial Indexes

Examples:

CREATE INDEX idx_active_driver_documents
ON driver.documents(driver_id)
WHERE verification_status = 'APPROVED';

CREATE INDEX idx_active_vehicles
ON vehicle.vehicles(driver_id, category)
WHERE verification_status = 'APPROVED'
  AND operational_status = 'ACTIVE';

CREATE INDEX idx_pending_offers
ON matching.ride_offers(expires_at)
WHERE status = 'PENDING';

CREATE INDEX idx_open_penalties
ON penalty.penalties(user_id, expires_at)
WHERE status = 'OUTSTANDING';

CREATE INDEX idx_open_settlements
ON wallet.outstanding_settlements(driver_id)
WHERE status = 'OPEN';

41. Financial Integrity

Wallet transaction rule

Never do:

UPDATE wallet.wallets
SET balance = balance - 20;

without creating the corresponding ledger transaction.

Correct pattern:

BEGIN
 ↓
Lock wallet
 ↓
Read balance
 ↓
Validate
 ↓
Calculate new balance
 ↓
Update wallet
 ↓
Insert ledger
 ↓
Commit

Both records must succeed or both must fail.

42. Wallet Concurrency

Use:

SELECT *
FROM wallet.wallets
WHERE driver_id = $1
FOR UPDATE;

during balance-changing operations.

Alternative optimistic locking may use version.

The implementation must prevent:

Request A sees ₹20
Request B sees ₹20

A spends ₹20
B spends ₹20

Final balance = invalid

43. Payment Idempotency

Payment gateway webhooks must be processed using the provider's unique event ID.

Flow:

Webhook received
 ↓
Check provider + external_event_id
 ↓
Already processed?
 ├── YES → return success
 └── NO
      ↓
Record webhook
      ↓
Process payment
      ↓
Mark processed

44. Promotion Concurrency

Two simultaneous booking/payment requests must not consume the same promotional use.

Use a transaction with row locking:

BEGIN
 ↓
Lock entitlement
 ↓
Check remaining_uses
 ↓
Reserve/decrement
 ↓
Insert usage
 ↓
COMMIT

45. Referral Concurrency

Referral rewards must be protected by:

Unique referral qualification

Unique reward idempotency key

Transactional reward creation

46. Soft Delete Policy

Do not physically delete financial records.

Never delete:

Wallet transactions

Payments

Settlements

Penalties

Admin audit logs

Safety incidents

For user-owned profile data, deactivation/anonymization may be used according to the final data-retention policy.

47. Data Retention

Exact retention periods remain TBD.

The retention policy must consider:

Indian legal requirements

Payment records

Tax/accounting requirements

Safety records

Location privacy

User deletion requirements

48. Migration Order

Recommended migration sequence:

001_extensions
002_shared
003_identity
004_customer
005_driver
006_vehicle
007_ride
008_matching
009_pricing
010_wallet
011_payment
012_promotion
013_referral
014_penalty
015_verification
016_safety
017_notification
018_support
019_advertisement
020_admin
021_indexes
022_constraints
023_outbox
024_idempotency

Migrations must be forward-only in production.

49. Seed Data

Initial seed configuration should include:

Vehicle categories:
BIKE
AUTO
CAB

Platform fees:
BIKE = ₹10
AUTO = ₹20
CAB = ₹20

Driver request timeout:
20 seconds

Pickup change threshold:
250 meters

Destination extension:
₹8/km

Customer cancellation grace:
2 minutes

First qualifying customer cancellation:
₹0

Subsequent qualifying cancellation:
₹15

No-show:
₹30

Driver cancellation:
₹30

Driver joining bonus:
₹100

Driver referral:
₹100

Promotion expiry:
30 days

Values that remain TBD must not be seeded as invented numbers.

50. Database Testing

Every migration must have tests for:

Foreign keys

Unique constraints

Check constraints

Index availability

Idempotency

Wallet concurrency

Payment webhook duplication

Promotion concurrency

Referral duplication

Penalty duplication

51. Backup and Recovery

Production PostgreSQL must support:

Automated backups

Point-in-time recovery

Restore testing

Backup monitoring

Recovery objectives:

RPO → TBD
RTO → TBD

These must be finalized before production launch.

52. Database Security

Use:

Encrypted connections

Secrets management

Least-privilege DB users

Separate migration credentials

Separate application credentials

No database credentials in source control

Sensitive values must not be logged.

53. Developer Rules

DO

Use migrations.

Use transactions for financial operations.

Use UUIDs.

Use NUMERIC for money.

Use PostGIS for spatial data.

Add indexes based on access patterns.

Use idempotency keys.

Preserve audit trails.

DO NOT

Store money as FLOAT.

Modify another domain's tables.

Delete financial history.

Trust client-provided fare totals.

Trust client-provided wallet balances.

Trust client-provided payment success.

Trust client-provided GPS completion without server verification.

Hard-code configurable business rules in UI/controllers.

54. Database-to-Domain Ownership

identity.*
    → Identity

customer.*
    → Customer

driver.*
    → Driver

vehicle.*
    → Vehicle

ride.*
    → Ride

matching.*
    → Matching

pricing.*
    → Pricing

wallet.*
    → Wallet

payment.*
    → Payment

promotion.*
    → Promotion

referral.*
    → Referral

penalty.*
    → Penalty

verification.*
    → Verification

safety.*
    → Safety

notification.*
    → Notification

support.*
    → Support

advertisement.*
    → Advertisement

admin.*
    → Admin

shared.*
    → Cross-domain infrastructure only

55. Open Database Decisions

The following must be finalized during implementation/design review:

Whether domains use one PostgreSQL cluster or separate databases.

Final foreign-key strategy across schemas.

Exact retention period for location history.

Exact retention period for documents.

Payment gateway schema requirements (narrowed — ADR-0025, 2026-08-25:
only for driver wallet recharge; the `payment.*` schema in §20-23 models
ride-fare collection, which is superseded and should not be built).

Settlement provider requirements.

Final fare-rule dimensions.

Exact GPS verification radii.

Partitioning strategy for location/event tables.

RPO/RTO targets.

Production database sizing.

Read replica requirements.

56. Next Document

Document chain (corrected to match actual repository folder names — see docs/14-decisions/ for the numbering-reconciliation record):

04-domain-design/domain-design.md
                ↓
04-database/database-design.md   ← THIS
                ↓
05-api/api-contracts.md
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

57. Document Status

Version: 1.0
Status: Draft
Derived from: PRD v2.0, Business Rules v1.0, Technical Architecture v2.0, Domain Design v1.0
Next: API Contracts