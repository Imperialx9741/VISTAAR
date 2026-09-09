"""FastAPI routes for Notification (ADR-0052).

Endpoints:

    POST   /api/v1/notifications/me/devices          Register/refresh a device
    DELETE /api/v1/notifications/me/devices/{token}   Unregister a device

The first HTTP router this module has ever had — every prior
notification feature (ADR-0034/ADR-0038/ADR-0044) was composed directly
into other modules' routers or reached only by Admin (api-contracts.md
§46.10/§46.13), with no customer/driver-facing surface documented
anywhere. Reachable by any authenticated account (get_current_account,
no account-type restriction) — ADR-0052 Decision 1: device registration
is a generic capability, not tied to one account type.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from modules.identity.dependencies import get_current_account
from modules.identity.domain.entities import Account
from modules.notification.dependencies import get_notification_service
from modules.notification.domain.entities import DeviceToken
from modules.notification.domain.errors import NotificationDomainError
from modules.notification.schemas import RegisterDeviceBody
from modules.notification.service import NotificationService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _device_data(device: DeviceToken) -> dict[str, object]:
    return {
        "device_id": str(device.id),
        "platform": device.platform.value,
        "token": device.token,
        "created_at": device.created_at.isoformat(),
        "updated_at": device.updated_at.isoformat(),
    }


@router.post("/me/devices")
async def register_device(
    body: RegisterDeviceBody,
    account: Annotated[Account, Depends(get_current_account)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        device = service.register_device(
            user_id=account.id,
            platform=body.platform,
            token=body.token,
            now=datetime.now(UTC),
        )
    except NotificationDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=201,
        content=success_envelope(_device_data(device), request_id=request_id),
    )


@router.delete("/me/devices/{token}")
async def unregister_device(
    token: str,
    account: Annotated[Account, Depends(get_current_account)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> JSONResponse:
    """No-op (200, not 404) if this account never registered `token` —
    same idempotent-delete convention DeviceTokenRepository.delete()'s
    own docstring documents."""
    request_id = new_request_id()
    service.unregister_device(user_id=account.id, token=token)

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": "UNREGISTERED"}, request_id=request_id),
    )
