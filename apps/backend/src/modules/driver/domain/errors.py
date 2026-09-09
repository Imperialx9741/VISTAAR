"""Domain-level errors for Driver.

Reuse existing error codes from docs/05-api/api-contracts.md §49 rather
than inventing new ones.
"""

from __future__ import annotations


class DriverDomainError(Exception):
    code: str = "DRIVER_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidFullNameError(DriverDomainError):
    code = "VALIDATION_FAILED"


class InvalidProfilePhotoUriError(DriverDomainError):
    code = "VALIDATION_FAILED"


class FullNameRequiredForCreationError(DriverDomainError):
    """driver.drivers.full_name is NOT NULL (database-design.md §7.1) —
    unlike customer.customers.full_name, a driver profile cannot be
    auto-provisioned with a null name. See service.py for where this is
    raised and modules/driver/__init__.py-adjacent design note in this
    task's final report for the full reasoning."""

    code = "VALIDATION_FAILED"


class DriverProfileNotFoundError(DriverDomainError):
    """Raised by GET when no driver.drivers row exists yet for this
    account. Unlike Customer, Get Profile does not auto-provision here —
    see FullNameRequiredForCreationError's docstring."""

    code = "RESOURCE_NOT_FOUND"


class InvalidDocumentTypeError(DriverDomainError):
    """See ADR-0007 — document_type has no canonical enum anywhere in the
    documentation set, so only shape (non-blank, VARCHAR(40)) is
    validated here, not a value list."""

    code = "VALIDATION_FAILED"


class InvalidDocumentNumberError(DriverDomainError):
    code = "VALIDATION_FAILED"


class InvalidEvidenceUriError(DriverDomainError):
    code = "VALIDATION_FAILED"


class DriverDocumentNotFoundError(DriverDomainError):
    """Same "not found or not owned" IDOR-protection pattern as
    DriverProfileNotFoundError/VehicleNotFoundError — never distinguishes
    "does not exist" from "belongs to another driver"."""

    code = "RESOURCE_NOT_FOUND"


class DriverDocumentAlreadyDecidedError(DriverDomainError):
    """Phase 2 / Task 2.6B. apply_verification_outcome() only ever
    transitions a document away from PENDING once — same "only one
    meaningful edge" guard already used for
    DriverVerificationAlreadyDecidedError."""

    code = "INVALID_STATE_TRANSITION"


class DriverRequiredDocumentsNotValidError(DriverDomainError):
    """Phase 2 / Task 2.6C — business-rules.md BR-123. Raised by
    approve_driver() when one or more required documents
    (modules.driver.domain.required_documents.REQUIRED_DRIVER_DOCUMENT_TYPES)
    are missing, PENDING, REJECTED, or EXPIRED. Reuses the existing,
    already-documented DRIVER_NOT_ELIGIBLE code (api-contracts.md §49) —
    no new code invented."""

    code = "DRIVER_NOT_ELIGIBLE"


class DriverVerificationAlreadyDecidedError(DriverDomainError):
    """Phase 2 / Task 2.7A. The only state transition any source document
    supports is PENDING -> APPROVED (or, per ADR-0009, PENDING ->
    REJECTED) — approve_driver()/reject_driver() only ever operate on a
    PENDING driver. Raised if verification_status is already APPROVED or
    REJECTED. Not a new business rule — the necessary consequence of that
    being the only documented edge, same reasoning as
    modules.vehicle.domain.errors.VehicleNotEligibleError."""

    code = "INVALID_STATE_TRANSITION"


class DriverNotApprovedError(DriverDomainError):
    """Phase 2 / Task 2.7B. Go Online (api-contracts.md §10) requires
    "Driver approved" — raised when go_online() is attempted while
    verification_status != APPROVED. Reuses the existing, already-
    documented DRIVER_NOT_ELIGIBLE code — no new code invented."""

    code = "DRIVER_NOT_ELIGIBLE"


class NoEligibleVehicleError(DriverDomainError):
    """Phase 2 / Task 2.7B. Go Online requires "Vehicle approved AND
    Vehicle active" (api-contracts.md §10) — raised when the driver has
    no vehicle that is simultaneously verification_status APPROVED and
    operational_status ACTIVE. Covers both "no ACTIVE vehicle at all" and
    "the ACTIVE vehicle is not APPROVED" the same way, since BR-122
    guarantees at most one ACTIVE vehicle per driver — there is never a
    second candidate to fall back to. Reuses DRIVER_NOT_ELIGIBLE, same as
    DriverNotApprovedError above."""

    code = "DRIVER_NOT_ELIGIBLE"


class VehicleDocumentsNotValidForGoOnlineError(DriverDomainError):
    """Phase 2 / Task 2.7B. Go Online's "Required documents valid"
    precondition (api-contracts.md §10) applies to the ACTIVE vehicle's
    documents (RC, Insurance — business-rules.md BR-123), not only the
    driver's own. Re-checked here (separately from
    VehicleService.approve_vehicle()'s one-time BR-123 gate at approval
    time) because a document can expire after the vehicle was already
    approved. Reuses DRIVER_NOT_ELIGIBLE — this is a Go Online
    precondition failure on the driver side of the operation, not a
    vehicle-verification-status change, so VEHICLE_NOT_ELIGIBLE (a
    modules.vehicle-owned code) would not fit."""

    code = "DRIVER_NOT_ELIGIBLE"


class DriverNotOfflineError(DriverDomainError):
    """Phase 2 / Task 2.7B. go_online() only transitions OFFLINE ->
    ONLINE (domain-design.md §7.4's GoOnline command) — raised when
    operational_status is already ONLINE or ON_RIDE. Distinct from
    modules.vehicle.domain.errors.DriverNotOfflineError (that one blocks
    a *vehicle* switch on a non-OFFLINE driver; this one blocks GoOnline
    itself) — modules.driver never imports modules.vehicle, so the two
    cannot share a class despite the identical name and code."""

    code = "INVALID_STATE_TRANSITION"


class DriverAlreadySuspendedError(DriverDomainError):
    """Phase 03 (ADR-0021). suspend_driver() only ever transitions INTO
    SUSPENDED once — raised when operational_status is already
    SUSPENDED. Same "only one meaningful edge" guard already used for
    DriverVerificationAlreadyDecidedError."""

    code = "INVALID_STATE_TRANSITION"


class DriverNotSuspendedError(DriverDomainError):
    """Phase 03 (ADR-0021). reactivate_driver() only ever transitions
    SUSPENDED -> OFFLINE — raised when operational_status is not
    currently SUSPENDED."""

    code = "INVALID_STATE_TRANSITION"


class DriverNotOnlineError(DriverDomainError):
    """Phase 2 / Task 2.7B. go_offline() only transitions ONLINE ->
    OFFLINE (domain-design.md §7.4's GoOffline command) — raised when
    operational_status is not ONLINE. Reuses the existing, already-
    documented DRIVER_NOT_ONLINE code (api-contracts.md §49), previously
    unused by any module.

    Deliberately raised identically for OFFLINE -> OFFLINE and ON_RIDE ->
    OFFLINE — api-contracts.md §10 separately documents "A driver cannot
    go offline while an active ride is in progress" as its own rule, and
    a real ride/offer model (Phase 3) would let that case return a more
    specific error (or auto-release the ride first). No ride/offer model
    exists yet in this codebase, so there is nothing to distinguish
    ON_RIDE's cancellation-of-an-active-ride semantics from the plain
    "already offline" case — collapsing them here is a sequencing
    consequence of that missing dependency, not an unresolved conflict in
    the documentation, and is recorded as a Phase 3 dependency rather
    than an ADR."""

    code = "DRIVER_NOT_ONLINE"
