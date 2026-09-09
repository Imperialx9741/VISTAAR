"""Unit tests for the pure DriverDocument domain layer (no DB/HTTP)."""

import uuid
from datetime import UTC, datetime

import pytest

from modules.driver.domain.entities import (
    DriverDocument,
    validate_document_number,
    validate_document_type,
    validate_evidence_uri,
)
from modules.driver.domain.errors import (
    InvalidDocumentNumberError,
    InvalidDocumentTypeError,
    InvalidEvidenceUriError,
)


class TestDocumentTypeValidation:
    def test_valid_type_is_trimmed_and_uppercased(self) -> None:
        assert validate_document_type("  driving_license  ") == "DRIVING_LICENSE"

    def test_blank_after_strip_is_rejected(self) -> None:
        with pytest.raises(InvalidDocumentTypeError):
            validate_document_type("   ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidDocumentTypeError):
            validate_document_type("x" * 41)

    def test_exactly_max_length_is_allowed(self) -> None:
        assert validate_document_type("x" * 40) == "X" * 40

    def test_no_canonical_vocabulary_is_enforced(self) -> None:
        """See ADR-0007 — any non-blank, shape-valid string is accepted,
        since no source document defines an enum."""
        assert validate_document_type("SOMETHING_NOT_ON_ANY_LIST") == (
            "SOMETHING_NOT_ON_ANY_LIST"
        )


class TestDocumentNumberValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_document_number(None) is None

    def test_blank_becomes_none(self) -> None:
        assert validate_document_number("   ") is None

    def test_valid_number_is_trimmed(self) -> None:
        assert validate_document_number("  XY1234  ") == "XY1234"

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidDocumentNumberError):
            validate_document_number("x" * 101)


class TestEvidenceUriValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_evidence_uri(None) is None

    def test_valid_uri_is_trimmed(self) -> None:
        assert validate_evidence_uri("  ref-1  ") == "ref-1"

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidEvidenceUriError):
            validate_evidence_uri("x" * 2049)


class TestDriverDocumentNew:
    def test_defaults_match_documented_schema(self) -> None:
        document = DriverDocument.new(
            driver_id=uuid.uuid4(),
            document_type="driving_license",
            document_number="XY1234",
            evidence_uri="ref-1",
            expires_at=None,
            now=datetime.now(UTC),
        )

        assert document.document_type == "DRIVING_LICENSE"
        assert document.document_number == "XY1234"
        assert document.evidence_uri == "ref-1"
        assert document.verification_status.value == "PENDING"
        assert document.expires_at is None

    def test_blank_document_type_is_rejected_at_creation(self) -> None:
        with pytest.raises(InvalidDocumentTypeError):
            DriverDocument.new(
                driver_id=uuid.uuid4(),
                document_type="   ",
                document_number=None,
                evidence_uri=None,
                expires_at=None,
                now=datetime.now(UTC),
            )
