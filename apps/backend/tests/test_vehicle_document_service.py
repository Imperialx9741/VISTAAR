"""Unit tests for VehicleDocumentService against an in-memory fake
repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from modules.vehicle.domain.entities import VehicleDocument
from modules.vehicle.domain.errors import (
    VehicleDocumentAlreadyDecidedError,
    VehicleDocumentNotFoundError,
)
from modules.vehicle.service import VehicleDocumentService
from modules.verification.domain.entities import VerificationOutcome


class FakeVehicleDocumentRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, VehicleDocument] = {}

    def create(self, document: VehicleDocument) -> VehicleDocument:
        self.by_id[document.id] = document
        return document

    def get_by_id(self, document_id: uuid.UUID) -> VehicleDocument | None:
        return self.by_id.get(document_id)

    def list_by_vehicle(self, vehicle_id: uuid.UUID) -> list[VehicleDocument]:
        return [d for d in self.by_id.values() if d.vehicle_id == vehicle_id]

    def save(self, document: VehicleDocument) -> None:
        self.by_id[document.id] = document


@pytest.fixture
def repo() -> FakeVehicleDocumentRepository:
    return FakeVehicleDocumentRepository()


@pytest.fixture
def service(repo: FakeVehicleDocumentRepository) -> VehicleDocumentService:
    return VehicleDocumentService(documents=repo)


VEHICLE_ID = uuid.uuid4()
OTHER_VEHICLE_ID = uuid.uuid4()


def test_submit_document_creates_pending_record(
    service: VehicleDocumentService,
) -> None:
    document = service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="insurance",
        document_number="POL-1",
        evidence_uri="ref-1",
        expires_at=None,
    )

    assert document.vehicle_id == VEHICLE_ID
    assert document.document_type == "INSURANCE"
    assert document.verification_status.value == "PENDING"


def test_list_documents_returns_only_this_vehicles_documents(
    service: VehicleDocumentService,
) -> None:
    service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )
    service.submit_document(
        vehicle_id=OTHER_VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    result = service.list_documents(vehicle_id=VEHICLE_ID)

    assert len(result) == 1
    assert result[0].vehicle_id == VEHICLE_ID


def test_get_document_returns_owned_document(
    service: VehicleDocumentService,
) -> None:
    document = service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    fetched = service.get_document(vehicle_id=VEHICLE_ID, document_id=document.id)

    assert fetched.id == document.id


def test_get_document_denies_another_vehicles_document(
    service: VehicleDocumentService,
) -> None:
    document = service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    with pytest.raises(VehicleDocumentNotFoundError):
        service.get_document(vehicle_id=OTHER_VEHICLE_ID, document_id=document.id)


def test_get_nonexistent_document_raises_not_found(
    service: VehicleDocumentService,
) -> None:
    with pytest.raises(VehicleDocumentNotFoundError):
        service.get_document(vehicle_id=VEHICLE_ID, document_id=uuid.uuid4())


def test_apply_verification_outcome_approved(service: VehicleDocumentService) -> None:
    document = service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
    )

    updated = service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.APPROVED
    )

    assert updated.verification_status.value == "APPROVED"


def test_apply_verification_outcome_rejected(service: VehicleDocumentService) -> None:
    document = service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
    )

    updated = service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.REJECTED
    )

    assert updated.verification_status.value == "REJECTED"


def test_apply_verification_outcome_twice_raises(
    service: VehicleDocumentService,
) -> None:
    document = service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
    )
    service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.APPROVED
    )

    with pytest.raises(VehicleDocumentAlreadyDecidedError):
        service.apply_verification_outcome(
            document_id=document.id, outcome=VerificationOutcome.APPROVED
        )


def test_apply_verification_outcome_leaves_expires_at_untouched(
    service: VehicleDocumentService,
) -> None:
    expiry = datetime(2028, 1, 1, tzinfo=UTC)
    document = service.submit_document(
        vehicle_id=VEHICLE_ID,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=expiry,
    )

    updated = service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.APPROVED
    )

    assert updated.expires_at == expiry


def test_apply_verification_outcome_raises_for_missing_document(
    service: VehicleDocumentService,
) -> None:
    with pytest.raises(VehicleDocumentNotFoundError):
        service.apply_verification_outcome(
            document_id=uuid.uuid4(), outcome=VerificationOutcome.APPROVED
        )
