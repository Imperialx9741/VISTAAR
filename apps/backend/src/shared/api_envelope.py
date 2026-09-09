"""Standard API response envelope, shared by every module's API layer.

Matches docs/05-api/api-contracts.md §3 (Standard Response Format) exactly:

    {"data": {...}, "error": null, "request_id": "req_123"}
    {"data": null, "error": {"code": "...", "message": "..."}, "request_id": "req_123"}

This is the first module to need it, but it belongs in shared/ rather than
inside modules/identity/ because every future module's API layer will need
the same envelope shape and the same api-contracts.md §49 error-code list
(implementation-readiness.md §22: "Shared infrastructure must not contain
domain-specific business rules" — this file contains none; it only knows
about the generic envelope shape and the codes already enumerated in
api-contracts.md).
"""

from __future__ import annotations

import uuid
from typing import Any

# HTTP status mapping for the error codes enumerated in
# docs/05-api/api-contracts.md §49. Codes not yet used by any module are
# omitted rather than guessed at; add them here when a module needs them.
_ERROR_CODE_HTTP_STATUS: dict[str, int] = {
    "AUTH_REQUIRED": 401,
    "AUTH_INVALID": 401,
    "FORBIDDEN": 403,
    "RESOURCE_NOT_FOUND": 404,
    "INVALID_REQUEST": 400,
    "VALIDATION_FAILED": 422,
    "INVALID_STATE_TRANSITION": 409,
    "VEHICLE_NOT_ELIGIBLE": 409,
    "DRIVER_NOT_ELIGIBLE": 409,
    "DRIVER_NOT_ONLINE": 409,
    "ACCOUNT_SUSPENDED": 403,
    "OTP_INVALID": 400,
    "OTP_EXPIRED": 400,
    "OTP_MAX_ATTEMPTS": 429,
    "IDEMPOTENCY_KEY_REUSE": 409,
    "RATE_LIMITED": 429,
    # Phase 3 / Task 3.2 (Matching).
    "OFFER_ALREADY_RESPONDED": 409,
    # Phase 3 / Task 3.3 (Ride Cancellation).
    "RIDE_NOT_FOUND": 404,
    "RIDE_NOT_CANCELLABLE": 409,
    # Minimal Wallet Foundation.
    "INSUFFICIENT_WALLET_BALANCE": 409,
    "WALLET_TRANSACTION_FAILED": 409,
    # Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02).
    "WALLET_RECHARGE_REQUIRED": 409,
    # Sarthi Wallet Recharge (ADR-0060, 2026-09-02).
    "RECHARGE_AMOUNT_TOO_LOW": 422,
    "PAYMENT_VERIFICATION_FAILED": 402,
    "PAYMENT_GATEWAY_ERROR": 502,
    "INVALID_WEBHOOK_SIGNATURE": 401,
    # Phase 3 / Task 3.4 (Accept Offer).
    "OFFER_EXPIRED": 409,
    "RIDE_ALREADY_ASSIGNED": 409,
    # Phase 12 / Growth (Promotion & Referral, ADR-0019).
    "PROMOTION_EXPIRED": 409,
    "PROMOTION_ALREADY_USED": 409,
    "REFERRAL_INVALID": 400,
    "REFERRAL_ALREADY_ATTACHED": 409,
    # Phase 06/07 (GPS Verification Foundation & Ride Lifecycle, ADR-0028).
    "RIDE_NOT_COMPLETABLE": 409,
    "NOT_WITHIN_PICKUP_RADIUS": 409,
    "NOT_WITHIN_DESTINATION_RADIUS": 409,
    "GPS_VERIFICATION_FAILED": 409,
    # Coupon/Campaign Schema (ADR-0041).
    "CAMPAIGN_NOT_ACTIVE": 409,
    "CAMPAIGN_NOT_ELIGIBLE": 409,
    "CAMPAIGN_MINIMUM_FARE_NOT_MET": 409,
    "CAMPAIGN_USAGE_LIMIT_EXCEEDED": 409,
    # Ride Modifications, pickup-change simplification (ADR-0056).
    "PICKUP_CHANGE_TOO_FAR": 409,
}

_DEFAULT_ERROR_STATUS = 400


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:16]}"


def success_envelope(data: Any, *, request_id: str | None = None) -> dict[str, Any]:
    return {"data": data, "error": None, "request_id": request_id or new_request_id()}


def error_envelope(
    code: str,
    message: str,
    *,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"data": None, "error": error, "request_id": request_id or new_request_id()}


def http_status_for_error_code(code: str) -> int:
    return _ERROR_CODE_HTTP_STATUS.get(code, _DEFAULT_ERROR_STATUS)
