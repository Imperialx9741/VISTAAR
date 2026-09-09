"""FastAPI routes for Support.

Endpoints (docs/05-api/api-contracts.md §44):

    POST /api/v1/support/cases              Create Support Case
    GET  /api/v1/support/cases              List My Support Cases (added 2026-09-04)
    GET  /api/v1/support/cases/{case_id}    Get Support Case

Assign/Resolve/PostMessage have no documented HTTP endpoint anywhere
(ADR-0022 Decision 6) — see modules/support/__init__.py. AI Support
(§45, POST /api/v1/support/ai/message) is BLOCKED (ADR-0022 Decision 4)
— no router for it exists here or anywhere.

Composes modules.ride (this is the one place modules/support/ imports
it, at the router/composition layer only) when a request supplies
ride_id — the caller must be that ride's customer or driver, same
IDOR-safe check modules/safety/router.py already established.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import get_db
from core.redis import get_redis
from modules.identity.dependencies import require_account_type
from modules.identity.domain.entities import Account, AccountType
from modules.ride.dependencies import get_ride_service
from modules.ride.domain.errors import RideDomainError, RideNotFoundError
from modules.ride.service import RideService
from modules.support.dependencies import get_support_service
from modules.support.domain.entities import (
    CaseStatus,
    SenderType,
    SupportCase,
    SupportMessage,
)
from modules.support.domain.errors import SupportCaseNotFoundError, SupportDomainError
from modules.support.schemas import CreateSupportCaseBody
from modules.support.service import SupportService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.outbox import OutboxStore, new_envelope
from shared.pagination import PageParams, pagination_envelope
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key

router = APIRouter(prefix="/api/v1/support", tags=["support"])

_require_customer_or_driver = require_account_type(
    AccountType.CUSTOMER, AccountType.DRIVER
)
_require_customer_driver_or_admin = require_account_type(
    AccountType.CUSTOMER, AccountType.DRIVER, AccountType.ADMIN
)

# api-contracts.md §44's request has no explicit sender-role field — the
# caller's own authenticated account_type is what determines it (never
# client-chosen), same "system-derived, not user-supplied" treatment
# every actor_type/sender_type field in this codebase already gets.
_ACCOUNT_TYPE_TO_SENDER_TYPE = {
    AccountType.CUSTOMER: SenderType.CUSTOMER,
    AccountType.DRIVER: SenderType.DRIVER,
}

# Derived from the enum, not hand-maintained — automatically stays
# correct if CaseStatus ever gains/loses a value (same pattern
# modules/admin/router.py's _VALID_PENALTY_STATUSES already uses).
_VALID_CASE_STATUSES = frozenset(status.value for status in CaseStatus)


def _case_data(case: SupportCase) -> dict[str, object]:
    return {
        "case_id": str(case.id),
        "ride_id": str(case.ride_id) if case.ride_id is not None else None,
        "category": case.category,
        "priority": case.priority,
        "status": case.status.value,
        "assigned_admin_id": (
            str(case.assigned_admin_id) if case.assigned_admin_id is not None else None
        ),
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


def _message_data(message: SupportMessage) -> dict[str, object]:
    return {
        "sender_type": message.sender_type.value,
        "sender_id": str(message.sender_id) if message.sender_id is not None else None,
        "message": message.message,
        "created_at": message.created_at.isoformat(),
    }


@router.post("/cases")
async def create_support_case(
    body: CreateSupportCaseBody,
    account: Annotated[Account, Depends(_require_customer_or_driver)],
    db: Annotated[DbSession, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    ride_service: Annotated[RideService, Depends(get_ride_service)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
) -> JSONResponse:
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="support_message", identity=str(account.id)),
            limit=settings.RATE_LIMIT_SUPPORT_MESSAGE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)
    try:
        if body.ride_id is not None:
            ride = ride_service.get_ride(ride_id=body.ride_id)
            if ride is None or account.id not in (ride.customer_id, ride.driver_id):
                raise RideNotFoundError("Ride not found.")

        case, _first_message = support_service.create_case(
            user_id=account.id,
            ride_id=body.ride_id,
            category=body.category,
            sender_type=_ACCOUNT_TYPE_TO_SENDER_TYPE[account.account_type],
            message=body.message,
            now=now,
        )
    except (RideDomainError, SupportDomainError) as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    # event-contracts.md §23 — exact documented payload shape.
    OutboxStore(db).append(
        new_envelope(
            event_type="support.case_created",
            producer="support-service",
            aggregate_type="support_case",
            aggregate_id=case.id,
            data={
                "case_id": str(case.id),
                "user_id": str(account.id),
                "category": case.category,
                "priority": case.priority,
            },
            now=now,
        )
    )

    return JSONResponse(
        status_code=201,
        content=success_envelope(_case_data(case), request_id=request_id),
    )


@router.get("/cases")
async def list_my_support_cases(
    account: Annotated[Account, Depends(_require_customer_or_driver)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    """List My Support Cases (api-contracts.md §44, added 2026-09-04) —
    the previously-missing self-service list endpoint: every case the
    caller filed, newest first, own-cases-only (never another user's —
    modules.support.service.SupportService.list_cases_for_user() is
    always scoped by the caller's own account.id, not a client-supplied
    id). Same pagination shape (shared/pagination.py, api-contracts.md
    §50) and optional single-field filter convention `GET /drivers/me/
    wallet/transactions` (modules/wallet/router.py) already established
    for a self-service list — `status` here plays the same role
    `type` does there."""
    request_id = new_request_id()

    if status is not None and status not in _VALID_CASE_STATUSES:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "VALIDATION_FAILED",
                f"Unknown status: {status!r}.",
                request_id=request_id,
            ),
        )

    params = PageParams.clamp(
        page=page, page_size=page_size, max_page_size=settings.MAX_PAGE_SIZE
    )
    cases, total = support_service.list_cases_for_user(
        user_id=account.id, status=status, offset=params.offset, limit=params.page_size
    )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_case_data(case) for case in cases], params=params, total=total
            ),
            request_id=request_id,
        ),
    )


@router.get("/cases/{case_id}")
async def get_support_case(
    case_id: uuid.UUID,
    account: Annotated[Account, Depends(_require_customer_driver_or_admin)],
    support_service: Annotated[SupportService, Depends(get_support_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        case, messages = support_service.get_case_with_messages(case_id=case_id)
        if account.account_type is not AccountType.ADMIN and case.user_id != account.id:
            # Same "not found or not owned" IDOR-protection pattern used
            # throughout this codebase — an admin may view any case.
            raise SupportCaseNotFoundError("Support case not found.")
    except SupportDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    data = _case_data(case)
    data["messages"] = [_message_data(m) for m in messages]
    return JSONResponse(
        status_code=200,
        content=success_envelope(data, request_id=request_id),
    )
