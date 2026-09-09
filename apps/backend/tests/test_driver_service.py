"""Unit tests for DriverService against an in-memory fake repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from modules.driver.domain.entities import (
    DocumentVerificationStatus,
    Driver,
    DriverDocument,
    DriverOperationalStatus,
)
from modules.driver.domain.errors import (
    DriverAlreadySuspendedError,
    DriverNotApprovedError,
    DriverNotOfflineError,
    DriverNotOnlineError,
    DriverNotSuspendedError,
    DriverProfileNotFoundError,
    DriverRequiredDocumentsNotValidError,
    DriverVerificationAlreadyDecidedError,
    FullNameRequiredForCreationError,
    NoEligibleVehicleError,
    VehicleDocumentsNotValidForGoOnlineError,
)
from modules.driver.service import DriverService


class FakeDriverRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Driver] = {}

    def get_by_id(self, driver_id: uuid.UUID) -> Driver | None:
        return self.by_id.get(driver_id)

    def get_by_id_for_update(self, driver_id: uuid.UUID) -> Driver | None:
        # No real locking in this in-memory fake — sequential test calls
        # never race, so plain get_by_id's behavior is sufficient here.
        return self.by_id.get(driver_id)

    def create(self, driver: Driver) -> Driver:
        self.by_id[driver.id] = driver
        return driver

    def save(self, driver: Driver) -> None:
        self.by_id[driver.id] = driver

    def search(
        self, *, query: str | None, status: str | None, offset: int, limit: int
    ) -> tuple[list[Driver], int]:
        matches = sorted(
            (
                d
                for d in self.by_id.values()
                if (query is None or query.lower() in d.full_name.lower())
                and (status is None or d.verification_status.value == status)
            ),
            key=lambda d: d.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def count_total(self) -> int:
        return len(self.by_id)

    def count_by_verification_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.by_id.values():
            key = d.verification_status.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def count_by_operational_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.by_id.values():
            key = d.operational_status.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def count_created_in_range(self, *, since: datetime, until: datetime) -> int:
        return sum(1 for d in self.by_id.values() if since <= d.created_at < until)

    def list_all_ids(self) -> list[uuid.UUID]:
        return list(self.by_id.keys())


@pytest.fixture
def repo() -> FakeDriverRepository:
    return FakeDriverRepository()


@pytest.fixture
def service(repo: FakeDriverRepository) -> DriverService:
    return DriverService(drivers=repo)


ACCOUNT_ID = uuid.uuid4()


def _valid_document(
    document_type: str, *, expires_at: datetime | None = None
) -> DriverDocument:
    """A document satisfying BR-123's required-document gate: APPROVED
    and (no expiry, or expiry in the future)."""
    doc = DriverDocument.new(
        driver_id=ACCOUNT_ID,
        document_type=document_type,
        document_number=None,
        evidence_uri="ref-1",
        expires_at=expires_at,
        now=datetime.now(UTC),
    )
    doc.verification_status = DocumentVerificationStatus.APPROVED
    return doc


def _valid_required_documents() -> list[DriverDocument]:
    return [_valid_document("GOVERNMENT_ID"), _valid_document("DRIVING_LICENSE")]


def test_get_profile_does_not_auto_provision(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    with pytest.raises(DriverProfileNotFoundError):
        service.get_profile(account_id=ACCOUNT_ID)
    assert ACCOUNT_ID not in repo.by_id


def test_update_profile_requires_full_name_to_create(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    with pytest.raises(FullNameRequiredForCreationError):
        service.update_profile(account_id=ACCOUNT_ID, update={})
    assert ACCOUNT_ID not in repo.by_id


def test_update_profile_creates_with_full_name(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    driver = service.update_profile(
        account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"}
    )

    assert driver.full_name == "Ravi Kumar"
    assert driver.verification_status.value == "PENDING"
    assert driver.operational_status.value == "OFFLINE"
    assert driver.strikes == 0
    assert ACCOUNT_ID in repo.by_id


def test_get_profile_succeeds_after_creation(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    fetched = service.get_profile(account_id=ACCOUNT_ID)

    assert fetched.full_name == "Ravi Kumar"


def test_update_profile_only_changes_supplied_fields(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(
        account_id=ACCOUNT_ID,
        update={"full_name": "Ravi Kumar", "profile_photo_uri": "ref-1"},
    )

    updated = service.update_profile(
        account_id=ACCOUNT_ID, update={"full_name": "Ravi K."}
    )

    assert updated.full_name == "Ravi K."
    assert updated.profile_photo_uri == "ref-1"  # untouched


def test_server_controlled_fields_are_not_client_writable(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    """DriverService.update_profile()/ProfileUpdate has no keys for
    verification_status/operational_status/strikes at all — there is no
    way to pass them in, by construction (not merely by validation)."""
    driver = service.update_profile(
        account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"}
    )
    assert driver.verification_status.value == "PENDING"
    assert driver.operational_status.value == "OFFLINE"
    assert driver.strikes == 0

    # Even a second update call cannot move these away from their
    # documented defaults through this service.
    driver = service.update_profile(
        account_id=ACCOUNT_ID, update={"profile_photo_uri": "ref-2"}
    )
    assert driver.verification_status.value == "PENDING"
    assert driver.operational_status.value == "OFFLINE"
    assert driver.strikes == 0


def test_approve_driver_transitions_pending_to_approved(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    approved = service.approve_driver(
        driver_id=ACCOUNT_ID, documents=_valid_required_documents()
    )

    assert approved.verification_status.value == "APPROVED"
    assert approved.operational_status.value == "OFFLINE"  # untouched — ADR-0009


def test_approve_driver_rejects_already_decided(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    service.approve_driver(driver_id=ACCOUNT_ID, documents=_valid_required_documents())

    with pytest.raises(DriverVerificationAlreadyDecidedError):
        service.approve_driver(
            driver_id=ACCOUNT_ID, documents=_valid_required_documents()
        )


def test_approve_driver_raises_for_missing_profile(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    with pytest.raises(DriverProfileNotFoundError):
        service.approve_driver(driver_id=uuid.uuid4(), documents=[])


def test_approve_driver_blocked_when_required_document_missing(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    with pytest.raises(DriverRequiredDocumentsNotValidError):
        service.approve_driver(driver_id=ACCOUNT_ID, documents=[])


def test_approve_driver_blocked_when_required_document_pending(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    pending_license = DriverDocument.new(
        driver_id=ACCOUNT_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
        now=datetime.now(UTC),
    )  # stays PENDING — never approved

    with pytest.raises(DriverRequiredDocumentsNotValidError):
        service.approve_driver(
            driver_id=ACCOUNT_ID,
            documents=[_valid_document("GOVERNMENT_ID"), pending_license],
        )


def test_approve_driver_blocked_when_required_document_rejected(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    rejected_license = DriverDocument.new(
        driver_id=ACCOUNT_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
        now=datetime.now(UTC),
    )
    rejected_license.verification_status = DocumentVerificationStatus.REJECTED

    with pytest.raises(DriverRequiredDocumentsNotValidError):
        service.approve_driver(
            driver_id=ACCOUNT_ID,
            documents=[_valid_document("GOVERNMENT_ID"), rejected_license],
        )


def test_approve_driver_blocked_when_required_document_expired(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    expired_license = _valid_document(
        "DRIVING_LICENSE", expires_at=datetime.now(UTC) - timedelta(days=1)
    )

    with pytest.raises(DriverRequiredDocumentsNotValidError):
        service.approve_driver(
            driver_id=ACCOUNT_ID,
            documents=[_valid_document("GOVERNMENT_ID"), expired_license],
        )


def test_approve_driver_succeeds_with_unexpired_valid_documents(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    future_license = _valid_document(
        "DRIVING_LICENSE", expires_at=datetime.now(UTC) + timedelta(days=365)
    )

    approved = service.approve_driver(
        driver_id=ACCOUNT_ID,
        documents=[_valid_document("GOVERNMENT_ID"), future_license],
    )

    assert approved.verification_status.value == "APPROVED"


def test_reject_driver_transitions_pending_to_rejected(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    rejected = service.reject_driver(driver_id=ACCOUNT_ID, reason="Document illegible")

    assert rejected.verification_status.value == "REJECTED"
    assert rejected.operational_status.value == "OFFLINE"


def test_reject_driver_accepts_no_reason(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    rejected = service.reject_driver(driver_id=ACCOUNT_ID, reason=None)

    assert rejected.verification_status.value == "REJECTED"


def test_reject_driver_rejects_already_decided(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    service.reject_driver(driver_id=ACCOUNT_ID, reason=None)

    with pytest.raises(DriverVerificationAlreadyDecidedError):
        service.reject_driver(driver_id=ACCOUNT_ID, reason=None)


# --- go_online / go_offline (Phase 2 / Task 2.7B) ----------------------


def _approved_driver(service: DriverService) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    service.approve_driver(driver_id=ACCOUNT_ID, documents=_valid_required_documents())


def _go_online(
    service: DriverService,
    *,
    invalid_required_driver_documents: bool = False,
    vehicle_verification_status: str | None = "APPROVED",
    vehicle_operational_status: str | None = "ACTIVE",
    invalid_required_vehicle_documents: bool = False,
) -> Driver:
    return service.go_online(
        account_id=ACCOUNT_ID,
        invalid_required_driver_documents=invalid_required_driver_documents,
        vehicle_verification_status=vehicle_verification_status,
        vehicle_operational_status=vehicle_operational_status,
        invalid_required_vehicle_documents=invalid_required_vehicle_documents,
    )


def test_go_online_raises_for_missing_profile(service: DriverService) -> None:
    with pytest.raises(DriverProfileNotFoundError):
        _go_online(service)


def test_go_online_succeeds_when_fully_eligible(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    _approved_driver(service)

    driver = _go_online(service)

    assert driver.operational_status is DriverOperationalStatus.ONLINE
    assert repo.by_id[ACCOUNT_ID].operational_status is DriverOperationalStatus.ONLINE


def test_go_online_rejects_when_not_offline(service: DriverService) -> None:
    _approved_driver(service)
    _go_online(service)

    with pytest.raises(DriverNotOfflineError):
        _go_online(service)


def test_go_online_rejects_unapproved_driver(service: DriverService) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    with pytest.raises(DriverNotApprovedError):
        _go_online(service)


def test_go_online_rejects_invalid_required_driver_documents(
    service: DriverService,
) -> None:
    _approved_driver(service)

    with pytest.raises(DriverRequiredDocumentsNotValidError):
        _go_online(service, invalid_required_driver_documents=True)


def test_go_online_rejects_no_active_vehicle(service: DriverService) -> None:
    _approved_driver(service)

    with pytest.raises(NoEligibleVehicleError):
        _go_online(
            service,
            vehicle_verification_status=None,
            vehicle_operational_status=None,
        )


def test_go_online_rejects_active_but_unapproved_vehicle(
    service: DriverService,
) -> None:
    _approved_driver(service)

    with pytest.raises(NoEligibleVehicleError):
        _go_online(
            service,
            vehicle_verification_status="PENDING",
            vehicle_operational_status="ACTIVE",
        )


def test_go_online_rejects_approved_but_inactive_vehicle(
    service: DriverService,
) -> None:
    _approved_driver(service)

    with pytest.raises(NoEligibleVehicleError):
        _go_online(
            service,
            vehicle_verification_status="APPROVED",
            vehicle_operational_status="INACTIVE",
        )


def test_go_online_rejects_invalid_required_vehicle_documents(
    service: DriverService,
) -> None:
    _approved_driver(service)

    with pytest.raises(VehicleDocumentsNotValidForGoOnlineError):
        _go_online(service, invalid_required_vehicle_documents=True)


def test_go_offline_raises_for_missing_profile(service: DriverService) -> None:
    with pytest.raises(DriverProfileNotFoundError):
        service.go_offline(account_id=ACCOUNT_ID)


def test_go_offline_succeeds_when_online(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    _approved_driver(service)
    _go_online(service)

    driver = service.go_offline(account_id=ACCOUNT_ID)

    assert driver.operational_status is DriverOperationalStatus.OFFLINE
    assert repo.by_id[ACCOUNT_ID].operational_status is DriverOperationalStatus.OFFLINE


def test_go_offline_rejects_when_already_offline(service: DriverService) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    with pytest.raises(DriverNotOnlineError):
        service.go_offline(account_id=ACCOUNT_ID)


def test_go_offline_rejects_when_on_ride(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    """ON_RIDE -> OFFLINE is rejected the same way as OFFLINE -> OFFLINE
    (DriverNotOnlineError) — see that error's docstring for why this is a
    documented Phase 3 dependency, not a bug."""
    _approved_driver(service)
    _go_online(service)
    repo.by_id[ACCOUNT_ID].operational_status = DriverOperationalStatus.ON_RIDE

    with pytest.raises(DriverNotOnlineError):
        service.go_offline(account_id=ACCOUNT_ID)


# --- suspend_driver / reactivate_driver (Phase 03, ADR-0021) ----------------


def test_suspend_driver_raises_for_missing_profile(service: DriverService) -> None:
    with pytest.raises(DriverProfileNotFoundError):
        service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)


def test_suspend_driver_succeeds_from_offline(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    driver = service.suspend_driver(driver_id=ACCOUNT_ID, reason="Safety complaint")

    assert driver.operational_status is DriverOperationalStatus.SUSPENDED
    assert (
        repo.by_id[ACCOUNT_ID].operational_status is DriverOperationalStatus.SUSPENDED
    )


def test_suspend_driver_succeeds_from_online(service: DriverService) -> None:
    """ADR-0021 Decision 4: reachable from any status, not just OFFLINE."""
    _approved_driver(service)
    _go_online(service)

    driver = service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)

    assert driver.operational_status is DriverOperationalStatus.SUSPENDED


def test_suspend_driver_succeeds_from_on_ride_and_does_not_touch_the_ride(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    """ADR-0021 Decision 4: no ride/matching side effect — this service
    has no access to ride.rides at all, so there is nothing to touch;
    this test documents the intent, not a real ride record."""
    _approved_driver(service)
    _go_online(service)
    repo.by_id[ACCOUNT_ID].operational_status = DriverOperationalStatus.ON_RIDE

    driver = service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)

    assert driver.operational_status is DriverOperationalStatus.SUSPENDED


def test_suspend_driver_rejects_already_suspended(service: DriverService) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)

    with pytest.raises(DriverAlreadySuspendedError):
        service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)


def test_reactivate_driver_raises_for_missing_profile(service: DriverService) -> None:
    with pytest.raises(DriverProfileNotFoundError):
        service.reactivate_driver(driver_id=ACCOUNT_ID)


def test_reactivate_driver_lands_on_offline_not_online(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    """ADR-0021 Decision 4: mirrors ADR-0009 — reactivation never
    auto-restores ONLINE; the driver must Go Online themselves."""
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})
    service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)

    driver = service.reactivate_driver(driver_id=ACCOUNT_ID)

    assert driver.operational_status is DriverOperationalStatus.OFFLINE
    assert repo.by_id[ACCOUNT_ID].operational_status is DriverOperationalStatus.OFFLINE


def test_reactivate_driver_rejects_when_not_suspended(service: DriverService) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Ravi Kumar"})

    with pytest.raises(DriverNotSuspendedError):
        service.reactivate_driver(driver_id=ACCOUNT_ID)


def test_reactivated_driver_can_go_online_again(service: DriverService) -> None:
    _approved_driver(service)
    service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)
    service.reactivate_driver(driver_id=ACCOUNT_ID)

    driver = _go_online(service)

    assert driver.operational_status is DriverOperationalStatus.ONLINE


def test_go_online_rejects_a_suspended_driver(
    service: DriverService, repo: FakeDriverRepository
) -> None:
    """ADR-0021 Decision 5: go_online()'s existing generic "must be
    OFFLINE" guard already covers SUSPENDED — no new branch needed."""
    _approved_driver(service)
    service.suspend_driver(driver_id=ACCOUNT_ID, reason=None)

    with pytest.raises(DriverNotOfflineError):
        _go_online(service)
