"""Unit tests for the pure Verification domain layer (no DB/HTTP)."""

import uuid
from datetime import UTC, datetime

from modules.verification.domain.entities import (
    Evidence,
    VerificationCase,
    VerificationOutcome,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)


class TestVerificationCaseNew:
    def test_defaults_to_pending(self) -> None:
        case = VerificationCase.new(
            subject_type="DRIVER_DOCUMENT",
            subject_id=uuid.uuid4(),
            verification_type=VerificationType.DRIVER_DOCUMENT,
            now=datetime.now(UTC),
        )

        assert case.status is VerificationStatus.PENDING
        assert case.completed_at is None

    def test_subject_type_and_verification_type_can_carry_the_same_value(self) -> None:
        """event-contracts.md §18's documented payload examples use the
        same value space for both fields (e.g. subject_type:
        "VEHICLE_DOCUMENT") — implemented faithfully, not deduplicated."""
        case = VerificationCase.new(
            subject_type="VEHICLE_DOCUMENT",
            subject_id=uuid.uuid4(),
            verification_type=VerificationType.VEHICLE_DOCUMENT,
            now=datetime.now(UTC),
        )

        assert case.subject_type == "VEHICLE_DOCUMENT"
        assert case.verification_type is VerificationType.VEHICLE_DOCUMENT


class TestEvidenceNew:
    def test_carries_uri_and_metadata(self) -> None:
        case_id = uuid.uuid4()
        evidence = Evidence.new(
            case_id=case_id,
            evidence_uri="ref-1",
            metadata={"quality": "ok"},
            now=datetime.now(UTC),
        )

        assert evidence.case_id == case_id
        assert evidence.evidence_uri == "ref-1"
        assert evidence.metadata == {"quality": "ok"}

    def test_metadata_may_be_none(self) -> None:
        evidence = Evidence.new(
            case_id=uuid.uuid4(),
            evidence_uri="ref-1",
            metadata=None,
            now=datetime.now(UTC),
        )

        assert evidence.metadata is None


class TestVerificationResultNew:
    def test_carries_outcome_and_optional_fields(self) -> None:
        case_id = uuid.uuid4()
        result = VerificationResult.new(
            case_id=case_id,
            result=VerificationOutcome.MANUAL_REVIEW,
            confidence=None,
            model_name="ManualReviewVerificationProvider",
            reviewer_id=None,
            reason=None,
            now=datetime.now(UTC),
        )

        assert result.case_id == case_id
        assert result.result is VerificationOutcome.MANUAL_REVIEW
        assert result.confidence is None
        assert result.reviewer_id is None
