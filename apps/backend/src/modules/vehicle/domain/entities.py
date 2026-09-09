"""Vehicle domain entity and validation.

Field shapes match docs/04-database/database-design.md §8.1
(vehicle.vehicles) exactly. vehicle.documents (§8.2) is added in Phase 2
/ Task 2.5 — see VehicleDocument below.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from modules.vehicle.domain.errors import (
    InvalidCabTierError,
    InvalidCategoryError,
    InvalidDocumentNumberError,
    InvalidDocumentTypeError,
    InvalidEvidenceUriError,
    InvalidMakeOrModelError,
    InvalidRegistrationNumberError,
)

_MAX_MAKE_MODEL_LENGTH = 100  # matches database-design.md §8.1's VARCHAR(100)
_MAX_REGISTRATION_NUMBER_LENGTH = 30  # matches VARCHAR(30)
_MAX_DOCUMENT_TYPE_LENGTH = 40  # matches database-design.md §8.2's VARCHAR(40)
_MAX_DOCUMENT_NUMBER_LENGTH = 100  # matches VARCHAR(100)
_MAX_EVIDENCE_URI_LENGTH = 2048  # same defensive bound as modules/driver


class VehicleCategory(StrEnum):
    """Exactly database-design.md §8.1's documented "Allowed
    categories" — matches business-rules.md §2's "Supported Vehicle
    Categories" (Bike, Auto, Cab) and PRD.md §7."""

    BIKE = "BIKE"
    AUTO = "AUTO"
    CAB = "CAB"


class CabTier(StrEnum):
    """CAB-only fare/eligibility sub-tier (ADR-0020 Decision 1) — not a
    new VehicleCategory. Selected by the driver at vehicle creation and,
    separately, by the customer at ride request (modules/ride/domain/
    entities.py::Ride.requested_cab_tier) — the two selections must
    match for a vehicle to be matched to a ride, enforced via
    matching_category_key() below."""

    ECO = "ECO"
    PREMIUM = "PREMIUM"
    PREMIUM_PLUS = "PREMIUM_PLUS"


def validate_cab_tier(
    category: VehicleCategory, cab_tier: str | None
) -> CabTier | None:
    """CAB requires a tier; every other category must not have one — a
    tier on a BIKE/AUTO would be meaningless data with nothing to key
    fare_rules or matching off of."""
    if category is VehicleCategory.CAB:
        if cab_tier is None:
            raise InvalidCabTierError("cab_tier is required when category is CAB.")
        try:
            return CabTier(cab_tier)
        except ValueError as exc:
            raise InvalidCabTierError(
                f"cab_tier must be one of {[t.value for t in CabTier]}."
            ) from exc
    if cab_tier is not None:
        raise InvalidCabTierError("cab_tier is only valid when category is CAB.")
    return None


def matching_category_key(category: VehicleCategory, cab_tier: CabTier | None) -> str:
    """The string modules.matching's entirely category-agnostic
    machinery (shared/geo.py's Redis geo-index keys, DriverEligibility
    Checker.check(), NearbyDriverIndex.nearest_driver_ids()) actually
    matches on — ADR-0020 Decision 1. CAB carries its tier in the key
    (e.g. "CAB:ECO") so a customer requesting PREMIUM is only ever
    offered a vehicle self-declared as PREMIUM; BIKE/AUTO are unchanged
    plain category strings, matching the pre-tier behavior exactly.
    Lives here (not in modules.matching) because building this key
    needs VehicleCategory/CabTier, and modules.matching deliberately
    never imports modules.vehicle (see modules/matching/service.py's
    docstring) — every caller of this function is already a
    router/composition-layer module that imports modules.vehicle
    directly (modules/ride/router.py, modules/matching/router.py,
    modules/matching/dependencies.py)."""
    if category is VehicleCategory.CAB:
        assert cab_tier is not None  # enforced by validate_cab_tier()
        return f"{category.value}:{cab_tier.value}"
    return category.value


ALL_MATCHING_CATEGORY_KEYS: list[str] = [
    VehicleCategory.BIKE.value,
    VehicleCategory.AUTO.value,
    *(matching_category_key(VehicleCategory.CAB, tier) for tier in CabTier),
]
"""Every real matching_category_key() value this codebase can produce —
BIKE, AUTO, CAB:ECO, CAB:PREMIUM, CAB:PREMIUM_PLUS. Used where a caller
needs to enumerate every possible geo:drivers:{category} Redis key
rather than build one for a specific vehicle (e.g. shared/geo.py's
count_online_drivers(), composed from modules/admin/router.py's
Dashboard Summary endpoint)."""


class VehicleVerificationStatus(StrEnum):
    """PENDING is database-design.md §8.1's documented default.
    APPROVED/REJECTED mirror the same pattern already used for
    driver.drivers.verification_status (see
    modules/driver/domain/entities.py's identical docstring reasoning) —
    domain-design.md §8.3's ApproveVehicle/RejectVehicle commands are the
    only sensible source of these two additional values. Nothing in this
    task ever transitions this field away from PENDING — see
    modules/vehicle/__init__.py."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class VehicleOperationalStatus(StrEnum):
    """INACTIVE is database-design.md §8.1's documented default. ACTIVE
    is the only other value api-contracts.md §11 (Activate/Deactivate
    Vehicle) and domain-design.md §8.3
    (ActivateVehicle/DeactivateVehicle) imply — no third value is
    documented anywhere for vehicle.vehicles.operational_status (unlike
    driver.drivers.operational_status's 5-value "Driver State")."""

    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"


def validate_category(category: str) -> VehicleCategory:
    try:
        return VehicleCategory(category)
    except ValueError as exc:
        raise InvalidCategoryError(
            f"category must be one of {[c.value for c in VehicleCategory]}."
        ) from exc


def validate_registration_number(registration_number: str) -> str:
    """No specific format (e.g. an Indian RTO regex) is validated —
    none is documented anywhere in this repository's source-of-truth
    documents, and inventing one would be exactly the kind of unrequested
    business rule this task must not add. Only the documented NOT NULL /
    length constraint is enforced here; global uniqueness is enforced by
    the database (database-design.md §8.1's UNIQUE constraint) and
    surfaced by the repository layer.

    Normalized to uppercase before that uniqueness check — a technical
    normalization (the same plate typed in different case should not be
    treated as two different vehicles), not a business rule, matching
    the same spirit as phone-number E.164 normalization in
    modules/identity/domain/phone_number.py."""
    stripped = registration_number.strip().upper()
    if not stripped:
        raise InvalidRegistrationNumberError("registration_number cannot be blank.")
    if len(stripped) > _MAX_REGISTRATION_NUMBER_LENGTH:
        raise InvalidRegistrationNumberError(
            f"registration_number cannot exceed "
            f"{_MAX_REGISTRATION_NUMBER_LENGTH} characters."
        )
    return stripped


def validate_make_or_model(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > _MAX_MAKE_MODEL_LENGTH:
        raise InvalidMakeOrModelError(
            f"{field_name} cannot exceed {_MAX_MAKE_MODEL_LENGTH} characters."
        )
    return stripped


class DocumentVerificationStatus(StrEnum):
    """PENDING is database-design.md §7.2/§8.2's documented default.
    APPROVED/REJECTED/EXPIRED are exactly the 4 values
    docs/07-state-machines/state-machines.md §44 ("Driver Document
    State") documents — the same 4 values used for
    driver.documents.verification_status
    (modules/driver/domain/entities.py). Defined independently here
    rather than imported from modules.driver, matching this module's
    existing no-cross-module-import rule (see service.py's docstring).
    Nothing in this task ever transitions a document away from PENDING —
    see modules/vehicle/__init__.py."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


def validate_document_type(document_type: str) -> str:
    """No canonical document_type enum exists anywhere in the
    documentation set — see docs/14-decisions/ADR-0007. Only shape
    (non-blank, VARCHAR(40)) is validated; normalized to uppercase for
    consistent querying, same rationale as registration_number above."""
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
    modules/vehicle/__init__.py). Only a defensive length bound is
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
class Vehicle:
    id: uuid.UUID
    driver_id: uuid.UUID
    category: VehicleCategory
    cab_tier: CabTier | None
    registration_number: str
    make: str | None
    model: str | None
    verification_status: VehicleVerificationStatus
    operational_status: VehicleOperationalStatus
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def new(
        *,
        driver_id: uuid.UUID,
        category: str,
        cab_tier: str | None = None,
        registration_number: str,
        make: str | None,
        model: str | None,
        now: datetime,
    ) -> Vehicle:
        validated_category = validate_category(category)
        return Vehicle(
            id=uuid.uuid4(),
            driver_id=driver_id,
            category=validated_category,
            cab_tier=validate_cab_tier(validated_category, cab_tier),
            registration_number=validate_registration_number(registration_number),
            make=validate_make_or_model(make, field_name="make"),
            model=validate_make_or_model(model, field_name="model"),
            verification_status=VehicleVerificationStatus.PENDING,
            operational_status=VehicleOperationalStatus.INACTIVE,
            created_at=now,
            updated_at=now,
        )


@dataclass(slots=True)
class VehicleDocument:
    """Mirrors docs/04-database/database-design.md §8.2 (vehicle.documents)
    exactly — notably, unlike driver.documents
    (modules/driver/domain/entities.py::DriverDocument), this table has
    NO updated_at column. That asymmetry is exactly as documented and is
    preserved here deliberately, not "fixed" to match driver.documents."""

    id: uuid.UUID
    vehicle_id: uuid.UUID
    document_type: str
    document_number: str | None
    evidence_uri: str | None
    verification_status: DocumentVerificationStatus
    expires_at: datetime | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        vehicle_id: uuid.UUID,
        document_type: str,
        document_number: str | None,
        evidence_uri: str | None,
        expires_at: datetime | None,
        now: datetime,
    ) -> VehicleDocument:
        return VehicleDocument(
            id=uuid.uuid4(),
            vehicle_id=vehicle_id,
            document_type=validate_document_type(document_type),
            document_number=validate_document_number(document_number),
            evidence_uri=validate_evidence_uri(evidence_uri),
            verification_status=DocumentVerificationStatus.PENDING,
            expires_at=expires_at,
            created_at=now,
        )
