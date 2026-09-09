"""Unit tests for the pure VehicleDocument domain layer (no DB/HTTP)."""

import uuid
from datetime import UTC, datetime

import pytest

from modules.vehicle.domain.entities import (
    VehicleDocument,
    validate_document_number,
    validate_document_type,
    validate_evidence_uri,
)
from modules.vehicle.domain.errors import (
    InvalidDocumentNumberError,
    InvalidDocumentTypeError,
    InvalidEvidenceUriError,
)


class TestDocumentTypeValidation:
    def test_valid_type_is_trimmed_and_uppercased(self) -> None:
        assert validate_document_type("  insurance  ") == "INSURANCE"

    def test_blank_after_strip_is_rejected(self) -> None:
        with pytest.raises(InvalidDocumentTypeError):
            validate_document_type("   ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidDocumentTypeError):
            validate_document_type("x" * 41)

    def test_no_canonical_vocabulary_is_enforced(self) -> None:
        """See ADR-0007 — any non-blank, shape-valid string is accepted,
        since no source document defines an enum."""
        assert validate_document_type("SOMETHING_NOT_ON_ANY_LIST") == (
            "SOMETHING_NOT_ON_ANY_LIST"
        )


class TestDocumentNumberValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_document_number(None) is None

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidDocumentNumberError):
            validate_document_number("x" * 101)


class TestEvidenceUriValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_evidence_uri(None) is None

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidEvidenceUriError):
            validate_evidence_uri("x" * 2049)


class TestVehicleDocumentNew:
    def test_defaults_match_documented_schema(self) -> None:
        document = VehicleDocument.new(
            vehicle_id=uuid.uuid4(),
            document_type="insurance",
            document_number="POL-1",
            evidence_uri="ref-1",
            expires_at=None,
            now=datetime.now(UTC),
        )

        assert document.document_type == "INSURANCE"
        assert document.verification_status.value == "PENDING"
        assert not hasattr(
            document, "updated_at"
        )  # no updated_at, unlike DriverDocument

    def test_blank_document_type_is_rejected_at_creation(self) -> None:
        with pytest.raises(InvalidDocumentTypeError):
            VehicleDocument.new(
                vehicle_id=uuid.uuid4(),
                document_type="   ",
                document_number=None,
                evidence_uri=None,
                expires_at=None,
                now=datetime.now(UTC),
            )
