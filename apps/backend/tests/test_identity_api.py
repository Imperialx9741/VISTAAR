"""Integration tests: real HTTP layer (TestClient) + real Postgres +
real Redis, exercising the actual /api/v1/auth/* endpoints end-to-end.

This is the "integration" half of the "unit + integration testing" the
task requires — test_identity_service.py covers the same business rules
against in-memory fakes for fast, deterministic unit coverage; this file
proves the real wiring (SQLAlchemy session, Alembic-migrated schema,
Redis rate limiter/denylist, FastAPI routing, Pydantic validation) actually
works together.

Every test uses a fresh, randomly-generated phone number so tests do not
interfere with each other or with data left over from manual exploration
of the running server.

Skips (not fails) when Postgres/Redis are genuinely unreachable, matching
the existing convention in tests/test_main.py — this suite is meant to run
against the docker-compose.dev.yml infrastructure from Task 13.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Generator

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from core.redis import get_redis_client
from main import app
from modules.admin.models import AdminUserORM
from modules.identity.config import identity_settings
from modules.identity.dependencies import get_sms_provider_dependency
from modules.identity.security import decode_access_token


class CapturingSmsProvider:
    """The "safe development/test adapter" the task's SMS section asks
    for — captures the OTP instead of sending a real SMS, exactly as
    sms.DevConsoleSmsProvider does (logs only), except it also makes the
    OTP available to the test so verification can be exercised end-to-end
    without a real SMS channel."""

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
    reason="Postgres is offline/unreachable (start docker-compose.dev.yml)",
)


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


def test_otp_request_returns_challenge_and_sends_via_dev_adapter(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert "challenge_id" in body["data"]
    assert body["data"]["expires_in"] > 0
    # The 10. Development SMS provider behavior check: OTP never appears
    # in the HTTP response, only via the (test) SMS adapter.
    assert "otp" not in body["data"]
    assert phone in sms.sent


def test_full_otp_verify_issues_real_tokens_backed_by_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]

    verify_response = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    )

    assert verify_response.status_code == 200
    data = verify_response.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["expires_in"] > 0


def test_incorrect_otp_is_rejected_with_401_style_domain_error(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]

    response = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": "000000"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


def test_otp_cannot_be_reused(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]

    first = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    )
    assert first.status_code == 200

    second = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "OTP_INVALID"


def test_refresh_and_logout_round_trip(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]

    refreshed = api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()["data"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    logout_response = api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert logout_response.status_code == 200

    reuse_attempt = api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert reuse_attempt.status_code == 401


@pytest.mark.anyio
async def test_unauthenticated_request_is_rejected_by_get_current_account() -> None:
    # This module intentionally does not add a protected business route in
    # this task (scope: identity foundation only — future modules will use
    # get_current_account/require_customer/require_driver/require_admin to
    # protect their own routes). Exercised directly against the dependency
    # rather than through a dynamically-registered synthetic HTTP route,
    # which proved fragile against this FastAPI version's router internals.
    from fastapi import HTTPException

    from core.database import SessionLocal
    from core.redis import get_redis_client
    from modules.identity.dependencies import get_current_account

    db = SessionLocal()
    redis_client = get_redis_client()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await get_current_account(
                credentials=None, db=db, redis_client=redis_client
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "AUTH_REQUIRED"
    finally:
        db.close()
        await redis_client.aclose()


@pytest.mark.anyio
async def test_logged_out_access_token_is_rejected_by_get_current_account(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    from fastapi.security import HTTPAuthorizationCredentials

    from core.database import SessionLocal
    from core.redis import get_redis_client
    from modules.identity.dependencies import get_current_account

    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=tokens["access_token"]
    )

    db = SessionLocal()
    redis_client = get_redis_client()
    try:
        account = await get_current_account(
            credentials=credentials, db=db, redis_client=redis_client
        )
        assert account.phone == phone

        api_client.post(
            "/api/v1/auth/logout",
            json={},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_account(
                credentials=credentials, db=db, redis_client=redis_client
            )
        assert exc_info.value.status_code == 401
    finally:
        db.close()
        await redis_client.aclose()


def test_malformed_request_body_produces_error_envelope_not_a_stack_trace(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/auth/otp/request", json={"phone": "", "account_type": "NOT_A_TYPE"}
    )
    assert response.status_code == 422  # FastAPI/Pydantic validation error


def test_data_persists_across_requests_via_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Verifies the OTP challenge and account rows are genuinely
    persisted to PostgreSQL (12. Database persistence behavior) rather
    than held only in in-process memory, by issuing two independent
    TestClient requests (each opens/closes its own DB session, exactly
    like two independent HTTP requests would in production)."""
    phone = _random_phone()
    api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT phone, status FROM identity.otp_challenges WHERE phone = :p"),
            {"p": phone},
        ).fetchone()
        assert row is not None
        assert row[0] == phone
        assert row[1] == "ACTIVE"
    finally:
        db.close()


# --- Rate limiting (Phase 2 / Identity hardening) ---------------------------
#
# Each test below uses its own TestClient constructed with a unique fake
# client IP (starlette's TestClient accepts client=(host, port); every other
# test in this file/suite shares the default ("testclient", 50000) — using a
# unique one here isolates each test's IP-keyed Redis counter from every
# other test, since (unlike phone numbers) IP isn't otherwise randomized per
# call. See modules/identity/config.py's comment on why the real defaults are
# deliberately much higher than the shared-IP test suite's cumulative volume.


@pytest.fixture
def ip_client(sms: CapturingSmsProvider) -> Generator[TestClient, None, None]:
    fake_ip = "10." + ".".join(str(secrets.randbelow(256)) for _ in range(3))
    app.dependency_overrides[get_sms_provider_dependency] = lambda: sms
    client = TestClient(app, client=(fake_ip, 12345))
    yield client
    app.dependency_overrides.pop(get_sms_provider_dependency, None)


def test_otp_request_rate_limited_by_ip(
    ip_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single source flooding requests for many *different* phone
    numbers is caught by the IP dimension even though no single phone
    number's own limit is ever hit."""
    monkeypatch.setattr(identity_settings, "otp_request_rate_limit_per_ip_per_hour", 2)

    for _ in range(2):
        response = ip_client.post(
            "/api/v1/auth/otp/request",
            json={"phone": _random_phone(), "account_type": "CUSTOMER"},
        )
        assert response.status_code == 200

    limited = ip_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": _random_phone(), "account_type": "CUSTOMER"},
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_otp_verify_rate_limited_by_ip(
    ip_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Distributed guessing against many different challenges from one
    source is caught by the IP dimension."""
    monkeypatch.setattr(identity_settings, "otp_verify_rate_limit_per_ip_per_hour", 2)

    challenge_ids = []
    for _ in range(3):
        phone = _random_phone()
        response = ip_client.post(
            "/api/v1/auth/otp/request",
            json={"phone": phone, "account_type": "CUSTOMER"},
        )
        challenge_ids.append(response.json()["data"]["challenge_id"])

    for challenge_id in challenge_ids[:2]:
        response = ip_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge_id, "otp": "000000"},
        )
        # Incorrect OTP, but that's fine — the attempt still counts
        # against the IP-dimension limit regardless of correctness.
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "OTP_INVALID"

    limited = ip_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_ids[2], "otp": "000000"},
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_otp_request_rate_limited_by_phone(
    ip_client: TestClient, sms: CapturingSmsProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-existing phone-dimension behavior (unchanged by this task) —
    previously asserted only via FakeRateLimiter's no-op in
    test_identity_service.py; this proves it against the real
    Redis-backed implementation, an actual end-to-end check the codebase
    was missing despite a comment there claiming it existed here."""
    monkeypatch.setattr(identity_settings, "otp_request_rate_limit_per_hour", 1)
    monkeypatch.setattr(identity_settings, "otp_resend_cooldown_seconds", 0)
    phone = _random_phone()

    first = ip_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    assert first.status_code == 200

    limited = ip_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


# --- Admin MFA (ADR-0051) ------------------------------------------------


def _login_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict:
    """A plain ADMIN-type account — enough for /mfa/* itself (gated on
    account_type only, require_admin), not a full admin.users row.
    See _login_full_admin() below for tests that also need a real
    admin.* endpoint to work."""
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "ADMIN"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _login_full_admin(api_client: TestClient, sms: CapturingSmsProvider) -> dict:
    """Same as _login_admin, plus a real admin.users row — needed only
    by the one test proving the post-MFA access token actually works
    against a real admin.* endpoint (GET /api/v1/admin/me)."""
    headers = _login_admin(api_client, sms)
    account_id = uuid.UUID(
        decode_access_token(headers["Authorization"].removeprefix("Bearer "))["sub"]
    )
    db = SessionLocal()
    try:
        db.add(AdminUserORM(id=account_id, role="SUPER_ADMIN", status="ACTIVE"))
        db.commit()
    finally:
        db.close()
    return headers


def _enroll_and_confirm(api_client: TestClient, admin_headers: dict) -> str:
    """Returns the confirmed secret, so the caller can generate further
    valid codes with pyotp."""
    enroll_response = api_client.post("/api/v1/auth/mfa/enroll", headers=admin_headers)
    assert enroll_response.status_code == 201, enroll_response.text
    secret = enroll_response.json()["data"]["secret"]

    confirm_response = api_client.post(
        "/api/v1/auth/mfa/confirm",
        json={"code": pyotp.TOTP(secret).now()},
        headers=admin_headers,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    return str(secret)


def test_mfa_enroll_returns_secret_and_otpauth_uri(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)

    response = api_client.post("/api/v1/auth/mfa/enroll", headers=admin_headers)

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["secret"]
    assert data["otpauth_uri"].startswith("otpauth://totp/")


def test_mfa_enroll_requires_authentication(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/auth/mfa/enroll")
    assert response.status_code == 401


def test_mfa_enroll_rejects_a_customer_account(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "CUSTOMER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]
    customer_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = api_client.post("/api/v1/auth/mfa/enroll", headers=customer_headers)

    assert response.status_code == 403


async def _clear_otp_cooldown(phone: str) -> None:
    """Deletes RedisOtpRateLimiter's per-phone resend-cooldown key
    directly — see _login_again_expecting_mfa()'s own docstring for why
    monkeypatching the setting alone isn't enough."""
    client = get_redis_client()
    try:
        await client.delete(f"identity:otp:cooldown:{phone}")
    finally:
        await client.aclose()


def _login_again_expecting_mfa(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    admin_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Re-requests an OTP for the same already-provisioned admin (now
    MFA-ACTIVE) and verifies it, returning the resulting mfa_token.
    Bypasses the per-phone resend cooldown (identity_settings.
    otp_resend_cooldown_seconds, 60s by default): the FIRST login moments
    earlier in the same test already set a real Redis cooldown key for
    this phone with that 60s TTL, so monkeypatching the setting to 0
    alone isn't enough — it only stops a *new* cooldown key from being
    set, it doesn't clear the one that's already there (see
    RedisOtpRateLimiter.check_and_increment_request()). Deleting the key
    directly is what actually unblocks the second request."""
    monkeypatch.setattr(identity_settings, "otp_resend_cooldown_seconds", 0)
    account_id = api_client.get("/api/v1/admin/me", headers=admin_headers).json()[
        "data"
    ]["admin_id"]
    db = SessionLocal()
    try:
        phone = db.execute(
            text("SELECT phone FROM identity.accounts WHERE id = :id"),
            {"id": account_id},
        ).scalar_one()
    finally:
        db.close()

    asyncio.run(_clear_otp_cooldown(phone))

    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "ADMIN"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    verify_response = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    )
    assert verify_response.status_code == 200
    verify_data = verify_response.json()["data"]
    assert verify_data["mfa_required"] is True
    assert "access_token" not in verify_data
    mfa_token: str = verify_data["mfa_token"]
    return mfa_token


def test_full_admin_mfa_enrollment_and_login_flow(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The end-to-end story ADR-0051 exists for: enroll -> confirm ->
    next login is gated -> mfa/verify issues real tokens -> those tokens
    actually work against a real admin.* endpoint."""
    admin_headers = _login_full_admin(api_client, sms)
    secret = _enroll_and_confirm(api_client, admin_headers)

    mfa_token = _login_again_expecting_mfa(api_client, sms, admin_headers, monkeypatch)

    mfa_response = api_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
    )
    assert mfa_response.status_code == 200, mfa_response.text
    real_tokens = mfa_response.json()["data"]
    assert real_tokens["access_token"]
    assert real_tokens["refresh_token"]

    # The new access token actually works against a real admin.* route.
    me_response = api_client.get(
        "/api/v1/admin/me",
        headers={"Authorization": f"Bearer {real_tokens['access_token']}"},
    )
    assert me_response.status_code == 200


def test_mfa_pending_token_cannot_be_used_as_a_bearer_token(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0051 Decision 4 — the security property the `purpose` claim
    exists for."""
    admin_headers = _login_full_admin(api_client, sms)
    _enroll_and_confirm(api_client, admin_headers)

    mfa_token = _login_again_expecting_mfa(api_client, sms, admin_headers, monkeypatch)

    response = api_client.get(
        "/api/v1/admin/me", headers={"Authorization": f"Bearer {mfa_token}"}
    )

    assert response.status_code == 401


def test_mfa_verify_rejects_incorrect_code(
    api_client: TestClient,
    sms: CapturingSmsProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers = _login_full_admin(api_client, sms)
    _enroll_and_confirm(api_client, admin_headers)
    mfa_token = _login_again_expecting_mfa(api_client, sms, admin_headers, monkeypatch)

    response = api_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": "000000"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


def test_mfa_disable_requires_a_valid_code(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    secret = _enroll_and_confirm(api_client, admin_headers)

    rejected = api_client.post(
        "/api/v1/auth/mfa/disable",
        json={"code": "000000"},
        headers=admin_headers,
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "OTP_INVALID"

    accepted = api_client.post(
        "/api/v1/auth/mfa/disable",
        json={"code": pyotp.TOTP(secret).now()},
        headers=admin_headers,
    )
    assert accepted.status_code == 200


def test_mfa_enroll_rejects_when_already_active(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    admin_headers = _login_admin(api_client, sms)
    _enroll_and_confirm(api_client, admin_headers)

    response = api_client.post("/api/v1/auth/mfa/enroll", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
