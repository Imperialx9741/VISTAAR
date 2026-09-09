"""FastAPI routes for Safety.

Endpoints (docs/05-api/api-contracts.md §41):

    POST /api/v1/rides/{ride_id}/sos    SOS

Covers the roadmap's "SOS creation"/"SOS location"/"SOS ride context"
tasks in one endpoint — the same "one real endpoint, several roadmap
tasks" shape ride creation itself already has. Acknowledge/Escalate/
Resolve have no documented HTTP endpoint anywhere (ADR-0022 Decision 6)
— see modules/safety/__init__.py.

Composes modules.ride (this is the one place modules/safety/ imports it,
at the router/composition layer only, same shape as every other
cross-module call in this codebase) to establish ride participation:
the caller must be that ride's customer or driver — same IDOR-safe "not
found" response either way as RideNotFoundError already gives.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.identity.dependencies import require_account_type
from modules.identity.domain.entities import Account, AccountType
from modules.ride.dependencies import get_ride_service
from modules.ride.domain.errors import RideDomainError, RideNotFoundError
from modules.ride.service import RideService
from modules.safety.dependencies import get_safety_service
from modules.safety.domain.entities import SafetyIncident
from modules.safety.domain.errors import SafetyDomainError
from modules.safety.schemas import SosRequest
from modules.safety.service import SafetyService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.outbox import OutboxStore, new_envelope

router = APIRouter(tags=["safety"])

_require_customer_or_driver = require_account_type(
    AccountType.CUSTOMER, AccountType.DRIVER
)


def _incident_data(incident: SafetyIncident) -> dict[str, object]:
    return {
        "incident_id": str(incident.id),
        "status": incident.status.value,
    }


@router.post("/api/v1/rides/{ride_id}/sos")
async def trigger_sos(
    ride_id: uuid.UUID,
    body: SosRequest,
    account: Annotated[Account, Depends(_require_customer_or_driver)],
    db: Annotated[DbSession, Depends(get_db)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    safety_service: Annotated[SafetyService, Depends(get_safety_service)],
) -> JSONResponse:
    request_id = new_request_id()
    now = datetime.now(UTC)
    try:
        ride = ride_service.get_ride(ride_id=ride_id)
        if ride is None or account.id not in (ride.customer_id, ride.driver_id):
            # Same "not found or not owned" IDOR-protection pattern
            # used throughout this codebase.
            raise RideNotFoundError("Ride not found.")

        incident = safety_service.trigger_sos(
            ride_id=ride.id,
            reporter_id=account.id,
            incident_type=body.incident_type,
            latitude=body.latitude,
            longitude=body.longitude,
            now=now,
        )
    except (RideDomainError, SafetyDomainError) as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    # event-contracts.md §21.1 — exact documented payload shape.
    assert incident.location is not None  # always set by trigger_sos()
    OutboxStore(db).append(
        new_envelope(
            event_type="safety.sos_triggered",
            producer="safety-service",
            aggregate_type="incident",
            aggregate_id=incident.id,
            data={
                "incident_id": str(incident.id),
                "ride_id": str(ride.id),
                "reporter_id": str(account.id),
                "location": {
                    "latitude": incident.location.latitude,
                    "longitude": incident.location.longitude,
                },
                "triggered_at": now.isoformat(),
            },
            now=now,
        )
    )

    return JSONResponse(
        status_code=201,
        content=success_envelope(_incident_data(incident), request_id=request_id),
    )
