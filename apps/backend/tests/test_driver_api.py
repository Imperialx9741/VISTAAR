"""Integration tests: real HTTP layer (TestClient) + real Postgres,
exercising GET/PATCH /api/v1/drivers/me end-to-end, authenticated via a
real OTP login through modules.identity — same pattern as
tests/test_customer_api.py.

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


def test_get_profile_before_creation_returns_not_found(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.get(
        "/api/v1/drivers/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_patch_without_full_name_cannot_create_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.patch(
        "/api/v1/drivers/me",
        json={"profile_photo_uri": "ref-1"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_patch_with_full_name_creates_and_returns_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.patch(
        "/api/v1/drivers/me",
        json={"full_name": "Ravi Kumar"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["full_name"] == "Ravi Kumar"
    assert data["verification_status"] == "PENDING"
    assert data["operational_status"] == "OFFLINE"
    assert data["strikes"] == 0
    assert data["phone"].startswith("+91")


def test_get_after_creation_returns_the_same_profile(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )

    response = api_client.get("/api/v1/drivers/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "Ravi Kumar"


def test_patch_updates_only_supplied_fields_and_persists(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    api_client.patch(
        "/api/v1/drivers/me",
        json={"full_name": "Ravi Kumar", "profile_photo_uri": "ref-1"},
        headers=headers,
    )

    response = api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi K."}, headers=headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["full_name"] == "Ravi K."
    assert data["profile_photo_uri"] == "ref-1"  # untouched

    get_response = api_client.get("/api/v1/drivers/me", headers=headers)
    assert get_response.json()["data"] == data  # persisted across requests


def test_server_controlled_fields_cannot_be_set_via_patch(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """5. Driver cannot modify fields that are server-controlled.

    verification_status/operational_status/strikes are not accepted
    fields on the PATCH schema at all — sending them is either ignored
    (Pydantic drops unknown fields by default) or rejected; either way
    they must never change."""
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    api_client.patch(
        "/api/v1/drivers/me", json={"full_name": "Ravi Kumar"}, headers=headers
    )

    response = api_client.patch(
        "/api/v1/drivers/me",
        json={
            "verification_status": "APPROVED",
            "operational_status": "ONLINE",
            "strikes": 99,
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["verification_status"] == "PENDING"
    assert data["operational_status"] == "OFFLINE"
    assert data["strikes"] == 0


def test_invalid_full_name_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.patch(
        "/api/v1/drivers/me",
        json={"full_name": "   "},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_unauthenticated_request_is_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/drivers/me")
    assert response.status_code == 401


def test_customer_account_cannot_access_driver_endpoint(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")

    response = api_client.get(
        "/api/v1/drivers/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 403


def test_data_persists_across_requests_via_postgres(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")
    api_client.patch(
        "/api/v1/drivers/me",
        json={"full_name": "Persisted Driver"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT full_name FROM driver.drivers WHERE full_name = :n"),
            {"n": "Persisted Driver"},
        ).fetchone()
        assert row is not None
    finally:
        db.close()


# --- POST /api/v1/drivers/me/uploads (ADR-0031) -----------------------------


def test_request_upload_url_returns_a_presigned_url_and_uri(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.post(
        "/api/v1/drivers/me/uploads",
        json={"content_type": "image/jpeg"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["upload_url"].startswith("https://")
    assert data["uri"].startswith("s3://")
    assert "/driver-uploads/" in data["uri"]
    assert data["uri"].endswith(".jpg")
    assert data["expires_at"] is not None
    # Presigned POST, not PUT (owner decision, 2026-09-03) — the client
    # must submit these exact form fields alongside the file, and S3
    # enforces the size/content-type/key scope encoded in them.
    assert data["upload_fields"]["key"]
    assert data["upload_fields"]["Content-Type"] == "image/jpeg"
    assert "policy" in data["upload_fields"]
    assert "x-amz-signature" in data["upload_fields"]


def test_request_upload_url_does_not_require_a_profile_to_exist_yet(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """Unlike GET /api/v1/drivers/me, this endpoint needs no prior
    PATCH /me call — a driver may fetch an upload URL for their profile
    photo before the profile itself exists (the resulting `uri` is what
    they then submit via that same PATCH call)."""
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.post(
        "/api/v1/drivers/me/uploads",
        json={"content_type": "application/pdf"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200


def test_request_upload_url_rejects_unsupported_content_type(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "DRIVER")

    response = api_client.post(
        "/api/v1/drivers/me/uploads",
        json={"content_type": "application/x-msdownload"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_request_upload_url_unauthenticated_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/drivers/me/uploads", json={"content_type": "image/jpeg"}
    )
    assert response.status_code == 401


def test_request_upload_url_customer_account_is_rejected(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    access_token = _login(api_client, sms, "CUSTOMER")

    response = api_client.post(
        "/api/v1/drivers/me/uploads",
        json={"content_type": "image/jpeg"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403


def test_returned_uri_from_upload_url_can_be_used_as_profile_photo(
    api_client: TestClient, sms: CapturingSmsProvider
) -> None:
    """End-to-end: the `uri` this endpoint returns is accepted as-is by
    the already-documented, unchanged PATCH /me endpoint."""
    access_token = _login(api_client, sms, "DRIVER")
    headers = {"Authorization": f"Bearer {access_token}"}
    upload = api_client.post(
        "/api/v1/drivers/me/uploads",
        json={"content_type": "image/jpeg"},
        headers=headers,
    ).json()["data"]

    response = api_client.patch(
        "/api/v1/drivers/me",
        json={"full_name": "Upload Test Driver", "profile_photo_uri": upload["uri"]},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["profile_photo_uri"] == upload["uri"]
