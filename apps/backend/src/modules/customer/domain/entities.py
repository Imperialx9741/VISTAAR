"""Customer domain entity and validation.

The domain entity combines both database-design.md §6 tables
(customer.customers + customer.preferences) into a single Customer
concept — they are 1:1 (customer.preferences.customer_id is customer.
customers.id) and always created/read together, so nothing outside this
module needs to know they are two rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from modules.customer.domain.errors import (
    InvalidFullNameError,
    InvalidLanguageError,
    InvalidProfilePhotoUriError,
)

_MAX_FULL_NAME_LENGTH = 150  # matches database-design.md §6.1's VARCHAR(150)
_MAX_PROFILE_PHOTO_URI_LENGTH = 2048  # generous bound for an opaque storage reference

# PRD.md §6: "Languages: English, Hindi ... must use localization so
# additional Indian languages can be added without major redesign." The
# column itself (VARCHAR(10)) does not constrain values at the database
# level for exactly that reason — this allow-list lives here, in the
# application/domain layer, so adding a language later is a one-line
# change here, not a migration.
_ALLOWED_LANGUAGES = frozenset({"en", "hi"})


class CustomerStatus(StrEnum):
    """ACTIVE is the only value used in this task.

    database-design.md §6.1 documents ACTIVE as the default and only
    mentions the concept of deactivation via domain-design.md §6.3's
    DeactivateCustomer/ReactivateCustomer commands, which this task
    deliberately does not implement (see modules/customer/__init__.py).
    No second status value is invented here ahead of that decision.
    """

    ACTIVE = "ACTIVE"


def validate_full_name(full_name: str | None) -> str | None:
    if full_name is None:
        return None
    stripped = full_name.strip()
    if not stripped:
        raise InvalidFullNameError("full_name cannot be blank.")
    if len(stripped) > _MAX_FULL_NAME_LENGTH:
        raise InvalidFullNameError(
            f"full_name cannot exceed {_MAX_FULL_NAME_LENGTH} characters."
        )
    return stripped


def validate_language(language: str | None) -> str | None:
    if language is None:
        return None
    normalized = language.strip().lower()
    if normalized not in _ALLOWED_LANGUAGES:
        raise InvalidLanguageError(
            f"language must be one of {sorted(_ALLOWED_LANGUAGES)}."
        )
    return normalized


def validate_profile_photo_uri(uri: str | None) -> str | None:
    if uri is None:
        return None
    stripped = uri.strip()
    if not stripped:
        raise InvalidProfilePhotoUriError("profile_photo_uri cannot be blank.")
    if len(stripped) > _MAX_PROFILE_PHOTO_URI_LENGTH:
        raise InvalidProfilePhotoUriError(
            f"profile_photo_uri cannot exceed "
            f"{_MAX_PROFILE_PHOTO_URI_LENGTH} characters."
        )
    return stripped


@dataclass(slots=True)
class Customer:
    id: uuid.UUID  # == identity.accounts.id (shared primary key)
    full_name: str | None
    profile_photo_uri: str | None
    status: CustomerStatus
    language: str
    notification_enabled: bool
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def new(customer_id: uuid.UUID, *, now: datetime) -> Customer:
        """Default profile for a customer account seen for the first
        time — see service.py's auto-provisioning."""
        return Customer(
            id=customer_id,
            full_name=None,
            profile_photo_uri=None,
            status=CustomerStatus.ACTIVE,
            language="en",
            notification_enabled=True,
            created_at=now,
            updated_at=now,
        )
