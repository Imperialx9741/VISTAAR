"""Application service (use cases) for Verification.

SubmitEvidence, RunAIVerification, and (Phase 2 / Task 2.6B)
CompleteManualReview are the three documented commands
(domain-design.md §18.3) this module implements. ApproveEvidence/
RejectEvidence/RequestManualReview are not implemented — Approve/
RejectEvidence duplicate what CompleteManualReview already does in one
step (record a final result + transition the case), and
RequestManualReview is implicit in run_verification()'s existing
MANUAL_REVIEW outcome (ADR-0008 item 2 — no separate admin action
requests it, the provider's own low-confidence-equivalent result does).

submit_evidence() is only ever called when evidence_uri is present at the
call site (ADR-0008 item 9) — this service itself does not decide that;
see modules/driver/router.py and the vehicle-side integration test for
where that decision is made. run_verification() is not invoked
automatically by submit_evidence() or by anything else — it exists,
fully tested, ready for whenever a trigger is approved.

complete_manual_review() (Task 2.6B) is deliberately subject-agnostic —
it knows nothing about driver.documents/vehicle.documents, only
verification.cases/results. Writing its outcome back onto the
corresponding document's verification_status is NOT done here — that
would require importing modules.driver/modules.vehicle, breaking this
module's subject-agnosticism. Instead, callers that already have both
services (currently only tests — no HTTP endpoint calls
complete_manual_review() at all, since none is documented; see
modules/driver/service.py::DriverDocumentService.apply_verification_outcome()
/ modules/vehicle/service.py::VehicleDocumentService.apply_verification_outcome())
call this method, then separately call the appropriate document
service's apply_verification_outcome() with the same outcome — two
explicit calls, one per domain, composed by the caller. This is flagged
as a real gap (no orchestrating endpoint exists yet), not silently
wired around.
"""

from __future__ import annotations

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
from modules.verification.domain.errors import (
    InvalidManualReviewOutcomeError,
    NoEvidenceForCaseError,
    VerificationCaseNotFoundError,
    VerificationCaseNotInManualReviewError,
)
from modules.verification.ports import VerificationCaseRepository
from modules.verification.providers import VerificationProvider

# VerificationOutcome values are a subset of VerificationStatus's — this
# maps a result's outcome onto the case's next status. See
# domain/entities.py's docstrings for why the two enums are kept separate.
_OUTCOME_TO_STATUS: dict[VerificationOutcome, VerificationStatus] = {
    VerificationOutcome.APPROVED: VerificationStatus.APPROVED,
    VerificationOutcome.REJECTED: VerificationStatus.REJECTED,
    VerificationOutcome.MANUAL_REVIEW: VerificationStatus.MANUAL_REVIEW,
}
_TERMINAL_OUTCOMES = frozenset(
    {VerificationOutcome.APPROVED, VerificationOutcome.REJECTED}
)
# CompleteManualReview's outcome must be a final decision — see
# InvalidManualReviewOutcomeError.
_MANUAL_REVIEW_COMPLETION_OUTCOMES = _TERMINAL_OUTCOMES


class VerificationService:
    def __init__(
        self, *, cases: VerificationCaseRepository, provider: VerificationProvider
    ) -> None:
        self._cases = cases
        self._provider = provider

    def submit_evidence(
        self,
        *,
        subject_type: str,
        subject_id: uuid.UUID,
        verification_type: VerificationType,
        evidence_uri: str,
        metadata: dict[str, object] | None = None,
    ) -> VerificationCase:
        now = datetime.now(UTC)
        case = VerificationCase.new(
            subject_type=subject_type,
            subject_id=subject_id,
            verification_type=verification_type,
            now=now,
        )
        case = self._cases.create_case(case)
        evidence = Evidence.new(
            case_id=case.id, evidence_uri=evidence_uri, metadata=metadata, now=now
        )
        self._cases.add_evidence(evidence)
        return case

    async def run_verification(self, *, case_id: uuid.UUID) -> VerificationCase:
        case = self._cases.get_case(case_id)
        if case is None:
            raise VerificationCaseNotFoundError("Verification case not found.")

        case.status = VerificationStatus.PROCESSING
        self._cases.save_case(case)

        evidence_list = self._cases.list_evidence_for_case(case.id)
        if not evidence_list:
            # Structurally shouldn't happen — submit_evidence() always
            # creates a case together with its evidence in the same call
            # — but checked explicitly rather than passing a possibly-None
            # evidence to the provider.
            raise NoEvidenceForCaseError("Verification case has no evidence to verify.")
        outcome = await self._provider.verify(case, evidence_list[-1])

        result = VerificationResult.new(
            case_id=case.id,
            result=outcome,
            confidence=None,
            model_name=type(self._provider).__name__,
            reviewer_id=None,
            reason=None,
            now=datetime.now(UTC),
        )
        self._cases.add_result(result)

        case.status = _OUTCOME_TO_STATUS[outcome]
        if outcome in _TERMINAL_OUTCOMES:
            case.completed_at = datetime.now(UTC)
        self._cases.save_case(case)
        return case

    def complete_manual_review(
        self,
        *,
        case_id: uuid.UUID,
        outcome: VerificationOutcome,
        reviewer_id: uuid.UUID,
        reason: str | None = None,
    ) -> VerificationCase:
        """CompleteManualReview (domain-design.md §18.3). Records the
        admin's final decision as a VerificationResult and transitions
        the case out of MANUAL_REVIEW. Only valid from MANUAL_REVIEW —
        same "only one meaningful edge" reasoning used throughout this
        codebase for other "already decided" guards. `outcome` must be
        APPROVED or REJECTED (see InvalidManualReviewOutcomeError).

        Does NOT write back onto driver.documents/vehicle.documents —
        see this module's docstring for why, and for what the caller
        must do next.
        """
        if outcome not in _MANUAL_REVIEW_COMPLETION_OUTCOMES:
            raise InvalidManualReviewOutcomeError(
                "complete_manual_review() requires a final outcome "
                "(APPROVED or REJECTED), not MANUAL_REVIEW."
            )

        case = self._cases.get_case(case_id)
        if case is None:
            raise VerificationCaseNotFoundError("Verification case not found.")
        if case.status is not VerificationStatus.MANUAL_REVIEW:
            raise VerificationCaseNotInManualReviewError(
                "This case is not awaiting manual review (already "
                "completed, or never reached MANUAL_REVIEW)."
            )

        result = VerificationResult.new(
            case_id=case.id,
            result=outcome,
            confidence=None,
            model_name=None,
            reviewer_id=reviewer_id,
            reason=reason,
            now=datetime.now(UTC),
        )
        self._cases.add_result(result)

        case.status = _OUTCOME_TO_STATUS[outcome]
        case.completed_at = datetime.now(UTC)
        self._cases.save_case(case)
        return case

    def get_case(self, *, case_id: uuid.UUID) -> VerificationCase:
        case = self._cases.get_case(case_id)
        if case is None:
            raise VerificationCaseNotFoundError("Verification case not found.")
        return case

    def list_cases_for_subject(
        self, *, subject_type: str, subject_id: uuid.UUID
    ) -> list[VerificationCase]:
        return self._cases.list_cases_for_subject(
            subject_type=subject_type, subject_id=subject_id
        )

    # --- Admin (Admin Web §4.4) ------------------------------------------

    def search_cases(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[VerificationCase], int]:
        return self._cases.list_by_status(status=status, offset=offset, limit=limit)
