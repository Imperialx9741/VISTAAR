"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising POST/DELETE /api/v1/notifications/me/devices end-to-end
(ADR-0052) — the first HTTP router this module has ever had.

Setup helpers (login) are copied from tests/test_safety_api.py — same
"no shared test-helper module" convention already used across this
codebase's integration tests.

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.database import SessionLocal
from main import app
from modules.identity.dependencies import get_sms_provider_dependency


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


def _login(
    api_client: TestClient, sms: CapturingSmsProvider, account_type: str
) -> dict:
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
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _random_token() -> str:
    return "fcm-" + secrets.token_hex(16)


def test_register_device_persists_and_is_upsertable(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _login(api_client, sms, "CUSTOMER")
    token = _random_token()

    response = api_client.post(
        "/api/v1/notifications/me/devices",
        json={"platform": "ANDROID", "token": token},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["platform"] == "ANDROID"
    assert data["token"] == token

    # Re-registering the same token (app reopened) upserts, not duplicates.
    second = api_client.post(
        "/api/v1/notifications/me/devices",
        json={"platform": "ANDROID", "token": token},
        headers=headers,
    )
    assert second.status_code == 201
    assert second.json()["data"]["device_id"] == data["device_id"]


def test_register_device_works_for_any_account_type(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """ADR-0052 Decision 1 — a generic capability, not gated to one
    account type."""
    for account_type in ("CUSTOMER", "DRIVER", "ADMIN"):
        headers = _login(api_client, sms, account_type)
        response = api_client.post(
            "/api/v1/notifications/me/devices",
            json={"platform": "IOS", "token": _random_token()},
            headers=headers,
        )
        assert response.status_code == 201, (account_type, response.text)


def test_register_device_requires_authentication(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/notifications/me/devices",
        json={"platform": "ANDROID", "token": _random_token()},
    )
    assert response.status_code == 401


def test_register_device_rejects_an_unknown_platform(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _login(api_client, sms, "CUSTOMER")

    response = api_client.post(
        "/api/v1/notifications/me/devices",
        json={"platform": "SMART_FRIDGE", "token": _random_token()},
        headers=headers,
    )

    assert response.status_code == 422


def test_unregister_device_removes_it(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    headers = _login(api_client, sms, "DRIVER")
    token = _random_token()
    api_client.post(
        "/api/v1/notifications/me/devices",
        json={"platform": "ANDROID", "token": token},
        headers=headers,
    )

    response = api_client.delete(
        f"/api/v1/notifications/me/devices/{token}", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UNREGISTERED"


def test_unregister_device_is_idempotent_for_an_unknown_token(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """No-op (200, not 404) for a token this account never registered —
    matching DeviceTokenRepository.delete()'s own documented
    convention."""
    headers = _login(api_client, sms, "CUSTOMER")

    response = api_client.delete(
        f"/api/v1/notifications/me/devices/{_random_token()}", headers=headers
    )

    assert response.status_code == 200


def test_unregister_device_does_not_remove_another_accounts_device(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    owner_headers = _login(api_client, sms, "CUSTOMER")
    other_headers = _login(api_client, sms, "CUSTOMER")
    token = _random_token()
    api_client.post(
        "/api/v1/notifications/me/devices",
        json={"platform": "ANDROID", "token": token},
        headers=owner_headers,
    )

    other_delete = api_client.delete(
        f"/api/v1/notifications/me/devices/{token}", headers=other_headers
    )
    assert other_delete.status_code == 200  # idempotent no-op, not an error

    # The original owner's registration survives the other account's
    # no-op delete attempt.
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id FROM notification.device_tokens WHERE token = :t"),
            {"t": token},
        ).fetchone()
    finally:
        db.close()
    assert row is not None
