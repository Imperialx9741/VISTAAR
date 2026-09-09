"""FastAPI dependencies: service wiring + authentication/authorization.

Reusable authorization checks (require_customer / require_driver /
require_admin) follow the naming implementation-readiness.md §33
("Authorization Module") specifies. Only account-type checks are
implemented in this task — resource-ownership checks
(require_resource_owner) are deferred to the tasks that own the resources
being protected (rides, wallet, etc.), per this task's explicit scope
("Do NOT yet implement the full Customer, Driver, Vehicle, or RBAC feature
sets").
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from core.redis import get_redis
from modules.identity.domain.entities import Account, AccountType
from modules.identity.domain.errors import AccessTokenInvalidError
from modules.identity.ports import SmsProvider
from modules.identity.rate_limit import RedisOtpRateLimiter
from modules.identity.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyMfaCredentialRepository,
    SqlAlchemyOtpChallengeRepository,
    SqlAlchemySessionRepository,
)
from modules.identity.security import decode_access_token
from modules.identity.service import IdentityService
from modules.identity.sms import get_sms_provider
from modules.identity.token_denylist import RedisAccessTokenDenylist

_bearer_scheme = HTTPBearer(auto_error=False)


def get_sms_provider_dependency() -> SmsProvider:
    """A thin Depends()-compatible wrapper around sms.get_sms_provider().

    Kept as its own dependency (rather than calling get_sms_provider()
    directly inside get_identity_service) specifically so tests can swap
    it via app.dependency_overrides — the "safe development/test adapter"
    the task's SMS section asks for — without touching real DB/Redis
    wiring. Typed as the SmsProvider Protocol (ports.py), not either
    concrete adapter — ADR-0031 added a second one (Msg91SmsProvider),
    and this dependency's callers only ever need the Protocol's shape.
    """
    return get_sms_provider()


def get_account_repository(
    db: Annotated[DbSession, Depends(get_db)],
) -> SqlAlchemyAccountRepository:
    """DI factory for looking up an *arbitrary* account by id (not just
    the currently-authenticated one) — needed by modules/admin/router.py
    (Phase 2 / Task 2.7A) to show a reviewed driver's phone number.
    Composed only at the router layer, same as every other
    cross-module service/repository reuse in this codebase; no
    domain/service-layer code in any other module imports
    modules.identity."""
    return SqlAlchemyAccountRepository(db)


def get_identity_service(
    db: Annotated[DbSession, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    sms: Annotated[SmsProvider, Depends(get_sms_provider_dependency)],
) -> IdentityService:
    return IdentityService(
        accounts=SqlAlchemyAccountRepository(db),
        challenges=SqlAlchemyOtpChallengeRepository(db),
        sessions=SqlAlchemySessionRepository(db),
        sms=sms,
        rate_limiter=RedisOtpRateLimiter(redis_client),
        denylist=RedisAccessTokenDenylist(redis_client),
        mfa_credentials=SqlAlchemyMfaCredentialRepository(db),
    )


async def get_current_account(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer_scheme)
    ],
    db: Annotated[DbSession, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> Account:
    if credentials is None:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")

    try:
        payload = decode_access_token(credentials.credentials)
    except AccessTokenInvalidError as exc:
        raise HTTPException(status_code=401, detail="AUTH_INVALID") from exc

    # ADR-0051 Decision 4: an MFA pre-auth token (purpose="mfa_pending")
    # must never authenticate an ordinary request — only
    # POST /api/v1/auth/mfa/verify may consume one (via
    # decode_mfa_pending_token(), not this dependency). Every real
    # access token issued by issue_access_token() already carries
    # purpose="access"; a token from before this change existing in the
    # wild would fail this check too, which is the intended effect, not
    # a bug — no such token is in production yet.
    if payload.get("purpose") != "access":
        raise HTTPException(status_code=401, detail="AUTH_INVALID")

    denylist = RedisAccessTokenDenylist(redis_client)
    if await denylist.is_revoked(payload["jti"]):
        raise HTTPException(status_code=401, detail="AUTH_INVALID")

    accounts = SqlAlchemyAccountRepository(db)
    try:
        account_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="AUTH_INVALID") from exc
    account = accounts.get_by_id(account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="AUTH_INVALID")
    if account.is_suspended():
        raise HTTPException(status_code=403, detail="ACCOUNT_SUSPENDED")

    return account


def require_account_type(*allowed: AccountType) -> object:
    """Factory for a FastAPI dependency restricting access to specific
    account types, e.g. Depends(require_account_type(AccountType.ADMIN))."""

    async def _check(
        account: Annotated[Account, Depends(get_current_account)],
    ) -> Account:
        if account.account_type not in allowed:
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        return account

    return _check


require_customer = require_account_type(AccountType.CUSTOMER)
require_driver = require_account_type(AccountType.DRIVER)
require_admin = require_account_type(AccountType.ADMIN)
# Phase 04 (Get Ride, ADR-0024) — api-contracts.md §13: "Customer may
# access their own ride. Driver may access rides assigned to them."
# require_account_type already supported multiple allowed types; only
# this named constant was missing.
require_customer_or_driver = require_account_type(
    AccountType.CUSTOMER, AccountType.DRIVER
)
