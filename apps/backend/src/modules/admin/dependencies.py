"""FastAPI dependency wiring for Admin.

Reuses modules.identity.dependencies.require_admin as-is — no new auth
code. Admin resource-ownership is not scoped the way driver/customer
resources are (an admin isn't scoped to "their own" driver) — every
route still requires require_admin + AdminService.require_active_admin()/
require_permission() together, see router.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.orm import Session as DbSession

from core.config import settings
from core.database import get_db
from core.redis import get_redis
from modules.admin.repositories import (
    SqlAlchemyAdminRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemySettingRepository,
)
from modules.admin.service import AdminService
from modules.identity.dependencies import get_account_repository, require_admin
from modules.identity.domain.entities import Account
from modules.identity.repositories import SqlAlchemyAccountRepository
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key


def get_admin_service(
    db: Annotated[DbSession, Depends(get_db)],
    accounts: Annotated[SqlAlchemyAccountRepository, Depends(get_account_repository)],
) -> AdminService:
    return AdminService(
        admins=SqlAlchemyAdminRepository(db),
        permissions=SqlAlchemyPermissionRepository(db),
        accounts=accounts,
        settings=SqlAlchemySettingRepository(db),
    )


async def enforce_admin_api_rate_limit(
    account: Annotated[Account, Depends(require_admin)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Admin APIs' blanket rate limit (security.md §20; security-review-
    2026-09-02.md finding 4.1) — a single per-minute limit
    (RATE_LIMIT_ADMIN_API_PER_MINUTE) covering every admin endpoint,
    applied once at the router level (`router = APIRouter(...,
    dependencies=[Depends(enforce_admin_api_rate_limit)])` in
    modules/admin/router.py) rather than per-endpoint like every other
    rate-limited category — admin/router.py has dozens of routes, and a
    single blanket limit per admin account is the right shape for "an
    admin operator is doing something abnormal across the whole API,"
    not a reason to hand-tune dozens of individual per-endpoint limits.

    Depends(require_admin) here is deduplicated by FastAPI's own
    per-request dependency cache against the same call every admin
    endpoint already makes for its own `account` parameter — evaluated
    once per request either way, not twice.

    Raises a raw HTTPException (detail="RATE_LIMITED"), matching
    require_account_type's own convention for auth-layer dependency
    failures (401/403) in modules/identity/dependencies.py — this
    dependency sits at the same layer, not inside a router handler body
    with its own try/except-envelope pattern."""
    try:
        await RateLimiter(redis_client).check_and_increment(
            key=rate_limit_key(category="admin_api", identity=str(account.id)),
            limit=settings.RATE_LIMIT_ADMIN_API_PER_MINUTE,
            window_seconds=60,
        )
    except RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=exc.code) from exc
