"""Domain-level errors for Verification.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class VerificationDomainError(Exception):
    code: str = "VERIFICATION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class VerificationCaseNotFoundError(VerificationDomainError):
    """Same "not found or not owned" IDOR-protection pattern used
    throughout this codebase (e.g.
    modules.identity.domain.errors.OtpChallengeNotFoundError)."""

    code = "RESOURCE_NOT_FOUND"


class NoEvidenceForCaseError(VerificationDomainError):
    """Defensive-only: submit_evidence() always creates a case together
    with its evidence, so this should be structurally unreachable via any
    path this task wires up. See service.py::run_verification()."""

    code = "INVALID_STATE_TRANSITION"


class VerificationCaseNotInManualReviewError(VerificationDomainError):
    """Phase 2 / Task 2.6B (CompleteManualReview — domain-design.md
    §18.3). Raised when complete_manual_review() is called on a case not
    currently in MANUAL_REVIEW — either it never reached that state
    (still PENDING/PROCESSING) or it was already completed
    (APPROVED/REJECTED/EXPIRED). Same "only one meaningful edge" guard
    reasoning as modules.driver.domain.errors.DriverVerificationAlreadyDecidedError."""

    code = "INVALID_STATE_TRANSITION"


class InvalidManualReviewOutcomeError(VerificationDomainError):
    """complete_manual_review()'s outcome must be a final admin decision
    — APPROVED or REJECTED. MANUAL_REVIEW is not a valid "completion"
    outcome (it would mean the review wasn't actually completed)."""

    code = "VALIDATION_FAILED"
