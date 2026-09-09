"""FastAPI routes for Wallet.

Endpoints (docs/05-api/api-contracts.md §34):

    GET /api/v1/drivers/me/wallet                Get Wallet
    GET /api/v1/drivers/me/wallet/transactions   Wallet Transactions
                                                  (Phase 11, ADR-0024)

See modules/wallet/__init__.py for what the Minimal Wallet Foundation
deliberately does not do (recharge, outstanding settlements, credit/bonus
paths — the debit/credit primitives themselves are used by other
modules' composed transactions, e.g. modules/matching/router.py's
accept-offer endpoint and modules/ride/router.py's cancellation
endpoints).

`outstanding_settlement` in the Get Wallet response is always 0 — not a
placeholder standing in for an unknown value (contrast Task 3.1's
`fare: null`), genuinely accurate: wallet.outstanding_settlements
doesn't exist yet, so nothing can ever create one.

Wallet Transactions is this driver's own immutable ledger — §51's
"Financial audit trail" roadmap task, traced via this module's own
docstring to this specific documented-but-previously-unbuilt route
(ADR-0024). Paginated per §50 (shared/pagination.py, ADR-0023); `type`
is validated against the documented TransactionType enum
(VALIDATION_FAILED for an unrecognized value, same treatment
modules/admin/router.py's Search Rides/Search Penalties give their own
`status` filters).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from core.config import settings
from core.redis import get_redis
from modules.driver.dependencies import get_driver_service
from modules.driver.domain.errors import DriverDomainError
from modules.driver.service import DriverService
from modules.identity.dependencies import require_driver
from modules.identity.domain.entities import Account
from modules.wallet.dependencies import (
    get_wallet_recharge_gateway_dependency,
    get_wallet_service,
)
from modules.wallet.domain.entities import TransactionType, Wallet, WalletTransaction
from modules.wallet.payment_gateway import PaymentGatewayError, WalletRechargeGateway
from modules.wallet.schemas import ConfirmRechargeBody, CreateRechargeOrderBody
from modules.wallet.service import WalletService
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)
from shared.pagination import PageParams, pagination_envelope
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key

logger = logging.getLogger("vistaar.wallet.router")

router = APIRouter(prefix="/api/v1/drivers/me/wallet", tags=["wallet"])

# Sarthi Wallet Recharge (ADR-0060, 2026-09-02) — a separate router, not
# under /drivers/me/ at all: a webhook call comes from the gateway's own
# servers, never from an authenticated driver, so it has no
# require_driver dependency and no driver-scoped prefix.
webhook_router = APIRouter(
    prefix="/api/v1/webhooks/wallet-recharge", tags=["wallet-webhooks"]
)

_VALID_TRANSACTION_TYPES = frozenset(t.value for t in TransactionType)


def _wallet_data(wallet: Wallet) -> dict[str, object]:
    return {
        "balance": float(wallet.balance),
        "currency": "INR",
        "outstanding_settlement": 0,
        # Sarthi Unpaid Cancellation-Penalty Recovery (ADR-0062,
        # 2026-09-03) — unlike outstanding_settlement above (always 0,
        # a superseded ADR-0025 concept nothing can ever populate),
        # this is genuinely real: an unpaid driver-cancellation penalty
        # the wallet balance couldn't cover, awaiting recovery from a
        # future recharge (WalletService.debit_or_record_as_debt()/
        # credit()).
        "outstanding_debt": float(wallet.outstanding_debt),
    }


def _debt_recovery_data(transaction: WalletTransaction) -> dict[str, object]:
    """ADR-0062 — WalletService.credit()'s own metadata for a
    WALLET_RECHARGE that paid down an outstanding cancellation-penalty
    debt. Empty dict (nothing added to the response) when no debt was
    recovered, so a plain recharge's response shape is unchanged."""
    if (
        not transaction.metadata
        or "outstanding_debt_recovered" not in transaction.metadata
    ):
        return {}
    return {
        "debt_recovered": float(transaction.metadata["outstanding_debt_recovered"]),  # type: ignore[arg-type]
        "outstanding_debt_remaining": float(
            transaction.metadata["outstanding_debt_remaining"]  # type: ignore[arg-type]
        ),
    }


def _transaction_data(transaction: WalletTransaction) -> dict[str, object]:
    return {
        "transaction_id": str(transaction.id),
        "ride_id": str(transaction.ride_id) if transaction.ride_id else None,
        "transaction_type": transaction.transaction_type.value,
        "amount": float(transaction.amount),
        "direction": transaction.direction.value,
        "balance_before": float(transaction.balance_before),
        "balance_after": float(transaction.balance_after),
        "reference_type": transaction.reference_type,
        "reference_id": (
            str(transaction.reference_id) if transaction.reference_id else None
        ),
        "created_at": transaction.created_at.isoformat(),
    }


@router.get("")
async def get_my_wallet(
    account: Annotated[Account, Depends(require_driver)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        # Establishes the driver.drivers row exists — required by
        # wallet.wallets.driver_id's foreign key (database-design.md
        # §17.1). Same precondition-check pattern
        # modules/vehicle/router.py already uses for driver.drivers.
        driver_service.get_profile(account_id=account.id)

        wallet = wallet_service.get_wallet(driver_id=account.id, now=datetime.now(UTC))
    except DriverDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(_wallet_data(wallet), request_id=request_id),
    )


@router.get("/transactions")
async def list_my_wallet_transactions(
    account: Annotated[Account, Depends(require_driver)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    type: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        driver_service.get_profile(account_id=account.id)
    except DriverDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    if type is not None and type not in _VALID_TRANSACTION_TYPES:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "VALIDATION_FAILED",
                f"Unknown transaction type: {type!r}.",
                request_id=request_id,
            ),
        )

    params = PageParams.clamp(
        page=page, page_size=page_size, max_page_size=settings.MAX_PAGE_SIZE
    )
    transactions, total = wallet_service.list_transactions(
        driver_id=account.id,
        transaction_type=type,
        offset=params.offset,
        limit=params.page_size,
    )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            pagination_envelope(
                [_transaction_data(t) for t in transactions],
                params=params,
                total=total,
            ),
            request_id=request_id,
        ),
    )


# --- Sarthi Wallet Recharge (ADR-0060, 2026-09-02) -------------------------
#
# Two client-facing steps (create the order, confirm the completed
# payment) plus a resilient webhook path below — either the confirm call
# or the webhook can credit the wallet first; both use the same
# idempotency key (f"{provider}:{payment_id}"), so whichever arrives
# first "wins" and the other is a no-op replay (WalletService.credit()'s
# own existing idempotency-key guarantee), matching the "duplicate
# payment states handled safely" requirement without any new locking.


@router.post("/recharge")
async def create_recharge_order(
    body: CreateRechargeOrderBody,
    account: Annotated[Account, Depends(require_driver)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    gateway: Annotated[
        WalletRechargeGateway, Depends(get_wallet_recharge_gateway_dependency)
    ],
) -> JSONResponse:
    """api-contracts.md §35 (Wallet Recharge) — creates a pending order
    with the configured gateway (Razorpay, TEST/DEVELOPMENT only —
    ADR-0060). No wallet effect yet; the wallet is credited only once
    the payment is verified (confirm_recharge()/the webhook below)."""
    request_id = new_request_id()

    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="wallet_recharge", identity=str(account.id)),
            limit=settings.RATE_LIMIT_WALLET_RECHARGE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    try:
        driver_service.get_profile(account_id=account.id)
    except DriverDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    minimum = Decimal(settings.WALLET_RECHARGE_MINIMUM_AMOUNT)
    if body.amount < minimum:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "RECHARGE_AMOUNT_TOO_LOW",
                f"Recharge amount must be at least ₹{minimum}.",
                request_id=request_id,
            ),
        )

    try:
        order = await gateway.create_order(driver_id=account.id, amount=body.amount)
    except PaymentGatewayError as exc:
        logger.error("Wallet recharge order creation failed: %s", exc)
        return JSONResponse(
            status_code=http_status_for_error_code("PAYMENT_GATEWAY_ERROR"),
            content=error_envelope(
                "PAYMENT_GATEWAY_ERROR",
                "Could not start the recharge. Please try again.",
                request_id=request_id,
            ),
        )

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            {
                "order_id": order.order_id,
                "amount": float(order.amount),
                "currency": order.currency,
                "client_key": order.client_key,
            },
            request_id=request_id,
        ),
    )


@router.post("/recharge/confirm")
async def confirm_recharge(
    body: ConfirmRechargeBody,
    account: Annotated[Account, Depends(require_driver)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    driver_service: Annotated[DriverService, Depends(get_driver_service)],
    gateway: Annotated[
        WalletRechargeGateway, Depends(get_wallet_recharge_gateway_dependency)
    ],
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
) -> JSONResponse:
    """Called by the mobile app once its checkout SDK reports a
    completed payment. Never trusts that report alone (security.md
    §27) — verifies server-side against the gateway before crediting
    anything. The webhook below is the resilient backup path if this
    call never happens (a dropped connection after a real successful
    payment); both are safe to run for the same payment exactly once
    each, in either order."""
    request_id = new_request_id()

    # Shares the "wallet_recharge" category/bucket with create_recharge_
    # order() above, deliberately — a create+confirm pair is one logical
    # recharge attempt, and this also stops confirm_recharge() itself
    # from being hammered with guessed payment_id values independent of
    # how many orders were actually created.
    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="wallet_recharge", identity=str(account.id)),
            limit=settings.RATE_LIMIT_WALLET_RECHARGE_PER_HOUR,
            window_seconds=3600,
        )
    except RateLimitedError as exc:
        return JSONResponse(
            status_code=429,
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    try:
        driver_service.get_profile(account_id=account.id)
    except DriverDomainError as exc:
        return JSONResponse(
            status_code=http_status_for_error_code(exc.code),
            content=error_envelope(exc.code, exc.message, request_id=request_id),
        )

    try:
        # Both "verified" and "how much" come from this one call — the
        # gateway's own record of the payment, never a client-supplied
        # amount (see WalletRechargeGateway.verify_payment's own doc
        # comment for why).
        verified_amount = await gateway.verify_payment(
            order_id=body.order_id,
            payment_id=body.payment_id,
            signature=body.signature,
        )
    except PaymentGatewayError as exc:
        logger.error("Wallet recharge payment verification failed: %s", exc)
        return JSONResponse(
            status_code=http_status_for_error_code("PAYMENT_GATEWAY_ERROR"),
            content=error_envelope(
                "PAYMENT_GATEWAY_ERROR",
                "Could not verify this payment right now. Please try again.",
                request_id=request_id,
            ),
        )

    if verified_amount is None:
        return JSONResponse(
            status_code=http_status_for_error_code("PAYMENT_VERIFICATION_FAILED"),
            content=error_envelope(
                "PAYMENT_VERIFICATION_FAILED",
                "This payment could not be verified.",
                request_id=request_id,
            ),
        )

    now = datetime.now(UTC)
    transaction = wallet_service.credit(
        driver_id=account.id,
        amount=verified_amount,
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key=f"razorpay:{body.payment_id}",
        now=now,
        metadata={
            "provider": "razorpay",
            "order_id": body.order_id,
            "payment_id": body.payment_id,
        },
    )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "status": "CREDITED",
                "wallet_balance": float(transaction.balance_after),
                # ADR-0062 — present only when this recharge paid down
                # an outstanding cancellation-penalty debt, so the
                # driver can see why `wallet_balance` is less than the
                # full amount they just paid.
                **_debt_recovery_data(transaction),
            },
            request_id=request_id,
        ),
    )


@webhook_router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    wallet_service: Annotated[WalletService, Depends(get_wallet_service)],
    gateway: Annotated[
        WalletRechargeGateway, Depends(get_wallet_recharge_gateway_dependency)
    ],
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Razorpay's own resilient delivery path — fires even if the
    mobile app's confirm_recharge() call above never reaches this
    backend (a dropped connection right after a real successful
    payment). Verifies the raw body against X-Razorpay-Signature before
    trusting anything in it (never parse-then-verify — the unparsed
    bytes are what the signature actually covers)."""
    request_id = new_request_id()
    raw_body = await request.body()

    if not x_razorpay_signature or not gateway.verify_webhook_signature(
        payload=raw_body, signature=x_razorpay_signature
    ):
        return JSONResponse(
            status_code=http_status_for_error_code("INVALID_WEBHOOK_SIGNATURE"),
            content=error_envelope(
                "INVALID_WEBHOOK_SIGNATURE",
                "Webhook signature verification failed.",
                request_id=request_id,
            ),
        )

    # Targeted negative-testing finding, security review 2026-09-03:
    # a genuinely-signed-but-malformed body (Razorpay's own delivery
    # glitching, or any other sender who somehow has the real webhook
    # secret) previously reached `request.json()` unguarded — a real
    # `json.JSONDecodeError` reproduced here propagated all the way to
    # an unhandled 500, instead of the clean, structured error every
    # other endpoint in this codebase returns. Caught explicitly now,
    # same "handle uncertain payment states safely" requirement the
    # rest of this flow already follows.
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=http_status_for_error_code("VALIDATION_FAILED"),
            content=error_envelope(
                "VALIDATION_FAILED",
                "Webhook payload is not valid JSON.",
                request_id=request_id,
            ),
        )
    parsed = gateway.parse_captured_payment(payload)
    if parsed is None:
        # Not a payment.captured event (e.g. payment.failed) — logged,
        # not acted on; security.md's "handle failed/cancelled states
        # safely" here means "don't credit," not "invent a matching
        # failure-handling flow nothing asked for."
        return JSONResponse(
            status_code=200,
            content=success_envelope({"status": "IGNORED"}, request_id=request_id),
        )

    driver_id, payment_id, amount = parsed
    now = datetime.now(UTC)
    wallet_service.credit(
        driver_id=driver_id,
        amount=amount,
        transaction_type="WALLET_RECHARGE",
        ride_id=None,
        idempotency_key=f"razorpay:{payment_id}",
        now=now,
        metadata={"provider": "razorpay", "payment_id": payment_id, "via": "webhook"},
    )

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": "PROCESSED"}, request_id=request_id),
    )
