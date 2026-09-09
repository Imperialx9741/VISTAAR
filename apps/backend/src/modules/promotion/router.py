"""FastAPI routes for Promotion.

Endpoints (docs/05-api/api-contracts.md §37, extended by ADR-0041
Decision 2):

    GET  /api/v1/customers/me/promotions           Get Promotions
    POST /api/v1/customers/me/promotions/redeem     Redeem Campaign Code

reserve/consume/restore are all composed into the real ride lifecycle
(ADR-0070, 2026-09-04) — automatically, not via these two endpoints:
`POST /api/v1/rides` (modules/ride/router.py) reserves against the
customer's soonest-expiring ACTIVE entitlement (including one this
module's own Redeem Campaign Code just created) with no client input
needed, `complete_ride()` consumes it, `cancel_ride()`/
`driver_cancel_ride()` restore it. This module's two endpoints only
ever read/create entitlements — see modules/promotion/__init__.py for
the full scope (ADR-0019/ADR-0070).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from core.config import settings
from core.redis import get_redis
from modules.customer.dependencies import get_customer_service
from modules.customer.domain.errors import CustomerDomainError
from modules.customer.service import CustomerService
from modules.identity.dependencies import require_customer
from modules.identity.domain.entities import Account
from modules.promotion.dependencies import get_promotion_service
from modules.promotion.domain.entities import Entitlement
from modules.promotion.domain.errors import PromotionDomainError
from modules.promotion.schemas import RedeemCampaignCodeBody
from modules.promotion.service import PromotionService
from modules.vehicle.domain.entities import VehicleCategory
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key

router = APIRouter(prefix="/api/v1/customers/me/promotions", tags=["promotions"])

_AnyDomainError = (CustomerDomainError, PromotionDomainError)


def _domain_error_response(
    exc: CustomerDomainError | PromotionDomainError, request_id: str
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for_error_code(exc.code),
        content=error_envelope(exc.code, exc.message, request_id=request_id),
    )


def _entitlement_data(entitlement: Entitlement) -> dict[str, object]:
    return {
        "type": entitlement.promotion_type.value,
        "discount_percent": float(entitlement.discount_percent),
        "remaining_uses": entitlement.remaining_uses,
        "expires_at": entitlement.expires_at.isoformat(),
        # ADR-0041: null for welcome/referral grants, set only for a
        # RedeemCampaignCode-created entitlement.
        "campaign_id": (
            str(entitlement.campaign_id) if entitlement.campaign_id else None
        ),
    }


@router.get("")
async def list_my_promotions(
    account: Annotated[Account, Depends(require_customer)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        # Establishes the customer.customers row exists — required by
        # promotion.entitlements.customer_id's foreign key
        # (database-design.md §24.1). Same precondition-check pattern
        # modules/wallet/router.py already uses for driver.drivers.
        customer_service.get_profile(account_id=account.id)

        entitlements = promotion_service.list_entitlements(
            customer_id=account.id, now=datetime.now(UTC)
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"promotions": [_entitlement_data(e) for e in entitlements]},
            request_id=request_id,
        ),
    )


@router.post("/redeem")
async def redeem_campaign_code(
    body: RedeemCampaignCodeBody,
    account: Annotated[Account, Depends(require_customer)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    """Redeem Campaign Code (ADR-0041 Decision 2) — validates the
    campaign's status/window/eligibility/minimum-fare/usage-limits and
    creates a new promotion.entitlements row with campaign_id set. The
    caller supplies vehicle_category/fare from their in-progress ride
    draft; this does not itself create or touch a ride."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="promotion_usage", identity=str(account.id)),
            limit=settings.RATE_LIMIT_PROMOTION_USAGE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    try:
        customer_service.get_profile(account_id=account.id)
        entitlement = promotion_service.redeem_campaign_code(
            customer_id=account.id,
            code=body.code,
            vehicle_category=VehicleCategory(body.vehicle_category),
            fare=body.fare,
            now=datetime.now(UTC),
        )
    except _AnyDomainError as exc:
        return _domain_error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(_entitlement_data(entitlement), request_id=request_id),
    )
