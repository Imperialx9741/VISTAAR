"""Domain-level errors for Safety.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class SafetyDomainError(Exception):
    code: str = "SAFETY_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidIncidentTypeError(SafetyDomainError):
    """No canonical incident_type enum is documented anywhere — see
    ADR-0022. Only shape (non-blank, VARCHAR(50)) is validated, the same
    treatment ADR-0007 established for document_type."""

    code = "VALIDATION_FAILED"


class InvalidCoordinateError(SafetyDomainError):
    code = "VALIDATION_FAILED"


class IncidentNotFoundError(SafetyDomainError):
    """Also used when the incident exists but the caller has no
    business seeing it — same "don't reveal existence" IDOR reasoning
    used throughout this codebase."""

    code = "RESOURCE_NOT_FOUND"


class IncidentNotAcknowledgeableError(SafetyDomainError):
    """state-machines.md §45: AcknowledgeSOS only ever transitions
    OPEN -> ACKNOWLEDGED."""

    code = "INVALID_STATE_TRANSITION"


class IncidentNotEscalatableError(SafetyDomainError):
    """state-machines.md §45: EscalateSOS only ever transitions
    ACKNOWLEDGED -> IN_PROGRESS (ADR-0022 Decision 3)."""

    code = "INVALID_STATE_TRANSITION"


class IncidentNotResolvableError(SafetyDomainError):
    """state-machines.md §45: ResolveSafetyIncident only ever
    transitions IN_PROGRESS -> RESOLVED."""

    code = "INVALID_STATE_TRANSITION"
