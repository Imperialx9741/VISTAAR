"""Domain-level errors for Vehicle.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones. VEHICLE_NOT_ELIGIBLE and INVALID_STATE_TRANSITION
already exist there for exactly the two documented Activate/Deactivate
preconditions (api-contracts.md §11: "Vehicle approved AND Driver
OFFLINE").
"""

from __future__ import annotations


class VehicleDomainError(Exception):
    code: str = "VEHICLE_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidCategoryError(VehicleDomainError):
    code = "VALIDATION_FAILED"


class InvalidRegistrationNumberError(VehicleDomainError):
    code = "VALIDATION_FAILED"


class InvalidMakeOrModelError(VehicleDomainError):
    code = "VALIDATION_FAILED"


class InvalidCabTierError(VehicleDomainError):
    """ADR-0020 Decision 1: cab_tier is required (and must be one of
    ECO/PREMIUM/PREMIUM_PLUS) when category is CAB, and must be absent
    for every other category."""

    code = "VALIDATION_FAILED"


class DuplicateRegistrationNumberError(VehicleDomainError):
    """vehicle.vehicles.registration_number is UNIQUE (database-design.md
    §8.1) — globally, not just per-driver."""

    code = "VALIDATION_FAILED"


class VehicleNotFoundError(VehicleDomainError):
    """Also used when the vehicle exists but belongs to a different
    driver — same "don't reveal existence to an unauthorized caller"
    reasoning used throughout this codebase (e.g.
    modules.identity.domain.errors.OtpChallengeNotFoundError)."""

    code = "RESOURCE_NOT_FOUND"


class VehicleNotEligibleError(VehicleDomainError):
    """api-contracts.md §11: Activate Vehicle requires "Vehicle
    approved" — raised when verification_status != APPROVED."""

    code = "VEHICLE_NOT_ELIGIBLE"


class DriverNotOfflineError(VehicleDomainError):
    """BR-102 / api-contracts.md §11: "Vehicle switching is not allowed
    while ONLINE or ON_RIDE." Reads driver.drivers.operational_status
    (Task 2.3) — see modules/vehicle/__init__.py."""

    code = "INVALID_STATE_TRANSITION"


class VehicleEditableFieldsOnlyError(VehicleDomainError):
    """PATCH /api/v1/drivers/me/vehicles/{id} accepts only make/model —
    see api-contracts.md §11."""

    code = "VALIDATION_FAILED"


class InvalidDocumentTypeError(VehicleDomainError):
    """See ADR-0007 — document_type has no canonical enum anywhere in the
    documentation set, so only shape (non-blank, VARCHAR(40)) is
    validated here, not a value list."""

    code = "VALIDATION_FAILED"


class InvalidDocumentNumberError(VehicleDomainError):
    code = "VALIDATION_FAILED"


class InvalidEvidenceUriError(VehicleDomainError):
    code = "VALIDATION_FAILED"


class VehicleDocumentNotFoundError(VehicleDomainError):
    """Same "not found or not owned" IDOR-protection pattern as
    VehicleNotFoundError."""

    code = "RESOURCE_NOT_FOUND"


class VehicleDocumentAlreadyDecidedError(VehicleDomainError):
    """Phase 2 / Task 2.6B. Mirrors
    modules.driver.domain.errors.DriverDocumentAlreadyDecidedError —
    apply_verification_outcome() only ever transitions a document away
    from PENDING once."""

    code = "INVALID_STATE_TRANSITION"


class VehicleRequiredDocumentsNotValidError(VehicleDomainError):
    """Phase 2 / Task 2.6C — business-rules.md BR-123. Raised by
    approve_vehicle() when one or more required documents
    (modules.vehicle.domain.required_documents.REQUIRED_VEHICLE_DOCUMENT_TYPES)
    are missing, PENDING, REJECTED, or EXPIRED. Reuses the existing,
    already-documented VEHICLE_NOT_ELIGIBLE code — no new code invented."""

    code = "VEHICLE_NOT_ELIGIBLE"


class VehicleVerificationAlreadyDecidedError(VehicleDomainError):
    """Phase 2 / Task 2.7A. Mirrors
    modules.driver.domain.errors.DriverVerificationAlreadyDecidedError —
    approve_vehicle()/reject_vehicle() only ever operate on a PENDING
    vehicle. Raised if verification_status is already APPROVED or
    REJECTED."""

    code = "INVALID_STATE_TRANSITION"


class VehicleActivationConflictError(VehicleDomainError):
    """Defensive backstop: raised if the database's
    uq_vehicles_one_active_per_driver partial unique index
    (database-design.md §8.1, BR-122) is ever violated despite the
    row-locking in VehicleService.activate_vehicle() — i.e. this should
    never actually happen in practice, but a clean domain error is
    preferable to a raw IntegrityError reaching the client if it ever
    does. See repositories.py::save()."""

    code = "INVALID_STATE_TRANSITION"
