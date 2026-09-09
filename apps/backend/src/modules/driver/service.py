"""Application service (use cases) for Driver.

Design note — why this differs from modules/customer/service.py's
auto-provision-on-any-access pattern:

driver.drivers.full_name is NOT NULL (database-design.md §7.1), unlike
customer.customers.full_name (nullable). identity.accounts has no name
field to default from. So a driver.drivers row cannot be silently
created with a placeholder name the moment an authenticated DRIVER
account is first seen — someone has to actually supply a name.

This service therefore does NOT auto-provision on get_profile(): if no
row exists yet, get_profile() raises DriverProfileNotFoundError
(RESOURCE_NOT_FOUND). update_profile() DOES create the row on first call,
but only if full_name is supplied in that first call; if it is not,
FullNameRequiredForCreationError (VALIDATION_FAILED) is raised rather
than silently creating a half-populated profile.

This interpretation is not spelled out verbatim in api-contracts.md
(which only names the two endpoints without describing create-vs-update
semantics) — it is the necessary consequence of the documented NOT NULL
constraint, not an invented business rule. Formally recorded as an
implementation/API decision (not a business rule) in
docs/14-decisions/ADR-0004-driver-profile-creation-semantics.md.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypedDict

from modules.driver.domain.entities import (
    DocumentVerificationStatus,
    Driver,
    DriverDocument,
    DriverOperationalStatus,
    DriverVerificationStatus,
)
from modules.driver.domain.entities import validate_full_name as _validate_full_name
from modules.driver.domain.entities import (
    validate_profile_photo_uri as _validate_profile_photo_uri,
)
from modules.driver.domain.errors import (
    DriverAlreadySuspendedError,
    DriverDocumentAlreadyDecidedError,
    DriverDocumentNotFoundError,
    DriverNotApprovedError,
    DriverNotOfflineError,
    DriverNotOnlineError,
    DriverNotSuspendedError,
    DriverProfileNotFoundError,
    DriverRequiredDocumentsNotValidError,
    DriverVerificationAlreadyDecidedError,
    FullNameRequiredForCreationError,
    NoEligibleVehicleError,
    VehicleDocumentsNotValidForGoOnlineError,
)
from modules.driver.domain.required_documents import (
    missing_or_invalid_required_documents,
)
from modules.driver.ports import DriverDocumentRepository, DriverRepository
from modules.verification.domain.entities import VerificationOutcome

# CompleteManualReview's outcome maps 1:1 onto DriverDocument's
# verification_status — see modules/verification/service.py's docstring
# for why this mapping happens here (document ownership) rather than in
# modules.verification (subject-agnosticism).
_VERIFICATION_OUTCOME_TO_DOCUMENT_STATUS: dict[
    VerificationOutcome, DocumentVerificationStatus
] = {
    VerificationOutcome.APPROVED: DocumentVerificationStatus.APPROVED,
    VerificationOutcome.REJECTED: DocumentVerificationStatus.REJECTED,
}


class ProfileUpdate(TypedDict, total=False):
    """Only keys actually present are applied — PATCH semantics, same
    convention as modules.customer.service.ProfileUpdate."""

    full_name: str
    profile_photo_uri: str | None


class DriverService:
    def __init__(self, *, drivers: DriverRepository) -> None:
        self._drivers = drivers

    def get_profile(self, *, account_id: uuid.UUID) -> Driver:
        driver = self._drivers.get_by_id(account_id)
        if driver is None:
            raise DriverProfileNotFoundError(
                "No driver profile exists yet. Call "
                "PATCH /api/v1/drivers/me with at least full_name to create one."
            )
        return driver

    def update_profile(self, *, account_id: uuid.UUID, update: ProfileUpdate) -> Driver:
        driver = self._drivers.get_by_id(account_id)

        if driver is None:
            full_name = update.get("full_name")
            if not full_name:
                raise FullNameRequiredForCreationError(
                    "full_name is required to create a driver profile."
                )
            driver = Driver.new(account_id, full_name=full_name, now=datetime.now(UTC))
            driver = self._drivers.create(driver)
            # full_name was already applied via Driver.new(); apply any
            # other supplied fields below, same as an ordinary update.

        if "full_name" in update:
            driver.full_name = _validate_full_name(update["full_name"])
        if "profile_photo_uri" in update:
            driver.profile_photo_uri = _validate_profile_photo_uri(
                update["profile_photo_uri"]
            )

        driver.updated_at = datetime.now(UTC)
        self._drivers.save(driver)
        return driver

    def approve_driver(
        self, *, driver_id: uuid.UUID, documents: list[DriverDocument]
    ) -> Driver:
        """Phase 2 / Task 2.7A (ApproveDriver — domain-design.md §7.4),
        extended in Task 2.6C to enforce business-rules.md BR-123. Only
        ever transitions verification_status PENDING -> APPROVED — never
        touches operational_status (stays OFFLINE) or strikes, matching
        driver.approved's documented payload (event-contracts.md §19.1,
        not published this task) and ADR-0009's explicit "approval does
        not change eligibility" constraint.

        `documents` must be the caller's already-fetched list of this
        driver's documents (via DriverDocumentService.list_documents()) —
        this method does not fetch them itself, same "caller loads,
        service decides" composition already used elsewhere in this
        codebase (e.g. modules.vehicle.service.VehicleService taking
        driver_operational_status as a plain value from its caller).
        Raises DriverRequiredDocumentsNotValidError (BR-123) if any
        required document (modules.driver.domain.required_documents) is
        missing, PENDING, REJECTED, or EXPIRED — checked only after
        confirming the driver itself is still PENDING, so an
        already-decided driver reports that first."""
        driver = self.get_profile(account_id=driver_id)
        if driver.verification_status is not DriverVerificationStatus.PENDING:
            raise DriverVerificationAlreadyDecidedError(
                "This driver has already been approved or rejected."
            )

        invalid = missing_or_invalid_required_documents(
            documents, now=datetime.now(UTC)
        )
        if invalid:
            raise DriverRequiredDocumentsNotValidError(
                "Cannot approve this driver — required document(s) not "
                f"in an approved/valid state: {', '.join(invalid)}."
            )

        driver.verification_status = DriverVerificationStatus.APPROVED
        driver.updated_at = datetime.now(UTC)
        self._drivers.save(driver)
        return driver

    def reject_driver(self, *, driver_id: uuid.UUID, reason: str | None) -> Driver:
        """Phase 2 / Task 2.7A (RejectDriver — domain-design.md §7.4).
        `reason` is not stored on driver.drivers (no such column is
        documented) — the caller (modules/admin/router.py) is
        responsible for recording it in admin.audit_logs.reason. See
        ADR-0009 point A."""
        driver = self.get_profile(account_id=driver_id)
        if driver.verification_status is not DriverVerificationStatus.PENDING:
            raise DriverVerificationAlreadyDecidedError(
                "This driver has already been approved or rejected."
            )
        driver.verification_status = DriverVerificationStatus.REJECTED
        driver.updated_at = datetime.now(UTC)
        self._drivers.save(driver)
        return driver

    def go_online(
        self,
        *,
        account_id: uuid.UUID,
        invalid_required_driver_documents: bool,
        vehicle_verification_status: str | None,
        vehicle_operational_status: str | None,
        invalid_required_vehicle_documents: bool,
    ) -> Driver:
        """Phase 2 / Task 2.7B (GoOnline — domain-design.md §7.4).
        Enforces api-contracts.md §10's documented Go Online preconditions
        in order: driver OFFLINE, driver approved, driver's own required
        documents valid (BR-123), an APPROVED+ACTIVE vehicle exists, and
        that vehicle's required documents valid (BR-123, re-checked here
        since a document can expire after the vehicle was approved).

        This module never imports modules.vehicle (see
        modules/driver/__init__.py) — vehicle_verification_status/
        vehicle_operational_status are therefore taken as plain strings
        (a vehicle enum's .value) rather than modules.vehicle's own
        enums, and invalid_required_vehicle_documents is a pre-computed
        bool rather than a document list this method could inspect
        itself. The caller (modules/driver/router.py) is responsible for
        fetching the driver's ACTIVE vehicle (if any) and its documents
        via modules.vehicle's own services and resolving both — same
        "caller loads, service decides" composition already used by
        approve_driver()/approve_vehicle(), just spanning two modules at
        the router layer instead of one. This method itself makes no
        vehicle-side database call and is pure with respect to that data.

        api-contracts.md §10 also lists "Driver not suspended" as a
        precondition. Phase 03 (ADR-0021) implemented SuspendDriver, so
        SUSPENDED (domain-design.md §7.3) is now a reachable
        operational_status — the generic "must currently be OFFLINE"
        guard below already covers it correctly, both functionally and
        against api-contracts.md §10's own documented error-code mapping
        (INVALID_STATE_TRANSITION for "Go Online, driver not currently
        OFFLINE"). No new branch was needed; this docstring previously
        claimed the precondition "holds by construction" because
        SUSPENDED was unreachable — see ADR-0021 Decision 5.

        Concurrency: get_by_id_for_update() locks this driver's row
        (SELECT ... FOR UPDATE) before any check or write, serializing
        concurrent go_online()/go_offline() calls for the same
        account_id — same reasoning as
        VehicleService.activate_vehicle()'s list_by_driver_for_update()
        (database-design.md §8.1.1, BR-122).
        """
        driver = self._get_profile_for_update(account_id=account_id)

        if driver.operational_status is not DriverOperationalStatus.OFFLINE:
            raise DriverNotOfflineError(
                "Cannot go online — driver is not currently OFFLINE "
                "(already ONLINE, ON_RIDE, SUSPENDED, or INELIGIBLE)."
            )
        if driver.verification_status is not DriverVerificationStatus.APPROVED:
            raise DriverNotApprovedError(
                "Cannot go online — driver has not been approved."
            )
        if invalid_required_driver_documents:
            raise DriverRequiredDocumentsNotValidError(
                "Cannot go online — one or more of the driver's required "
                "documents are not in an approved/valid state."
            )
        if vehicle_verification_status != "APPROVED" or (
            vehicle_operational_status != "ACTIVE"
        ):
            raise NoEligibleVehicleError(
                "Cannot go online — no approved, active vehicle."
            )
        if invalid_required_vehicle_documents:
            raise VehicleDocumentsNotValidForGoOnlineError(
                "Cannot go online — one or more of the active vehicle's "
                "required documents are not in an approved/valid state."
            )

        driver.operational_status = DriverOperationalStatus.ONLINE
        driver.updated_at = datetime.now(UTC)
        self._drivers.save(driver)
        return driver

    def go_offline(self, *, account_id: uuid.UUID) -> Driver:
        """Phase 2 / Task 2.7B (GoOffline — domain-design.md §7.4).
        Only transitions ONLINE -> OFFLINE — see DriverNotOnlineError's
        docstring for why OFFLINE -> OFFLINE and ON_RIDE -> OFFLINE are
        both rejected the same way for now (a documented Phase 3
        dependency, not an unresolved conflict). api-contracts.md §10's
        "A driver cannot go offline while an active ride is in progress"
        and "must first reject or allow [a pending request] to expire"
        rules both reduce to this same guard until a ride/offer model
        exists to give ON_RIDE (or a pending-offer state) a distinct
        error. Concurrency: see go_online()'s docstring — the same locked
        fetch is used here."""
        driver = self._get_profile_for_update(account_id=account_id)

        if driver.operational_status is not DriverOperationalStatus.ONLINE:
            raise DriverNotOnlineError("Cannot go offline — driver is not online.")

        driver.operational_status = DriverOperationalStatus.OFFLINE
        driver.updated_at = datetime.now(UTC)
        self._drivers.save(driver)
        return driver

    def suspend_driver(self, *, driver_id: uuid.UUID, reason: str | None) -> Driver:
        """Phase 03 (SuspendDriver — domain-design.md §7.4, ADR-0021).
        Reachable from any operational_status except SUSPENDED itself
        (ADR-0021 Decision 4) — including ON_RIDE: this does NOT touch
        any in-progress ride.rides row; no source document describes
        force-cancelling an active ride as part of suspension. `reason`
        is not stored on driver.drivers (no such column is documented,
        matching reject_driver()'s identical shape) — a future caller
        would record it in admin.audit_logs.reason, the same way
        modules/admin/router.py already does for reject_driver().

        Concurrency: get_by_id_for_update() locks this driver's row —
        same mechanism as go_online()/go_offline()."""
        driver = self._get_profile_for_update(account_id=driver_id)
        if driver.operational_status is DriverOperationalStatus.SUSPENDED:
            raise DriverAlreadySuspendedError("This driver is already suspended.")

        driver.operational_status = DriverOperationalStatus.SUSPENDED
        driver.updated_at = datetime.now(UTC)
        self._drivers.save(driver)
        return driver

    def reactivate_driver(self, *, driver_id: uuid.UUID) -> Driver:
        """Phase 03 (ReactivateDriver — domain-design.md §7.4,
        ADR-0021). Always lands on OFFLINE, never directly ONLINE —
        mirrors ADR-0009's "approval does not change eligibility"
        precedent (ApproveVehicle/ApproveDriver): the driver must
        explicitly Go Online themselves through the existing, already-
        validated go_online() path, not reappear as immediately
        dispatchable. Only valid from SUSPENDED.

        Concurrency: get_by_id_for_update() locks this driver's row —
        same mechanism as go_online()/go_offline()."""
        driver = self._get_profile_for_update(account_id=driver_id)
        if driver.operational_status is not DriverOperationalStatus.SUSPENDED:
            raise DriverNotSuspendedError("This driver is not currently suspended.")

        driver.operational_status = DriverOperationalStatus.OFFLINE
        driver.updated_at = datetime.now(UTC)
        self._drivers.save(driver)
        return driver

    def _get_profile_for_update(self, *, account_id: uuid.UUID) -> Driver:
        driver = self._drivers.get_by_id_for_update(account_id)
        if driver is None:
            raise DriverProfileNotFoundError(
                "No driver profile exists yet. Call "
                "PATCH /api/v1/drivers/me with at least full_name to create one."
            )
        return driver

    # --- Admin (Admin Web §4.2) ------------------------------------------

    def search_drivers(
        self, *, query: str | None, status: str | None, offset: int, limit: int
    ) -> tuple[list[Driver], int]:
        return self._drivers.search(
            query=query, status=status, offset=offset, limit=limit
        )

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_total_drivers(self) -> int:
        return self._drivers.count_total()

    def count_drivers_by_verification_status(self) -> dict[str, int]:
        return self._drivers.count_by_verification_status()

    def count_drivers_by_operational_status(self) -> dict[str, int]:
        return self._drivers.count_by_operational_status()

    def count_new_drivers_in_range(self, *, since: datetime, until: datetime) -> int:
        return self._drivers.count_created_in_range(since=since, until=until)

    # --- Notification Broadcast (Admin Web §4.12, ADR-0055) -----------

    def list_all_driver_ids(self) -> list[uuid.UUID]:
        """The "All drivers" audience — every driver_id, unpaginated."""
        return self._drivers.list_all_ids()


class DriverDocumentService:
    """Phase 2 / Task 2.5. See ADR-0007 for the two open API-contract
    questions this service's shape follows: no document_type enum, and
    only submit_document() is wired to an HTTP route (router.py) —
    list/get exist here for internal completeness and are covered by
    service-level tests, but have no documented endpoint yet."""

    def __init__(self, *, documents: DriverDocumentRepository) -> None:
        self._documents = documents

    def submit_document(
        self,
        *,
        driver_id: uuid.UUID,
        document_type: str,
        document_number: str | None,
        evidence_uri: str | None,
        expires_at: datetime | None,
    ) -> DriverDocument:
        document = DriverDocument.new(
            driver_id=driver_id,
            document_type=document_type,
            document_number=document_number,
            evidence_uri=evidence_uri,
            expires_at=expires_at,
            now=datetime.now(UTC),
        )
        return self._documents.create(document)

    def list_documents(self, *, driver_id: uuid.UUID) -> list[DriverDocument]:
        return self._documents.list_by_driver(driver_id)

    def get_document(
        self, *, driver_id: uuid.UUID, document_id: uuid.UUID
    ) -> DriverDocument:
        document = self._documents.get_by_id(document_id)
        if document is None or document.driver_id != driver_id:
            # Same "not found or not owned" response either way — see
            # DriverDocumentNotFoundError's docstring.
            raise DriverDocumentNotFoundError("Document not found.")
        return document

    def apply_verification_outcome(
        self, *, document_id: uuid.UUID, outcome: VerificationOutcome
    ) -> DriverDocument:
        """Phase 2 / Task 2.6B. The write-back half of
        CompleteManualReview — see modules/verification/service.py's
        docstring for why this call is separate from, and not triggered
        automatically by, VerificationService.complete_manual_review().
        Only valid from PENDING; keeps expiry (expires_at) entirely
        untouched — verification validity and expiry are deliberately
        kept as separate concerns (no expiry-related logic here)."""
        document = self._documents.get_by_id(document_id)
        if document is None:
            raise DriverDocumentNotFoundError("Document not found.")
        if document.verification_status is not DocumentVerificationStatus.PENDING:
            raise DriverDocumentAlreadyDecidedError(
                "This document has already been approved or rejected."
            )

        document.verification_status = _VERIFICATION_OUTCOME_TO_DOCUMENT_STATUS[outcome]
        document.updated_at = datetime.now(UTC)
        self._documents.save(document)
        return document
