"""Unit tests for RideService against an in-memory fake repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from modules.identity.domain.otp import hash_otp
from modules.ride.domain.entities import (
    Coordinates,
    EarlyDropRequest,
    GpsDispute,
    GpsDisputeEvidence,
    GpsDisputeStatus,
    GpsVerification,
    GpsVerificationResult,
    Ride,
    RideOtp,
    RideOtpStatus,
    RideStatus,
)
from modules.ride.domain.errors import (
    EarlyDropAlreadyRequestedError,
    EarlyDropLocationRequiredError,
    EarlyDropRequestNotFoundError,
    GpsDisputeNotFoundError,
    GpsDisputeNotOpenError,
    GpsVerificationFailedError,
    InvalidCancellationReasonError,
    InvalidCoordinateError,
    InvalidGpsDisputeActionError,
    InvalidGpsDisputeEvidenceError,
    NotWithinDestinationRadiusError,
    NotWithinPickupRadiusError,
    RideAlreadyAssignedError,
    RideNotCancellableError,
    RideNotCompletableError,
    RideNotFoundError,
    RideNotInExpectedStateError,
    RideOtpExpiredError,
    RideOtpInvalidError,
    RideOtpMaxAttemptsError,
)
from modules.ride.service import RideService
from modules.vehicle.domain.errors import InvalidCategoryError


class FakeRideRepository:
    def __init__(self) -> None:
        self.created: list[Ride] = []
        self.history: list[dict[str, object]] = []
        self.active_fare_quote_by_ride: dict[uuid.UUID, uuid.UUID] = {}

    def create(self, ride: Ride) -> Ride:
        self.created.append(ride)
        return ride

    def get_by_id(self, ride_id: uuid.UUID) -> Ride | None:
        return next((r for r in self.created if r.id == ride_id), None)

    def get_by_id_for_update(self, ride_id: uuid.UUID) -> Ride | None:
        # No real locking in the fake — same shape as get_by_id().
        return self.get_by_id(ride_id)

    def save(
        self,
        ride: Ride,
        *,
        from_status: RideStatus,
        reason: str | None,
        actor_type: str,
        actor_id: uuid.UUID,
    ) -> None:
        if not any(r.id == ride.id for r in self.created):
            raise LookupError(f"Ride {ride.id} not found")
        self.history.append(
            {
                "ride_id": ride.id,
                "from_status": from_status,
                "to_status": ride.status,
                "reason": reason,
                "actor_type": actor_type,
                "actor_id": actor_id,
            }
        )

    def set_active_fare_quote(
        self, ride_id: uuid.UUID, fare_quote_id: uuid.UUID
    ) -> None:
        if not any(r.id == ride_id for r in self.created):
            raise LookupError(f"Ride {ride_id} not found")
        self.active_fare_quote_by_ride[ride_id] = fare_quote_id

    def update_current_pickup(self, ride_id: uuid.UUID, pickup: Coordinates) -> None:
        ride = self.get_by_id(ride_id)
        if ride is None:
            raise LookupError(f"Ride {ride_id} not found")
        ride.current_pickup = pickup

    def update_current_destination(
        self, ride_id: uuid.UUID, destination: Coordinates
    ) -> None:
        ride = self.get_by_id(ride_id)
        if ride is None:
            raise LookupError(f"Ride {ride_id} not found")
        ride.current_destination = destination

    def search(
        self,
        *,
        status: str | None,
        driver_id: uuid.UUID | None,
        customer_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Ride], int]:
        matches = [
            r
            for r in self.created
            if (status is None or r.status.value == status)
            and (driver_id is None or r.driver_id == driver_id)
            and (customer_id is None or r.customer_id == customer_id)
        ]
        return matches[offset : offset + limit], len(matches)

    def list_due_scheduled(self, *, before: datetime, limit: int) -> list[Ride]:
        due = [
            r
            for r in self.created
            if r.status is RideStatus.SCHEDULED
            and r.lock_in_at is not None
            and r.lock_in_at <= before
        ]
        due.sort(key=lambda r: cast(datetime, r.lock_in_at))
        return due[:limit]

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.created:
            if since <= r.created_at < until:
                key = r.status.value
                counts[key] = counts.get(key, 0) + 1
        return counts

    def count_by_vehicle_category_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.created:
            if since <= r.created_at < until:
                key = r.requested_vehicle_category.value
                counts[key] = counts.get(key, 0) + 1
        return counts

    def list_active_fare_quote_ids_for_closed_in_range(
        self, *, since: datetime, until: datetime
    ) -> list[uuid.UUID]:
        return [
            r.active_fare_quote_id
            for r in self.created
            if r.status.value == "CLOSED"
            and r.active_fare_quote_id is not None
            and since <= r.created_at < until
        ]


class FakeGpsVerificationRepository:
    """Phase 06/07 (ADR-0028)."""

    def __init__(self) -> None:
        self.created: list[GpsVerification] = []

    def create(self, verification: GpsVerification) -> GpsVerification:
        self.created.append(verification)
        return verification

    def count_failed(self, ride_id: uuid.UUID, *, verification_type: str) -> int:
        return sum(
            1
            for v in self.created
            if v.ride_id == ride_id
            and v.verification_type.value == verification_type
            and v.result is GpsVerificationResult.FAIL
        )


class FakeRideOtpRepository:
    """Phase 06/07 (ADR-0028)."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, RideOtp] = {}

    def create(self, otp: RideOtp) -> RideOtp:
        self.rows[otp.id] = otp
        return otp

    def get_active_for_update(self, ride_id: uuid.UUID) -> RideOtp | None:
        candidates = [
            o
            for o in self.rows.values()
            if o.ride_id == ride_id and o.status is RideOtpStatus.ACTIVE
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda o: o.created_at)

    def save(self, otp: RideOtp) -> None:
        if otp.id not in self.rows:
            raise LookupError(f"RideOtp {otp.id} not found")
        self.rows[otp.id] = otp


class FakeEarlyDropRequestRepository:
    """Phase 08 (ADR-0030)."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, EarlyDropRequest] = {}
        self.deleted: list[uuid.UUID] = []

    def create(self, request: EarlyDropRequest) -> EarlyDropRequest:
        self.rows[request.id] = request
        return request

    def get_pending_for_update(self, ride_id: uuid.UUID) -> EarlyDropRequest | None:
        candidates = [
            r
            for r in self.rows.values()
            if r.ride_id == ride_id and r.confirmed_at is None
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.requested_at)

    def save(self, request: EarlyDropRequest) -> None:
        if request.id not in self.rows:
            raise LookupError(f"EarlyDropRequest {request.id} not found")
        self.rows[request.id] = request

    def delete(self, request_id: uuid.UUID) -> None:
        if request_id not in self.rows:
            raise LookupError(f"EarlyDropRequest {request_id} not found")
        del self.rows[request_id]
        self.deleted.append(request_id)


class FakeGpsDisputeRepository:
    """BR-124/BR-125 (ADR-0032)."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, GpsDispute] = {}

    def create(self, dispute: GpsDispute) -> GpsDispute:
        self.rows[dispute.id] = dispute
        return dispute

    def get_by_id_for_update(self, dispute_id: uuid.UUID) -> GpsDispute | None:
        return self.rows.get(dispute_id)

    def get_by_id(self, dispute_id: uuid.UUID) -> GpsDispute | None:
        return self.rows.get(dispute_id)

    def list_for_ride(self, ride_id: uuid.UUID) -> list[GpsDispute]:
        matches = [d for d in self.rows.values() if d.ride_id == ride_id]
        matches.sort(key=lambda d: d.opened_at, reverse=True)
        return matches

    def save(self, dispute: GpsDispute) -> None:
        if dispute.id not in self.rows:
            raise LookupError(f"GpsDispute {dispute.id} not found")
        self.rows[dispute.id] = dispute

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[GpsDispute], int]:
        matches = [
            d for d in self.rows.values() if status is None or d.status.value == status
        ]
        matches.sort(key=lambda d: d.opened_at, reverse=True)
        return matches[offset : offset + limit], len(matches)


class FakeGpsDisputeEvidenceRepository:
    """BR-125 (ADR-0032)."""

    def __init__(self) -> None:
        self.rows: list[GpsDisputeEvidence] = []

    def create(self, evidence: GpsDisputeEvidence) -> GpsDisputeEvidence:
        self.rows.append(evidence)
        return evidence

    def list_for_dispute(self, dispute_id: uuid.UUID) -> list[GpsDisputeEvidence]:
        return sorted(
            (e for e in self.rows if e.dispute_id == dispute_id),
            key=lambda e: e.submitted_at,
        )


@pytest.fixture
def repo() -> FakeRideRepository:
    return FakeRideRepository()


@pytest.fixture
def service(repo: FakeRideRepository) -> RideService:
    return RideService(rides=repo)


@pytest.fixture
def gps_repo() -> FakeGpsVerificationRepository:
    return FakeGpsVerificationRepository()


@pytest.fixture
def otp_repo() -> FakeRideOtpRepository:
    return FakeRideOtpRepository()


@pytest.fixture
def early_drop_repo() -> FakeEarlyDropRequestRepository:
    return FakeEarlyDropRequestRepository()


@pytest.fixture
def gps_dispute_repo() -> FakeGpsDisputeRepository:
    return FakeGpsDisputeRepository()


@pytest.fixture
def gps_dispute_evidence_repo() -> FakeGpsDisputeEvidenceRepository:
    return FakeGpsDisputeEvidenceRepository()


@pytest.fixture
def full_service(
    repo: FakeRideRepository,
    gps_repo: FakeGpsVerificationRepository,
    otp_repo: FakeRideOtpRepository,
    early_drop_repo: FakeEarlyDropRequestRepository,
    gps_dispute_repo: FakeGpsDisputeRepository,
    gps_dispute_evidence_repo: FakeGpsDisputeEvidenceRepository,
) -> RideService:
    """Phase 06/07 (ADR-0028) + Phase 08 (ADR-0030) + BR-124/BR-125
    (ADR-0032) — wires all six repositories, needed for mark_arrived()/
    refresh_otp()/start_ride()/complete_ride()/request_early_drop()/
    confirm_early_drop()/submit_gps_dispute_evidence()/get_gps_dispute()/
    search_gps_disputes()/resolve_gps_dispute()."""
    return RideService(
        rides=repo,
        gps_verifications=gps_repo,
        ride_otps=otp_repo,
        early_drop_requests=early_drop_repo,
        gps_disputes=gps_dispute_repo,
        gps_dispute_evidence=gps_dispute_evidence_repo,
    )


CUSTOMER_ID = uuid.uuid4()
NOW = datetime.now(UTC)

# Same fixed pickup/destination _create() below defaults to.
_PICKUP_LAT, _PICKUP_LON = 25.5941, 85.1376
_DESTINATION_LAT, _DESTINATION_LON = 25.6120, 85.1580
# ~1.1km away — well outside both the 50m arrival and 100m completion
# radii used in tests below.
_FAR_LAT, _FAR_LON = _PICKUP_LAT + 0.01, _PICKUP_LON
_ARRIVAL_RADIUS_METERS = 50.0
_COMPLETION_RADIUS_METERS = 100.0
_MAX_GPS_ATTEMPTS_BEFORE_REVIEW = 3
_DISPUTE_EVIDENCE_WINDOW_SECONDS = 24 * 3600
_OTP_EXPIRY_SECONDS = 900
_OTP_MAX_ATTEMPTS = 5
_OTP_HASH_PEPPER = "test-ride-otp-pepper"


def _create(service: RideService, **overrides: object) -> Ride:
    defaults: dict[str, object] = {
        "customer_id": CUSTOMER_ID,
        "pickup_latitude": 25.5941,
        "pickup_longitude": 85.1376,
        "destination_latitude": 25.6120,
        "destination_longitude": 85.1580,
        "vehicle_category": "CAB",
        "cab_tier": "ECO",
    }
    defaults.update(overrides)
    # ADR-0020 Decision 1: cab_tier is only valid alongside CAB.
    if defaults["vehicle_category"] != "CAB" and "cab_tier" not in overrides:
        defaults.pop("cab_tier")
    return service.create_ride(**defaults)  # type: ignore[arg-type]


def test_create_ride_persists_via_repository(
    service: RideService, repo: FakeRideRepository
) -> None:
    ride = _create(service)
    assert repo.created == [ride]


def test_create_ride_returns_searching_status(service: RideService) -> None:
    ride = _create(service)
    assert ride.status is RideStatus.SEARCHING


def test_create_ride_belongs_to_the_requesting_customer(service: RideService) -> None:
    ride = _create(service)
    assert ride.customer_id == CUSTOMER_ID


@pytest.mark.parametrize("category", ["BIKE", "AUTO", "CAB"])
def test_create_ride_accepts_every_documented_category(
    service: RideService, category: str
) -> None:
    ride = _create(service, vehicle_category=category)
    assert ride.status is RideStatus.SEARCHING


def test_create_ride_rejects_lowercase_category(service: RideService) -> None:
    """modules.vehicle.domain.entities.validate_category (reused as-is,
    no new normalization added here) is case-sensitive — matches
    existing Add Vehicle behavior exactly."""
    with pytest.raises(InvalidCategoryError):
        _create(service, vehicle_category="cab")


def test_create_ride_rejects_unknown_vehicle_category(service: RideService) -> None:
    with pytest.raises(InvalidCategoryError):
        _create(service, vehicle_category="TRUCK")


def test_create_ride_rejects_invalid_pickup_coordinates(service: RideService) -> None:
    with pytest.raises(InvalidCoordinateError):
        _create(service, pickup_latitude=999.0)


def test_create_ride_rejects_invalid_destination_coordinates(
    service: RideService,
) -> None:
    with pytest.raises(InvalidCoordinateError):
        _create(service, destination_longitude=999.0)


def test_create_ride_does_not_set_a_fare_quote(service: RideService) -> None:
    """ADR-0010 Decision 1: Task 3.1 never calculates a fare —
    set_active_fare_quote() is a separate, later call (ADR-0020
    Decision 6, composed from modules/ride/router.py)."""
    ride = _create(service)
    assert ride.active_fare_quote_id is None


def test_create_ride_requesting_cab_persists_the_tier(service: RideService) -> None:
    """ADR-0020 Decision 1."""
    ride = _create(service, vehicle_category="CAB", cab_tier="PREMIUM_PLUS")
    assert ride.requested_cab_tier is not None
    assert ride.requested_cab_tier.value == "PREMIUM_PLUS"


def test_set_active_fare_quote_updates_the_ride(
    service: RideService, repo: FakeRideRepository
) -> None:
    """ADR-0020 Decision 6."""
    ride = _create(service)
    fare_quote_id = uuid.uuid4()

    service.set_active_fare_quote(ride_id=ride.id, fare_quote_id=fare_quote_id)

    assert repo.active_fare_quote_by_ride[ride.id] == fare_quote_id


def test_get_ride_returns_a_previously_created_ride(service: RideService) -> None:
    created = _create(service)
    fetched = service.get_ride(ride_id=created.id)
    assert fetched == created


def test_get_ride_returns_none_for_unknown_id(service: RideService) -> None:
    assert service.get_ride(ride_id=uuid.uuid4()) is None


# --- cancel_ride (Phase 3 / Task 3.3, ADR-0012) -----------------------------


def test_cancel_ride_transitions_searching_ride_to_cancelled(
    service: RideService,
) -> None:
    ride = _create(service)

    cancelled, previous_status = service.cancel_ride(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        reason="CUSTOMER_CHANGED_PLANS",
        now=NOW,
    )

    assert cancelled.status is RideStatus.CANCELLED
    assert cancelled.cancelled_at is not None
    assert previous_status is RideStatus.SEARCHING


def test_cancel_ride_records_state_history(
    service: RideService, repo: FakeRideRepository
) -> None:
    ride = _create(service)

    service.cancel_ride(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        reason="CUSTOMER_CHANGED_PLANS",
        now=NOW,
    )

    assert len(repo.history) == 1
    entry = repo.history[0]
    assert entry["from_status"] is RideStatus.SEARCHING
    assert entry["to_status"] is RideStatus.CANCELLED
    assert entry["reason"] == "CUSTOMER_CHANGED_PLANS"
    assert entry["actor_type"] == "CUSTOMER"
    assert entry["actor_id"] == CUSTOMER_ID


def test_cancel_ride_raises_for_unknown_ride(service: RideService) -> None:
    with pytest.raises(RideNotFoundError):
        service.cancel_ride(
            ride_id=uuid.uuid4(), customer_id=CUSTOMER_ID, reason="x", now=NOW
        )


def test_cancel_ride_raises_when_ride_belongs_to_another_customer(
    service: RideService,
) -> None:
    ride = _create(service)
    with pytest.raises(RideNotFoundError):
        service.cancel_ride(
            ride_id=ride.id, customer_id=uuid.uuid4(), reason="x", now=NOW
        )


def test_cancel_ride_raises_when_already_cancelled(service: RideService) -> None:
    ride = _create(service)
    service.cancel_ride(ride_id=ride.id, customer_id=CUSTOMER_ID, reason="x", now=NOW)

    with pytest.raises(RideNotCancellableError):
        service.cancel_ride(
            ride_id=ride.id, customer_id=CUSTOMER_ID, reason="x", now=NOW
        )


def test_cancel_ride_rejects_blank_reason(service: RideService) -> None:
    ride = _create(service)
    with pytest.raises(InvalidCancellationReasonError):
        service.cancel_ride(
            ride_id=ride.id, customer_id=CUSTOMER_ID, reason="   ", now=NOW
        )


def test_cancel_ride_rejects_reason_over_max_length(service: RideService) -> None:
    ride = _create(service)
    with pytest.raises(InvalidCancellationReasonError):
        service.cancel_ride(
            ride_id=ride.id, customer_id=CUSTOMER_ID, reason="x" * 101, now=NOW
        )


def test_cancel_ride_allows_accepted_ride(service: RideService) -> None:
    """Phase 3 / Task 3.5 (ADR-0015) — the whole reason this task
    exists: ACCEPTED is now a cancellable state, not just SEARCHING."""
    ride = _create(service)
    accepted = service.accept_ride(
        ride_id=ride.id, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4(), now=NOW
    )

    cancelled, previous_status = service.cancel_ride(
        ride_id=accepted.id, customer_id=CUSTOMER_ID, reason="x", now=NOW
    )

    assert cancelled.status is RideStatus.CANCELLED
    assert previous_status is RideStatus.ACCEPTED


# --- driver_cancel_ride (Phase 3 / Task 3.6, ADR-0016) ----------------------


def test_driver_cancel_ride_transitions_accepted_to_cancelled(
    service: RideService,
) -> None:
    ride = _create(service)
    driver_id = uuid.uuid4()
    service.accept_ride(
        ride_id=ride.id, driver_id=driver_id, vehicle_id=uuid.uuid4(), now=NOW
    )

    cancelled = service.driver_cancel_ride(
        ride_id=ride.id, driver_id=driver_id, reason="UNWILLING_TO_PROCEED", now=NOW
    )

    assert cancelled.status is RideStatus.CANCELLED
    assert cancelled.cancelled_at is not None


def test_driver_cancel_ride_raises_for_searching_ride(service: RideService) -> None:
    """A SEARCHING ride never has driver_id set, so an unrelated
    driver_id fails the ownership check first — same IDOR-safe "not
    found" treatment used throughout this codebase, not the status
    check (there is no reachable state where a SEARCHING ride has a
    real assigned driver_id to test the status check against here)."""
    ride = _create(service)
    with pytest.raises(RideNotFoundError):
        service.driver_cancel_ride(
            ride_id=ride.id, driver_id=uuid.uuid4(), reason="x", now=NOW
        )


def test_driver_cancel_ride_raises_once_already_cancelled(
    service: RideService,
) -> None:
    """state-machines.md §13: driver cancellation is ACCEPTED ->
    CANCELLED only. Uses a ride the SAME driver was assigned to and
    that has since moved past ACCEPTED (customer-cancelled) — a
    genuinely reachable state where the ownership check passes but the
    status check must still refuse."""
    ride = _create(service)
    driver_id = uuid.uuid4()
    accepted = service.accept_ride(
        ride_id=ride.id, driver_id=driver_id, vehicle_id=uuid.uuid4(), now=NOW
    )
    service.cancel_ride(
        ride_id=accepted.id, customer_id=CUSTOMER_ID, reason="x", now=NOW
    )

    with pytest.raises(RideNotCancellableError):
        service.driver_cancel_ride(
            ride_id=ride.id, driver_id=driver_id, reason="x", now=NOW
        )


def test_driver_cancel_ride_raises_when_ride_belongs_to_another_driver(
    service: RideService,
) -> None:
    ride = _create(service)
    service.accept_ride(
        ride_id=ride.id, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4(), now=NOW
    )

    with pytest.raises(RideNotFoundError):
        service.driver_cancel_ride(
            ride_id=ride.id, driver_id=uuid.uuid4(), reason="x", now=NOW
        )


def test_driver_cancel_ride_raises_for_arrived_ride(service: RideService) -> None:
    """ADR-0016 Decision 1: unlike customer cancellation, driver
    cancellation does not extend to ARRIVED — only ACCEPTED, matching
    state-machines.md §13's literal transition."""
    ride = _create(service)
    driver_id = uuid.uuid4()
    accepted = service.accept_ride(
        ride_id=ride.id, driver_id=driver_id, vehicle_id=uuid.uuid4(), now=NOW
    )
    accepted.status = RideStatus.ARRIVED  # simulate ACCEPTED -> ARRIVED

    with pytest.raises(RideNotCancellableError):
        service.driver_cancel_ride(
            ride_id=accepted.id, driver_id=driver_id, reason="x", now=NOW
        )


# --- accept_ride (Phase 3 / Task 3.4, ADR-0014) -----------------------------


def test_accept_ride_transitions_searching_ride_to_accepted(
    service: RideService,
) -> None:
    ride = _create(service)
    driver_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()

    accepted = service.accept_ride(
        ride_id=ride.id, driver_id=driver_id, vehicle_id=vehicle_id, now=NOW
    )

    assert accepted.status is RideStatus.ACCEPTED
    assert accepted.driver_id == driver_id
    assert accepted.vehicle_id == vehicle_id
    assert accepted.accepted_at == NOW


def test_accept_ride_records_state_history(
    service: RideService, repo: FakeRideRepository
) -> None:
    ride = _create(service)
    driver_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()

    service.accept_ride(
        ride_id=ride.id, driver_id=driver_id, vehicle_id=vehicle_id, now=NOW
    )

    assert len(repo.history) == 1
    entry = repo.history[0]
    assert entry["from_status"] is RideStatus.SEARCHING
    assert entry["to_status"] is RideStatus.ACCEPTED
    assert entry["reason"] is None
    assert entry["actor_type"] == "DRIVER"
    assert entry["actor_id"] == driver_id


def test_accept_ride_raises_for_unknown_ride(service: RideService) -> None:
    with pytest.raises(RideNotFoundError):
        service.accept_ride(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            now=NOW,
        )


def test_accept_ride_raises_when_not_searching(service: RideService) -> None:
    ride = _create(service)
    service.accept_ride(
        ride_id=ride.id, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4(), now=NOW
    )

    with pytest.raises(RideAlreadyAssignedError):
        service.accept_ride(
            ride_id=ride.id, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4(), now=NOW
        )


def test_accept_ride_raises_when_cancelled(service: RideService) -> None:
    ride = _create(service)
    service.cancel_ride(ride_id=ride.id, customer_id=CUSTOMER_ID, reason="x", now=NOW)

    with pytest.raises(RideAlreadyAssignedError):
        service.accept_ride(
            ride_id=ride.id, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4(), now=NOW
        )


# --- search_rides() (Phase 16, ADR-0023) -----------------------------------


def test_search_rides_filters_by_status(service: RideService) -> None:
    searching = _create(service)
    accepted = _create(service)
    service.accept_ride(
        ride_id=accepted.id, driver_id=uuid.uuid4(), vehicle_id=uuid.uuid4(), now=NOW
    )

    results, total = service.search_rides(
        status="SEARCHING", driver_id=None, customer_id=None, offset=0, limit=20
    )

    assert total == 1
    assert [r.id for r in results] == [searching.id]


def test_search_rides_filters_by_customer_id(service: RideService) -> None:
    mine = _create(service)
    _create(service, customer_id=uuid.uuid4())

    results, total = service.search_rides(
        status=None, driver_id=None, customer_id=CUSTOMER_ID, offset=0, limit=20
    )

    assert total == 1
    assert [r.id for r in results] == [mine.id]


def test_search_rides_filters_by_driver_id(service: RideService) -> None:
    ride = _create(service)
    driver_id = uuid.uuid4()
    service.accept_ride(
        ride_id=ride.id, driver_id=driver_id, vehicle_id=uuid.uuid4(), now=NOW
    )
    _create(service)  # a second, unrelated ride with no driver

    results, total = service.search_rides(
        status=None, driver_id=driver_id, customer_id=None, offset=0, limit=20
    )

    assert total == 1
    assert [r.id for r in results] == [ride.id]


def test_search_rides_paginates(service: RideService) -> None:
    for _ in range(3):
        _create(service)

    page, total = service.search_rides(
        status=None, driver_id=None, customer_id=None, offset=0, limit=2
    )

    assert total == 3
    assert len(page) == 2


# --- mark_arrived / refresh_otp / start_ride / complete_ride ---------------
# Phase 06/07 (GPS Verification Foundation & Ride Lifecycle, ADR-0028).


def _accept(service: RideService, *, driver_id: uuid.UUID | None = None) -> Ride:
    ride = _create(service)
    return service.accept_ride(
        ride_id=ride.id,
        driver_id=driver_id or uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        now=NOW,
    )


def _arrive(service: RideService, *, driver_id: uuid.UUID) -> Ride:
    accepted = _accept(service, driver_id=driver_id)
    ride, _verification = service.mark_arrived(
        ride_id=accepted.id,
        driver_id=driver_id,
        latitude=_PICKUP_LAT,
        longitude=_PICKUP_LON,
        radius_meters=_ARRIVAL_RADIUS_METERS,
        max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
        dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )
    return ride


def test_mark_arrived_transitions_accepted_to_arrived(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)

    assert ride.status is RideStatus.ARRIVED
    assert ride.arrived_at == NOW


def test_mark_arrived_records_a_pass_verification(
    full_service: RideService, gps_repo: FakeGpsVerificationRepository
) -> None:
    driver_id = uuid.uuid4()
    _arrive(full_service, driver_id=driver_id)

    assert len(gps_repo.created) == 1
    assert gps_repo.created[0].result is GpsVerificationResult.PASS_


def test_mark_arrived_auto_issues_an_active_otp(
    full_service: RideService, otp_repo: FakeRideOtpRepository
) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)

    active = otp_repo.get_active_for_update(ride.id)
    assert active is not None
    assert active.status is RideOtpStatus.ACTIVE


def test_mark_arrived_raises_for_unknown_ride(full_service: RideService) -> None:
    with pytest.raises(RideNotFoundError):
        full_service.mark_arrived(
            ride_id=uuid.uuid4(),
            driver_id=uuid.uuid4(),
            latitude=_PICKUP_LAT,
            longitude=_PICKUP_LON,
            radius_meters=_ARRIVAL_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_mark_arrived_raises_when_ride_belongs_to_another_driver(
    full_service: RideService,
) -> None:
    accepted = _accept(full_service)
    with pytest.raises(RideNotFoundError):
        full_service.mark_arrived(
            ride_id=accepted.id,
            driver_id=uuid.uuid4(),
            latitude=_PICKUP_LAT,
            longitude=_PICKUP_LON,
            radius_meters=_ARRIVAL_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_mark_arrived_raises_when_ride_not_accepted(full_service: RideService) -> None:
    ride = _create(full_service)  # still SEARCHING, no driver yet
    with pytest.raises(RideNotFoundError):
        # No driver_id was ever assigned, so any driver_id fails the
        # ownership check first — same IDOR-safe shape as
        # driver_cancel_ride's equivalent test above.
        full_service.mark_arrived(
            ride_id=ride.id,
            driver_id=uuid.uuid4(),
            latitude=_PICKUP_LAT,
            longitude=_PICKUP_LON,
            radius_meters=_ARRIVAL_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_mark_arrived_outside_radius_is_retriable(
    full_service: RideService, gps_repo: FakeGpsVerificationRepository
) -> None:
    """ADR-0028 Decision 1: attempts 1 through
    RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW - 1 raise the retriable error,
    not the terminal one — and the ride stays ACCEPTED."""
    driver_id = uuid.uuid4()
    accepted = _accept(full_service, driver_id=driver_id)

    with pytest.raises(NotWithinPickupRadiusError):
        full_service.mark_arrived(
            ride_id=accepted.id,
            driver_id=driver_id,
            latitude=_FAR_LAT,
            longitude=_FAR_LON,
            radius_meters=_ARRIVAL_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )

    assert len(gps_repo.created) == 1
    assert gps_repo.created[0].result is GpsVerificationResult.FAIL
    refetched = full_service.get_ride(ride_id=accepted.id)
    assert refetched is not None
    assert refetched.status is RideStatus.ACCEPTED


def test_mark_arrived_becomes_terminal_after_max_attempts(
    full_service: RideService,
) -> None:
    """The (max_attempts_before_review + 1)-th failed attempt raises the
    terminal, manual-review error instead of the retriable one."""
    driver_id = uuid.uuid4()
    accepted = _accept(full_service, driver_id=driver_id)

    for _ in range(_MAX_GPS_ATTEMPTS_BEFORE_REVIEW):
        with pytest.raises(NotWithinPickupRadiusError):
            full_service.mark_arrived(
                ride_id=accepted.id,
                driver_id=driver_id,
                latitude=_FAR_LAT,
                longitude=_FAR_LON,
                radius_meters=_ARRIVAL_RADIUS_METERS,
                max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
                dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
                otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
                otp_hash_pepper=_OTP_HASH_PEPPER,
                now=NOW,
            )

    with pytest.raises(GpsVerificationFailedError):
        full_service.mark_arrived(
            ride_id=accepted.id,
            driver_id=driver_id,
            latitude=_FAR_LAT,
            longitude=_FAR_LON,
            radius_meters=_ARRIVAL_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_refresh_otp_returns_a_plaintext_matching_the_stored_hash(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)

    otp, plaintext = full_service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    assert otp.otp_hash == hash_otp(plaintext, pepper=_OTP_HASH_PEPPER)
    assert otp.status is RideOtpStatus.ACTIVE


def test_refresh_otp_invalidates_the_previous_active_otp(
    full_service: RideService, otp_repo: FakeRideOtpRepository
) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)
    first_active = otp_repo.get_active_for_update(ride.id)
    assert first_active is not None

    full_service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    assert otp_repo.rows[first_active.id].status is RideOtpStatus.EXPIRED


def test_refresh_otp_raises_for_ride_belonging_to_another_customer(
    full_service: RideService,
) -> None:
    ride = _arrive(full_service, driver_id=uuid.uuid4())
    with pytest.raises(RideNotFoundError):
        full_service.refresh_otp(
            ride_id=ride.id,
            customer_id=uuid.uuid4(),
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_refresh_otp_raises_when_ride_not_arrived(full_service: RideService) -> None:
    accepted = _accept(full_service)
    with pytest.raises(RideNotInExpectedStateError):
        full_service.refresh_otp(
            ride_id=accepted.id,
            customer_id=CUSTOMER_ID,
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_start_ride_transitions_arrived_to_started(full_service: RideService) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)
    _otp, plaintext = full_service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    started = full_service.start_ride(
        ride_id=ride.id,
        driver_id=driver_id,
        otp=plaintext,
        max_attempts=_OTP_MAX_ATTEMPTS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    assert started.status is RideStatus.STARTED
    assert started.started_at == NOW


def test_start_ride_marks_the_otp_used(
    full_service: RideService, otp_repo: FakeRideOtpRepository
) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)
    otp, plaintext = full_service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    full_service.start_ride(
        ride_id=ride.id,
        driver_id=driver_id,
        otp=plaintext,
        max_attempts=_OTP_MAX_ATTEMPTS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    assert otp_repo.rows[otp.id].status is RideOtpStatus.USED


def test_start_ride_raises_for_incorrect_otp(
    full_service: RideService, otp_repo: FakeRideOtpRepository
) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)
    otp, plaintext = full_service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )
    wrong = "000000" if plaintext != "000000" else "111111"

    with pytest.raises(RideOtpInvalidError):
        full_service.start_ride(
            ride_id=ride.id,
            driver_id=driver_id,
            otp=wrong,
            max_attempts=_OTP_MAX_ATTEMPTS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )

    assert otp_repo.rows[otp.id].attempts == 1
    assert otp_repo.rows[otp.id].status is RideOtpStatus.ACTIVE


def test_start_ride_raises_after_max_attempts_exceeded(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)
    _otp, plaintext = full_service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )
    wrong = "000000" if plaintext != "000000" else "111111"

    for _ in range(_OTP_MAX_ATTEMPTS):
        with pytest.raises(RideOtpInvalidError):
            full_service.start_ride(
                ride_id=ride.id,
                driver_id=driver_id,
                otp=wrong,
                max_attempts=_OTP_MAX_ATTEMPTS,
                otp_hash_pepper=_OTP_HASH_PEPPER,
                now=NOW,
            )

    with pytest.raises(RideOtpMaxAttemptsError):
        full_service.start_ride(
            ride_id=ride.id,
            driver_id=driver_id,
            otp=plaintext,  # even the correct code no longer works
            max_attempts=_OTP_MAX_ATTEMPTS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_start_ride_raises_once_otp_expired(full_service: RideService) -> None:
    driver_id = uuid.uuid4()
    ride = _arrive(full_service, driver_id=driver_id)
    _otp, plaintext = full_service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )
    past_expiry = NOW + timedelta(seconds=_OTP_EXPIRY_SECONDS + 1)

    with pytest.raises(RideOtpExpiredError):
        full_service.start_ride(
            ride_id=ride.id,
            driver_id=driver_id,
            otp=plaintext,
            max_attempts=_OTP_MAX_ATTEMPTS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=past_expiry,
        )


def test_start_ride_raises_when_ride_not_arrived(full_service: RideService) -> None:
    accepted = _accept(full_service)
    assert accepted.driver_id is not None
    with pytest.raises(RideNotInExpectedStateError):
        full_service.start_ride(
            ride_id=accepted.id,
            driver_id=accepted.driver_id,
            otp="123456",
            max_attempts=_OTP_MAX_ATTEMPTS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def _start(service: RideService, *, driver_id: uuid.UUID) -> Ride:
    ride = _arrive(service, driver_id=driver_id)
    _otp, plaintext = service.refresh_otp(
        ride_id=ride.id,
        customer_id=CUSTOMER_ID,
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )
    return service.start_ride(
        ride_id=ride.id,
        driver_id=driver_id,
        otp=plaintext,
        max_attempts=_OTP_MAX_ATTEMPTS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )


def test_complete_ride_transitions_started_straight_to_closed(
    full_service: RideService,
) -> None:
    """ADR-0028 Decision 3: COMPLETED -> CLOSED is automatic/immediate,
    so a successful complete_ride() call leaves the ride CLOSED, not
    merely COMPLETED."""
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)

    closed, verification = full_service.complete_ride(
        ride_id=started.id,
        driver_id=driver_id,
        latitude=_DESTINATION_LAT,
        longitude=_DESTINATION_LON,
        radius_meters=_COMPLETION_RADIUS_METERS,
        max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
        dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
        now=NOW,
    )

    assert closed.status is RideStatus.CLOSED
    assert closed.completed_at == NOW
    assert closed.closed_at == NOW
    assert verification.result is GpsVerificationResult.PASS_


def test_complete_ride_records_two_state_history_rows(
    full_service: RideService, repo: FakeRideRepository
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)
    history_before = len(repo.history)

    full_service.complete_ride(
        ride_id=started.id,
        driver_id=driver_id,
        latitude=_DESTINATION_LAT,
        longitude=_DESTINATION_LON,
        radius_meters=_COMPLETION_RADIUS_METERS,
        max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
        dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
        now=NOW,
    )

    new_entries = repo.history[history_before:]
    assert [e["to_status"] for e in new_entries] == [
        RideStatus.COMPLETED,
        RideStatus.CLOSED,
    ]


def test_complete_ride_outside_radius_is_retriable(full_service: RideService) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)

    with pytest.raises(NotWithinDestinationRadiusError):
        full_service.complete_ride(
            ride_id=started.id,
            driver_id=driver_id,
            latitude=_FAR_LAT,
            longitude=_FAR_LON,
            radius_meters=_COMPLETION_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            now=NOW,
        )

    refetched = full_service.get_ride(ride_id=started.id)
    assert refetched is not None
    assert refetched.status is RideStatus.STARTED


def test_complete_ride_becomes_terminal_after_max_attempts(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)

    for _ in range(_MAX_GPS_ATTEMPTS_BEFORE_REVIEW):
        with pytest.raises(NotWithinDestinationRadiusError):
            full_service.complete_ride(
                ride_id=started.id,
                driver_id=driver_id,
                latitude=_FAR_LAT,
                longitude=_FAR_LON,
                radius_meters=_COMPLETION_RADIUS_METERS,
                max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
                dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
                now=NOW,
            )

    with pytest.raises(GpsVerificationFailedError):
        full_service.complete_ride(
            ride_id=started.id,
            driver_id=driver_id,
            latitude=_FAR_LAT,
            longitude=_FAR_LON,
            radius_meters=_COMPLETION_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            now=NOW,
        )


def test_complete_ride_raises_when_ride_not_started(full_service: RideService) -> None:
    driver_id = uuid.uuid4()
    accepted = _accept(full_service, driver_id=driver_id)
    with pytest.raises(RideNotCompletableError):
        full_service.complete_ride(
            ride_id=accepted.id,
            driver_id=driver_id,
            latitude=_DESTINATION_LAT,
            longitude=_DESTINATION_LON,
            radius_meters=_COMPLETION_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            now=NOW,
        )


def test_complete_ride_raises_when_ride_belongs_to_another_driver(
    full_service: RideService,
) -> None:
    started = _start(full_service, driver_id=uuid.uuid4())
    with pytest.raises(RideNotFoundError):
        full_service.complete_ride(
            ride_id=started.id,
            driver_id=uuid.uuid4(),
            latitude=_DESTINATION_LAT,
            longitude=_DESTINATION_LON,
            radius_meters=_COMPLETION_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            now=NOW,
        )


# --- request_early_drop / confirm_early_drop --------------------------------
# Phase 08 (Early Drop, ADR-0030).


def test_request_early_drop_creates_a_pending_request(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)

    request = full_service.request_early_drop(
        ride_id=started.id,
        customer_id=CUSTOMER_ID,
        reason="CUSTOMER_REQUESTED",
        now=NOW,
    )

    assert request.ride_id == started.id
    assert request.requested_by == CUSTOMER_ID
    assert request.reason == "CUSTOMER_REQUESTED"
    assert request.customer_confirmed is False
    assert request.driver_confirmed is False
    assert request.gps_location is None
    assert request.confirmed_at is None


def test_request_early_drop_raises_when_ride_not_started(
    full_service: RideService,
) -> None:
    accepted = _accept(full_service)
    with pytest.raises(RideNotInExpectedStateError):
        full_service.request_early_drop(
            ride_id=accepted.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
        )


def test_request_early_drop_raises_for_ride_belonging_to_another_customer(
    full_service: RideService,
) -> None:
    started = _start(full_service, driver_id=uuid.uuid4())
    with pytest.raises(RideNotFoundError):
        full_service.request_early_drop(
            ride_id=started.id, customer_id=uuid.uuid4(), reason=None, now=NOW
        )


def test_request_early_drop_raises_when_already_pending(
    full_service: RideService,
) -> None:
    started = _start(full_service, driver_id=uuid.uuid4())
    full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )

    with pytest.raises(EarlyDropAlreadyRequestedError):
        full_service.request_early_drop(
            ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
        )


def test_confirm_early_drop_customer_side_alone_does_not_close_the_ride(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)
    full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )

    ride, request = full_service.confirm_early_drop(
        ride_id=started.id,
        account_id=CUSTOMER_ID,
        confirmed=True,
        latitude=None,
        longitude=None,
        now=NOW,
    )

    assert ride is None
    assert request.customer_confirmed is True
    assert request.driver_confirmed is False

    refetched = full_service.get_ride(ride_id=started.id)
    assert refetched is not None
    assert refetched.status is RideStatus.STARTED


def test_confirm_early_drop_both_sides_closes_the_ride(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)
    full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )
    full_service.confirm_early_drop(
        ride_id=started.id,
        account_id=CUSTOMER_ID,
        confirmed=True,
        latitude=None,
        longitude=None,
        now=NOW,
    )

    ride, request = full_service.confirm_early_drop(
        ride_id=started.id,
        account_id=driver_id,
        confirmed=True,
        latitude=25.6001,
        longitude=85.1420,
        now=NOW,
    )

    assert ride is not None
    assert ride.status is RideStatus.CLOSED
    assert ride.completed_at == NOW
    assert ride.closed_at == NOW
    assert request.is_fully_confirmed
    assert request.gps_location is not None
    assert request.gps_location.latitude == 25.6001
    assert request.gps_location.longitude == 85.1420
    assert request.confirmed_at == NOW
    # BR-090 — no fare recalculation.
    assert ride.active_fare_quote_id == started.active_fare_quote_id


def test_confirm_early_drop_records_two_state_history_rows(
    full_service: RideService, repo: FakeRideRepository
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)
    full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )
    full_service.confirm_early_drop(
        ride_id=started.id,
        account_id=CUSTOMER_ID,
        confirmed=True,
        latitude=None,
        longitude=None,
        now=NOW,
    )
    history_before = len(repo.history)

    full_service.confirm_early_drop(
        ride_id=started.id,
        account_id=driver_id,
        confirmed=True,
        latitude=25.6001,
        longitude=85.1420,
        now=NOW,
    )

    new_entries = repo.history[history_before:]
    assert [e["to_status"] for e in new_entries] == [
        RideStatus.COMPLETED,
        RideStatus.CLOSED,
    ]


def test_confirm_early_drop_driver_without_gps_raises(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)
    full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )

    with pytest.raises(EarlyDropLocationRequiredError):
        full_service.confirm_early_drop(
            ride_id=started.id,
            account_id=driver_id,
            confirmed=True,
            latitude=None,
            longitude=None,
            now=NOW,
        )


def test_confirm_early_drop_false_discards_the_request(
    full_service: RideService, early_drop_repo: FakeEarlyDropRequestRepository
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)
    request = full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )

    ride, returned = full_service.confirm_early_drop(
        ride_id=started.id,
        account_id=driver_id,
        confirmed=False,
        latitude=None,
        longitude=None,
        now=NOW,
    )

    assert ride is None
    assert returned.id == request.id
    assert request.id in early_drop_repo.deleted
    assert early_drop_repo.get_pending_for_update(started.id) is None

    refetched = full_service.get_ride(ride_id=started.id)
    assert refetched is not None
    assert refetched.status is RideStatus.STARTED

    # A fresh request can be filed afterward.
    full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )


def test_confirm_early_drop_raises_when_no_pending_request(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)

    with pytest.raises(EarlyDropRequestNotFoundError):
        full_service.confirm_early_drop(
            ride_id=started.id,
            account_id=CUSTOMER_ID,
            confirmed=True,
            latitude=None,
            longitude=None,
            now=NOW,
        )


def test_confirm_early_drop_raises_for_unrelated_account(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started = _start(full_service, driver_id=driver_id)
    full_service.request_early_drop(
        ride_id=started.id, customer_id=CUSTOMER_ID, reason=None, now=NOW
    )

    with pytest.raises(RideNotFoundError):
        full_service.confirm_early_drop(
            ride_id=started.id,
            account_id=uuid.uuid4(),
            confirmed=True,
            latitude=None,
            longitude=None,
            now=NOW,
        )


# --- GPS Dispute Manual Review (submit_gps_dispute_evidence/
# get_gps_dispute/search_gps_disputes/resolve_gps_dispute) ------------------
# BR-124/BR-125 (ADR-0032).


def _open_arrival_dispute(
    full_service: RideService, *, driver_id: uuid.UUID
) -> tuple[Ride, GpsDispute]:
    """Drives mark_arrived() with out-of-radius coordinates through the
    same (max_attempts_before_review + 1)-call sequence as
    test_mark_arrived_becomes_terminal_after_max_attempts, then re-fetches
    the dispute the terminal failure opened. Returns (the ACCEPTED ride,
    the opened dispute)."""
    accepted = _accept(full_service, driver_id=driver_id)
    for _ in range(_MAX_GPS_ATTEMPTS_BEFORE_REVIEW):
        with pytest.raises(NotWithinPickupRadiusError):
            full_service.mark_arrived(
                ride_id=accepted.id,
                driver_id=driver_id,
                latitude=_FAR_LAT,
                longitude=_FAR_LON,
                radius_meters=_ARRIVAL_RADIUS_METERS,
                max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
                dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
                otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
                otp_hash_pepper=_OTP_HASH_PEPPER,
                now=NOW,
            )

    with pytest.raises(GpsVerificationFailedError) as exc_info:
        full_service.mark_arrived(
            ride_id=accepted.id,
            driver_id=driver_id,
            latitude=_FAR_LAT,
            longitude=_FAR_LON,
            radius_meters=_ARRIVAL_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )

    dispute_id = exc_info.value.dispute_id
    assert dispute_id is not None
    dispute, _evidence = full_service.get_gps_dispute(
        dispute_id=dispute_id, account_id=driver_id, is_admin=False, now=NOW
    )
    return accepted, dispute


def _open_completion_dispute(
    full_service: RideService, *, driver_id: uuid.UUID
) -> tuple[Ride, GpsDispute]:
    """Same idea as _open_arrival_dispute() but for complete_ride() (a
    real arrival first, then a terminal completion failure)."""
    started = _start(full_service, driver_id=driver_id)
    for _ in range(_MAX_GPS_ATTEMPTS_BEFORE_REVIEW):
        with pytest.raises(NotWithinDestinationRadiusError):
            full_service.complete_ride(
                ride_id=started.id,
                driver_id=driver_id,
                latitude=_FAR_LAT,
                longitude=_FAR_LON,
                radius_meters=_COMPLETION_RADIUS_METERS,
                max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
                dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
                now=NOW,
            )

    with pytest.raises(GpsVerificationFailedError) as exc_info:
        full_service.complete_ride(
            ride_id=started.id,
            driver_id=driver_id,
            latitude=_FAR_LAT,
            longitude=_FAR_LON,
            radius_meters=_COMPLETION_RADIUS_METERS,
            max_attempts_before_review=_MAX_GPS_ATTEMPTS_BEFORE_REVIEW,
            dispute_evidence_window_seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS,
            now=NOW,
        )

    dispute_id = exc_info.value.dispute_id
    assert dispute_id is not None
    dispute, _evidence = full_service.get_gps_dispute(
        dispute_id=dispute_id, account_id=driver_id, is_admin=False, now=NOW
    )
    return started, dispute


def test_mark_arrived_terminal_failure_opens_a_dispute(
    full_service: RideService, gps_dispute_repo: FakeGpsDisputeRepository
) -> None:
    driver_id = uuid.uuid4()
    accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    assert dispute.ride_id == accepted.id
    assert dispute.verification_type.value == "ARRIVAL"
    assert dispute.status is GpsDisputeStatus.OPEN
    assert dispute.opened_at == NOW
    assert dispute.evidence_deadline == NOW + timedelta(
        seconds=_DISPUTE_EVIDENCE_WINDOW_SECONDS
    )
    assert dispute.id in gps_dispute_repo.rows

    # The ride itself is left exactly where the max-attempts test already
    # asserts it stays — ACCEPTED, not auto-transitioned by the dispute.
    refetched = full_service.get_ride(ride_id=accepted.id)
    assert refetched is not None
    assert refetched.status is RideStatus.ACCEPTED


def test_complete_ride_terminal_failure_opens_a_dispute(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started, dispute = _open_completion_dispute(full_service, driver_id=driver_id)

    assert dispute.ride_id == started.id
    assert dispute.verification_type.value == "COMPLETION"
    assert dispute.status is GpsDisputeStatus.OPEN

    refetched = full_service.get_ride(ride_id=started.id)
    assert refetched is not None
    assert refetched.status is RideStatus.STARTED


def test_submit_gps_dispute_evidence_by_driver_with_a_photo(
    full_service: RideService,
    gps_dispute_evidence_repo: FakeGpsDisputeEvidenceRepository,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    evidence = full_service.submit_gps_dispute_evidence(
        dispute_id=dispute.id,
        account_id=driver_id,
        evidence_type="PHOTO",
        uri="s3://vistaar-storage/driver-uploads/evidence.jpg",
        text=None,
        now=NOW,
    )

    assert evidence.dispute_id == dispute.id
    assert evidence.submitted_by == driver_id
    assert evidence.uri == "s3://vistaar-storage/driver-uploads/evidence.jpg"
    assert evidence.text_explanation is None
    assert gps_dispute_evidence_repo.rows == [evidence]


def test_submit_gps_dispute_evidence_by_customer_with_text(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    evidence = full_service.submit_gps_dispute_evidence(
        dispute_id=dispute.id,
        account_id=CUSTOMER_ID,
        evidence_type="TEXT",
        uri=None,
        text="I was standing right next to the car when this happened.",
        now=NOW,
    )

    assert evidence.submitted_by == CUSTOMER_ID
    assert evidence.uri is None
    assert evidence.text_explanation == (
        "I was standing right next to the car when this happened."
    )


def test_submit_gps_dispute_evidence_raises_for_unrelated_account(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    with pytest.raises(GpsDisputeNotFoundError):
        full_service.submit_gps_dispute_evidence(
            dispute_id=dispute.id,
            account_id=uuid.uuid4(),
            evidence_type="TEXT",
            uri=None,
            text="Not my ride.",
            now=NOW,
        )


def test_submit_gps_dispute_evidence_raises_for_unknown_dispute(
    full_service: RideService,
) -> None:
    with pytest.raises(GpsDisputeNotFoundError):
        full_service.submit_gps_dispute_evidence(
            dispute_id=uuid.uuid4(),
            account_id=CUSTOMER_ID,
            evidence_type="TEXT",
            uri=None,
            text="Doesn't matter.",
            now=NOW,
        )


def test_submit_gps_dispute_evidence_rejects_an_unknown_evidence_type(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    with pytest.raises(InvalidGpsDisputeEvidenceError):
        full_service.submit_gps_dispute_evidence(
            dispute_id=dispute.id,
            account_id=driver_id,
            evidence_type="AUDIO",
            uri="s3://vistaar-storage/driver-uploads/clip.mp3",
            text=None,
            now=NOW,
        )


def test_submit_gps_dispute_evidence_requires_uri_for_photo(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    with pytest.raises(InvalidGpsDisputeEvidenceError):
        full_service.submit_gps_dispute_evidence(
            dispute_id=dispute.id,
            account_id=driver_id,
            evidence_type="PHOTO",
            uri=None,
            text=None,
            now=NOW,
        )


def test_submit_gps_dispute_evidence_requires_text_for_text_type(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    with pytest.raises(InvalidGpsDisputeEvidenceError):
        full_service.submit_gps_dispute_evidence(
            dispute_id=dispute.id,
            account_id=driver_id,
            evidence_type="TEXT",
            uri=None,
            text="   ",
            now=NOW,
        )


def test_submit_gps_dispute_evidence_expires_lazily_past_the_deadline(
    full_service: RideService, gps_dispute_repo: FakeGpsDisputeRepository
) -> None:
    """ADR-0032 Decision 5 — the evidence-submission call that first
    observes the 24h window has elapsed is the one that flips OPEN ->
    EXPIRED, and is itself rejected."""
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)
    past_deadline = dispute.evidence_deadline + timedelta(seconds=1)

    with pytest.raises(GpsDisputeNotOpenError):
        full_service.submit_gps_dispute_evidence(
            dispute_id=dispute.id,
            account_id=driver_id,
            evidence_type="TEXT",
            uri=None,
            text="Too late.",
            now=past_deadline,
        )

    assert gps_dispute_repo.rows[dispute.id].status is GpsDisputeStatus.EXPIRED


def test_submit_gps_dispute_evidence_raises_once_dispute_is_resolved(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)
    full_service.resolve_gps_dispute(
        dispute_id=dispute.id,
        admin_id=uuid.uuid4(),
        action="REJECT",
        reason="GPS trail confirms the driver was never within range.",
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    with pytest.raises(GpsDisputeNotOpenError):
        full_service.submit_gps_dispute_evidence(
            dispute_id=dispute.id,
            account_id=driver_id,
            evidence_type="TEXT",
            uri=None,
            text="Too late, already resolved.",
            now=NOW,
        )


def test_get_gps_dispute_admin_can_view_any_dispute(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    fetched, evidence = full_service.get_gps_dispute(
        dispute_id=dispute.id, account_id=uuid.uuid4(), is_admin=True, now=NOW
    )

    assert fetched.id == dispute.id
    assert evidence == []


def test_get_gps_dispute_raises_for_an_unrelated_customer_or_driver(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    with pytest.raises(GpsDisputeNotFoundError):
        full_service.get_gps_dispute(
            dispute_id=dispute.id, account_id=uuid.uuid4(), is_admin=False, now=NOW
        )


def test_get_gps_dispute_lazily_expires_past_the_deadline(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)
    past_deadline = dispute.evidence_deadline + timedelta(seconds=1)

    fetched, _evidence = full_service.get_gps_dispute(
        dispute_id=dispute.id, account_id=driver_id, is_admin=False, now=past_deadline
    )

    assert fetched.status is GpsDisputeStatus.EXPIRED


def test_list_gps_disputes_for_ride_returns_it_to_customer_and_driver(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    for account_id in (accepted.customer_id, driver_id):
        results = full_service.list_gps_disputes_for_ride(
            ride_id=accepted.id, account_id=account_id, is_admin=False, now=NOW
        )
        assert len(results) == 1
        fetched, evidence = results[0]
        assert fetched.id == dispute.id
        assert evidence == []


def test_list_gps_disputes_for_ride_is_empty_when_none_opened(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    accepted = _accept(full_service, driver_id=driver_id)

    results = full_service.list_gps_disputes_for_ride(
        ride_id=accepted.id,
        account_id=accepted.customer_id,
        is_admin=False,
        now=NOW,
    )

    assert results == []


def test_list_gps_disputes_for_ride_raises_for_an_unrelated_account(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    accepted, _dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    with pytest.raises(RideNotFoundError):
        full_service.list_gps_disputes_for_ride(
            ride_id=accepted.id, account_id=uuid.uuid4(), is_admin=False, now=NOW
        )


def test_list_gps_disputes_for_ride_lazily_expires_past_the_deadline(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)
    past_deadline = dispute.evidence_deadline + timedelta(seconds=1)

    results = full_service.list_gps_disputes_for_ride(
        ride_id=accepted.id, account_id=driver_id, is_admin=False, now=past_deadline
    )

    assert len(results) == 1
    assert results[0][0].status is GpsDisputeStatus.EXPIRED


def test_search_gps_disputes_filters_by_status_and_paginates(
    full_service: RideService,
) -> None:
    for _ in range(3):
        _open_arrival_dispute(full_service, driver_id=uuid.uuid4())

    open_matches, open_total = full_service.search_gps_disputes(
        status="OPEN", offset=0, limit=2
    )
    assert open_total == 3
    assert len(open_matches) == 2
    assert all(d.status is GpsDisputeStatus.OPEN for d in open_matches)

    resolved_matches, resolved_total = full_service.search_gps_disputes(
        status="RESOLVED", offset=0, limit=10
    )
    assert resolved_total == 0
    assert resolved_matches == []

    all_matches, all_total = full_service.search_gps_disputes(
        status=None, offset=0, limit=10
    )
    assert all_total == 3
    assert len(all_matches) == 3


def test_resolve_gps_dispute_approve_finalizes_the_blocked_arrival(
    full_service: RideService, otp_repo: FakeRideOtpRepository
) -> None:
    driver_id = uuid.uuid4()
    accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)
    admin_id = uuid.uuid4()

    resolved, ride = full_service.resolve_gps_dispute(
        dispute_id=dispute.id,
        admin_id=admin_id,
        action="APPROVE",
        reason="Photo evidence confirms the driver was at the pickup point.",
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    assert resolved.status is GpsDisputeStatus.RESOLVED
    assert resolved.decision is not None and resolved.decision.value == "APPROVE"
    assert resolved.decided_by == admin_id
    assert resolved.decided_at == NOW
    assert ride is not None
    assert ride.id == accepted.id
    assert ride.status is RideStatus.ARRIVED
    # APPROVE performs the exact PASS finalization mark_arrived() itself
    # would have — including auto-issuing the ride-start OTP.
    assert otp_repo.get_active_for_update(ride.id) is not None


def test_resolve_gps_dispute_approve_finalizes_the_blocked_completion(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    started, dispute = _open_completion_dispute(full_service, driver_id=driver_id)

    _resolved, ride = full_service.resolve_gps_dispute(
        dispute_id=dispute.id,
        admin_id=uuid.uuid4(),
        action="APPROVE",
        reason="Driver's GPS trail confirms arrival at the destination.",
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    assert ride is not None
    assert ride.id == started.id
    # ADR-0028 Decision 3: COMPLETED -> CLOSED is automatic/immediate.
    assert ride.status is RideStatus.CLOSED


def test_resolve_gps_dispute_reject_leaves_the_ride_unchanged(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    resolved, ride = full_service.resolve_gps_dispute(
        dispute_id=dispute.id,
        admin_id=uuid.uuid4(),
        action="REJECT",
        reason="No evidence was submitted within the window.",
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    assert resolved.decision is not None and resolved.decision.value == "REJECT"
    assert ride is None

    refetched = full_service.get_ride(ride_id=accepted.id)
    assert refetched is not None
    assert refetched.status is RideStatus.ACCEPTED


def test_resolve_gps_dispute_raises_for_an_invalid_action(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)

    with pytest.raises(InvalidGpsDisputeActionError):
        full_service.resolve_gps_dispute(
            dispute_id=dispute.id,
            admin_id=uuid.uuid4(),
            action="MAYBE",
            reason="Unsure.",
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_resolve_gps_dispute_raises_for_an_unknown_dispute(
    full_service: RideService,
) -> None:
    with pytest.raises(GpsDisputeNotFoundError):
        full_service.resolve_gps_dispute(
            dispute_id=uuid.uuid4(),
            admin_id=uuid.uuid4(),
            action="APPROVE",
            reason="N/A",
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )


def test_resolve_gps_dispute_raises_once_already_resolved(
    full_service: RideService,
) -> None:
    driver_id = uuid.uuid4()
    _accepted, dispute = _open_arrival_dispute(full_service, driver_id=driver_id)
    full_service.resolve_gps_dispute(
        dispute_id=dispute.id,
        admin_id=uuid.uuid4(),
        action="REJECT",
        reason="First decision.",
        otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
        otp_hash_pepper=_OTP_HASH_PEPPER,
        now=NOW,
    )

    with pytest.raises(GpsDisputeNotOpenError):
        full_service.resolve_gps_dispute(
            dispute_id=dispute.id,
            admin_id=uuid.uuid4(),
            action="APPROVE",
            reason="Second decision — should never be reached.",
            otp_expiry_seconds=_OTP_EXPIRY_SECONDS,
            otp_hash_pepper=_OTP_HASH_PEPPER,
            now=NOW,
        )
