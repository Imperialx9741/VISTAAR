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
    phone VARCHAR(20) NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Indexes:

CREATE INDEX idx_otp_phone_status
ON identity.otp_challenges(phone, status);

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

    original_pickup GEOMETRY(Point, 4326) NOT NULL,
    current_pickup GEOMETRY(Point, 4326) NOT NULL,

    original_destination GEOMETRY(Point, 4326) NOT NULL,
    current_destination GEOMETRY(Point, 4326) NOT NULL,

    active_fare_quote_id UUID,

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

12. Early Drop

12.1 ride.early_drop_requests

CREATE TABLE ride.early_drop_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ride_id UUID NOT NULL REFERENCES ride.rides(id),
    requested_by UUID NOT NULL,
    customer_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    driver_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    gps_location GEOMETRY(Point, 4326),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

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

15. Pricing Tables

15.1 pricing.fare_rules

CREATE TABLE pricing.fare_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_category VARCHAR(20) NOT NULL,
    base_fare NUMERIC(12,2) NOT NULL,
    per_km NUMERIC(12,2) NOT NULL,
    per_minute NUMERIC(12,2) NOT NULL,
    waiting_per_minute NUMERIC(12,2) NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

Exact fare values remain TBD.

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
    CONSTRAINT wallet_balance_nonnegative CHECK (balance >= 0)
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
WALLET_RECHARGE
JOINING_BONUS
DRIVER_REFERRAL_BONUS
ADVERTISEMENT_PAYOUT
DRIVER_PENALTY
CASH_SETTLEMENT
FEE_REVERSAL
PENALTY_REVERSAL
ADMIN_ADJUSTMENT

18. Wallet Outstanding Settlements

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

DRIVER_RIDE_FARE
VISTAAR_PENALTY
VISTAAR_PARKING
VISTAAR_OTHER
PROMOTION_DISCOUNT
TAX

21. Payment Webhooks

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
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

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
    expires_at TIMESTAMPTZ NOT NULL,
    settled_at TIMESTAMPTZ
);

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
    category VARCHAR(50),
    priority VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    assigned_admin_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ
);

Unique delivery key should prevent duplicate notification processing.

33. Admin Tables

33.1 admin.users

CREATE TABLE admin.users (
    id UUID PRIMARY KEY REFERENCES identity.accounts(id),
    role VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

Payment gateway schema requirements.

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