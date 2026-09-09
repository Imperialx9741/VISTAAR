"""Application service (use cases) for Vehicle.

activate_vehicle()/deactivate_vehicle() take driver_operational_status as
a plain str (rather than importing modules.driver's
DriverOperationalStatus enum) — this module has no import dependency on
modules/driver/ at all. router.py is responsible for fetching the
driver's current operational_status (via modules.driver's own service)
and passing its .value through — the same API-layer-composition pattern
used for Identity account data elsewhere in this codebase. See
modules/vehicle/__init__.py for the full reasoning.

VehicleDocumentService.apply_verification_outcome() (Phase 2 / Task
2.6B) does import modules.verification.domain.entities.VerificationOutcome
— a narrow, one-directional dependency (vehicle -> verification, never
the reverse; modules.verification never imports modules.vehicle, staying
subject-agnostic per its own docstring), the same shape of dependency
modules/driver/service.py already has for the identical driver-side
method. Distinct from the "no modules.driver import" rule above.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypedDict

from modules.vehicle.domain.entities import (
    DocumentVerificationStatus,
    Vehicle,
    VehicleDocument,
    VehicleOperationalStatus,
    VehicleVerificationStatus,
    validate_make_or_model,
)
from modules.vehicle.domain.errors import (
    DriverNotOfflineError,
    DuplicateRegistrationNumberError,
    VehicleDocumentAlreadyDecidedError,
    VehicleDocumentNotFoundError,
    VehicleNotEligibleError,
    VehicleNotFoundError,
    VehicleRequiredDocumentsNotValidError,
    VehicleVerificationAlreadyDecidedError,
)
from modules.vehicle.domain.required_documents import (
    missing_or_invalid_required_documents,
)
from modules.vehicle.ports import VehicleDocumentRepository, VehicleRepository
from modules.verification.domain.entities import VerificationOutcome

_VERIFICATION_OUTCOME_TO_DOCUMENT_STATUS: dict[
    VerificationOutcome, DocumentVerificationStatus
] = {
    VerificationOutcome.APPROVED: DocumentVerificationStatus.APPROVED,
    VerificationOutcome.REJECTED: DocumentVerificationStatus.REJECTED,
}

_NOT_OFFLINE_STATUSES = frozenset({"ONLINE", "ON_RIDE"})


class VehicleUpdate(TypedDict, total=False):
    """Only keys actually present are applied — PATCH semantics, same
    convention as modules.customer.service.ProfileUpdate and
    modules.driver.service.ProfileUpdate. Intentionally has no keys for
    driver_id/category/registration_number/verification_status/
    operational_status — see update_vehicle()'s docstring."""

    make: str | None
    model: str | None


class VehicleService:
    def __init__(self, *, vehicles: VehicleRepository) -> None:
        self._vehicles = vehicles

    def list_vehicles(self, *, driver_id: uuid.UUID) -> list[Vehicle]:
        return self._vehicles.list_by_driver(driver_id)

    def add_vehicle(
        self,
        *,
        driver_id: uuid.UUID,
        category: str,
        cab_tier: str | None = None,
        registration_number: str,
        make: str | None,
        model: str | None,
    ) -> Vehicle:
        candidate = Vehicle.new(
            driver_id=driver_id,
            category=category,
            cab_tier=cab_tier,
            registration_number=registration_number,
            make=make,
            model=model,
            now=datetime.now(UTC),
        )
        # database-design.md §8.1: registration_number is globally UNIQUE
        # (not just per-driver). Checked here (in addition to the
        # database's own constraint) to return a clean domain error
        # rather than surfacing a raw IntegrityError.
        if self._vehicles.registration_number_exists(candidate.registration_number):
            raise DuplicateRegistrationNumberError(
                f"registration_number '{candidate.registration_number}' "
                "is already registered."
            )
        return self._vehicles.create(candidate)

    def activate_vehicle(
        self,
        *,
        driver_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        driver_operational_status: str,
    ) -> Vehicle:
        """Enforces BR-122 (approved): at most one of this driver's
        vehicles may be ACTIVE at a time. Activating a different vehicle
        deactivates the previously ACTIVE one as part of this same
        operation.

        Concurrency: list_by_driver_for_update() locks every one of this
        driver's vehicle rows (SELECT ... FOR UPDATE) before any check or
        write — a second, concurrent activate_vehicle() call for the same
        driver_id blocks until this transaction commits, then re-reads
        the now-current state. database-design.md §8.1's
        uq_vehicles_one_active_per_driver partial unique index is the
        unconditional backstop if that were ever bypassed — see
        repositories.py::save() and
        domain/errors.py::VehicleActivationConflictError.
        """
        self._require_driver_offline(driver_operational_status)

        driver_vehicles = self._vehicles.list_by_driver_for_update(driver_id)
        target = next((v for v in driver_vehicles if v.id == vehicle_id), None)
        if target is None:
            # Same response whether the vehicle doesn't exist or belongs
            # to another driver — see _get_owned_vehicle()'s docstring.
            raise VehicleNotFoundError("Vehicle not found.")

        # api-contracts.md §11: Activate Vehicle requires "Vehicle
        # approved AND Driver OFFLINE". Nothing in this codebase
        # currently transitions verification_status away from PENDING
        # (see modules/vehicle/__init__.py) — so this branch will always
        # be taken until a later (admin approval) task exists. That is
        # correct, documented behavior, not a bug.
        if target.verification_status is not VehicleVerificationStatus.APPROVED:
            raise VehicleNotEligibleError("Only an approved vehicle may be activated.")

        now = datetime.now(UTC)
        for other in driver_vehicles:
            if other.id != target.id and other.operational_status is (
                VehicleOperationalStatus.ACTIVE
            ):
                other.operational_status = VehicleOperationalStatus.INACTIVE
                other.updated_at = now
                self._vehicles.save(other)

        target.operational_status = VehicleOperationalStatus.ACTIVE
        target.updated_at = now
        self._vehicles.save(target)
        return target

    def deactivate_vehicle(
        self,
        *,
        driver_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        driver_operational_status: str,
    ) -> Vehicle:
        vehicle = self._get_owned_vehicle(driver_id=driver_id, vehicle_id=vehicle_id)
        self._require_driver_offline(driver_operational_status)

        vehicle.operational_status = VehicleOperationalStatus.INACTIVE
        vehicle.updated_at = datetime.now(UTC)
        self._vehicles.save(vehicle)
        return vehicle

    def get_vehicle(self, *, driver_id: uuid.UUID, vehicle_id: uuid.UUID) -> Vehicle:
        return self._get_owned_vehicle(driver_id=driver_id, vehicle_id=vehicle_id)

    def update_vehicle(
        self,
        *,
        driver_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        update: VehicleUpdate,
    ) -> Vehicle:
        """Only make/model are editable — see schemas.py's
        UpdateVehicleBody and api-contracts.md §11's PATCH
        documentation for why driver_id, category,
        registration_number, verification_status, operational_status,
        and the timestamps are excluded."""
        vehicle = self._get_owned_vehicle(driver_id=driver_id, vehicle_id=vehicle_id)

        if "make" in update:
            vehicle.make = validate_make_or_model(update["make"], field_name="make")
        if "model" in update:
            vehicle.model = validate_make_or_model(update["model"], field_name="model")

        vehicle.updated_at = datetime.now(UTC)
        self._vehicles.save(vehicle)
        return vehicle

    def approve_vehicle(
        self, *, vehicle_id: uuid.UUID, documents: list[VehicleDocument]
    ) -> Vehicle:
        """Phase 2 / Task 2.7A (ApproveVehicle — domain-design.md §8.3),
        extended in Task 2.6C to enforce business-rules.md BR-123. Only
        ever transitions verification_status PENDING -> APPROVED — never
        touches operational_status (stays INACTIVE). Approval does not
        activate a vehicle; Activate Vehicle (activate_vehicle(), above)
        remains the only, separate, driver-initiated, OFFLINE-only path
        to ACTIVE (BR-102, ADR-0006) — matching ADR-0009's explicit
        "do not let approval automatically make a vehicle ACTIVE"
        constraint.

        `documents` must be the caller's already-fetched list of this
        vehicle's documents (via VehicleDocumentService.list_documents())
        — same "caller loads, service decides" composition as
        modules.driver.service.DriverService.approve_driver(). Raises
        VehicleRequiredDocumentsNotValidError (BR-123) if any required
        document (modules.vehicle.domain.required_documents) is missing,
        PENDING, REJECTED, or EXPIRED — checked only after confirming the
        vehicle itself is still PENDING."""
        vehicle = self._vehicles.get_by_id(vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError("Vehicle not found.")
        if vehicle.verification_status is not VehicleVerificationStatus.PENDING:
            raise VehicleVerificationAlreadyDecidedError(
                "This vehicle has already been approved or rejected."
            )

        invalid = missing_or_invalid_required_documents(
            documents, now=datetime.now(UTC)
        )
        if invalid:
            raise VehicleRequiredDocumentsNotValidError(
                "Cannot approve this vehicle — required document(s) not "
                f"in an approved/valid state: {', '.join(invalid)}."
            )

        vehicle.verification_status = VehicleVerificationStatus.APPROVED
        vehicle.updated_at = datetime.now(UTC)
        self._vehicles.save(vehicle)
        return vehicle

    def reject_vehicle(self, *, vehicle_id: uuid.UUID, reason: str | None) -> Vehicle:
        """Phase 2 / Task 2.7A (RejectVehicle — domain-design.md §8.3).
        `reason` is not stored on vehicle.vehicles (no such column is
        documented) — the caller (modules/admin/router.py) records it in
        admin.audit_logs.reason. See ADR-0009 point A."""
        vehicle = self._vehicles.get_by_id(vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError("Vehicle not found.")
        if vehicle.verification_status is not VehicleVerificationStatus.PENDING:
            raise VehicleVerificationAlreadyDecidedError(
                "This vehicle has already been approved or rejected."
            )
        vehicle.verification_status = VehicleVerificationStatus.REJECTED
        vehicle.updated_at = datetime.now(UTC)
        self._vehicles.save(vehicle)
        return vehicle

    # --- Admin (Admin Web §4.3) ------------------------------------------

    def get_vehicle_for_admin(self, vehicle_id: uuid.UUID) -> Vehicle:
        """Unlike get_vehicle()/_get_owned_vehicle(), no driver_id
        ownership check — an admin looks up any vehicle by id directly,
        same as approve_vehicle()/reject_vehicle() already do."""
        vehicle = self._vehicles.get_by_id(vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError("Vehicle not found.")
        return vehicle

    def search_vehicles(
        self, *, query: str | None, status: str | None, offset: int, limit: int
    ) -> tuple[list[Vehicle], int]:
        return self._vehicles.search(
            query=query, status=status, offset=offset, limit=limit
        )

    def _get_owned_vehicle(
        self, *, driver_id: uuid.UUID, vehicle_id: uuid.UUID
    ) -> Vehicle:
        vehicle = self._vehicles.get_by_id(vehicle_id)
        if vehicle is None or vehicle.driver_id != driver_id:
            # Same response for "does not exist" and "belongs to another
            # driver" — avoids revealing another driver's vehicle IDs to
            # an unauthorized caller (IDOR/enumeration protection, same
            # pattern used throughout this codebase).
            raise VehicleNotFoundError("Vehicle not found.")
        return vehicle

    def _require_driver_offline(self, driver_operational_status: str) -> None:
        if driver_operational_status in _NOT_OFFLINE_STATUSES:
            raise DriverNotOfflineError(
                "Vehicle switching is not allowed while ONLINE or ON_RIDE."
            )


class VehicleDocumentService:
    """Phase 2 / Task 2.5. See ADR-0007: no vehicle-document HTTP
    endpoint is documented anywhere, so this service has no router
    wired to it — it exists for internal completeness and is covered by
    service-level tests against a real Postgres.

    Unlike VehicleService's driver-scoped methods, this service trusts
    its caller to have already established vehicle ownership (e.g. via
    VehicleService.get_vehicle(driver_id, vehicle_id), which already
    enforces it) before calling here with a vehicle_id — the same
    API-layer-composition pattern this module already uses for driver
    data (see this module's docstring). It does not re-derive
    driver_id from vehicle_id itself, since that would require importing
    modules.driver, which this module deliberately never does.
    """

    def __init__(self, *, documents: VehicleDocumentRepository) -> None:
        self._documents = documents

    def submit_document(
        self,
        *,
        vehicle_id: uuid.UUID,
        document_type: str,
        document_number: str | None,
        evidence_uri: str | None,
        expires_at: datetime | None,
    ) -> VehicleDocument:
        document = VehicleDocument.new(
            vehicle_id=vehicle_id,
            document_type=document_type,
            document_number=document_number,
            evidence_uri=evidence_uri,
            expires_at=expires_at,
            now=datetime.now(UTC),
        )
        return self._documents.create(document)

    def list_documents(self, *, vehicle_id: uuid.UUID) -> list[VehicleDocument]:
        return self._documents.list_by_vehicle(vehicle_id)

    def get_document(
        self, *, vehicle_id: uuid.UUID, document_id: uuid.UUID
    ) -> VehicleDocument:
        document = self._documents.get_by_id(document_id)
        if document is None or document.vehicle_id != vehicle_id:
            raise VehicleDocumentNotFoundError("Document not found.")
        return document

    def apply_verification_outcome(
        self, *, document_id: uuid.UUID, outcome: VerificationOutcome
    ) -> VehicleDocument:
        """Phase 2 / Task 2.6B. Mirrors
        modules.driver.service.DriverDocumentService.apply_verification_outcome()
        exactly — the write-back half of CompleteManualReview. Only
        valid from PENDING; expiry (expires_at) is entirely untouched."""
        document = self._documents.get_by_id(document_id)
        if document is None:
            raise VehicleDocumentNotFoundError("Document not found.")
        if document.verification_status is not DocumentVerificationStatus.PENDING:
            raise VehicleDocumentAlreadyDecidedError(
                "This document has already been approved or rejected."
            )

        document.verification_status = _VERIFICATION_OUTCOME_TO_DOCUMENT_STATUS[outcome]
        self._documents.save(document)
        return document
