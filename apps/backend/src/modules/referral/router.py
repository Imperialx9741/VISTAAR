"""FastAPI routes for Referral.

Endpoints (docs/05-api/api-contracts.md §38):

    GET  /api/v1/customers/me/referral   Get Referral Code
    POST /api/v1/referrals/attach        Attach Referral

Get Referral Code is customer-facing only — its URL is literally
`/api/v1/customers/me/referral` (ADR-0019 Decision 5: no invented
driver-facing equivalent; a driver's code is provisioned lazily by the
same ReferralService.get_or_create_code() call, just with nothing routed
to reach it for drivers yet).

Attach Referral, by contrast, is documented at the account-type-neutral
path `/api/v1/referrals/attach` — both a newly-registering customer
(BR-059/060) and a newly-registering driver (BR-022/023) can genuinely
enter a referral code, so this endpoint accepts either `require_customer`
or `require_driver` account and branches on `account.account_type`:

- Customer: attach -> qualify immediately (BR-060: activates on first
  login through the referral, no completed ride required) -> grant a
  3-use promotion to the referred customer and a 2-use promotion to the
  referrer (BR-059/060) -> record an audit/idempotency Reward row for
  each side.
- Driver: attach only. Qualification (BR-023: registration -> onboarding
  -> verification -> approval) and the ₹100/₹100 wallet reward (BR-022)
  are composed into modules/admin/router.py's driver-approval endpoint
  instead, per ADR-0019 Decision 4 — a driver referral is not activated
  at attach time.
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
from modules.identity.dependencies import require_account_type, require_customer
from modules.identity.domain.entities import Account, AccountType
from modules.promotion.dependencies import get_promotion_service
from modules.promotion.service import PromotionService
from modules.referral.dependencies import get_referral_service
from modules.referral.domain.entities import OwnerType, RewardType
from modules.referral.domain.errors import ReferralDomainError
from modules.referral.schemas import AttachReferralRequest
from modules.referral.service import ReferralService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key

router = APIRouter(tags=["referrals"])

_require_customer_or_driver = require_account_type(
    AccountType.CUSTOMER, AccountType.DRIVER
)


@router.get("/api/v1/customers/me/referral")
async def get_my_referral_code(
    account: Annotated[Account, Depends(require_customer)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        customer_service.get_profile(account_id=account.id)
        code = referral_service.get_or_create_code(
            owner_type=OwnerType.CUSTOMER, owner_id=account.id, now=datetime.now(UTC)
        )
    except CustomerDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope({"code": code.code}, request_id=request_id),
    )


@router.post("/api/v1/referrals/attach")
async def attach_referral(
    body: AttachReferralRequest,
    account: Annotated[Account, Depends(_require_customer_or_driver)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    customer_service: Annotated[CustomerService, Depends(get_customer_service)],
    referral_service: Annotated[ReferralService, Depends(get_referral_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="referral_attach", identity=str(account.id)),
            limit=settings.RATE_LIMIT_REFERRAL_ATTACH_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    now = datetime.now(UTC)
    referred_type = OwnerType(account.account_type.value)
    try:
        if referred_type is OwnerType.CUSTOMER:
            # promotion.entitlements.customer_id's FK (database-design.md
            # §24.1) requires the customer.customers row exist first.
            customer_service.get_profile(account_id=account.id)

        referral = referral_service.attach_referral(
            code=body.code,
            referred_id=account.id,
            referred_type=referred_type,
            now=now,
        )

        if referred_type is OwnerType.CUSTOMER:
            referral = referral_service.qualify_customer_referral(
                referral_id=referral.id, now=now
            )
            # ADR-0043: read the live-published reward rule for each
            # side, if one exists — None falls through to
            # PromotionService's own last-resort constants (BR-059/060).
            referred_rule = referral_service.get_active_customer_reward_rule(
                reward_type="REFERRAL_REFERRED", now=now
            )
            referred_entitlement = promotion_service.grant_referral_promotion(
                customer_id=referral.referred_id,
                is_referring_customer=False,
                now=now,
                total_uses=referred_rule.total_uses if referred_rule else None,
                discount_percent=(
                    referred_rule.discount_percent if referred_rule else None
                ),
            )
            referrer_rule = referral_service.get_active_customer_reward_rule(
                reward_type="REFERRAL_REFERRING", now=now
            )
            referrer_entitlement = promotion_service.grant_referral_promotion(
                customer_id=referral.referrer_id,
                is_referring_customer=True,
                now=now,
                total_uses=referrer_rule.total_uses if referrer_rule else None,
                discount_percent=(
                    referrer_rule.discount_percent if referrer_rule else None
                ),
            )
            # promotion_uses below is read back from the entitlement
            # PromotionService actually created, not re-hardcoded here
            # — the two can never drift apart (they used to: this
            # router previously passed a literal 3/2 that happened to
            # match promotion's own separate constants by hand).
            referral_service.record_reward(
                referral_id=referral.id,
                recipient_id=referral.referred_id,
                reward_type=RewardType.CUSTOMER_REFERRAL_PROMOTION,
                amount=None,
                promotion_uses=referred_entitlement.total_uses,
                idempotency_key=f"referral:{referral.id}:referred",
                now=now,
            )
            referral_service.record_reward(
                referral_id=referral.id,
                recipient_id=referral.referrer_id,
                reward_type=RewardType.CUSTOMER_REFERRAL_PROMOTION,
                amount=None,
                promotion_uses=referrer_entitlement.total_uses,
                idempotency_key=f"referral:{referral.id}:referrer",
                now=now,
            )
        # Driver referrals stay ATTACHED — BR-023 qualification and
        # BR-022's wallet reward are composed at admin driver-approval
        # time instead (modules/admin/router.py).
    except (CustomerDomainError, ReferralDomainError) as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"status": referral.status.value}, request_id=request_id
        ),
    )
