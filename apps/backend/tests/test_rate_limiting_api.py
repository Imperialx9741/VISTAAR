"""Integration tests: real HTTP layer (TestClient) + real Postgres +
real Redis, proving the API rate limiting wired into real endpoints in
this pass (security.md §20; security-review-2026-09-02.md finding 4.1,
HIGH) actually works end-to-end — not just that the generic mechanism
itself works (tests/test_rate_limit.py covers that in isolation).

Every affected router uses the identical composition pattern: `await
RateLimiter(redis_client).check_and_increment(...)` wrapped in a
try/except RateLimitedError, called before any state-changing work, in
every router this pass touched (modules/ride, modules/matching,
modules/wallet, modules/promotion, modules/referral, modules/support,
modules/driver) — except modules/admin, which uses a single
router-level `dependencies=[Depends(enforce_admin_api_rate_limit)]`
blanket instead (see modules/admin/dependencies.py's own docstring for
why). This file exercises a representative endpoint from each of those
two composition styles, across all three account types (customer,
driver, admin) the pattern is used for — not every single rate-limited
endpoint, since the wiring is mechanically identical everywhere else it
was applied (modules/ride's ride cancellation and fare-change
endpoints, modules/promotion's redeem, modules/referral's attach) and
is already exercised, without any RATE_LIMITED-specific assertion, by
those endpoints' own existing test files passing.

Each test monkeypatches the relevant RATE_LIMIT_* setting down to a
small number so the real limit can be hit within a handful of real HTTP
calls, same convention test_identity_api.py's own OTP rate-limit tests
already use for RedisOtpRateLimiter.

Skips (not fails) when Postgres/Redis are genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator

import pytest
from _integration_db import truncate_integration_tables
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.config import settings
from core.database import SessionLocal, engine
from core.redis import get_redis_client
from main import app
from modules.admin.models import AdminUserORM
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token


class CapturingSmsProvider:
    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    async def send_otp(self, phone_number: str, otp: str) -> None:
        self.sent[phone_number] = otp


def _infra_available() -> bool:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except OperationalError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _infra_available(),
    reason="Postgres/Redis are offline/unreachable (start docker-compose.dev.yml)",
)


@pytest.fixture(autouse=True)
def _clean_integration_tables() -> None:
    truncate_integration_tables(engine)
    asyncio.run(_clean_rate_limit_keys())


async def _clean_rate_limit_keys() -> None:
    """Unlike most integration test files in this codebase, this one's
    own correctness *depends on* a clean rate-limit counter per test
    (a leftover `ratelimit:*` key from an earlier run in the same
    rolling window would make a test see a lower effective limit than
    it configured) — this is essential cleanup here, not incidental."""
    client = get_redis_client()
    try:
        async for key in client.scan_iter(match="ratelimit:*"):
            await client.delete(key)
    finally:
        await client.aclose()


@pytest.fixture
def sms() -> CapturingSmsProvider:
    return CapturingSmsProvider()


@pytest.fixture
def api_client(sms: CapturingSmsProvider) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_sms_provider_dependency] = lambda: sms
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_sms_provider_dependency, None)


def _random_phone() -> str:
    return "+91" + "".join(str(secrets.randbelow(10)) for _ in range(10))


def _login(api_client: TestClient, sms: CapturingSmsProvider, account_type: str) -> str:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": account_type},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    access_token: str = tokens["access_token"]
    return access_token


def _account_id_from_token(access_token: str) -> uuid.UUID:
    payload = decode_access_token(access_token)
    return uuid.UUID(payload["sub"])


def _login_customer(
    api_client: TestClient, sms: CapturingSmsProvider
) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(api_client, sms, 'CUSTOMER')}"}


def _login_driver_with_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> dict[str, str]:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )
    return headers


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict[str, str]:
    access_token = _login(api_client, sms, "ADMIN")
    account_id = _account_id_from_token(access_token)
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {access_token}"}


def _ride_body() -> dict[str, object]:
    return {
        "pickup": {"latitude": 22.5, "longitude": 88.3},
        "destination": {"latitude": 22.6, "longitude": 88.4},
        "vehicle_category": "CAB",
        "cab_tier": "ECO",
        "payment_method": "CASH",
    }


# --- Ride Creation (customer, explicit try/except pattern) ------------------


def test_ride_creation_is_rate_limited_per_customer(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_RIDE_CREATE_PER_HOUR", 1)
    headers = _login_customer(api_client, sms)

    first = api_client.post(
        "/api/v1/rides",
        json=_ride_body(),
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    second = api_client.post(
        "/api/v1/rides",
        json=_ride_body(),
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_ride_creation_rate_limit_is_per_customer_not_global(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_RIDE_CREATE_PER_HOUR", 1)
    first_customer = _login_customer(api_client, sms)
    second_customer = _login_customer(api_client, sms)

    first = api_client.post(
        "/api/v1/rides",
        json=_ride_body(),
        headers={**first_customer, "Idempotency-Key": str(uuid.uuid4())},
    )
    second = api_client.post(
        "/api/v1/rides",
        json=_ride_body(),
        headers={**second_customer, "Idempotency-Key": str(uuid.uuid4())},
    )

    assert first.status_code == 201
    assert second.status_code == 201  # a different customer, own bucket


# --- Wallet Recharge (driver, explicit try/except pattern) ------------------


def test_wallet_recharge_order_creation_is_rate_limited_per_driver(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_WALLET_RECHARGE_PER_HOUR", 1)
    headers = _login_driver_with_profile(api_client, sms)

    first = api_client.post(
        "/api/v1/drivers/me/wallet/recharge",
        json={"amount": "500.00"},
        headers=headers,
    )
    second = api_client.post(
        "/api/v1/drivers/me/wallet/recharge",
        json={"amount": "500.00"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


# --- Evidence Upload (driver, explicit try/except pattern) ------------------


def test_evidence_upload_url_request_is_rate_limited_per_driver(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_EVIDENCE_UPLOAD_PER_HOUR", 1)
    headers = _login_driver_with_profile(api_client, sms)

    first = api_client.post(
        "/api/v1/drivers/me/uploads",
        json={"content_type": "image/jpeg"},
        headers=headers,
    )
    second = api_client.post(
        "/api/v1/drivers/me/uploads",
        json={"content_type": "image/jpeg"},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


# --- Support Case Creation (customer, explicit try/except pattern) ----------


def test_support_case_creation_is_rate_limited_per_user(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_SUPPORT_MESSAGE_PER_HOUR", 1)
    headers = _login_customer(api_client, sms)
    body = {"category": "OTHER", "message": "Need help with something."}

    first = api_client.post("/api/v1/support/cases", json=body, headers=headers)
    second = api_client.post("/api/v1/support/cases", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


# --- Admin APIs (blanket, router-level Depends() pattern) -------------------


def test_admin_api_blanket_rate_limit_applies_across_endpoints(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves the router-level `dependencies=[Depends(
    enforce_admin_api_rate_limit)]` composition (structurally different
    from every other category's explicit per-handler call) actually
    applies — and that it's a single shared bucket across *different*
    admin endpoints, not one counter per route, matching "an admin
    operator is doing something abnormal across the whole API" (see
    enforce_admin_api_rate_limit's own docstring)."""
    monkeypatch.setattr(settings, "RATE_LIMIT_ADMIN_API_PER_MINUTE", 1)
    headers = _login_admin(api_client, sms)

    first = api_client.get("/api/v1/admin/audit-logs", headers=headers)
    # A DIFFERENT admin endpoint, same admin — still blocked by the same
    # blanket counter.
    second = api_client.get("/api/v1/admin/customers", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    # Enveloped since 2026-09-08 (main.py's _enveloped_http_exception_
    # handler) — this dependency-layer 429 used to bypass the app's own
    # error_envelope() shape (a raw {"detail": "RATE_LIMITED"}), the same
    # gap that made an admin-web bug report ("UNKNOWN_ERROR", no real
    # message) hard to diagnose. Every admin-layer error code now goes
    # through the same envelope, whether raised via a Depends() dependency
    # or from inside a route handler's own try/except.
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_admin_api_blanket_rate_limit_is_per_admin_not_global(
    api_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ADMIN_API_PER_MINUTE", 1)
    first_admin = _login_admin(api_client, sms)
    second_admin = _login_admin(api_client, sms)

    first = api_client.get("/api/v1/admin/audit-logs", headers=first_admin)
    second = api_client.get("/api/v1/admin/audit-logs", headers=second_admin)

    assert first.status_code == 200
    assert second.status_code == 200  # a different admin, own bucket
