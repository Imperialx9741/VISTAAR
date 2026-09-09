"""Unit tests for VehicleService against an in-memory fake repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from modules.vehicle.domain.entities import (
    DocumentVerificationStatus,
    Vehicle,
    VehicleDocument,
    VehicleVerificationStatus,
)
from modules.vehicle.domain.errors import (
    DriverNotOfflineError,
    DuplicateRegistrationNumberError,
    VehicleNotEligibleError,
    VehicleNotFoundError,
    VehicleRequiredDocumentsNotValidError,
    VehicleVerificationAlreadyDecidedError,
)
from modules.vehicle.service import VehicleService


class FakeVehicleRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Vehicle] = {}

    def list_by_driver(self, driver_id: uuid.UUID) -> list[Vehicle]:
        return [v for v in self.by_id.values() if v.driver_id == driver_id]

    def list_by_driver_for_update(self, driver_id: uuid.UUID) -> list[Vehicle]:
        # No real locking needed for a fake, in-memory, single-threaded
        # repository — same list as list_by_driver(). Real concurrency
        # behavior is covered by tests/test_vehicle_api.py's real-Postgres
        # test.
        return self.list_by_driver(driver_id)

    def get_by_id(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return self.by_id.get(vehicle_id)

    def registration_number_exists(self, registration_number: str) -> bool:
        return any(
            v.registration_number == registration_number for v in self.by_id.values()
        )

    def create(self, vehicle: Vehicle) -> Vehicle:
        self.by_id[vehicle.id] = vehicle
        return vehicle

    def save(self, vehicle: Vehicle) -> None:
        self.by_id[vehicle.id] = vehicle

    def search(
        self, *, query: str | None, status: str | None, offset: int, limit: int
    ) -> tuple[list[Vehicle], int]:
        matches = sorted(
            (
                v
                for v in self.by_id.values()
                if (query is None or query.lower() in v.registration_number.lower())
                and (status is None or v.verification_status.value == status)
            ),
            key=lambda v: v.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)


@pytest.fixture
def repo() -> FakeVehicleRepository:
    return FakeVehicleRepository()


@pytest.fixture
def service(repo: FakeVehicleRepository) -> VehicleService:
    return VehicleService(vehicles=repo)


DRIVER_ID = uuid.uuid4()
OTHER_DRIVER_ID = uuid.uuid4()


def _valid_document(
    document_type: str, *, expires_at: datetime | None = None
) -> VehicleDocument:
    """A document satisfying BR-123's required-document gate: APPROVED
    and (no expiry, or expiry in the future)."""
    doc = VehicleDocument.new(
        vehicle_id=uuid.uuid4(),
        document_type=document_type,
        document_number=None,
        evidence_uri="ref-1",
        expires_at=expires_at,
        now=datetime.now(UTC),
    )
    doc.verification_status = DocumentVerificationStatus.APPROVED
    return doc


def _valid_required_documents() -> list[VehicleDocument]:
    return [_valid_document("RC"), _valid_document("INSURANCE")]


def test_list_vehicles_returns_only_this_drivers_vehicles(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1111",
        make=None,
        model=None,
    )
    service.add_vehicle(
        driver_id=OTHER_DRIVER_ID,
        category="BIKE",
        registration_number="BR01AB2222",
        make=None,
        model=None,
    )

    result = service.list_vehicles(driver_id=DRIVER_ID)

    assert len(result) == 1
    assert result[0].driver_id == DRIVER_ID


def test_add_vehicle_succeeds_with_valid_data(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="AUTO",
        registration_number="BR01AB1234",
        make="Bajaj",
        model="RE",
    )

    assert vehicle.driver_id == DRIVER_ID
    assert vehicle.verification_status.value == "PENDING"
    assert vehicle.operational_status.value == "INACTIVE"


def test_add_vehicle_rejects_duplicate_registration_number(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    with pytest.raises(DuplicateRegistrationNumberError):
        service.add_vehicle(
            driver_id=OTHER_DRIVER_ID,
            category="CAB",
            cab_tier="ECO",
            registration_number="br01ab1234",  # same, different case
            make=None,
            model=None,
        )


def test_multiple_vehicles_per_driver_are_supported(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    service.add_vehicle(
        driver_id=DRIVER_ID,
        category="BIKE",
        registration_number="BR01AB0001",
        make=None,
        model=None,
    )
    service.add_vehicle(
        driver_id=DRIVER_ID,
        category="AUTO",
        registration_number="BR01AB0002",
        make=None,
        model=None,
    )
    service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB0003",
        make=None,
        model=None,
    )

    assert len(service.list_vehicles(driver_id=DRIVER_ID)) == 3


def test_activate_rejects_unapproved_vehicle(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    with pytest.raises(VehicleNotEligibleError):
        service.activate_vehicle(
            driver_id=DRIVER_ID,
            vehicle_id=vehicle.id,
            driver_operational_status="OFFLINE",
        )


def test_activate_succeeds_once_approved(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    # Simulates the not-yet-implemented ApproveVehicle admin command
    # (out of scope for this task) so the documented "approved" branch of
    # Activate can be exercised.
    vehicle.verification_status = VehicleVerificationStatus.APPROVED
    repo.save(vehicle)

    activated = service.activate_vehicle(
        driver_id=DRIVER_ID,
        vehicle_id=vehicle.id,
        driver_operational_status="OFFLINE",
    )

    assert activated.operational_status.value == "ACTIVE"


def test_activating_a_vehicle_deactivates_the_previously_active_one(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    """BR-122: at most one ACTIVE vehicle per driver."""
    first = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB0001",
        make=None,
        model=None,
    )
    second = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="AUTO",
        registration_number="BR01AB0002",
        make=None,
        model=None,
    )
    for v in (first, second):
        v.verification_status = VehicleVerificationStatus.APPROVED
        repo.save(v)

    service.activate_vehicle(
        driver_id=DRIVER_ID, vehicle_id=first.id, driver_operational_status="OFFLINE"
    )
    service.activate_vehicle(
        driver_id=DRIVER_ID, vehicle_id=second.id, driver_operational_status="OFFLINE"
    )

    vehicles = {v.id: v for v in service.list_vehicles(driver_id=DRIVER_ID)}
    assert vehicles[first.id].operational_status.value == "INACTIVE"
    assert vehicles[second.id].operational_status.value == "ACTIVE"
    active_count = sum(
        1 for v in vehicles.values() if v.operational_status.value == "ACTIVE"
    )
    assert active_count == 1


@pytest.mark.parametrize("status", ["ONLINE", "ON_RIDE"])
def test_activate_rejected_while_driver_not_offline(
    service: VehicleService, repo: FakeVehicleRepository, status: str
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    vehicle.verification_status = VehicleVerificationStatus.APPROVED
    repo.save(vehicle)

    with pytest.raises(DriverNotOfflineError):
        service.activate_vehicle(
            driver_id=DRIVER_ID,
            vehicle_id=vehicle.id,
            driver_operational_status=status,
        )


@pytest.mark.parametrize("status", ["ONLINE", "ON_RIDE"])
def test_deactivate_rejected_while_driver_not_offline(
    service: VehicleService, repo: FakeVehicleRepository, status: str
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    with pytest.raises(DriverNotOfflineError):
        service.deactivate_vehicle(
            driver_id=DRIVER_ID,
            vehicle_id=vehicle.id,
            driver_operational_status=status,
        )


def test_deactivate_succeeds_while_offline(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    vehicle.verification_status = VehicleVerificationStatus.APPROVED
    repo.save(vehicle)
    service.activate_vehicle(
        driver_id=DRIVER_ID,
        vehicle_id=vehicle.id,
        driver_operational_status="OFFLINE",
    )

    deactivated = service.deactivate_vehicle(
        driver_id=DRIVER_ID,
        vehicle_id=vehicle.id,
        driver_operational_status="OFFLINE",
    )

    assert deactivated.operational_status.value == "INACTIVE"


def test_another_driver_cannot_activate_someone_elses_vehicle(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    with pytest.raises(VehicleNotFoundError):
        service.activate_vehicle(
            driver_id=OTHER_DRIVER_ID,
            vehicle_id=vehicle.id,
            driver_operational_status="OFFLINE",
        )


def test_get_vehicle_returns_owned_vehicle(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    fetched = service.get_vehicle(driver_id=DRIVER_ID, vehicle_id=vehicle.id)

    assert fetched.id == vehicle.id


def test_get_vehicle_denies_another_drivers_vehicle(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    with pytest.raises(VehicleNotFoundError):
        service.get_vehicle(driver_id=OTHER_DRIVER_ID, vehicle_id=vehicle.id)


def test_update_vehicle_changes_only_make_and_model(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make="Old Make",
        model="Old Model",
    )

    updated = service.update_vehicle(
        driver_id=DRIVER_ID, vehicle_id=vehicle.id, update={"make": "New Make"}
    )

    assert updated.make == "New Make"
    assert updated.model == "Old Model"  # untouched
    assert updated.category.value == "CAB"  # untouched — not editable
    assert updated.registration_number == "BR01AB1234"  # untouched — not editable


def test_nonexistent_vehicle_raises_not_found(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    with pytest.raises(VehicleNotFoundError):
        service.activate_vehicle(
            driver_id=DRIVER_ID,
            vehicle_id=uuid.uuid4(),
            driver_operational_status="OFFLINE",
        )


def test_approve_vehicle_transitions_pending_to_approved(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    approved = service.approve_vehicle(
        vehicle_id=vehicle.id, documents=_valid_required_documents()
    )

    assert approved.verification_status.value == "APPROVED"
    assert approved.operational_status.value == "INACTIVE"  # untouched — ADR-0009


def test_approve_vehicle_rejects_already_decided(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    service.approve_vehicle(
        vehicle_id=vehicle.id, documents=_valid_required_documents()
    )

    with pytest.raises(VehicleVerificationAlreadyDecidedError):
        service.approve_vehicle(
            vehicle_id=vehicle.id, documents=_valid_required_documents()
        )


def test_approve_vehicle_raises_for_missing_vehicle(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    with pytest.raises(VehicleNotFoundError):
        service.approve_vehicle(vehicle_id=uuid.uuid4(), documents=[])


def test_approve_vehicle_blocked_when_required_document_missing(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    with pytest.raises(VehicleRequiredDocumentsNotValidError):
        service.approve_vehicle(vehicle_id=vehicle.id, documents=[])


def test_approve_vehicle_blocked_when_required_document_pending(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    pending_insurance = VehicleDocument.new(
        vehicle_id=vehicle.id,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
        now=datetime.now(UTC),
    )  # stays PENDING — never approved

    with pytest.raises(VehicleRequiredDocumentsNotValidError):
        service.approve_vehicle(
            vehicle_id=vehicle.id,
            documents=[_valid_document("RC"), pending_insurance],
        )


def test_approve_vehicle_blocked_when_required_document_rejected(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    rejected_insurance = VehicleDocument.new(
        vehicle_id=vehicle.id,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
        now=datetime.now(UTC),
    )
    rejected_insurance.verification_status = DocumentVerificationStatus.REJECTED

    with pytest.raises(VehicleRequiredDocumentsNotValidError):
        service.approve_vehicle(
            vehicle_id=vehicle.id,
            documents=[_valid_document("RC"), rejected_insurance],
        )


def test_approve_vehicle_blocked_when_required_document_expired(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    expired_insurance = _valid_document(
        "INSURANCE", expires_at=datetime.now(UTC) - timedelta(days=1)
    )

    with pytest.raises(VehicleRequiredDocumentsNotValidError):
        service.approve_vehicle(
            vehicle_id=vehicle.id,
            documents=[_valid_document("RC"), expired_insurance],
        )


def test_approve_vehicle_succeeds_with_unexpired_valid_documents(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    future_insurance = _valid_document(
        "INSURANCE", expires_at=datetime.now(UTC) + timedelta(days=365)
    )

    approved = service.approve_vehicle(
        vehicle_id=vehicle.id,
        documents=[_valid_document("RC"), future_insurance],
    )

    assert approved.verification_status.value == "APPROVED"


def test_approve_vehicle_ignores_vehicle_photo(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    """VEHICLE_PHOTO is deliberately excluded from the required set
    (ADR-0009 point C) — its presence/absence must not affect approval."""
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    approved = service.approve_vehicle(
        vehicle_id=vehicle.id, documents=_valid_required_documents()
    )  # no VEHICLE_PHOTO document at all

    assert approved.verification_status.value == "APPROVED"


def test_reject_vehicle_transitions_pending_to_rejected(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )

    rejected = service.reject_vehicle(
        vehicle_id=vehicle.id, reason="RC does not match registration_number"
    )

    assert rejected.verification_status.value == "REJECTED"
    assert rejected.operational_status.value == "INACTIVE"


def test_reject_vehicle_rejects_already_decided(
    service: VehicleService, repo: FakeVehicleRepository
) -> None:
    vehicle = service.add_vehicle(
        driver_id=DRIVER_ID,
        category="CAB",
        cab_tier="ECO",
        registration_number="BR01AB1234",
        make=None,
        model=None,
    )
    service.reject_vehicle(vehicle_id=vehicle.id, reason=None)

    with pytest.raises(VehicleVerificationAlreadyDecidedError):
        service.reject_vehicle(vehicle_id=vehicle.id, reason=None)
