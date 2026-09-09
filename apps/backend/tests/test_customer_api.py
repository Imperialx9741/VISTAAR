"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising GET/PATCH /api/v1/customers/me end-to-end, authenticated via a
real OTP login through modules.identity (reusing that flow rather than
minting a token by hand, so this also proves the identity <-> customer
seam works together).

Skips (not fails) when Postgres is genuinely unreachable, matching the
convention already established in tests/test_identity_api.py.
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


def _login_as_new_customer(api_client: TestClient, sms: CapturingSmsProvider) -> str:
    """Drives a real OTP login through modules.identity and returns a
    genuine access token for a brand-new CUSTOMER account."""
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
    access_token: str = tokens["access_token"]
    return access_token


def test_get_profile_auto_provisions_on_first_access(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)

    response = api_client.get(
        "/api/v1/customers/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["full_name"] is None
    assert data["language"] == "en"
    assert data["notification_enabled"] is True
    assert data["status"] == "ACTIVE"
    assert data["phone"].startswith("+91")


def test_patch_updates_only_supplied_fields_and_persists(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    headers = {"Authorization": f"Bearer {access_token}"}

    first_patch = api_client.patch(
        "/api/v1/customers/me",
        json={"full_name": "Jane Doe", "language": "hi"},
        headers=headers,
    )
    assert first_patch.status_code == 200
    assert first_patch.json()["data"]["full_name"] == "Jane Doe"
    assert first_patch.json()["data"]["language"] == "hi"

    second_patch = api_client.patch(
        "/api/v1/customers/me",
        json={"notification_enabled": False},
        headers=headers,
    )
    assert second_patch.status_code == 200
    data = second_patch.json()["data"]
    assert data["full_name"] == "Jane Doe"  # untouched
    assert data["language"] == "hi"  # untouched
    assert data["notification_enabled"] is False  # changed

    get_response = api_client.get("/api/v1/customers/me", headers=headers)
    assert get_response.json()["data"] == data  # persisted across requests


def test_patch_rejects_invalid_language(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)

    response = api_client.patch(
        "/api/v1/customers/me",
        json={"language": "fr"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_unauthenticated_request_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/customers/me")
    assert response.status_code == 401


def test_driver_account_cannot_access_customer_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    phone = _random_phone()
    request_response = api_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone, "account_type": "DRIVER"},
    )
    challenge_id = request_response.json()["data"]["challenge_id"]
    otp = sms.sent[phone]
    tokens = api_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "otp": otp},
    ).json()["data"]

    response = api_client.get(
        "/api/v1/customers/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 403


def test_data_persists_across_requests_via_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login_as_new_customer(api_client, sms)
    api_client.patch(
        "/api/v1/customers/me",
        json={"full_name": "Persisted Name"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT full_name FROM customer.customers WHERE full_name = :n"),
            {"n": "Persisted Name"},
        ).fetchone()
        assert row is not None
    finally:
        db.close()
