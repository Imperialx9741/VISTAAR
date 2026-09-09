"""Domain-level errors for Support.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class SupportDomainError(Exception):
    code: str = "SUPPORT_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidCategoryError(SupportDomainError):
    """No canonical category enum is documented anywhere — see
    ADR-0022. Only shape (non-blank when supplied, VARCHAR(50)) is
    validated, the same treatment ADR-0007 established for
    document_type."""

    code = "VALIDATION_FAILED"


class InvalidMessageError(SupportDomainError):
    code = "VALIDATION_FAILED"


class SupportCaseNotFoundError(SupportDomainError):
    """Also used when the case exists but the caller has no business
    seeing it — same "don't reveal existence" IDOR reasoning used
    throughout this codebase."""

    code = "RESOURCE_NOT_FOUND"


class SupportCaseNotAssignableError(SupportDomainError):
    """state-machines.md §46: AssignSupportCase (ADR-0022 Decision 2)
    only ever transitions OPEN -> ASSIGNED."""

    code = "INVALID_STATE_TRANSITION"


class SupportCaseNotResolvableError(SupportDomainError):
    """A case already RESOLVED or CLOSED cannot be resolved again."""

    code = "INVALID_STATE_TRANSITION"
