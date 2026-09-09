"""Unit tests for DriverDocumentService against an in-memory fake
repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from modules.driver.domain.entities import DriverDocument
from modules.driver.domain.errors import (
    DriverDocumentAlreadyDecidedError,
    DriverDocumentNotFoundError,
)
from modules.driver.service import DriverDocumentService
from modules.verification.domain.entities import VerificationOutcome


class FakeDriverDocumentRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, DriverDocument] = {}

    def create(self, document: DriverDocument) -> DriverDocument:
        self.by_id[document.id] = document
        return document

    def get_by_id(self, document_id: uuid.UUID) -> DriverDocument | None:
        return self.by_id.get(document_id)

    def list_by_driver(self, driver_id: uuid.UUID) -> list[DriverDocument]:
        return [d for d in self.by_id.values() if d.driver_id == driver_id]

    def save(self, document: DriverDocument) -> None:
        self.by_id[document.id] = document


@pytest.fixture
def repo() -> FakeDriverDocumentRepository:
    return FakeDriverDocumentRepository()


@pytest.fixture
def service(repo: FakeDriverDocumentRepository) -> DriverDocumentService:
    return DriverDocumentService(documents=repo)


DRIVER_ID = uuid.uuid4()
OTHER_DRIVER_ID = uuid.uuid4()


def test_submit_document_creates_pending_record(
    service: DriverDocumentService,
) -> None:
    document = service.submit_document(
        driver_id=DRIVER_ID,
        document_type="driving_license",
        document_number="XY1234",
        evidence_uri="ref-1",
        expires_at=None,
    )

    assert document.driver_id == DRIVER_ID
    assert document.document_type == "DRIVING_LICENSE"
    assert document.verification_status.value == "PENDING"


def test_multiple_documents_per_driver_are_supported(
    service: DriverDocumentService,
) -> None:
    """No versioning/replacement rule exists — see ADR-0007. Resubmitting
    the same document_type creates a second, independent row."""
    service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number="OLD",
        evidence_uri=None,
        expires_at=None,
    )
    service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number="NEW",
        evidence_uri=None,
        expires_at=None,
    )

    documents = service.list_documents(driver_id=DRIVER_ID)
    assert len(documents) == 2


def test_list_documents_returns_only_this_drivers_documents(
    service: DriverDocumentService,
) -> None:
    service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )
    service.submit_document(
        driver_id=OTHER_DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    result = service.list_documents(driver_id=DRIVER_ID)

    assert len(result) == 1
    assert result[0].driver_id == DRIVER_ID


def test_get_document_returns_owned_document(
    service: DriverDocumentService,
) -> None:
    document = service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    fetched = service.get_document(driver_id=DRIVER_ID, document_id=document.id)

    assert fetched.id == document.id


def test_get_document_denies_another_drivers_document(
    service: DriverDocumentService,
) -> None:
    document = service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    with pytest.raises(DriverDocumentNotFoundError):
        service.get_document(driver_id=OTHER_DRIVER_ID, document_id=document.id)


def test_get_nonexistent_document_raises_not_found(
    service: DriverDocumentService,
) -> None:
    with pytest.raises(DriverDocumentNotFoundError):
        service.get_document(driver_id=DRIVER_ID, document_id=uuid.uuid4())


def test_apply_verification_outcome_approved(service: DriverDocumentService) -> None:
    document = service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
    )

    updated = service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.APPROVED
    )

    assert updated.verification_status.value == "APPROVED"


def test_apply_verification_outcome_rejected(service: DriverDocumentService) -> None:
    document = service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
    )

    updated = service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.REJECTED
    )

    assert updated.verification_status.value == "REJECTED"


def test_apply_verification_outcome_twice_raises(
    service: DriverDocumentService,
) -> None:
    document = service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=None,
    )
    service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.APPROVED
    )

    with pytest.raises(DriverDocumentAlreadyDecidedError):
        service.apply_verification_outcome(
            document_id=document.id, outcome=VerificationOutcome.APPROVED
        )


def test_apply_verification_outcome_leaves_expires_at_untouched(
    service: DriverDocumentService,
) -> None:
    expiry = datetime(2028, 1, 1, tzinfo=UTC)
    document = service.submit_document(
        driver_id=DRIVER_ID,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-1",
        expires_at=expiry,
    )

    updated = service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.APPROVED
    )

    assert updated.expires_at == expiry


def test_apply_verification_outcome_raises_for_missing_document(
    service: DriverDocumentService,
) -> None:
    with pytest.raises(DriverDocumentNotFoundError):
        service.apply_verification_outcome(
            document_id=uuid.uuid4(), outcome=VerificationOutcome.APPROVED
        )
