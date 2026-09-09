"""Domain-level errors for Penalty."""

from __future__ import annotations


class PenaltyDomainError(Exception):
    code: str = "PENALTY_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class PenaltyNotFoundError(PenaltyDomainError):
    code = "RESOURCE_NOT_FOUND"


class PenaltyNotOutstandingError(PenaltyDomainError):
    """Phase 16 (ResolvePenalty, ADR-0023) — raised by
    PenaltyService.resolve_penalty() when the targeted penalty's status
    is not OUTSTANDING (already SETTLED/WAIVED). Reuses the same
    error code Approve/Reject Driver/Vehicle already use for their own
    "not in the expected starting state" case — no new code invented."""

    code = "INVALID_STATE_TRANSITION"


class InvalidPenaltyResolutionActionError(PenaltyDomainError):
    """Phase 16 (ADR-0023) — `action` must be exactly "WAIVE", the only
    value api-contracts.md §48's example shows and the only outcome
    state-machines.md §40 documents an admin action reaching. No
    canonical `action` enum exists to validate more permissively
    against."""

    code = "VALIDATION_FAILED"
