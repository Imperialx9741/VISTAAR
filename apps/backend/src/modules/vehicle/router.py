"""FastAPI routes for Vehicle.

Endpoints (docs/05-api/api-contracts.md §11):

    POST   /api/v1/drivers/me/vehicles
    GET    /api/v1/drivers/me/vehicles
    GET    /api/v1/drivers/me/vehicles/{vehicle_id}
    PATCH  /api/v1/drivers/me/vehicles/{vehicle_id}
    POST   /api/v1/drivers/me/vehicles/{vehicle_id}/activate
    POST   /api/v1/drivers/me/vehicles/{vehicle_id}/deactivate
    POST   /api/v1/drivers/me/vehicles/{vehicle_id}/documents  (ADR-0072)
    GET    /api/v1/drivers/me/vehicles/{vehicle_id}/documents  (ADR-0072)

GET-single/PATCH were added by the Vehicle Lifecycle Decision & API
Contract Clarification follow-up task (Task 2.4 originally omitted them
as undocumented). PATCH accepts only make/model — see schemas.py's
UpdateVehicleBody. The two document endpoints close the equivalent gap
ADR-0007 §5 item B flagged for vehicle documents specifically — see
ADR-0072 for the full account; they mirror modules/driver/router.py's
own driver-document POST/GET field-for-field.

Add/Activate/Deactivate all first fetch the caller's own Driver profile
(via modules.driver's existing service, not a new query) — Add needs it
because vehicle.vehicles.driver_id has a foreign key to driver.drivers.id
(database-design.md §8.1), and Activate/Deactivate need
driver.operational_status to enforce the documented offline-only rule.
This composes the two modules only at the API layer; neither module's
service/domain code imports the other's (see modules/vehicle/__init__.py).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from modules.driver.dependencies import get_driver_service
from modules.driver.domain.errors import DriverDomainError
from modules.driver.service import DriverService
from modules.identity.dependencies import require_driver
from modules.identity.domain.entities import Account
from modules.vehicle.dependencies import (
    get_vehicle_document_service,
    get_vehicle_service,
)
from modules.vehicle.domain.entities import Vehicle, VehicleDocument
from modules.vehicle.domain.errors import VehicleDomainError
from modules.vehicle.schemas import (
    AddVehicleBody,
    SubmitVehicleDocumentBody,
    UpdateVehicleBody,
)
from modules.vehicle.service import (
    VehicleDocumentService,
    VehicleService,
    VehicleUpdate,
)
from modules.verification.dependencies import get_verification_service
from modules.verification.domain.entities import VerificationType
from modules.verification.domain.errors import VerificationDomainError
from modules.verification.service import VerificationService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)

router = APIRouter(prefix="/api/v1/drivers/me/vehicles", tags=["vehicles"])


def _vehicle_data(vehicle: Vehicle) -> dict[str, object]:
    return {
        "vehicle_id": str(vehicle.id),
        "category": vehicle.category.value,
        "cab_tier": vehicle.cab_tier.value if vehicle.cab_tier is not None else None,
        "registration_number": vehicle.registration_number,
        "make": vehicle.make,
        "model": vehicle.model,
        "verification_status": vehicle.verification_status.value,
        "operational_status": vehicle.operational_status.value,
        "created_at": vehicle.created_at.isoformat(),
        "updated_at": vehicle.updated_at.isoformat(),
    }


def _vehicle_document_data(
    document: VehicleDocument, *, verification_case_id: str | None
) -> dict[str, object]:
    """Mirrors modules/driver/router.py's own _document_data() — the
    one real asymmetry (no updated_at) matches VehicleDocument's own
    documented schema exactly (database-design.md §8.2), not an
    oversight (see that entity's own docstring)."""
    return {
        "document_id": str(document.id),
        "document_type": document.document_type,
        "document_number": document.document_number,
        "evidence_uri": document.evidence_uri,
        "verification_status": document.verification_status.value,
        "expires_at": document.expires_at.isoformat() if document.expires_at else None,
        "created_at": document.created_at.isoformat(),
        "verification_case_id": verification_case_id,
    }


def _domain_error_response(
    exc: DriverDomainError | VehicleDomainError | VerificationDomainError,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for_error_code(exc.code),
        content=error_envelope(exc.code, exc.message, request_id=request_id),
    )


@router.get("")
async def list_my_vehicles(
    account: Annotated[Account, Depends(require_driver)],
    service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> JSONResponse:
    request_id = new_request_id()
    vehicles = service.list_vehicles(driver_id=account.id)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"vehicles": [_vehicle_data(v) for v in vehicles]}, request_id=request_id
        ),
    )


@router.post("")
async def add_my_vehicle(
    body: AddVehicleBody,
    account: Annotated[Account, Depends(require_driver)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        # Establishes the driver.drivers row exists — required by
        # vehicle.vehicles.driver_id's foreign key (database-design.md
        # §8.1). Raises DriverProfileNotFoundError (RESOURCE_NOT_FOUND)
        # otherwise, per ADR-0004's documented driver-profile-creation
        # flow (PATCH /api/v1/drivers/me first).
        driver_service.get_profile(account_id=account.id)

        vehicle = vehicle_service.add_vehicle(
            driver_id=account.id,
            category=body.category,
            cab_tier=body.cab_tier,
            registration_number=body.registration_number,
            make=body.make,
            model=body.model,
        )
    except (DriverDomainError, VehicleDomainError) as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


@router.get("/{vehicle_id}")
async def get_my_vehicle(
    vehicle_id: uuid.UUID,
    account: Annotated[Account, Depends(require_driver)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        vehicle = vehicle_service.get_vehicle(
            driver_id=account.id, vehicle_id=vehicle_id
        )
    except VehicleDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


@router.patch("/{vehicle_id}")
async def update_my_vehicle(
    vehicle_id: uuid.UUID,
    body: UpdateVehicleBody,
    account: Annotated[Account, Depends(require_driver)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
) -> JSONResponse:
    request_id = new_request_id()
    update: VehicleUpdate = body.model_dump(exclude_unset=True)  # type: ignore[assignment]
    try:
        vehicle = vehicle_service.update_vehicle(
            driver_id=account.id, vehicle_id=vehicle_id, update=update
        )
    except VehicleDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


@router.post("/{vehicle_id}/activate")
async def activate_my_vehicle(
    vehicle_id: uuid.UUID,
    account: Annotated[Account, Depends(require_driver)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        driver = driver_service.get_profile(account_id=account.id)
        vehicle = vehicle_service.activate_vehicle(
            driver_id=account.id,
            vehicle_id=vehicle_id,
            driver_operational_status=driver.operational_status.value,
        )
    except (DriverDomainError, VehicleDomainError) as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


@router.post("/{vehicle_id}/deactivate")
async def deactivate_my_vehicle(
    vehicle_id: uuid.UUID,
    account: Annotated[Account, Depends(require_driver)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        driver = driver_service.get_profile(account_id=account.id)
        vehicle = vehicle_service.deactivate_vehicle(
            driver_id=account.id,
            vehicle_id=vehicle_id,
            driver_operational_status=driver.operational_status.value,
        )
    except (DriverDomainError, VehicleDomainError) as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(_vehicle_data(vehicle), request_id=request_id),
    )


@router.post("/{vehicle_id}/documents")
async def submit_my_vehicle_document(
    vehicle_id: uuid.UUID,
    body: SubmitVehicleDocumentBody,
    account: Annotated[Account, Depends(require_driver)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    document_service: Annotated[
        VehicleDocumentService, Depends(get_vehicle_document_service)
    ],
    verification_service: Annotated[
        VerificationService, Depends(get_verification_service)
    ],
) -> JSONResponse:
    """Submit Vehicle Document (ADR-0072, 2026-09-04) — mirrors
    modules/driver/router.py's own submit_my_document() field-for-field,
    including the same conditional verification.cases composition when
    evidence_uri is supplied."""
    request_id = new_request_id()
    try:
        # Ownership check — get_vehicle() already raises
        # VehicleNotFoundError (RESOURCE_NOT_FOUND) for another driver's
        # vehicle_id, the same IDOR-safe pattern get_my_vehicle() uses.
        vehicle_service.get_vehicle(driver_id=account.id, vehicle_id=vehicle_id)

        document = document_service.submit_document(
            vehicle_id=vehicle_id,
            document_type=body.document_type,
            document_number=body.document_number,
            evidence_uri=body.evidence_uri,
            expires_at=body.expires_at,
        )

        verification_case_id: str | None = None
        if document.evidence_uri is not None:
            case = verification_service.submit_evidence(
                subject_type="VEHICLE_DOCUMENT",
                subject_id=document.id,
                verification_type=VerificationType.VEHICLE_DOCUMENT,
                evidence_uri=document.evidence_uri,
            )
            verification_case_id = str(case.id)
    except (VehicleDomainError, VerificationDomainError) as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            _vehicle_document_data(document, verification_case_id=verification_case_id),
            request_id=request_id,
        ),
    )


@router.get("/{vehicle_id}/documents")
async def list_my_vehicle_documents(
    vehicle_id: uuid.UUID,
    account: Annotated[Account, Depends(require_driver)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    document_service: Annotated[
        VehicleDocumentService, Depends(get_vehicle_document_service)
    ],
) -> JSONResponse:
    """List My Vehicle Documents (ADR-0072, 2026-09-04). Newest first,
    same ownership check as the POST above."""
    request_id = new_request_id()
    try:
        vehicle_service.get_vehicle(driver_id=account.id, vehicle_id=vehicle_id)
    except VehicleDomainError as exc:
        return _domain_error_response(exc, request_id)

    documents = sorted(
        document_service.list_documents(vehicle_id=vehicle_id),
        key=lambda d: d.created_at,
        reverse=True,
    )
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "documents": [
                    _vehicle_document_data(d, verification_case_id=None)
                    for d in documents
                ]
            },
            request_id=request_id,
        ),
    )
