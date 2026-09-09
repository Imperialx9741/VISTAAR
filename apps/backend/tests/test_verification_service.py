"""Unit tests for VerificationService against an in-memory fake
repository and the real ManualReviewVerificationProvider stub (no
network I/O — it's a pure in-memory default, safe to use directly in
unit tests, same as every other module's fakes)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from modules.verification.domain.entities import (
    Evidence,
    VerificationCase,
    VerificationOutcome,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)
from modules.verification.domain.errors import (
    InvalidManualReviewOutcomeError,
    NoEvidenceForCaseError,
    VerificationCaseNotFoundError,
    VerificationCaseNotInManualReviewError,
)
from modules.verification.providers import ManualReviewVerificationProvider
from modules.verification.service import VerificationService


class FakeVerificationCaseRepository:
    def __init__(self) -> None:
        self.cases: dict[uuid.UUID, VerificationCase] = {}
        self.evidence: dict[uuid.UUID, list[Evidence]] = {}
        self.results: dict[uuid.UUID, list[VerificationResult]] = {}

    def create_case(self, case: VerificationCase) -> VerificationCase:
        self.cases[case.id] = case
        self.evidence[case.id] = []
        self.results[case.id] = []
        return case

    def get_case(self, case_id: uuid.UUID) -> VerificationCase | None:
        return self.cases.get(case_id)

    def list_cases_for_subject(
        self, *, subject_type: str, subject_id: uuid.UUID
    ) -> list[VerificationCase]:
        return [
            c
            for c in self.cases.values()
            if c.subject_type == subject_type and c.subject_id == subject_id
        ]

    def save_case(self, case: VerificationCase) -> None:
        self.cases[case.id] = case

    def add_evidence(self, evidence: Evidence) -> Evidence:
        self.evidence.setdefault(evidence.case_id, []).append(evidence)
        return evidence

    def list_evidence_for_case(self, case_id: uuid.UUID) -> list[Evidence]:
        return self.evidence.get(case_id, [])

    def add_result(self, result: VerificationResult) -> VerificationResult:
        self.results.setdefault(result.case_id, []).append(result)
        return result

    def list_by_status(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[VerificationCase], int]:
        matches = sorted(
            (
                c
                for c in self.cases.values()
                if status is None or c.status.value == status
            ),
            key=lambda c: c.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)


@pytest.fixture
def repo() -> FakeVerificationCaseRepository:
    return FakeVerificationCaseRepository()


@pytest.fixture
def service(repo: FakeVerificationCaseRepository) -> VerificationService:
    return VerificationService(cases=repo, provider=ManualReviewVerificationProvider())


DRIVER_DOC_ID = uuid.uuid4()
VEHICLE_DOC_ID = uuid.uuid4()


def test_submit_evidence_creates_pending_case(
    service: VerificationService, repo: FakeVerificationCaseRepository
) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )

    assert case.status.value == "PENDING"
    assert case.subject_id == DRIVER_DOC_ID
    assert len(repo.evidence[case.id]) == 1
    assert repo.evidence[case.id][0].evidence_uri == "ref-1"


def test_submit_evidence_works_identically_for_vehicle_documents(
    service: VerificationService,
) -> None:
    """ADR-0008 item 3: VerificationService is subject-agnostic."""
    case = service.submit_evidence(
        subject_type="VEHICLE_DOCUMENT",
        subject_id=VEHICLE_DOC_ID,
        verification_type=VerificationType.VEHICLE_DOCUMENT,
        evidence_uri="ref-2",
    )

    assert case.status.value == "PENDING"
    assert case.subject_type == "VEHICLE_DOCUMENT"


@pytest.mark.anyio
async def test_run_verification_transitions_to_manual_review(
    service: VerificationService, repo: FakeVerificationCaseRepository
) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )

    updated = await service.run_verification(case_id=case.id)

    assert updated.status.value == "MANUAL_REVIEW"
    assert updated.completed_at is None  # not terminal — awaiting human review
    assert len(repo.results[case.id]) == 1
    assert repo.results[case.id][0].result.value == "MANUAL_REVIEW"


@pytest.mark.anyio
async def test_run_verification_raises_for_unknown_case(
    service: VerificationService,
) -> None:
    with pytest.raises(VerificationCaseNotFoundError):
        await service.run_verification(case_id=uuid.uuid4())


@pytest.mark.anyio
async def test_run_verification_raises_when_case_has_no_evidence(
    service: VerificationService, repo: FakeVerificationCaseRepository
) -> None:
    # Construct a case directly via the repo, bypassing submit_evidence(),
    # to exercise the defensive no-evidence path.
    case = VerificationCase.new(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        now=datetime.now(UTC),
    )
    repo.create_case(case)

    with pytest.raises(NoEvidenceForCaseError):
        await service.run_verification(case_id=case.id)


def test_get_case_returns_case(service: VerificationService) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )

    fetched = service.get_case(case_id=case.id)

    assert fetched.id == case.id


def test_get_nonexistent_case_raises_not_found(service: VerificationService) -> None:
    with pytest.raises(VerificationCaseNotFoundError):
        service.get_case(case_id=uuid.uuid4())


@pytest.mark.anyio
async def test_complete_manual_review_approved(
    service: VerificationService, repo: FakeVerificationCaseRepository
) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )
    await service.run_verification(case_id=case.id)  # -> MANUAL_REVIEW
    reviewer_id = uuid.uuid4()

    completed = service.complete_manual_review(
        case_id=case.id,
        outcome=VerificationOutcome.APPROVED,
        reviewer_id=reviewer_id,
        reason=None,
    )

    assert completed.status.value == "APPROVED"
    assert completed.completed_at is not None
    results = repo.results[case.id]
    assert results[-1].result.value == "APPROVED"
    assert results[-1].reviewer_id == reviewer_id


def test_complete_manual_review_rejected_with_reason(
    service: VerificationService, repo: FakeVerificationCaseRepository
) -> None:
    case = VerificationCase.new(
        subject_type="VEHICLE_DOCUMENT",
        subject_id=VEHICLE_DOC_ID,
        verification_type=VerificationType.VEHICLE_DOCUMENT,
        now=datetime.now(UTC),
    )
    case.status = VerificationStatus.MANUAL_REVIEW
    repo.create_case(case)

    completed = service.complete_manual_review(
        case_id=case.id,
        outcome=VerificationOutcome.REJECTED,
        reviewer_id=uuid.uuid4(),
        reason="Document illegible",
    )

    assert completed.status.value == "REJECTED"
    assert repo.results[case.id][-1].reason == "Document illegible"


def test_complete_manual_review_raises_when_not_in_manual_review(
    service: VerificationService,
) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )  # still PENDING — never run through run_verification()

    with pytest.raises(VerificationCaseNotInManualReviewError):
        service.complete_manual_review(
            case_id=case.id,
            outcome=VerificationOutcome.APPROVED,
            reviewer_id=uuid.uuid4(),
            reason=None,
        )


@pytest.mark.anyio
async def test_complete_manual_review_twice_raises(
    service: VerificationService,
) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )
    await service.run_verification(case_id=case.id)
    service.complete_manual_review(
        case_id=case.id,
        outcome=VerificationOutcome.APPROVED,
        reviewer_id=uuid.uuid4(),
        reason=None,
    )

    with pytest.raises(VerificationCaseNotInManualReviewError):
        service.complete_manual_review(
            case_id=case.id,
            outcome=VerificationOutcome.APPROVED,
            reviewer_id=uuid.uuid4(),
            reason=None,
        )


@pytest.mark.anyio
async def test_complete_manual_review_rejects_manual_review_as_outcome(
    service: VerificationService,
) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )
    await service.run_verification(case_id=case.id)

    with pytest.raises(InvalidManualReviewOutcomeError):
        service.complete_manual_review(
            case_id=case.id,
            outcome=VerificationOutcome.MANUAL_REVIEW,
            reviewer_id=uuid.uuid4(),
            reason=None,
        )


def test_complete_manual_review_raises_for_unknown_case(
    service: VerificationService,
) -> None:
    with pytest.raises(VerificationCaseNotFoundError):
        service.complete_manual_review(
            case_id=uuid.uuid4(),
            outcome=VerificationOutcome.APPROVED,
            reviewer_id=uuid.uuid4(),
            reason=None,
        )


def test_list_cases_for_subject_scoped_correctly(service: VerificationService) -> None:
    service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=DRIVER_DOC_ID,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )
    service.submit_evidence(
        subject_type="VEHICLE_DOCUMENT",
        subject_id=VEHICLE_DOC_ID,
        verification_type=VerificationType.VEHICLE_DOCUMENT,
        evidence_uri="ref-2",
    )

    driver_cases = service.list_cases_for_subject(
        subject_type="DRIVER_DOCUMENT", subject_id=DRIVER_DOC_ID
    )

    assert len(driver_cases) == 1
    assert driver_cases[0].subject_id == DRIVER_DOC_ID
