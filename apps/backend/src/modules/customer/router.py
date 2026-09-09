"""FastAPI routes for Customer.

Endpoints (docs/05-api/api-contracts.md §8, extended in this same change):

    GET   /api/v1/customers/me
    PATCH /api/v1/customers/me

Handlers are kept thin (implementation-readiness.md §25), matching
modules/identity/router.py's pattern exactly, including the response
envelope (shared/api_envelope.py) and domain-error-to-HTTP-status
translation.

GET /api/v1/customers/me composes modules.promotion.grant_welcome_promotion()
the moment it first provisions a customer.customers row (ADR-0019
Decision 4, BR-058) — the standard router/composition-layer pattern;
modules/customer/service.py never imports modules.promotion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from modules.customer.dependencies import get_customer_service
from modules.customer.domain.entities import Customer
from modules.customer.domain.errors import CustomerDomainError
from modules.customer.schemas import UpdateCustomerProfileBody
from modules.customer.service import CustomerService, ProfileUpdate
from modules.identity.dependencies import require_customer
from modules.identity.domain.entities import Account
from modules.promotion.dependencies import get_promotion_service
from modules.promotion.service import PromotionService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


def _profile_data(account: Account, customer: Customer) -> dict[str, object]:
    return {
        "customer_id": str(customer.id),
        "phone": account.phone,
        "full_name": customer.full_name,
        "profile_photo_uri": customer.profile_photo_uri,
        "language": customer.language,
        "notification_enabled": customer.notification_enabled,
        "status": customer.status.value,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat(),
    }


@router.get("/me")
async def get_my_profile(
    account: Annotated[Account, Depends(require_customer)],
    service: Annotated[CustomerService, Depends(get_customer_service)],
    promotion_service: Annotated[PromotionService, Depends(get_promotion_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        customer, created = service.get_or_provision_profile(account_id=account.id)
        if created:
            # BR-058: unconditional on referral — registration/first
            # access is the trigger (ADR-0019 Decision 4).
            promotion_service.grant_welcome_promotion(
                customer_id=customer.id, now=datetime.now(UTC)
            )
    except CustomerDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _profile_data(account, customer), request_id=request_id
        ),
    )


@router.patch("/me")
async def update_my_profile(
    body: UpdateCustomerProfileBody,
    account: Annotated[Account, Depends(require_customer)],
    service: Annotated[CustomerService, Depends(get_customer_service)],
) -> JSONResponse:
    request_id = new_request_id()
    update: ProfileUpdate = body.model_dump(exclude_unset=True)  # type: ignore[assignment]

    try:
        customer = service.update_profile(account_id=account.id, update=update)
    except CustomerDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            _profile_data(account, customer), request_id=request_id
        ),
    )
