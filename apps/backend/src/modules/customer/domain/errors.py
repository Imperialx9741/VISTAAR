"""Domain-level errors for Customer.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones — none of this module's failure cases need a code
that doesn't already exist there.
"""

from __future__ import annotations


class CustomerDomainError(Exception):
    code: str = "CUSTOMER_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidFullNameError(CustomerDomainError):
    code = "VALIDATION_FAILED"


class InvalidLanguageError(CustomerDomainError):
    code = "VALIDATION_FAILED"


class InvalidProfilePhotoUriError(CustomerDomainError):
    code = "VALIDATION_FAILED"


class CustomerNotFoundError(CustomerDomainError):
    """Admin Web §4.1's Customer Detail — unlike get_profile() (which
    auto-provisions for the self-service /me flow, ADR-0019 Decision 4),
    an admin looking up an arbitrary customer_id gets a real
    RESOURCE_NOT_FOUND for one with no customer.customers row, not a
    row silently created for a typo'd id."""

    code = "RESOURCE_NOT_FOUND"
