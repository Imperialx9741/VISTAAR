"""FastAPI routes for Driver.

Endpoints (docs/05-api/api-contracts.md §9, §10):

    GET   /api/v1/drivers/me
    PATCH /api/v1/drivers/me
    POST  /api/v1/drivers/me/documents   (Phase 2 / Task 2.5, extended Task 2.6)
    GET   /api/v1/drivers/me/documents   (ADR-0072, 2026-09-04)
    GET   /api/v1/drivers/me/strikes     (ADR-0073, 2026-09-04)
    POST  /api/v1/drivers/me/online      (Phase 2 / Task 2.7B)
    POST  /api/v1/drivers/me/offline     (Phase 2 / Task 2.7B)
    POST  /api/v1/drivers/me/uploads     (ADR-0031) — returns a presigned S3
                                          upload URL; the resulting URI is
                                          then supplied to the two endpoints
                                          above as evidence_uri/
                                          profile_photo_uri, both unchanged

Vehicle-document endpoints (POST/GET .../vehicles/{vehicle_id}/documents)
are implemented in modules/vehicle/router.py, ADR-0072 — same task,
mirrored shape, kept in that module since it composes VehicleDocumentService
directly.

Phase 2 / Task 2.6: submitting a document with an evidence_uri also
creates a verification.cases row (SubmitEvidence), composed here at the
router layer with modules.verification's own service — same
API-layer-composition pattern modules/vehicle/router.py already uses for
driver+vehicle. See modules/verification/__init__.py and ADR-0008 items 1
and 9 for why this is conditional on evidence_uri being present.

Go Online (Phase 2 / Task 2.7B) composes driver+vehicle the same way:
DriverService.go_online() takes vehicle eligibility as plain,
pre-computed values (never importing modules.vehicle — see
modules/driver/__init__.py), so this router fetches the driver's ACTIVE
vehicle (if any) and both driver's and vehicle's required-document
validity here, before calling go_online().

Go Offline (Admin Web Dashboard's "Online drivers" widget, fixed here):
composes modules.matching's shared/geo.py the same one-directional way
modules/matching/router.py's own POST .../location already does —
DriverService.go_offline() itself stays Postgres-only (domain-design.md
§10.2 assigns the geo index to Matching, not Driver), so the Redis
cleanup is composed here at the router layer, after the Postgres
transition succeeds. Previously this endpoint did no such composition at
all — shared/geo.py's remove_driver_location() existed, fully written,
but nothing ever called it, so a driver's driver:online:{id} Redis hash
(and their geo:drivers:{category} entry) outlived every session
indefinitely, the reason the Dashboard's "Online drivers" figure stayed
NEEDS SCOPING (admin-web-implementation-plan.md §3) rather than a real
count. The Redis cleanup is best-effort, not authoritative — a RedisError
here is logged and swallowed, never fails the response, matching
shared/geo.py's own stated philosophy that a stale Redis entry can only
ever waste a wasted eligibility re-check against Postgres, never produce
an incorrect offer.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.config import settings
from core.redis import get_redis
from modules.driver.dependencies import (
    get_driver_document_service,
    get_driver_service,
    get_object_storage,
)
from modules.driver.domain.entities import Driver, DriverDocument
from modules.driver.domain.errors import DriverDomainError
from modules.driver.domain.required_documents import (
    missing_or_invalid_required_documents,
)
from modules.driver.schemas import (
    RequestUploadUrlBody,
    SubmitDriverDocumentBody,
    UpdateDriverProfileBody,
)
from modules.driver.service import DriverDocumentService, DriverService, ProfileUpdate
from modules.identity.dependencies import require_driver
from modules.identity.domain.entities import Account
from modules.penalty.dependencies import get_penalty_service
from modules.penalty.domain.entities import Strike
from modules.penalty.service import PenaltyService
from modules.vehicle.dependencies import (
    get_vehicle_document_service,
    get_vehicle_service,
)
from modules.vehicle.domain.entities import (
    VehicleOperationalStatus,
    matching_category_key,
)
from modules.vehicle.domain.errors import VehicleDomainError
from modules.vehicle.domain.required_documents import (
    missing_or_invalid_required_documents as vehicle_missing_or_invalid_docs,
)
from modules.vehicle.service import VehicleDocumentService, VehicleService
from modules.verification.dependencies import get_verification_service
from modules.verification.domain.entities import VerificationType
from modules.verification.domain.errors import VerificationDomainError
from modules.verification.service import VerificationService
from shared import geo
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.pagination import PageParams, pagination_envelope
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key
from shared.storage import ObjectStorage, UnsupportedContentTypeError

router = APIRouter(prefix="/api/v1/drivers", tags=["drivers"])
logger = logging.getLogger("vistaar.driver")


def _domain_error_response(
    exc: DriverDomainError | VehicleDomainError, request_id: str
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for_error_code(exc.code),
        content=error_envelope(exc.code, exc.message, request_id=request_id),
    )


def _profile_data(account: Account, driver: Driver) -> dict[str, object]:
    return {
        "driver_id": str(driver.id),
        "phone": account.phone,
        "full_name": driver.full_name,
        "profile_photo_uri": driver.profile_photo_uri,
        "verification_status": driver.verification_status.value,
        "operational_status": driver.operational_status.value,
        "strikes": driver.strikes,
        "created_at": driver.created_at.isoformat(),
        "updated_at": driver.updated_at.isoformat(),
    }


@router.get("/me")
async def get_my_profile(
    account: Annotated[Account, Depends(require_driver)],
    service: Annotated[DriverService, Depends(get_driver_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        driver = service.get_profile(account_id=account.id)
    except DriverDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(_profile_data(account, driver), request_id=request_id),
    )


@router.post("/me/uploads")
async def request_upload_url(
    body: RequestUploadUrlBody,
    account: Annotated[Account, Depends(require_driver)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> JSONResponse:
    """ADR-0031 (2026-08-25); presigned POST since 2026-09-03 (owner
    decision — see shared/storage.py's own docstring). Driver-only.
    Returns a short-lived presigned S3 POST target (a URL plus form
    fields, not a single PUT URL) — the client POSTs the file directly
    to S3 as multipart form data (the actual file must be the LAST
    field, S3's own requirement), then supplies the returned `uri` as
    `evidence_uri` (POST .../documents) or `profile_photo_uri`
    (PATCH /me), neither of which changes shape. Not tied to
    `account.id` in the returned URL/key beyond authorization — see
    shared/storage.py for why the object key itself is randomized
    rather than derived from the driver.

    Also this app's "Evidence uploads" rate-limit category
    (security.md §20) — the presigned-URL request is the real point to
    gate, not document-metadata submission afterward, since generating
    presigned S3 URLs at unlimited volume is the actual abuse surface."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="evidence_upload", identity=str(account.id)),
            limit=settings.RATE_LIMIT_EVIDENCE_UPLOAD_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    try:
        target = storage.create_upload_url(content_type=body.content_type)
    except UnsupportedContentTypeError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "upload_url": target.upload_url,
                "upload_fields": target.upload_fields,
                "uri": target.object_uri,
                "expires_at": target.expires_at.isoformat(),
            },
            request_id=request_id,
        ),
    )


@router.post("/me/online")
async def go_online(
    account: Annotated[Account, Depends(require_driver)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    driver_document_service: Annotated[
        DriverDocumentService, Depends(get_driver_document_service)
    ],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    vehicle_document_service: Annotated[
        VehicleDocumentService, Depends(get_vehicle_document_service)
    ],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        now = datetime.now(UTC)

        driver_documents = driver_document_service.list_documents(driver_id=account.id)
        invalid_required_driver_documents = bool(
            missing_or_invalid_required_documents(driver_documents, now=now)
        )

        # BR-122: at most one of this driver's vehicles is ever ACTIVE —
        # no need to disambiguate multiple candidates.
        vehicles = vehicle_service.list_vehicles(driver_id=account.id)
        active_vehicle = next(
            (
                v
                for v in vehicles
                if v.operational_status is VehicleOperationalStatus.ACTIVE
            ),
            None,
        )
        if active_vehicle is not None:
            vehicle_documents = vehicle_document_service.list_documents(
                vehicle_id=active_vehicle.id
            )
            invalid_required_vehicle_documents = bool(
                vehicle_missing_or_invalid_docs(vehicle_documents, now=now)
            )
        else:
            # No active vehicle at all — go_online() rejects this via
            # NoEligibleVehicleError before this flag is ever consulted.
            invalid_required_vehicle_documents = False

        driver = driver_service.go_online(
            account_id=account.id,
            invalid_required_driver_documents=invalid_required_driver_documents,
            vehicle_verification_status=(
                active_vehicle.verification_status.value
                if active_vehicle is not None
                else None
            ),
            vehicle_operational_status=(
                active_vehicle.operational_status.value
                if active_vehicle is not None
                else None
            ),
            invalid_required_vehicle_documents=invalid_required_vehicle_documents,
        )
    except (DriverDomainError, VehicleDomainError) as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "status": driver.operational_status.value,
                "vehicle_id": (
                    str(active_vehicle.id) if active_vehicle is not None else None
                ),
            },
            request_id=request_id,
        ),
    )


@router.post("/me/offline")
async def go_offline(
    account: Annotated[Account, Depends(require_driver)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    vehicle_service: Annotated[VehicleService, Depends(get_vehicle_service)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        driver = driver_service.go_offline(account_id=account.id)
    except DriverDomainError as exc:
        return _domain_error_response(exc, request_id)

    # Best-effort Redis cleanup — see this module's docstring. The
    # driver's ACTIVE vehicle (if any) determines which geo:drivers:
    # {category} key their location was last written under; if they
    # somehow have none (shouldn't happen — go_online() requires one),
    # there's nothing to remove, not an error.
    active_vehicle = next(
        (
            v
            for v in vehicle_service.list_vehicles(driver_id=account.id)
            if v.operational_status is VehicleOperationalStatus.ACTIVE
        ),
        None,
    )
    if active_vehicle is not None:
        try:
            await geo.remove_driver_location(
                redis_client,
                driver_id=account.id,
                category=matching_category_key(
                    active_vehicle.category, active_vehicle.cab_tier
                ),
            )
        except RedisError:
            logger.warning(
                "Redis cleanup failed on go_offline for driver %s — "
                "driver:online/geo:drivers entries may be stale until "
                "the next successful cleanup.",
                account.id,
            )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"status": driver.operational_status.value}, request_id=request_id
        ),
    )


def _document_data(
    document: DriverDocument, *, verification_case_id: str | None
) -> dict[str, object]:
    return {
        "document_id": str(document.id),
        "document_type": document.document_type,
        "document_number": document.document_number,
        "evidence_uri": document.evidence_uri,
        "verification_status": document.verification_status.value,
        "expires_at": document.expires_at.isoformat() if document.expires_at else None,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "verification_case_id": verification_case_id,
    }


@router.post("/me/documents")
async def submit_my_document(
    body: SubmitDriverDocumentBody,
    account: Annotated[Account, Depends(require_driver)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    document_service: Annotated[
        DriverDocumentService, Depends(get_driver_document_service)
    ],
    verification_service: Annotated[
        VerificationService, Depends(get_verification_service)
    ],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        # Establishes the driver.drivers row exists — required by
        # driver.documents.driver_id's foreign key (database-design.md
        # §7.2), same precondition-check pattern as
        # modules/vehicle/router.py::add_my_vehicle().
        driver_service.get_profile(account_id=account.id)

        document = document_service.submit_document(
            driver_id=account.id,
            document_type=body.document_type,
            document_number=body.document_number,
            evidence_uri=body.evidence_uri,
            expires_at=body.expires_at,
        )

        # ADR-0008 items 1 and 9: a verification case is only created
        # when there is actual evidence to verify. Task 2.5's
        # evidence_uri stays optional (unchanged); no placeholder value
        # is ever invented to force a case into existence —
        # verification.evidence.evidence_uri is NOT NULL by design.
        verification_case_id: str | None = None
        if document.evidence_uri is not None:
            case = verification_service.submit_evidence(
                subject_type="DRIVER_DOCUMENT",
                subject_id=document.id,
                verification_type=VerificationType.DRIVER_DOCUMENT,
                evidence_uri=document.evidence_uri,
            )
            verification_case_id = str(case.id)
    except (DriverDomainError, VerificationDomainError) as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            _document_data(document, verification_case_id=verification_case_id),
            request_id=request_id,
        ),
    )


@router.get("/me/documents")
async def list_my_documents(
    account: Annotated[Account, Depends(require_driver)],
    document_service: Annotated[
        DriverDocumentService, Depends(get_driver_document_service)
    ],
) -> JSONResponse:
    """List My Driver Documents (ADR-0072, 2026-09-04) — the previously-
    missing GET this codebase's own DriverDocumentService.list_documents()
    already supported at the service layer (ADR-0007 §5). Newest first,
    same shape as the POST above's own response — `verification_case_id`
    is always null here (a list read has no single submission event to
    report one against)."""
    request_id = new_request_id()
    documents = sorted(
        document_service.list_documents(driver_id=account.id),
        key=lambda d: d.created_at,
        reverse=True,
    )
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "documents": [
                    _document_data(d, verification_case_id=None) for d in documents
                ]
            },
            request_id=request_id,
        ),
    )


def _strike_data(strike: Strike) -> dict[str, object]:
    return {
        "strike_id": str(strike.id),
        "driver_id": str(strike.driver_id),
        "ride_id": str(strike.ride_id) if strike.ride_id is not None else None,
        "reason": strike.reason,
        "created_at": strike.created_at.isoformat(),
    }


@router.get("/me/strikes")
async def list_my_strikes(
    account: Annotated[Account, Depends(require_driver)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    penalty_service: Annotated[PenaltyService, Depends(get_penalty_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List My Strikes (ADR-0073, 2026-09-04) — the previously admin-only
    `PenaltyService.list_strikes_for_driver()` (api-contracts.md §46.18),
    scoped to the caller instead of an admin-supplied driver_id. Same
    item shape as the admin route; newest first."""
    request_id = new_request_id()
    try:
        # Establishes the driver.drivers row exists — same precondition-
        # check pattern modules/wallet/router.py's own
        # list_my_wallet_transactions() already uses.
        driver_service.get_profile(account_id=account.id)
    except DriverDomainError as exc:
        return _domain_error_response(exc, request_id)

    params = PageParams.clamp(
        page=page, page_size=page_size, max_page_size=settings.MAX_PAGE_SIZE
    )
    strikes, total = penalty_service.list_strikes_for_driver(
        account.id, offset=params.offset, limit=params.page_size
    )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_strike_data(s) for s in strikes], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.patch("/me")
async def update_my_profile(
    body: UpdateDriverProfileBody,
    account: Annotated[Account, Depends(require_driver)],
    service: Annotated[DriverService, Depends(get_driver_service)],
) -> JSONResponse:
    request_id = new_request_id()
    update: ProfileUpdate = body.model_dump(exclude_unset=True)  # type: ignore[assignment]

    try:
        driver = service.update_profile(account_id=account.id, update=update)
    except DriverDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(_profile_data(account, driver), request_id=request_id),
    )
