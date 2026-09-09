"""Ride domain entity and validation.

Field shapes match docs/04-database/database-design.md §9.1 (ride.rides)
exactly. `requested_vehicle_category` was added by Phase 3 / Task 3.2
(ADR-0011 Decision 1) — Task 3.1 validated `vehicle_category` but had
nowhere to persist it (ADR-0010 §8 Addendum).

`payment_method` (accepted-but-unpersisted since Task 3.1, ADR-0010
Decision 2) was removed entirely 2026-09-03 — owner decision: "Do NOT
display or ask the User to select UPI or CASH in the VISTAAR app... the
User has freedom to choose how they settle the ride amount directly
with the Sarthi." It never had a column, never influenced ride creation
in any way, and was already flagged as belonging to a Payment domain
this project never built (the P2P model, ADR-0025, made that domain
moot for the ride fare specifically). Removed from the request schema,
this module, and the mobile booking screen together — see ADR-0025's
own cross-reference update for the full account.

Create Ride Request (Phase 3 / Task 3.1), dispatching the first matching
offer (Phase 3 / Task 3.2, via modules/matching/, composed at
modules/ride/router.py — this module has no dependency on
modules/matching/), SEARCHING -> CANCELLED cancellation (Phase 3 / Task
3.3), and SEARCHING -> ACCEPTED / AssignDriver (Phase 3 / Task 3.4,
ADR-0014 — RideService.accept_ride()) are implemented. No other
ride-lifecycle command (MarkArrived, StartRide, ...) exists yet —
domain-design.md §9.4 lists the full command set this module will
eventually grow into.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from modules.identity.domain.errors import InvalidPhoneNumberError
from modules.identity.domain.phone_number import PhoneNumber
from modules.ride.domain.errors import (
    InvalidCancellationReasonError,
    InvalidCoordinateError,
    InvalidLinkedContactError,
    InvalidScheduledForError,
)
from modules.vehicle.domain.entities import (
    CabTier,
    VehicleCategory,
    validate_cab_tier,
    validate_category,
)

_MIN_LATITUDE = -90.0
_MAX_LATITUDE = 90.0
_MIN_LONGITUDE = -180.0
_MAX_LONGITUDE = 180.0
_MAX_CANCELLATION_REASON_LENGTH = 100  # matches database-design.md §9.2's
# ride.state_history.reason VARCHAR(100) — cancel's `reason` is stored
# there (Task 3.3).

# ADR-0057, BR-137 — Schedule a Ride's window: engineering defaults the
# owner approved as a starting point, not independently re-derived
# business values.
_MIN_SCHEDULE_LEAD = timedelta(hours=1)
_MAX_SCHEDULE_LEAD = timedelta(hours=24)
# ADR-0057 Decision 1 — how close to scheduled_for matching actually
# begins; also an engineering default, not a business value.
SCHEDULED_RIDE_LOCK_IN_WINDOW = timedelta(minutes=30)
_MAX_LINKED_CONTACT_NAME_LENGTH = 200  # matches database-design.md §9.1's
# ride.rides.linked_contact_name VARCHAR(200).

_EARTH_RADIUS_METERS = 6_371_000.0


class RideStatus(StrEnum):
    """Exactly state-machines.md §3.1's documented ride states. Task 3.1
    only ever produces SEARCHING (see Ride.new() below) — the other
    values exist here because they're part of the same documented enum
    that future ride-lifecycle tasks will transition into, not because
    this module can reach them yet.

    NO_DRIVER is deliberately excluded: domain-design.md §9.3 and
    technical-architecture.md §12 list it, but state-machines.md §3.1 —
    the authoritative state-machine document — does not. ADR-0010 Item 6
    records this conflict as unresolved rather than silently picking a
    side; Task 3.1 never reaches a "no driver accepts" outcome, so it
    doesn't need to.

    SCHEDULED (ADR-0057) is entered instead of SEARCHING when
    Ride.new() is given a scheduled_for time — see state-machines.md
    §3.9. A ride never returns to SCHEDULED once it leaves it."""

    SCHEDULED = "SCHEDULED"
    SEARCHING = "SEARCHING"
    ACCEPTED = "ACCEPTED"
    ARRIVED = "ARRIVED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


@dataclass(slots=True)
class Coordinates:
    """latitude/longitude only — presence and standard geographic-range
    validation is all that's documented anywhere for ride pickup/
    destination (api-contracts.md §12's "Validate coordinates" step). No
    same-location, service-area, or geofence restriction exists in any
    source document, so none is invented here."""

    latitude: float
    longitude: float


def validate_coordinates(
    latitude: float, longitude: float, *, field_name: str
) -> Coordinates:
    if not (_MIN_LATITUDE <= latitude <= _MAX_LATITUDE):
        raise InvalidCoordinateError(
            f"{field_name}.latitude must be between {_MIN_LATITUDE} and "
            f"{_MAX_LATITUDE}."
        )
    if not (_MIN_LONGITUDE <= longitude <= _MAX_LONGITUDE):
        raise InvalidCoordinateError(
            f"{field_name}.longitude must be between {_MIN_LONGITUDE} and "
            f"{_MAX_LONGITUDE}."
        )
    return Coordinates(latitude=latitude, longitude=longitude)


@dataclass(slots=True)
class Ride:
    id: uuid.UUID
    customer_id: uuid.UUID
    driver_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    status: RideStatus
    requested_vehicle_category: VehicleCategory
    requested_cab_tier: CabTier | None
    original_pickup: Coordinates
    current_pickup: Coordinates
    original_destination: Coordinates
    current_destination: Coordinates
    active_fare_quote_id: uuid.UUID | None
    scheduled_for: datetime | None
    lock_in_at: datetime | None
    linked_contact_name: str | None
    linked_contact_phone: str | None
    requested_at: datetime
    accepted_at: datetime | None
    arrived_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def new(
        *,
        customer_id: uuid.UUID,
        pickup_latitude: float,
        pickup_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        vehicle_category: str,
        cab_tier: str | None = None,
        scheduled_for: datetime | None = None,
        linked_contact_name: str | None = None,
        linked_contact_phone: str | None = None,
        now: datetime,
    ) -> Ride:
        """Creates a ride directly in SEARCHING
        (state-machines.md §4: "Entered when: Customer successfully
        requests a ride."), or in SCHEDULED (state-machines.md §3.9,
        ADR-0057) when `scheduled_for` is given. active_fare_quote_id
        stays None here — modules/ride/router.py sets it once
        PricingService.calculate_fare() has run against this
        already-created ride (ADR-0020 Decision 6; pricing.fare_quotes.
        ride_id is a NOT NULL FK, so the ride must exist first) —
        unchanged for a SCHEDULED ride: its fare is locked at this same
        moment, just earlier in the ride's life than an immediate
        ride's own SEARCHING entry (ADR-0057 Decision 1). driver_id/
        vehicle_id stay None until AssignDriver (ADR-0011 Decision 3).
        `cab_tier` mirrors `vehicle_category`'s validation exactly
        (ADR-0020 Decision 1) — required and validated only when
        requesting CAB."""
        pickup = validate_coordinates(
            pickup_latitude, pickup_longitude, field_name="pickup"
        )
        destination = validate_coordinates(
            destination_latitude, destination_longitude, field_name="destination"
        )
        category = validate_category(vehicle_category)
        status, lock_in_at = validate_scheduled_for(scheduled_for, now=now)
        contact_name, contact_phone = validate_linked_contact(
            linked_contact_name, linked_contact_phone
        )
        return Ride(
            id=uuid.uuid4(),
            customer_id=customer_id,
            driver_id=None,
            vehicle_id=None,
            status=status,
            requested_vehicle_category=category,
            requested_cab_tier=validate_cab_tier(category, cab_tier),
            original_pickup=pickup,
            current_pickup=pickup,
            original_destination=destination,
            current_destination=destination,
            active_fare_quote_id=None,
            scheduled_for=scheduled_for,
            lock_in_at=lock_in_at,
            linked_contact_name=contact_name,
            linked_contact_phone=contact_phone,
            requested_at=now,
            accepted_at=None,
            arrived_at=None,
            started_at=None,
            completed_at=None,
            closed_at=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
        )


def validate_cancellation_reason(reason: str) -> str:
    """No canonical reason enum is documented anywhere (Task 3.3) — only
    shape (non-blank, VARCHAR(100)) is validated, same treatment as
    modules.vehicle.domain.entities.validate_document_type for the
    identical "no documented enum" situation."""
    stripped = reason.strip()
    if not stripped:
        raise InvalidCancellationReasonError("reason cannot be blank.")
    if len(stripped) > _MAX_CANCELLATION_REASON_LENGTH:
        raise InvalidCancellationReasonError(
            f"reason cannot exceed {_MAX_CANCELLATION_REASON_LENGTH} characters."
        )
    return stripped


def validate_scheduled_for(
    scheduled_for: datetime | None, *, now: datetime
) -> tuple[RideStatus, datetime | None]:
    """ADR-0057, BR-137. `None` (the ordinary immediate-ride case) always
    returns `(SEARCHING, None)` — zero behavior change. Otherwise
    `scheduled_for` must be 1-24 hours from `now`; returns `(SCHEDULED,
    lock_in_at)` where `lock_in_at = scheduled_for -
    SCHEDULED_RIDE_LOCK_IN_WINDOW` (ADR-0057 Decision 1 — the moment the
    Celery Beat task, modules/ride/tasks.py, promotes this ride to
    SEARCHING)."""
    if scheduled_for is None:
        return RideStatus.SEARCHING, None
    lead_time = scheduled_for - now
    if lead_time < _MIN_SCHEDULE_LEAD or lead_time > _MAX_SCHEDULE_LEAD:
        raise InvalidScheduledForError(
            "scheduled_for must be between "
            f"{_MIN_SCHEDULE_LEAD.total_seconds() / 3600:g} and "
            f"{_MAX_SCHEDULE_LEAD.total_seconds() / 3600:g} hours from now."
        )
    return RideStatus.SCHEDULED, scheduled_for - SCHEDULED_RIDE_LOCK_IN_WINDOW


def validate_linked_contact(
    name: str | None, phone: str | None
) -> tuple[str | None, str | None]:
    """ADR-0057, BR-138-140 (Book for Someone Else). Both `None`
    (the ordinary self-booked case) is valid and returns `(None, None)`
    — zero behavior change. Exactly one of the two being `None` is
    rejected — they're required together (a name with no way to reach
    the rider, or a phone with no way to address them, are both
    incomplete). `phone` is normalized/validated via
    modules.identity.domain.phone_number.PhoneNumber — reused rather
    than reimplemented, its own InvalidPhoneNumberError translated to
    this module's InvalidLinkedContactError so every error this module
    raises stays a RideDomainError."""
    if name is None and phone is None:
        return None, None
    if name is None or phone is None:
        raise InvalidLinkedContactError(
            "linked_contact requires both name and phone together."
        )
    stripped_name = name.strip()
    if not stripped_name:
        raise InvalidLinkedContactError("linked_contact.name cannot be blank.")
    if len(stripped_name) > _MAX_LINKED_CONTACT_NAME_LENGTH:
        raise InvalidLinkedContactError(
            "linked_contact.name cannot exceed "
            f"{_MAX_LINKED_CONTACT_NAME_LENGTH} characters."
        )
    try:
        normalized_phone = PhoneNumber.parse(phone)
    except InvalidPhoneNumberError as exc:
        raise InvalidLinkedContactError(f"linked_contact.phone: {exc.message}") from exc
    return stripped_name, normalized_phone.value


def haversine_distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Standard haversine great-circle distance, in meters — a small,
    intentional duplicate of modules.pricing.domain.entities.
    haversine_distance_km() (Decimal, kilometers, fare-calculation
    rounding) rather than a cross-domain import, matching this
    codebase's own "small pure domain helper duplicated per-domain"
    precedent (e.g. modules.safety.domain.entities' own Coordinates/
    validate_coordinates, duplicated from this same module). GPS
    verification needs plain float meters at a much smaller scale
    (tens of meters) than fare calculation needs kilometers — different
    enough numeric needs that sharing one Decimal-returning,
    kilometer-scaled function would be awkward either way."""
    lat1, lon1, lat2, lon2 = map(
        math.radians, [latitude_a, longitude_a, latitude_b, longitude_b]
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return _EARTH_RADIUS_METERS * c


class GpsVerificationType(StrEnum):
    """Exactly database-design.md §14.1's documented "Verification
    types". EARLY_DROP is listed here because it's part of the same
    documented enum a future task (Phase 08) will produce — this task
    (ADR-0028) only ever writes ARRIVAL/COMPLETION rows."""

    ARRIVAL = "ARRIVAL"
    COMPLETION = "COMPLETION"
    EARLY_DROP = "EARLY_DROP"


class GpsVerificationResult(StrEnum):
    PASS_ = "PASS"
    FAIL = "FAIL"


@dataclass(slots=True)
class GpsVerification:
    """Field shapes match database-design.md §14.1 (ride.gps_verifications)
    exactly. Every verification attempt is recorded here, pass or fail —
    this table is the audit trail ADR-0028 Decision 3 leaves ready for a
    future Dispute-as-Support review, not an afterthought."""

    id: uuid.UUID
    ride_id: uuid.UUID
    verification_type: GpsVerificationType
    latitude: float
    longitude: float
    reference_latitude: float | None
    reference_longitude: float | None
    distance_meters: float | None
    result: GpsVerificationResult
    created_at: datetime

    @staticmethod
    def new(
        *,
        ride_id: uuid.UUID,
        verification_type: GpsVerificationType,
        latitude: float,
        longitude: float,
        reference_latitude: float,
        reference_longitude: float,
        radius_meters: float,
        now: datetime,
    ) -> GpsVerification:
        """Computes the straight-line distance from (latitude, longitude)
        to the reference point and records PASS/FAIL against
        `radius_meters` — the caller (RideService) supplies the
        already-resolved reference point (current pickup for ARRIVAL,
        current destination for COMPLETION) and radius (ADR-0028
        Decision 1's owner-approved 50m/100m, core.config.settings)."""
        distance = haversine_distance_meters(
            latitude, longitude, reference_latitude, reference_longitude
        )
        result = (
            GpsVerificationResult.PASS_
            if distance <= radius_meters
            else GpsVerificationResult.FAIL
        )
        return GpsVerification(
            id=uuid.uuid4(),
            ride_id=ride_id,
            verification_type=verification_type,
            latitude=latitude,
            longitude=longitude,
            reference_latitude=reference_latitude,
            reference_longitude=reference_longitude,
            distance_meters=distance,
            result=result,
            created_at=now,
        )


class RideOtpStatus(StrEnum):
    """No documented enum exists for this column (database-design.md
    §13.1 lists no "status values" the way e.g. penalty.penalties does) —
    shape-only inference from the column's own name and
    "Only the latest valid OTP can start the ride" note. ACTIVE is the
    only value this task's code ever sets; USED/EXPIRED exist so a
    future read (e.g. an audit view) has a real vocabulary rather than
    inferring state purely from `expires_at`/a JOIN."""

    ACTIVE = "ACTIVE"
    USED = "USED"
    EXPIRED = "EXPIRED"


@dataclass(slots=True)
class RideOtp:
    """Field shapes match database-design.md §13.1 (ride.ride_otps)
    exactly. `otp_hash` is produced by modules.identity.domain.otp.
    hash_otp() — reused, not duplicated, for this security-sensitive
    HMAC code (ADR-0028 §3's one deliberate exception to the
    "duplicate small pure domain helpers" precedent)."""

    id: uuid.UUID
    ride_id: uuid.UUID
    otp_hash: str
    expires_at: datetime
    attempts: int
    status: RideOtpStatus
    created_at: datetime

    @staticmethod
    def new(
        *,
        ride_id: uuid.UUID,
        otp_hash: str,
        expiry_seconds: int,
        now: datetime,
    ) -> RideOtp:
        return RideOtp(
            id=uuid.uuid4(),
            ride_id=ride_id,
            otp_hash=otp_hash,
            expires_at=now + timedelta(seconds=expiry_seconds),
            attempts=0,
            status=RideOtpStatus.ACTIVE,
            created_at=now,
        )


@dataclass(slots=True)
class EarlyDropRequest:
    """Phase 08 (Early Drop, ADR-0030). Field shapes match database-
    design.md §12.1 (ride.early_drop_requests) exactly, plus the
    additive `reason` column (ADR-0030 Decision 4). `gps_location` is
    only ever set once both `customer_confirmed`/`driver_confirmed` are
    True (ADR-0030 Decision 1: recorded as evidence, never verified
    against a threshold) — None until then."""

    id: uuid.UUID
    ride_id: uuid.UUID
    requested_by: uuid.UUID
    reason: str | None
    customer_confirmed: bool
    driver_confirmed: bool
    gps_location: Coordinates | None
    requested_at: datetime
    confirmed_at: datetime | None

    @property
    def is_fully_confirmed(self) -> bool:
        return self.customer_confirmed and self.driver_confirmed

    @staticmethod
    def new(
        *,
        ride_id: uuid.UUID,
        requested_by: uuid.UUID,
        reason: str | None,
        now: datetime,
    ) -> EarlyDropRequest:
        return EarlyDropRequest(
            id=uuid.uuid4(),
            ride_id=ride_id,
            requested_by=requested_by,
            reason=reason,
            customer_confirmed=False,
            driver_confirmed=False,
            gps_location=None,
            requested_at=now,
            confirmed_at=None,
        )


class ChangeRequestType(StrEnum):
    """database-design.md §11.1's documented `request_type` values — one
    shared table for both Ride Modifications commands (ADR-0033).
    DESTINATION_CHANGE is documented but not yet implemented by any
    service method; the table/entity shape is deliberately unified now
    so that future work reuses this schema rather than adding a second,
    parallel one."""

    PICKUP_CHANGE = "PICKUP_CHANGE"
    DESTINATION_CHANGE = "DESTINATION_CHANGE"


class ChangeRequestStatus(StrEnum):
    """state-machines.md §14-16 (BR-071/075-078, ADR-0033).
    AWAITING_DRIVER_DECISION/PASSED were only ever reached by a
    PICKUP_CHANGE request — DESTINATION_CHANGE has no driver-decision
    step. As of ADR-0056 (2026-08-31), pickup change no longer has a
    driver-decision step either: a request either applies immediately
    (≤threshold) or is rejected outright (>threshold, PickupChangeTooFar
    Error) — no PICKUP_CHANGE row is ever created either way anymore.
    These two values are kept in the enum only for schema/backward
    compatibility with any request row created before that ADR; new
    code never sets them."""

    AWAITING_DRIVER_DECISION = "AWAITING_DRIVER_DECISION"
    AWAITING_CUSTOMER_CONFIRMATION = "AWAITING_CUSTOMER_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    PASSED = "PASSED"


class ChangeRequestDriverDecision(StrEnum):
    PROCEED = "PROCEED"
    PASS_ = "PASS"


class ChangeRequestCustomerDecision(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


@dataclass(slots=True)
class ChangeRequest:
    """ADR-0033 Decision 4. Field shapes match database-design.md §11.1
    (ride.change_requests) exactly — one table shared by both Pickup
    Change and (a future) Destination Change, discriminated by
    `request_type`. `old_location`/`old_fare_quote_id` capture the
    ride's state at request time (audit/rollback reference);
    `new_fare_quote_id` stays None until the driver's PROCEED decision
    computes one (ADR-0033 Decision 6) — a PASS decision, or the request
    being REJECTED by the customer, never sets one. No `distance_meters`
    column exists in the documented schema — callers recompute it from
    `old_location`/`new_location` via haversine_distance_meters() rather
    than persisting a derived value."""

    id: uuid.UUID
    ride_id: uuid.UUID
    request_type: ChangeRequestType
    requested_by: uuid.UUID
    old_location: Coordinates | None
    new_location: Coordinates
    old_fare_quote_id: uuid.UUID | None
    new_fare_quote_id: uuid.UUID | None
    status: ChangeRequestStatus
    driver_decision: ChangeRequestDriverDecision | None
    customer_decision: ChangeRequestCustomerDecision | None
    created_at: datetime
    resolved_at: datetime | None

    @staticmethod
    def new(
        *,
        ride_id: uuid.UUID,
        request_type: ChangeRequestType,
        requested_by: uuid.UUID,
        old_location: Coordinates | None,
        new_location: Coordinates,
        old_fare_quote_id: uuid.UUID | None,
        status: ChangeRequestStatus,
        now: datetime,
        new_fare_quote_id: uuid.UUID | None = None,
    ) -> ChangeRequest:
        return ChangeRequest(
            id=uuid.uuid4(),
            ride_id=ride_id,
            request_type=request_type,
            requested_by=requested_by,
            old_location=old_location,
            new_location=new_location,
            old_fare_quote_id=old_fare_quote_id,
            new_fare_quote_id=new_fare_quote_id,
            status=status,
            driver_decision=None,
            customer_decision=None,
            created_at=now,
            resolved_at=None,
        )


class GpsDisputeStatus(StrEnum):
    """state-machines.md §69 (BR-124/BR-125, ADR-0032)."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


class GpsDisputeDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class GpsDisputeEvidenceType(StrEnum):
    """BR-125's documented evidence types."""

    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    DOCUMENT = "DOCUMENT"
    TEXT = "TEXT"


@dataclass(slots=True)
class GpsDispute:
    """Field shapes match database-design.md §14.2 (ride.gps_disputes)
    exactly. Auto-opened by mark_arrived()/complete_ride() (ADR-0028)
    when GPS verification reaches its terminal GPS_VERIFICATION_FAILED
    outcome — never created directly in response to a client request
    (ADR-0032 Decision 2)."""

    id: uuid.UUID
    ride_id: uuid.UUID
    gps_verification_id: uuid.UUID
    verification_type: GpsVerificationType
    opened_at: datetime
    evidence_deadline: datetime
    status: GpsDisputeStatus
    decision: GpsDisputeDecision | None
    decided_by: uuid.UUID | None
    decided_reason: str | None
    decided_at: datetime | None

    def is_past_deadline(self, *, now: datetime) -> bool:
        return now > self.evidence_deadline

    @staticmethod
    def new(
        *,
        ride_id: uuid.UUID,
        gps_verification_id: uuid.UUID,
        verification_type: GpsVerificationType,
        evidence_window_seconds: int,
        now: datetime,
    ) -> GpsDispute:
        return GpsDispute(
            id=uuid.uuid4(),
            ride_id=ride_id,
            gps_verification_id=gps_verification_id,
            verification_type=verification_type,
            opened_at=now,
            evidence_deadline=now + timedelta(seconds=evidence_window_seconds),
            status=GpsDisputeStatus.OPEN,
            decision=None,
            decided_by=None,
            decided_reason=None,
            decided_at=None,
        )


@dataclass(slots=True)
class GpsDisputeEvidence:
    """Field shapes match database-design.md §14.3
    (ride.gps_dispute_evidence) exactly. `uri` is set for PHOTO/VIDEO/
    DOCUMENT, `text_explanation` for TEXT — never both (BR-125)."""

    id: uuid.UUID
    dispute_id: uuid.UUID
    submitted_by: uuid.UUID
    evidence_type: GpsDisputeEvidenceType
    uri: str | None
    text_explanation: str | None
    submitted_at: datetime

    @staticmethod
    def new(
        *,
        dispute_id: uuid.UUID,
        submitted_by: uuid.UUID,
        evidence_type: GpsDisputeEvidenceType,
        uri: str | None,
        text_explanation: str | None,
        now: datetime,
    ) -> GpsDisputeEvidence:
        return GpsDisputeEvidence(
            id=uuid.uuid4(),
            dispute_id=dispute_id,
            submitted_by=submitted_by,
            evidence_type=evidence_type,
            uri=uri,
            text_explanation=text_explanation,
            submitted_at=now,
        )
