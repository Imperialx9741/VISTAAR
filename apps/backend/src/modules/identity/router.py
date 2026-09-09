"""FastAPI routes for Identity & Authentication.

Endpoints (docs/05-api/api-contracts.md §6-7 document the first two;
refresh/logout are added per this task's explicit scope and
domain-design.md's RefreshSession/Logout commands — see the
api-contracts.md update made in this same change):

    POST /api/v1/auth/otp/request
    POST /api/v1/auth/otp/verify
    POST /api/v1/auth/refresh
    POST /api/v1/auth/logout
    POST /api/v1/auth/mfa/enroll    (ADR-0051 — Admin MFA)
    POST /api/v1/auth/mfa/confirm   (ADR-0051)
    POST /api/v1/auth/mfa/verify    (ADR-0051)
    POST /api/v1/auth/mfa/disable   (ADR-0051)

Handlers are kept thin (implementation-readiness.md §25: "API handlers
should be thin") — all business logic lives in service.py.

MFA enrollment is gated to ADMIN accounts (require_admin) at this router
layer only — the underlying IdentityService/schema is account-type-
agnostic (ADR-0051 Decision 1), not because MFA is admin-specific, but
because ADMIN is the only account type asked for today.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from modules.identity.dependencies import get_identity_service, require_admin
from modules.identity.domain.entities import Account
from modules.identity.domain.errors import IdentityDomainError
from modules.identity.schemas import (
    LogoutBody,
    MfaConfirmBody,
    MfaDisableBody,
    MfaVerifyBody,
    OtpRequestBody,
    OtpVerifyBody,
    RefreshBody,
)
from modules.identity.service import IdentityService, MfaRequiredResult
from shared.api_envelope import (
    error_envelope,
    http_status_for_error_code,
    new_request_id,
    success_envelope,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _error_response(exc: IdentityDomainError, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for_error_code(exc.code),
        content=error_envelope(exc.code, exc.message, request_id=request_id),
    )


def _client_ip(request: Request) -> str | None:
    """Phase 2 Identity hardening — security.md §5's IP dimension. Uses
    the request's own connection info only (`request.client.host`), not
    an `X-Forwarded-For`-style header: this deployment has no documented
    trusted-proxy configuration, and honoring a client-supplied header as
    the rate-limit key would let it be trivially spoofed to evade the
    limit entirely. If/when a real reverse proxy is introduced (Phase 21
    deployment), this is the one place to teach it to trust that proxy's
    specific header."""
    return request.client.host if request.client is not None else None


@router.post("/otp/request")
async def request_otp(
    body: OtpRequestBody,
    request: Request,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        result = await service.request_otp(
            raw_phone=body.phone,
            account_type=body.account_type,
            ip_address=_client_ip(request),
        )
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "challenge_id": str(result.challenge_id),
                "expires_in": result.expires_in_seconds,
            },
            request_id=request_id,
        ),
    )


@router.post("/otp/verify")
async def verify_otp(
    body: OtpVerifyBody,
    request: Request,
    service: Annotated[IdentityService, Depends(get_identity_service)],
    user_agent: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    try:
        challenge_id = uuid.UUID(body.challenge_id)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content=error_envelope(
                "VALIDATION_FAILED",
                "challenge_id must be a valid UUID.",
                request_id=request_id,
            ),
        )

    try:
        result = await service.verify_otp(
            challenge_id=challenge_id,
            otp=body.otp,
            device_metadata=user_agent,
            ip_address=_client_ip(request),
        )
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    if isinstance(result, MfaRequiredResult):
        # ADR-0051 — this account has an ACTIVE MFA credential; the
        # caller must call POST /api/v1/auth/mfa/verify next with this
        # token instead of using it as a normal access token (it isn't
        # one — get_current_account() rejects it, see ADR-0051
        # Decision 4).
        return JSONResponse(
            status_code=200,
            content=success_envelope(
                {
                    "mfa_required": True,
                    "mfa_token": result.mfa_token,
                    "expires_in": result.expires_in_seconds,
                },
                request_id=request_id,
            ),
        )

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "expires_in": result.expires_in_seconds,
            },
            request_id=request_id,
        ),
    )


@router.post("/refresh")
async def refresh(
    body: RefreshBody,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        result = await service.refresh(refresh_token=body.refresh_token)
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "expires_in": result.expires_in_seconds,
            },
            request_id=request_id,
        ),
    )


@router.post("/logout")
async def logout(
    body: LogoutBody,
    service: Annotated[IdentityService, Depends(get_identity_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    request_id = new_request_id()
    if not authorization or not authorization.lower().startswith("bearer "):
        return JSONResponse(
            status_code=401,
            content=error_envelope(
                "AUTH_REQUIRED", "Missing bearer token.", request_id=request_id
            ),
        )
    access_token = authorization.split(" ", 1)[1]

    try:
        await service.logout(
            access_token=access_token, refresh_token=body.refresh_token
        )
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": "LOGGED_OUT"}, request_id=request_id),
    )


# ----------------------------------------------------------------------
# Admin MFA (ADR-0051). Enrollment/confirm/disable require a real bearer
# access token (require_admin) — an already-authenticated admin managing
# their own second factor. verify is the one exception: it's part of the
# login flow itself, so it takes the short-lived mfa_token from
# otp/verify instead of a bearer token.
# ----------------------------------------------------------------------


@router.post("/mfa/enroll")
async def enroll_mfa(
    account: Annotated[Account, Depends(require_admin)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        result = service.enroll_mfa(account_id=account.id, now=datetime.now(UTC))
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    return JSONResponse(
        status_code=201,
        content=success_envelope(
            {"secret": result.secret, "otpauth_uri": result.otpauth_uri},
            request_id=request_id,
        ),
    )


@router.post("/mfa/confirm")
async def confirm_mfa(
    body: MfaConfirmBody,
    account: Annotated[Account, Depends(require_admin)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        service.confirm_mfa(
            account_id=account.id, code=body.code, now=datetime.now(UTC)
        )
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": "ACTIVE"}, request_id=request_id),
    )


@router.post("/mfa/verify")
async def verify_mfa(
    body: MfaVerifyBody,
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> JSONResponse:
    """Second step of login for an account with an ACTIVE MFA
    credential — not authenticated by a bearer token (there isn't one
    yet); mfa_token itself is the proof of the first factor already
    having succeeded."""
    request_id = new_request_id()
    try:
        result = await service.verify_mfa(mfa_token=body.mfa_token, code=body.code)
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "expires_in": result.expires_in_seconds,
            },
            request_id=request_id,
        ),
    )


@router.post("/mfa/disable")
async def disable_mfa(
    body: MfaDisableBody,
    account: Annotated[Account, Depends(require_admin)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> JSONResponse:
    request_id = new_request_id()
    try:
        service.disable_mfa(account_id=account.id, code=body.code)
    except IdentityDomainError as exc:
        return _error_response(exc, request_id)

    return JSONResponse(
        status_code=200,
        content=success_envelope({"status": "DISABLED"}, request_id=request_id),
    )
