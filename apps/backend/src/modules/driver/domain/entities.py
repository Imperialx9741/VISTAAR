"""Driver domain entity and validation.

Field shapes match docs/04-database/database-design.md §7.1
(driver.drivers) exactly. driver.documents (§7.2) is added in Phase 2 /
Task 2.5 — see DriverDocument below. vehicle fields belong to
vehicle.vehicles (modules/vehicle/), out of scope for this module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from modules.driver.domain.errors import (
    InvalidDocumentNumberError,
    InvalidDocumentTypeError,
    InvalidEvidenceUriError,
    InvalidFullNameError,
    InvalidProfilePhotoUriError,
)

_MAX_FULL_NAME_LENGTH = 150  # matches database-design.md §7.1's VARCHAR(150)
_MAX_PROFILE_PHOTO_URI_LENGTH = 2048  # same bound used in modules/customer
_MAX_DOCUMENT_TYPE_LENGTH = 40  # matches database-design.md §7.2's VARCHAR(40)
_MAX_DOCUMENT_NUMBER_LENGTH = 100  # matches VARCHAR(100)
_MAX_EVIDENCE_URI_LENGTH = 2048  # same bound as profile_photo_uri (TEXT column,
# no documented limit — this is a defensive application-level bound only)


class DriverVerificationStatus(StrEnum):
    """PENDING is database-design.md §7.1's documented default.

    APPROVED/REJECTED are not otherwise enumerated in one place in the
    documentation set, but are the only sensible outcomes of
    domain-design.md §7.4's ApproveDriver/RejectDriver commands, and
    mirror the identical PENDING/APPROVED/REJECTED pattern already used
    for driver.documents.verification_status and
    vehicle.vehicles.verification_status (database-design.md §7.2, §8.1).
    Nothing in this task ever transitions this field away from PENDING —
    see modules/driver/__init__.py.
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DriverOperationalStatus(StrEnum):
    """Exactly the 5 values docs/04-domain-design/domain-design.md §7.3
    ("Driver State") documents. OFFLINE is database-design.md §7.1's
    documented default. Nothing in this task ever transitions this field
    away from OFFLINE — see modules/driver/__init__.py."""

    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"
    ON_RIDE = "ON_RIDE"
    SUSPENDED = "SUSPENDED"
    INELIGIBLE = "INELIGIBLE"


def validate_full_name(full_name: str) -> str:
    """Unlike modules.customer's version, this one does not accept None —
    driver.drivers.full_name is NOT NULL (database-design.md §7.1)."""
    stripped = full_name.strip()
    if not stripped:
        raise InvalidFullNameError("full_name cannot be blank.")
    if len(stripped) > _MAX_FULL_NAME_LENGTH:
        raise InvalidFullNameError(
            f"full_name cannot exceed {_MAX_FULL_NAME_LENGTH} characters."
        )
    return stripped


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


class DocumentVerificationStatus(StrEnum):
    """PENDING is database-design.md §7.2/§8.2's documented default.
    APPROVED/REJECTED/EXPIRED are exactly the 4 values
    docs/07-state-machines/state-machines.md §44 ("Driver Document
    State") documents — shared by driver.documents and
    vehicle.documents.verification_status (see
    modules/vehicle/domain/entities.py, which reuses this same enum's
    values rather than redefining them). Nothing in this task ever
    transitions a document away from PENDING — see
    modules/driver/__init__.py."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


def validate_document_type(document_type: str) -> str:
    """No canonical document_type enum exists anywhere in the
    documentation set — see docs/14-decisions/ADR-0007. Only shape
    (non-blank, VARCHAR(40)) is validated; normalized to uppercase for
    consistent querying, the same technical-normalization rationale used
    for vehicle.registration_number (modules/vehicle/domain/entities.py)."""
    stripped = document_type.strip().upper()
    if not stripped:
        raise InvalidDocumentTypeError("document_type cannot be blank.")
    if len(stripped) > _MAX_DOCUMENT_TYPE_LENGTH:
        raise InvalidDocumentTypeError(
            f"document_type cannot exceed {_MAX_DOCUMENT_TYPE_LENGTH} characters."
        )
    return stripped


def validate_document_number(document_number: str | None) -> str | None:
    if document_number is None:
        return None
    stripped = document_number.strip()
    if not stripped:
        return None
    if len(stripped) > _MAX_DOCUMENT_NUMBER_LENGTH:
        raise InvalidDocumentNumberError(
            f"document_number cannot exceed {_MAX_DOCUMENT_NUMBER_LENGTH} characters."
        )
    return stripped


def validate_evidence_uri(evidence_uri: str | None) -> str | None:
    """evidence_uri is opaque metadata only — never dereferenced, fetched,
    or validated as a real/reachable URL (see ADR-0007 and
    modules/driver/__init__.py). Only a defensive length bound is
    enforced."""
    if evidence_uri is None:
        return None
    stripped = evidence_uri.strip()
    if not stripped:
        return None
    if len(stripped) > _MAX_EVIDENCE_URI_LENGTH:
        raise InvalidEvidenceUriError(
            f"evidence_uri cannot exceed {_MAX_EVIDENCE_URI_LENGTH} characters."
        )
    return stripped


@dataclass(slots=True)
class Driver:
    id: uuid.UUID  # == identity.accounts.id (shared primary key)
    full_name: str
    profile_photo_uri: str | None
    verification_status: DriverVerificationStatus
    operational_status: DriverOperationalStatus
    strikes: int
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def new(driver_id: uuid.UUID, *, full_name: str, now: datetime) -> Driver:
        """The initial profile for a driver account seen for the first
        time — see service.py. full_name must be supplied by the caller
        (there is no sensible default for a NOT NULL column with no
        source of truth elsewhere — identity.accounts has no name field)."""
        return Driver(
            id=driver_id,
            full_name=validate_full_name(full_name),
            profile_photo_uri=None,
            verification_status=DriverVerificationStatus.PENDING,
            operational_status=DriverOperationalStatus.OFFLINE,
            strikes=0,
            created_at=now,
            updated_at=now,
        )


@dataclass(slots=True)
class DriverDocument:
    """Mirrors docs/04-database/database-design.md §7.2 (driver.documents)
    exactly — including having updated_at (unlike vehicle.documents,
    which does not; see modules/vehicle/domain/entities.py::VehicleDocument).
    """

    id: uuid.UUID
    driver_id: uuid.UUID
    document_type: str
    document_number: str | None
    evidence_uri: str | None
    verification_status: DocumentVerificationStatus
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def new(
        *,
        driver_id: uuid.UUID,
        document_type: str,
        document_number: str | None,
        evidence_uri: str | None,
        expires_at: datetime | None,
        now: datetime,
    ) -> DriverDocument:
        return DriverDocument(
            id=uuid.uuid4(),
            driver_id=driver_id,
            document_type=validate_document_type(document_type),
            document_number=validate_document_number(document_number),
            evidence_uri=validate_evidence_uri(evidence_uri),
            verification_status=DocumentVerificationStatus.PENDING,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
